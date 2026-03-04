#!/usr/bin/env python3
"""Phase 2b: Entity Resolution — collapse restaurant name variants into canonical entries.

Usage:
    python scripts/resolve_entities.py           # Full resolution
    python scripts/resolve_entities.py --dry-run  # Preview without writing to DB
    python scripts/resolve_entities.py --threshold 90  # Stricter fuzzy threshold

Idempotent: re-running clears and rebuilds all canonical data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import (
    get_connection,
    create_tables,
    reset_canonical_data,
    insert_canonical_restaurant,
    link_mentions_to_canonical,
)
from src.entity_resolution import (
    CanonicalEntry,
    MergeRecord,
    load_name_metadata,
    resolve,
    build_canonical_entries,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2b: Entity Resolution")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview results without writing to DB",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=85,
        help="Fuzzy match threshold (default: 85)",
    )
    parser.add_argument(
        "--borderline",
        type=int,
        default=75,
        help="Borderline threshold for LLM review (default: 75)",
    )
    args = parser.parse_args()

    console = Console()
    data_dir = Path(__file__).parent.parent / "data"

    # ------------------------------------------------------------------
    # Step 1: Load data
    # ------------------------------------------------------------------
    console.print("\n[bold cyan]Phase 2b: Entity Resolution[/bold cyan]")
    console.print("=" * 60)

    conn = get_connection()
    create_tables(conn)

    console.print("\n[bold]Step 1:[/bold] Loading restaurant name metadata...")
    name_infos = load_name_metadata(conn)
    console.print(f"  Loaded [green]{len(name_infos)}[/green] unique restaurant names")

    total_mentions = sum(info.mention_count for info in name_infos.values())
    console.print(f"  Total mentions: [green]{total_mentions:,}[/green]")

    # ------------------------------------------------------------------
    # Step 2: Run resolution
    # ------------------------------------------------------------------
    console.print(f"\n[bold]Step 2:[/bold] Running 4-stage entity resolution (threshold={args.threshold})...")

    canonical_clusters, merge_log, borderline_pairs, manual_count = resolve(
        name_infos,
        fuzzy_threshold=args.threshold,
        borderline_threshold=args.borderline,
    )

    # Count merges by stage
    stage_counts = {"exact_normalized": 0, "base_name": 0, "fuzzy": 0, "manual": 0}
    for record in merge_log:
        if record.merge_reason == "exact_normalized":
            stage_counts["exact_normalized"] += 1
        elif record.merge_reason.startswith("base_name"):
            stage_counts["base_name"] += 1
        elif record.merge_reason.startswith("fuzzy"):
            stage_counts["fuzzy"] += 1
        elif record.merge_reason == "manual":
            stage_counts["manual"] += 1

    console.print(f"  Stage 1 (exact normalized): [yellow]{stage_counts['exact_normalized']}[/yellow] merges")
    console.print(f"  Stage 2 (base name):        [yellow]{stage_counts['base_name']}[/yellow] merges")
    console.print(f"  Stage 3 (fuzzy ≥{args.threshold}%):     [yellow]{stage_counts['fuzzy']}[/yellow] merges")
    console.print(f"  Stage 4 (manual overrides): [yellow]{stage_counts['manual']}[/yellow] merges")
    console.print(f"  Borderline pairs (review):  [yellow]{len(borderline_pairs)}[/yellow]")
    console.print(
        f"\n  [bold green]{len(name_infos)} unique names → {len(canonical_clusters)} canonical restaurants[/bold green]"
    )

    # ------------------------------------------------------------------
    # Step 3: Build canonical entries with aggregated stats
    # ------------------------------------------------------------------
    console.print("\n[bold]Step 3:[/bold] Computing aggregated stats...")
    entries = build_canonical_entries(canonical_clusters, name_infos)

    # ------------------------------------------------------------------
    # Step 4: Write to DB (unless dry-run)
    # ------------------------------------------------------------------
    if not args.dry_run:
        console.print("\n[bold]Step 4:[/bold] Writing to database...")
        reset_canonical_data(conn)

        for entry in entries:
            canonical_id = insert_canonical_restaurant(
                conn,
                canonical_name=entry.canonical_name,
                variant_names=entry.variant_names,
                total_mentions=entry.total_mentions,
                model_count=entry.model_count,
                models_mentioning=entry.models_mentioning,
            )
            linked = link_mentions_to_canonical(
                conn, canonical_id, entry.variant_names
            )

        conn.commit()

        # Verify: count mentions with canonical_id set
        linked_count = conn.execute(
            "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id IS NOT NULL"
        ).fetchone()[0]
        unlinked_count = conn.execute(
            "SELECT COUNT(*) FROM restaurant_mentions WHERE canonical_id IS NULL"
        ).fetchone()[0]
        console.print(f"  Linked: [green]{linked_count:,}[/green] mentions")
        if unlinked_count > 0:
            console.print(f"  [red]Unlinked: {unlinked_count}[/red] (investigate!)")
        else:
            console.print(f"  Unlinked: [green]0[/green] — all mentions resolved!")
    else:
        console.print("\n[bold yellow]Step 4: DRY RUN — skipping DB write[/bold yellow]")

    # ------------------------------------------------------------------
    # Step 5: Save merge log
    # ------------------------------------------------------------------
    merge_log_path = data_dir / "merge_log.json"
    merge_log_data = [
        {
            "canonical_name": r.canonical_name,
            "merged_name": r.merged_name,
            "merge_reason": r.merge_reason,
            "similarity_score": r.similarity_score,
        }
        for r in merge_log
    ]
    merge_log_path.write_text(json.dumps(merge_log_data, indent=2, ensure_ascii=False))
    console.print(f"\n  Merge log saved: {merge_log_path} ({len(merge_log)} records)")

    # Save borderline pairs for review
    if borderline_pairs:
        borderline_path = data_dir / "borderline_pairs.json"
        borderline_data = [
            {"name_a": a, "name_b": b, "score": round(s, 1)}
            for a, b, s in sorted(borderline_pairs, key=lambda x: -x[2])
        ]
        borderline_path.write_text(
            json.dumps(borderline_data, indent=2, ensure_ascii=False)
        )
        console.print(f"  Borderline pairs saved: {borderline_path} ({len(borderline_pairs)} pairs)")

    # ------------------------------------------------------------------
    # Step 6: Summary report
    # ------------------------------------------------------------------
    console.print("\n" + "=" * 60)
    console.print("[bold cyan]RESULTS SUMMARY[/bold cyan]")
    console.print("=" * 60)

    # Top 30 by total mentions
    top30_table = Table(title="Top 30 Restaurants by Total Mentions (Post-Resolution)")
    top30_table.add_column("#", style="dim", width=4)
    top30_table.add_column("Restaurant", style="bold")
    top30_table.add_column("Mentions", justify="right")
    top30_table.add_column("Models", justify="center")
    top30_table.add_column("Variants", justify="right")

    for i, entry in enumerate(entries[:30], 1):
        model_str = f"{entry.model_count}/4"
        if entry.model_count == 4:
            model_str = "[green]4/4[/green]"
        elif entry.model_count == 1:
            model_str = "[red]1/4[/red]"

        top30_table.add_row(
            str(i),
            entry.canonical_name,
            str(entry.total_mentions),
            model_str,
            str(len(entry.variant_names)),
        )

    console.print(top30_table)

    # Model distribution: how many restaurants mentioned by 4/3/2/1 models
    model_dist = {1: 0, 2: 0, 3: 0, 4: 0}
    for entry in entries:
        model_dist[entry.model_count] = model_dist.get(entry.model_count, 0) + 1

    dist_table = Table(title="Model Coverage Distribution")
    dist_table.add_column("Models Mentioning", style="bold")
    dist_table.add_column("Restaurant Count", justify="right")
    dist_table.add_column("% of Total", justify="right")

    for n_models in [4, 3, 2, 1]:
        count = model_dist.get(n_models, 0)
        pct = count / len(entries) * 100 if entries else 0
        dist_table.add_row(
            f"{n_models}/4 models",
            str(count),
            f"{pct:.1f}%",
        )

    console.print(dist_table)

    # Per-model stats: how many canonical restaurants does each model "know"?
    model_restaurant_counts: dict[str, int] = {}
    for entry in entries:
        for model in entry.models_mentioning:
            model_restaurant_counts[model] = model_restaurant_counts.get(model, 0) + 1

    model_table = Table(title="Restaurants Known Per Model")
    model_table.add_column("Model", style="bold")
    model_table.add_column("Canonical Restaurants", justify="right")
    model_table.add_column("% of Total", justify="right")

    for model in sorted(model_restaurant_counts.keys()):
        count = model_restaurant_counts[model]
        pct = count / len(entries) * 100 if entries else 0
        short_name = model.split("/")[-1]
        model_table.add_row(short_name, str(count), f"{pct:.1f}%")

    console.print(model_table)

    # Multi-variant clusters (most variants)
    multi_variant = sorted(entries, key=lambda e: len(e.variant_names), reverse=True)
    multi_variant = [e for e in multi_variant if len(e.variant_names) > 2][:15]

    if multi_variant:
        variant_table = Table(title="Top 15 Clusters by Variant Count")
        variant_table.add_column("Canonical Name", style="bold")
        variant_table.add_column("Variants", justify="right")
        variant_table.add_column("Example Variants", max_width=60)

        for entry in multi_variant:
            examples = entry.variant_names[:5]
            if len(entry.variant_names) > 5:
                examples_str = ", ".join(examples) + f" (+{len(entry.variant_names) - 5} more)"
            else:
                examples_str = ", ".join(examples)
            variant_table.add_row(
                entry.canonical_name,
                str(len(entry.variant_names)),
                examples_str,
            )

        console.print(variant_table)

    # Quick stats
    singletons = sum(1 for e in entries if len(e.variant_names) == 1)
    multi = sum(1 for e in entries if len(e.variant_names) > 1)
    max_variants = max(len(e.variant_names) for e in entries) if entries else 0

    console.print(f"\n[bold]Quick Stats:[/bold]")
    console.print(f"  Canonical restaurants:  [green]{len(entries):,}[/green]")
    console.print(f"  Singletons (1 variant): [yellow]{singletons:,}[/yellow] ({singletons/len(entries)*100:.1f}%)")
    console.print(f"  Multi-variant clusters: [yellow]{multi:,}[/yellow]")
    console.print(f"  Max variants in one cluster: [yellow]{max_variants}[/yellow]")
    console.print(f"  Total merge operations: [yellow]{len(merge_log)}[/yellow]")

    # Spot-check known cases
    console.print(f"\n[bold]Spot-Check Known Cases:[/bold]")
    spot_checks = [
        "Burnt Ends", "Labyrinth", "PS.Cafe", "Lau Pa Sat",
        "Hawker Chan", "Komala Vilas", "Tian Tian Hainanese Chicken Rice",
        "Maxwell Food Centre",
    ]
    for check_name in spot_checks:
        for entry in entries:
            if check_name in entry.variant_names or entry.canonical_name == check_name:
                variants_str = ", ".join(entry.variant_names[:4])
                if len(entry.variant_names) > 4:
                    variants_str += f" (+{len(entry.variant_names) - 4} more)"
                console.print(
                    f"  [green]✓[/green] {entry.canonical_name} → {len(entry.variant_names)} variants, "
                    f"{entry.total_mentions} mentions: {variants_str}"
                )
                break

    conn.close()
    console.print("\n[bold green]Done![/bold green]\n")


if __name__ == "__main__":
    main()
