#!/usr/bin/env python3
"""Test Google Places matching on top-300 re-fetch targets.

Fetches from the Google Places API, saves raw candidates to
data/raw/google_places/, runs select_best_match(), detects review anomalies,
and prints grouped results tables. Does NOT write to the database.

Re-fetch targets = top 300 canonical restaurants (≥5 mentions) minus
the verified trustworthy set (data/high_confidence_operational.csv).

If a raw JSON file already exists for a restaurant (from a prior run),
it is reused instead of making a new API call.

Usage:
    python scripts/test_google_match.py --dry-run   # Cost estimate only
    python scripts/test_google_match.py              # Full run
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import httpx
from rich.console import Console
from rich.table import Table

from src.google_places import (
    COST_PER_REQUEST,
    build_search_query,
    compute_match_confidence,
    search_place,
    select_best_match,
    _has_food_type,
    _save_raw_response,
    _sanitize_filename,
)

load_dotenv()
console = Console()

RAW_DIR = Path("data/raw/google_places")
DB_PATH = Path("data/aeo.db")
TRUSTWORTHY_CSV = Path("data/high_confidence_operational.csv")

# Review anomaly: rejected candidate has 5x+ winner's reviews AND scored ≥55%
REVIEW_ANOMALY_RATIO = 5
REVIEW_ANOMALY_MIN_SCORE = 55.0


# ---------------------------------------------------------------------------
# Target selection
# ---------------------------------------------------------------------------


def get_refetch_targets() -> list[tuple[int, str, int]]:
    """Return (canonical_id, canonical_name, total_mentions) for re-fetch targets.

    Re-fetch = top 300 by mentions minus the trustworthy CSV set.
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    top300 = conn.execute("""
        SELECT id, canonical_name, total_mentions
        FROM canonical_restaurants
        WHERE total_mentions >= 5
        ORDER BY total_mentions DESC
        LIMIT 300
    """).fetchall()
    conn.close()

    # Load trustworthy names
    trustworthy_names: set[str] = set()
    with open(TRUSTWORTHY_CSV) as f:
        for row in csv.DictReader(f):
            trustworthy_names.add(row["canonical_name"].strip())

    return [
        (r["id"], r["canonical_name"], r["total_mentions"])
        for r in top300
        if r["canonical_name"] not in trustworthy_names
    ]


# ---------------------------------------------------------------------------
# Review anomaly detection
# ---------------------------------------------------------------------------


def detect_review_anomaly(
    canonical_name: str,
    winner: dict | None,
    all_results: list[dict],
) -> dict | None:
    """Check if any rejected candidate has overwhelmingly more reviews.

    Returns info about the anomalous candidate, or None.
    """
    if winner is None or not all_results:
        return None

    winner_pid = winner.get("place_id")
    winner_reviews = winner.get("user_ratings_total", 0) or 0

    for r in all_results:
        if r.get("place_id") == winner_pid:
            continue  # skip the winner itself

        r_reviews = r.get("user_ratings_total", 0) or 0
        if r_reviews < REVIEW_ANOMALY_RATIO * max(winner_reviews, 1):
            continue

        # Check score
        lat = r.get("geometry", {}).get("location", {}).get("lat", 0)
        lng = r.get("geometry", {}).get("location", {}).get("lng", 0)
        _, score = compute_match_confidence(canonical_name, r.get("name", ""), lat, lng)

        if score >= REVIEW_ANOMALY_MIN_SCORE:
            return {
                "rejected_name": r.get("name", "?"),
                "rejected_reviews": r_reviews,
                "rejected_score": score,
                "rejected_status": r.get("business_status", "UNKNOWN"),
                "winner_reviews": winner_reviews,
            }

    return None


# ---------------------------------------------------------------------------
# Process one restaurant (API call or cached raw JSON)
# ---------------------------------------------------------------------------


def _raw_path(canonical_id: int, canonical_name: str) -> Path:
    return RAW_DIR / f"{canonical_id}_{_sanitize_filename(canonical_name)}.json"


