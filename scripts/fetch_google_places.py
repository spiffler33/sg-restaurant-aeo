#!/usr/bin/env python3
"""Phase 3a: Fetch Google Places ground truth data.

Matches canonical restaurants against the Google Places API to create
an independent ground truth dataset. Answers: are LLMs recommending
real, open, well-reviewed restaurants?

Uses the Legacy Text Search API (single call per restaurant — returns
rating, price, location, review count, business status).

Batching strategy:
  Batch 1: Top 300 by total_mentions (≥5 each)      ~$9.60
  Batch 2: Consensus (4/4 models) NOT in batch 1     ~$0.22
  Batch 3: Remaining long tail                       ~$108.93
  Baseline: Popular Google searches                  ~$0.48

Usage:
    python scripts/fetch_google_places.py --dry-run            # Cost estimate only
    python scripts/fetch_google_places.py --batch 1            # Top 300
    python scripts/fetch_google_places.py --batch 2            # Consensus stragglers
    python scripts/fetch_google_places.py --batch 1 --batch 2  # Both
    python scripts/fetch_google_places.py --baseline           # Popular baseline
    python scripts/fetch_google_places.py --max-concurrent 5   # Lower concurrency
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.db import (
    get_matched_canonical_ids,
    get_baseline_place_ids,
    init_db,
    insert_google_place,
)
from src.google_places import (
    COST_PER_REQUEST,
    fetch_popular_baseline,
    fetch_restaurant_places,
)

load_dotenv()
console = Console()

# ---------------------------------------------------------------------------
# Batch selection
# ---------------------------------------------------------------------------


def get_batch_restaurants(
    conn, batch_nums: list[int]
) -> list[tuple[int, str]]:
    """Select restaurants for the requested batches.

    Returns list of (canonical_id, canonical_name) tuples, deduplicated
    across batches.
    """
    selected: dict[int, str] = {}  # id -> name, deduped

    if 1 in batch_nums:
        # Batch 1: Top by total_mentions (≥5)
        rows = conn.execute(
            """
            SELECT id, canonical_name, total_mentions
            FROM canonical_restaurants
            WHERE total_mentions >= 5
            ORDER BY total_mentions DESC
            LIMIT 300
            """
        ).fetchall()
        for r in rows:
            selected[r["id"]] = r["canonical_name"]
        console.print(f"  Batch 1: {len(rows)} restaurants (≥5 mentions, top 300)")

    if 2 in batch_nums:
        # Batch 2: Consensus (4/4 models) not already in batch 1
        existing_ids = set(selected.keys())
        rows = conn.execute(
            """
            SELECT id, canonical_name, total_mentions, model_count
            FROM canonical_restaurants
            WHERE model_count = 4
            ORDER BY total_mentions DESC
            """
        ).fetchall()
        added = 0
        for r in rows:
            if r["id"] not in existing_ids:
                selected[r["id"]] = r["canonical_name"]
                added += 1
        console.print(f"  Batch 2: {added} consensus restaurants not in batch 1")

    if 3 in batch_nums:
        # Batch 3: Everything not in batches 1+2
        existing_ids = set(selected.keys())
        rows = conn.execute(
            """
            SELECT id, canonical_name, total_mentions
            FROM canonical_restaurants
            ORDER BY total_mentions DESC
            """
        ).fetchall()
        added = 0
        for r in rows:
            if r["id"] not in existing_ids:
                selected[r["id"]] = r["canonical_name"]
                added += 1
        console.print(f"  Batch 3: {added} remaining long-tail restaurants")

    return [(cid, name) for cid, name in selected.items()]


# ---------------------------------------------------------------------------
# Summary display
# ---------------------------------------------------------------------------


def print_summary(
    places, stats: dict, already_fetched: int, cost: float
) -> None:
    """Print a rich summary table of match results."""
    console.print()

    # Match distribution table
    table = Table(title="Match Distribution")
    table.add_column("Confidence", style="bold")
    table.add_column("Count", justify="right")
    table.add_column("Pct", justify="right")

    total_attempted = sum(
        stats[k] for k in ("high", "medium", "unmatched")
    )
    for level in ("high", "medium", "unmatched"):
        count = stats[level]
        pct = f"{count / total_attempted * 100:.1f}%" if total_attempted else "—"
        style = {
            "high": "green",
            "medium": "yellow",
            "unmatched": "dim",
        }[level]
        table.add_row(f"[{style}]{level.upper()}[/{style}]", str(count), pct)

    table.add_row("ERRORS", str(stats.get("errors", 0)), "—", style="red")
    table.add_row("Already fetched", str(already_fetched), "—", style="dim")
    console.print(table)

    # Cost
    console.print(
        f"\n[bold]API cost:[/bold] ${cost:.2f} "
        f"({total_attempted} requests × ${COST_PER_REQUEST:.3f})"
    )

    # Top matches
    if places:
        console.print("\n[bold]Top 10 matches by review count:[/bold]")
        top = sorted(
            places, key=lambda p: p.user_ratings_total or 0, reverse=True
        )[:10]
        for p in top:
            conf_color = {
                "high": "green",
                "medium": "yellow",
            }.get(p.match_confidence.value, "dim")
            console.print(
                f"  [{conf_color}]{p.match_confidence.value.upper():>8}[/{conf_color}] "
                f"({p.match_score:.0f}%) "
                f"[bold]{p.google_name}[/bold] — "
                f"★{p.rating or 0:.1f} ({p.user_ratings_total or 0:,} reviews) "
                f"{'[red]CLOSED[/red]' if p.business_status == 'CLOSED_PERMANENTLY' else ''}"
            )

    # Unmatched list
    unmatched_names = [
        # We don't have canonical names on the place objects for unmatched,
        # so we report from stats
    ]
    console.print(
        f"\n[bold]Summary:[/bold] {len(places)} matched, "
        f"{stats['unmatched']} unmatched, "
        f"{stats.get('errors', 0)} errors"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Google Places ground truth data"
    )
    parser.add_argument(
        "--batch",
        type=int,
        action="append",
        choices=[1, 2, 3],
        help="Which batch(es) to process (default: 1). Can specify multiple.",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="Run popular baseline search",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show cost estimate only, don't make API calls",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Max concurrent API calls (default: 10)",
    )
    args = parser.parse_args()

    # Default to batch 1 if nothing specified
    if not args.batch and not args.baseline:
        args.batch = [1]

    # Check API key
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        console.print(
            "[red]GOOGLE_PLACES_API_KEY not set.[/red] "
            "Add it to your .env file."
        )
        sys.exit(1)

    # Init DB
    conn = init_db()

    # -----------------------------------------------------------------------
    # Restaurant batches
    # -----------------------------------------------------------------------
    if args.batch:
        console.print("\n[bold]Selecting restaurants...[/bold]")
        restaurants = get_batch_restaurants(conn, args.batch)

        if not restaurants:
            console.print("[yellow]No restaurants found for selected batches.[/yellow]")
        else:
            # Filter already fetched (idempotent)
            already_matched = get_matched_canonical_ids(conn)
            before_count = len(restaurants)
            restaurants = [
                (cid, name)
                for cid, name in restaurants
                if cid not in already_matched
            ]
            already_fetched = before_count - len(restaurants)

            if already_fetched:
                console.print(
                    f"  [dim]Skipping {already_fetched} already fetched[/dim]"
                )

            if not restaurants:
                console.print("[green]All restaurants already fetched![/green]")
            else:
                # Cost estimate
                est_cost = len(restaurants) * COST_PER_REQUEST
                console.print(
                    f"\n[bold]Plan:[/bold] {len(restaurants)} API calls "
                    f"× ${COST_PER_REQUEST:.3f} = [bold]${est_cost:.2f}[/bold]"
                )

                if args.dry_run:
                    console.print("[yellow]Dry run — no API calls made.[/yellow]")
                else:
                    # Execute
                    places, stats = await fetch_restaurant_places(
                        restaurants, api_key, args.max_concurrent
                    )

                    # Insert into DB
                    for place in places:
                        insert_google_place(conn, place)

                    actual_cost = (
                        sum(stats[k] for k in ("high", "medium", "unmatched"))
                        * COST_PER_REQUEST
                    )
                    print_summary(places, stats, already_fetched, actual_cost)

                    # Save unmatched to JSON for review
                    unmatched_names = []
                    matched_cids = {p.canonical_id for p in places}
                    for cid, name in get_batch_restaurants(conn, args.batch):
                        if cid not in matched_cids and cid not in already_matched:
                            unmatched_names.append(
                                {"canonical_id": cid, "canonical_name": name}
                            )

                    if unmatched_names:
                        unmatched_path = (
                            Path(__file__).parent.parent
                            / "data"
                            / "unmatched_google.json"
                        )
                        unmatched_path.write_text(
                            json.dumps(unmatched_names, indent=2)
                        )
                        console.print(
                            f"\n[dim]Unmatched list saved to {unmatched_path}[/dim]"
                        )

    # -----------------------------------------------------------------------
    # Baseline
    # -----------------------------------------------------------------------
    if args.baseline:
        console.print("\n[bold]Fetching popular baseline...[/bold]")

        if args.dry_run:
            # 5 queries × up to 3 pages = 15 requests max
            est_cost = 15 * COST_PER_REQUEST
            console.print(
                f"  Est. cost: up to 15 requests × ${COST_PER_REQUEST:.3f} "
                f"= [bold]${est_cost:.2f}[/bold]"
            )
            console.print("[yellow]Dry run — no API calls made.[/yellow]")
        else:
            places = await fetch_popular_baseline(api_key)

            # For each baseline place, check if it already exists as a
            # restaurant match. If so, just flag is_popular_baseline=1
            # on the existing row — don't overwrite canonical match data.
            existing_pids = {
                r["place_id"]: r["canonical_id"]
                for r in conn.execute(
                    "SELECT place_id, canonical_id FROM google_places"
                ).fetchall()
            }

            inserted = 0
            flagged = 0
            skipped = 0
            for place in places:
                if place.place_id in existing_pids:
                    if existing_pids[place.place_id] is not None:
                        # Already has canonical match — just flag as baseline
                        conn.execute(
                            "UPDATE google_places SET is_popular_baseline = 1 WHERE place_id = ?",
                            (place.place_id,),
                        )
                        flagged += 1
                    else:
                        skipped += 1  # Already a baseline-only entry
                else:
                    insert_google_place(conn, place)
                    inserted += 1
            conn.commit()

            console.print(
                f"  {inserted} new baseline entries inserted, "
                f"{flagged} existing matches flagged as also-baseline, "
                f"{skipped} already in DB"
            )
            console.print(
                f"[bold green]Baseline complete.[/bold green]"
            )

    conn.close()
    console.print("\n[bold green]Done.[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
