#!/usr/bin/env python3
"""Parse raw LLM responses into structured restaurant mentions.

Usage:
    python scripts/parse_responses.py --test       # Parse 20 responses (5 per model)
    python scripts/parse_responses.py              # Parse all unparsed responses
    python scripts/parse_responses.py --show       # Show sample parsed output (no DB write)

Idempotent: skips already-parsed query_result_ids on re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

from src.db import get_connection, init_db, insert_parsed_response
from src.response_parser import parse_batch

console = Console()


def get_query_rows(conn, limit: int | None = None, test_mode: bool = False) -> list[dict]:
    """Fetch query result rows from DB.

    In test mode, picks 5 responses per model (spread across search ON/OFF).
    """
    if test_mode:
        # 5 per model: 2 or 3 search OFF + 2 or 3 search ON to get variety
        rows = []
        models = conn.execute("SELECT DISTINCT model_name FROM query_results").fetchall()
        for (model,) in models:
            off = conn.execute(
                "SELECT id, raw_response, model_name, prompt_id, search_enabled "
                "FROM query_results WHERE model_name = ? AND search_enabled = 0 LIMIT 3",
                (model,),
            ).fetchall()
            on = conn.execute(
                "SELECT id, raw_response, model_name, prompt_id, search_enabled "
                "FROM query_results WHERE model_name = ? AND search_enabled = 1 LIMIT 2",
                (model,),
            ).fetchall()
            rows.extend(off)
            rows.extend(on)
        return [dict(r) for r in rows]

    query = (
        "SELECT id, raw_response, model_name, prompt_id, search_enabled "
        "FROM query_results ORDER BY id"
    )
    if limit:
        query += f" LIMIT {limit}"
    return [dict(r) for r in conn.execute(query).fetchall()]


def get_already_parsed(conn) -> set[int]:
    """Get set of query_result_ids that have already been parsed."""
    rows = conn.execute("SELECT query_result_id FROM parsed_responses").fetchall()
    return {r[0] for r in rows}


def print_sample_output(parsed_list, query_rows_by_id: dict, n: int = 5):
    """Print sample parsed output for quality review."""
    console.print("\n[bold underline]Sample Parsed Output[/bold underline]\n")

    for parsed in parsed_list[:n]:
        qr = query_rows_by_id.get(parsed.query_result_id, {})
        model = qr.get("model_name", "?")
        prompt = qr.get("prompt_id", "?")
        search = "ON" if qr.get("search_enabled") else "OFF"

        console.print(f"[bold cyan]Query {parsed.query_result_id}[/bold cyan] | "
                      f"{model} | {prompt} | search={search}")
        console.print(f"  Restaurants extracted: {len(parsed.restaurants)}")

        for r in parsed.restaurants[:5]:
            tags = ", ".join(r.cuisine_tags[:3]) if r.cuisine_tags else "-"
            vibes = ", ".join(r.vibe_tags[:3]) if r.vibe_tags else "-"
            console.print(
                f"    {r.rank_position:2d}. [bold]{r.restaurant_name}[/bold] "
                f"| {r.neighbourhood or '-':15s} | {r.price_indicator.value:5s} "
                f"| cuisine=[{tags}] | vibe=[{vibes}]"
            )
        if len(parsed.restaurants) > 5:
            console.print(f"    ... +{len(parsed.restaurants) - 5} more")
        console.print()


def print_summary(parsed_list, query_rows_by_id: dict, total_in: int, total_out: int):
    """Print comprehensive summary of parsed results."""
    console.print("\n" + "=" * 70)
    console.print("[bold]PARSING SUMMARY[/bold]")
    console.print("=" * 70)

    # Total restaurants
    all_names = []
    model_counts: dict[str, list[int]] = {}
    search_counts: dict[str, list[int]] = {}

    for parsed in parsed_list:
        qr = query_rows_by_id.get(parsed.query_result_id, {})
        model = qr.get("model_name", "unknown")
        search = "ON" if qr.get("search_enabled") else "OFF"
        n = len(parsed.restaurants)

        model_counts.setdefault(model, []).append(n)
        search_counts.setdefault(search, []).append(n)

        for r in parsed.restaurants:
            all_names.append(r.restaurant_name)

    total = len(all_names)
    unique = len(set(n.lower().strip() for n in all_names))

    console.print(f"\n[bold]Total restaurant mentions:[/bold] {total:,}")
    console.print(f"[bold]Unique names (case-insensitive):[/bold] {unique:,}")
    console.print(f"[bold]Avg restaurants per response:[/bold] {total / len(parsed_list):.1f}")

    # By model
    console.print("\n[bold underline]By Model[/bold underline]")
    table = Table(show_header=True)
    table.add_column("Model", style="cyan")
    table.add_column("Responses", justify="right")
    table.add_column("Total Mentions", justify="right")
    table.add_column("Avg/Response", justify="right")

    for model in sorted(model_counts):
        counts = model_counts[model]
        table.add_row(
            model,
            str(len(counts)),
            str(sum(counts)),
            f"{sum(counts)/len(counts):.1f}",
        )
    console.print(table)

    # By search mode
    console.print("\n[bold underline]By Search Mode[/bold underline]")
    table2 = Table(show_header=True)
    table2.add_column("Search", style="cyan")
    table2.add_column("Responses", justify="right")
    table2.add_column("Total Mentions", justify="right")
    table2.add_column("Avg/Response", justify="right")

    for mode in sorted(search_counts):
        counts = search_counts[mode]
        table2.add_row(
            f"Search {mode}",
            str(len(counts)),
            str(sum(counts)),
            f"{sum(counts)/len(counts):.1f}",
        )
    console.print(table2)

    # Top 20 most mentioned
    name_counter = Counter(n.strip() for n in all_names)
    console.print("\n[bold underline]Top 20 Most Mentioned Restaurants[/bold underline]")
    table3 = Table(show_header=True)
    table3.add_column("Rank", justify="right", style="bold")
    table3.add_column("Restaurant", style="cyan")
    table3.add_column("Mentions", justify="right")

    for i, (name, count) in enumerate(name_counter.most_common(20), 1):
        table3.add_row(str(i), name, str(count))
    console.print(table3)

    # Cost estimate
    haiku_in_rate = 1.00  # $/M tokens
    haiku_out_rate = 5.00  # $/M tokens
    cost = (total_in / 1_000_000 * haiku_in_rate) + (total_out / 1_000_000 * haiku_out_rate)
    console.print(f"\n[bold]Token usage:[/bold] {total_in:,} input + {total_out:,} output")
    console.print(f"[bold]Estimated cost:[/bold] ${cost:.2f}")
    console.print()


async def main():
    parser = argparse.ArgumentParser(description="Parse raw LLM responses into structured restaurant data")
    parser.add_argument("--test", action="store_true", help="Test mode: parse 20 responses (5 per model)")
    parser.add_argument("--show", action="store_true", help="Show sample output only, don't save to DB")
    parser.add_argument("--concurrency", type=int, default=10, help="Max concurrent API calls (default: 10)")
    args = parser.parse_args()

    conn = init_db()

    # Get rows to parse
    query_rows = get_query_rows(conn, test_mode=args.test)
    console.print(f"[bold]Query results to process:[/bold] {len(query_rows)}")

    # Build lookup dict
    rows_by_id = {r["id"]: r for r in query_rows}

    # Check idempotency
    already_parsed = get_already_parsed(conn)
    console.print(f"[bold]Already parsed:[/bold] {len(already_parsed)}")

    # Run parsing
    parsed_list, total_in, total_out = await parse_batch(
        query_rows,
        max_concurrent=args.concurrency,
        already_parsed=already_parsed,
    )

    if not parsed_list:
        conn.close()
        return

    # Show sample output for quality review
    print_sample_output(parsed_list, rows_by_id, n=8 if args.test else 5)

    # Save to DB unless --show
    if not args.show:
        console.print("[bold]Saving to database...[/bold]")
        saved = 0
        for parsed in parsed_list:
            try:
                insert_parsed_response(conn, parsed)
                saved += 1
            except Exception as e:
                console.print(f"[red]DB error for query_result_id={parsed.query_result_id}: {e}[/red]")
        console.print(f"[bold green]Saved {saved} parsed responses to DB[/bold green]")

    # Print summary
    print_summary(parsed_list, rows_by_id, total_in, total_out)

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