async def process_one(
    canonical_id: int,
    canonical_name: str,
    api_key: str,
    client: httpx.AsyncClient,
) -> dict:
    """Fetch (or load cached) Google results and return match + anomaly info."""
    raw_file = _raw_path(canonical_id, canonical_name)

    # Reuse existing raw file if present
    if raw_file.exists():
        cached = json.loads(raw_file.read_text())
        results = cached.get("results", [])
        from_cache = True
    else:
        query = build_search_query(canonical_name)
        try:
            data = await search_place(query, api_key, client)
            results = data.get("results", [])
            _save_raw_response(RAW_DIR, canonical_id, canonical_name, query, results)
        except Exception as e:
            return {
                "canonical_id": canonical_id,
                "canonical_name": canonical_name,
                "error": str(e),
                "num_candidates": 0,
                "from_cache": False,
            }
        from_cache = False

    # Run matching
    match = select_best_match(canonical_name, results)

    if match is None:
        # Check anomaly even for unmatched — a high-review candidate might exist
        anomaly = detect_review_anomaly(canonical_name, None, results)
        return {
            "canonical_id": canonical_id,
            "canonical_name": canonical_name,
            "google_name": "—",
            "confidence": "UNMATCHED",
            "status": "—",
            "score": 0.0,
            "reviews": 0,
            "num_candidates": len(results),
            "review_anomaly": None,
            "from_cache": from_cache,
        }

    winner, confidence, score = match
    anomaly = detect_review_anomaly(canonical_name, winner, results)

    return {
        "canonical_id": canonical_id,
        "canonical_name": canonical_name,
        "google_name": winner.get("name", "?"),
        "confidence": confidence.value.upper(),
        "status": winner.get("business_status", "UNKNOWN"),
        "score": score,
        "reviews": winner.get("user_ratings_total", 0) or 0,
        "num_candidates": len(results),
        "review_anomaly": anomaly,
        "from_cache": from_cache,
    }


# ---------------------------------------------------------------------------
# Grouped output
# ---------------------------------------------------------------------------


def print_group(title: str, rows: list[dict], show_anomaly_col: bool = False) -> None:
    """Print a rich table for one result group."""
    if not rows:
        return

    table = Table(title=f"{title} ({len(rows)})")
    table.add_column("Canonical Name", max_width=38)
    table.add_column("Google Match", max_width=40)
    table.add_column("Conf", justify="center")
    table.add_column("Status", justify="center")
    table.add_column("Score", justify="right")
    table.add_column("Reviews", justify="right")
    if show_anomaly_col:
        table.add_column("Anomaly", max_width=45)

    for r in rows:
        if "error" in r:
            cols = [
                r["canonical_name"],
                f"[red]ERROR: {r['error'][:35]}[/red]",
                "—", "—", "—", "—",
            ]
            if show_anomaly_col:
                cols.append("—")
            table.add_row(*cols)
            continue

        conf = r["confidence"]
        conf_style = {"HIGH": "green", "MEDIUM": "yellow", "UNMATCHED": "red"}.get(conf, "dim")
        status = r["status"]
        status_style = (
            "green" if status == "OPERATIONAL"
            else "red" if "CLOSED" in status
            else "dim"
        )

        cols = [
            r["canonical_name"],
            r["google_name"],
            f"[{conf_style}]{conf}[/{conf_style}]",
            f"[{status_style}]{status}[/{status_style}]",
            f"{r['score']:.0f}%",
            f"{r['reviews']:,}",
        ]

        if show_anomaly_col:
            a = r.get("review_anomaly")
            if a:
                cols.append(
                    f"[bold red]{a['rejected_name']}[/bold red] "
                    f"({a['rejected_reviews']:,} reviews, {a['rejected_score']:.0f}%)"
                )
            else:
                cols.append("—")

        table.add_row(*cols)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Google Places matching on top-300 re-fetch targets"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show targets and cost estimate only",
    )
    args = parser.parse_args()

    targets = get_refetch_targets()
    console.print(f"\n[bold]Top-300 Re-fetch Targets: {len(targets)} restaurants[/bold]")

    # Check which already have raw files cached
    cached = [t for t in targets if _raw_path(t[0], t[1]).exists()]
    to_fetch = [t for t in targets if not _raw_path(t[0], t[1]).exists()]
    api_cost = len(to_fetch) * COST_PER_REQUEST

    console.print(f"  Cached (reuse raw JSON): {len(cached)}")
    console.print(f"  Need API calls: {len(to_fetch)}")
    console.print(f"  Estimated API cost: [bold]${api_cost:.2f}[/bold]")

    if args.dry_run:
        console.print("\n[yellow]Dry run — no API calls made.[/yellow]\n")
        return

    # Check API key
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        console.print("[red]GOOGLE_PLACES_API_KEY not set.[/red] Add it to .env")
        sys.exit(1)

    console.print(f"\nProcessing {len(targets)} restaurants...\n")

    results: list[dict] = []
    async with httpx.AsyncClient() as client:
        for i, (cid, name, mentions) in enumerate(targets, 1):
            cached_flag = _raw_path(cid, name).exists()
            tag = "[dim]cached[/dim]" if cached_flag else "[cyan]API[/cyan]"
            console.print(f"  [{i:>3}/{len(targets)}] {tag} {name}")
            r = await process_one(cid, name, api_key, client)
            r["total_mentions"] = mentions
            results.append(r)

    # -----------------------------------------------------------------------
    # Group results
    # -----------------------------------------------------------------------
    high_op = [r for r in results if r["confidence"] == "HIGH" and r.get("status") == "OPERATIONAL" and "error" not in r]
    high_closed = [r for r in results if r["confidence"] == "HIGH" and "CLOSED" in r.get("status", "") and "error" not in r]
    medium = [r for r in results if r["confidence"] == "MEDIUM" and "error" not in r]
    unmatched = [r for r in results if r["confidence"] == "UNMATCHED" and "error" not in r]
    errors = [r for r in results if "error" in r]
    anomalies = [r for r in results if r.get("review_anomaly") and "error" not in r]

    # Sort each group by total_mentions descending
    for group in [high_op, high_closed, medium, unmatched, errors, anomalies]:
        group.sort(key=lambda r: r.get("total_mentions", 0), reverse=True)

    console.print("\n" + "=" * 70)
    console.print("[bold]GROUPED RESULTS[/bold]")
    console.print("=" * 70 + "\n")

    print_group("HIGH / OPERATIONAL", high_op)
    print_group("HIGH / CLOSED", high_closed)
    print_group("MEDIUM", medium)
    print_group("UNMATCHED", unmatched)
    if errors:
        print_group("ERRORS", errors)

    # Anomalies get their own table (may overlap with above groups)
    if anomalies:
        console.print("[bold red]REVIEW ANOMALIES[/bold red] — winner may be wrong branch/franchise:\n")
        print_group("REVIEW ANOMALIES", anomalies, show_anomaly_col=True)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    console.print("=" * 70)
    console.print("[bold]SUMMARY[/bold]")
    console.print("=" * 70)
    console.print(f"  HIGH/OPERATIONAL:  {len(high_op)}")
    console.print(f"  HIGH/CLOSED:       {len(high_closed)}")
    console.print(f"  MEDIUM:            {len(medium)}")
    console.print(f"  UNMATCHED:         {len(unmatched)}")
    console.print(f"  ERRORS:            {len(errors)}")
    console.print(f"  Review anomalies:  [bold red]{len(anomalies)}[/bold red]")
    api_calls = sum(1 for r in results if not r.get("from_cache", False) and "error" not in r)
    console.print(f"\n  API calls made:    {api_calls}")
    console.print(f"  Cached reused:     {sum(1 for r in results if r.get('from_cache', False))}")
    console.print(f"  Actual API cost:   ${api_calls * COST_PER_REQUEST:.2f}")
    console.print(f"  Raw files:         {RAW_DIR}/\n")


if __name__ == "__main__":
    asyncio.run(main())
