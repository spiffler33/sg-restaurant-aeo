"""AEO Research Toolkit — CLI interface.

Wraps the sg-restaurant-aeo research pipeline into a single `aeo` command
with subcommands for running sweeps, parsing responses, resolving entities,
probing specific restaurants, and analyzing results.

Usage:
    aeo sweep [--search-on] [--test] [--max-concurrent N]
    aeo parse [--test]
    aeo resolve [--dry-run]
    aeo probe <business> [--city CITY] [--dry-run]
    aeo zombie [--top N]
    aeo stats
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

console = Console()
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "aeo.db"


def _get_conn() -> sqlite3.Connection:
    """Open a read-only connection to the research database."""
    if not DB_PATH.exists():
        console.print(f"[red]Database not found at {DB_PATH}[/red]")
        console.print("Run 'aeo sweep' first to create it, or check your working directory.")
        raise SystemExit(1)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@click.group()
@click.version_option(version="0.1.0", prog_name="aeo")
def cli():
    """AEO Research Toolkit — study how AI models recommend restaurants."""
    pass


# ── sweep ────────────────────────────────────────────────────────────


@cli.command()
@click.option("--search-on/--search-off", default=False, help="Enable web search tools on models.")
@click.option("--test", is_flag=True, help="Test run: 5 prompts only.")
@click.option("--max-concurrent", default=5, type=int, help="Max concurrent API calls.")
def sweep(search_on: bool, test: bool, max_concurrent: int):
    """Run a query sweep: prompts x models x search mode.

    Sends discovery prompts to GPT-4o, Claude, Gemini, and Perplexity,
    stores raw responses to data/raw/ and the SQLite database.
    """
    from .db import init_db, insert_prompt, insert_query_result
    from .models import DiscoveryPrompt
    from .query_runner import run_sweep

    prompts_path = PROJECT_ROOT / "prompts" / "discovery_prompts.json"
    if not prompts_path.exists():
        console.print("[red]No prompts found.[/red] Add prompts to prompts/discovery_prompts.json")
        raise SystemExit(1)

    raw = json.loads(prompts_path.read_text())
    prompts = [DiscoveryPrompt(**p) for p in raw]

    if test:
        prompts = prompts[:5]
        console.print(f"[yellow]Test mode:[/yellow] using first 5 prompts")

    search_modes = [search_on]
    console.print(
        f"Sweep: {len(prompts)} prompts x 4 models x search={'ON' if search_on else 'OFF'}"
    )

    conn = init_db(DB_PATH)
    for p in prompts:
        insert_prompt(conn, p)

    results = asyncio.run(
        run_sweep(prompts, search_modes=search_modes, max_concurrent=max_concurrent)
    )

    for r in results:
        insert_query_result(conn, r)

    conn.close()
    console.print(f"[green]Done.[/green] {len(results)} results saved to {DB_PATH}")


# ── parse ────────────────────────────────────────────────────────────


@cli.command()
@click.option("--test", is_flag=True, help="Parse first 20 responses only.")
def parse(test: bool):
    """Parse raw LLM responses into structured restaurant mentions.

    Uses Claude Haiku to extract restaurant names, rankings, cuisine tags,
    and other attributes from raw text responses.
    """
    from .db import init_db, insert_parsed_response
    from .response_parser import parse_batch

    conn = init_db(DB_PATH)

    rows = conn.execute(
        "SELECT id, raw_response, model_name, prompt_id FROM query_results ORDER BY id"
    ).fetchall()

    if test:
        rows = rows[:20]
        console.print(f"[yellow]Test mode:[/yellow] parsing first 20 responses")

    already_parsed = {
        r[0] for r in conn.execute("SELECT query_result_id FROM parsed_responses").fetchall()
    }
    to_parse = [dict(r) for r in rows if r["id"] not in already_parsed]

    if not to_parse:
        console.print("[green]All responses already parsed.[/green]")
        return

    console.print(f"Parsing {len(to_parse)} responses ({len(already_parsed)} already done)...")

    parsed, in_tok, out_tok = asyncio.run(parse_batch(to_parse, already_parsed=already_parsed))

    for p in parsed:
        insert_parsed_response(conn, p)

    conn.close()
    cost = (in_tok * 0.25 + out_tok * 1.25) / 1_000_000
    console.print(
        f"[green]Done.[/green] {len(parsed)} parsed. "
        f"Tokens: {in_tok:,} in + {out_tok:,} out (~${cost:.2f})"
    )


# ── resolve ──────────────────────────────────────────────────────────


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show merges without writing to DB.")
def resolve(dry_run: bool):
    """Run entity resolution to deduplicate restaurant names.

    Three-stage pipeline: exact normalized, base name grouping, fuzzy matching
    with shared-word penalty. Produces canonical_restaurants entries.
    """
    from .db import init_db, insert_canonical_restaurant, link_mentions_to_canonical
    from .entity_resolution import build_canonical_entries, load_name_metadata, resolve as er_resolve

    conn = init_db(DB_PATH)
    name_infos = load_name_metadata(conn)
    console.print(f"Loaded {len(name_infos)} unique restaurant names")

    canonical_clusters, merge_log, borderline, stage_counts = er_resolve(name_infos)
    entries = build_canonical_entries(canonical_clusters, name_infos)

    console.print(f"Resolved to {len(entries)} canonical restaurants ({len(merge_log)} merges)")
    console.print(f"  Stage 1 (exact): {stage_counts.get(1, 0)}")
    console.print(f"  Stage 2 (base):  {stage_counts.get(2, 0)}")
    console.print(f"  Stage 3 (fuzzy): {stage_counts.get(3, 0)}")
    console.print(f"  Borderline pairs: {len(borderline)}")

    if dry_run:
        console.print("[yellow]Dry run — no changes written.[/yellow]")
        # Show top merges
        for m in merge_log[:20]:
            console.print(f"  {m['merged_name']} → {m['canonical_name']} ({m['merge_reason']})")
        return

    for entry in entries:
        cid = insert_canonical_restaurant(
            conn,
            entry.canonical_name,
            entry.variant_names,
            entry.total_mentions,
            entry.model_count,
            entry.models_mentioning,
        )
        link_mentions_to_canonical(conn, cid, entry.variant_names)

    conn.commit()
    conn.close()

    # Save merge log
    log_path = PROJECT_ROOT / "data" / "merge_log.json"
    log_path.write_text(json.dumps(merge_log, indent=2, ensure_ascii=False))
    console.print(f"[green]Done.[/green] Merge log saved to {log_path}")


# ── probe ────────────────────────────────────────────────────────────


@cli.command()
@click.argument("business")
@click.option("--city", default="Singapore", help="City to probe (default: Singapore).")
@click.option("--dry-run", is_flag=True, help="Show prompts and cost estimate only.")
@click.option("--skip-queries", is_flag=True, help="Re-parse and re-analyze saved results.")
@click.option("--analyze-only", is_flag=True, help="Re-analyze saved parsed results.")
def probe(business: str, city: str, dry_run: bool, skip_queries: bool, analyze_only: bool):
    """Run a targeted AEO probe for a specific business.

    Generates 20 discovery prompts across 4 specificity tiers, queries 4 AI models
    with search ON and OFF (160 queries), parses responses, and generates a
    detection report.

    Example: aeo probe "Sabai Fine Thai" --city Singapore
    """
    from .models import DiscoveryPrompt, Dimension, ModelName, Specificity
    from .query_runner import query_model
    from .response_parser import parse_batch

    probe_dir = PROJECT_ROOT / "data" / "probes" / business.lower().replace(" ", "_")
    probe_dir.mkdir(parents=True, exist_ok=True)
    results_path = probe_dir / "results.json"
    parsed_path = probe_dir / "parsed.json"
    report_path = probe_dir / "report.md"

    # Generate prompts
    prompts_data = [
        # Tier 1 — Generic
        {"tier": 1, "text": f"Best restaurants in {city}"},
        {"tier": 1, "text": f"Top dining spots in {city}"},
        {"tier": 1, "text": f"Restaurant recommendations {city}"},
        {"tier": 1, "text": f"Where to eat in {city}"},
        {"tier": 1, "text": f"Good places to eat in {city}"},
        # Tier 2 — Category (user should customize)
        {"tier": 2, "text": f"Best restaurants near {business.split()[-1] if len(business.split()) > 2 else city} area"},
        {"tier": 2, "text": f"Good dining near downtown {city}"},
        {"tier": 2, "text": f"Restaurants in central {city}"},
        {"tier": 2, "text": f"Where to eat near {city} waterfront"},
        {"tier": 2, "text": f"Popular restaurants in {city} CBD"},
        # Tier 3 — Attribute-specific
        {"tier": 3, "text": f"Upscale dining with a view in {city}"},
        {"tier": 3, "text": f"Best restaurants for a special occasion in {city}"},
        {"tier": 3, "text": f"Hidden gem restaurants in {city}"},
        {"tier": 3, "text": f"Restaurants with good ambiance in {city}"},
        {"tier": 3, "text": f"Chef-driven restaurants in {city}"},
        # Tier 4 — Near-name
        {"tier": 4, "text": f"Is {business} any good?"},
        {"tier": 4, "text": f"Tell me about {business} in {city}"},
        {"tier": 4, "text": f"{business} restaurant review"},
        {"tier": 4, "text": f"What's {business} known for?"},
        {"tier": 4, "text": f"Should I eat at {business} in {city}?"},
    ]

    tier_names = {1: "Generic", 2: "Location", 3: "Attribute", 4: "Near-name"}
    models = list(ModelName)
    total_queries = len(prompts_data) * len(models) * 2

    # Cost estimate
    cost_est = total_queries * 0.07  # rough average
    console.print(f"\n[bold]AEO Probe: {business}[/bold] ({city})")
    console.print(f"  {len(prompts_data)} prompts x {len(models)} models x 2 search = {total_queries} queries")
    console.print(f"  Estimated cost: ~${cost_est:.0f}")

    if dry_run:
        for tier in sorted(tier_names):
            console.print(f"\n  [bold]Tier {tier}: {tier_names[tier]}[/bold]")
            for p in prompts_data:
                if p["tier"] == tier:
                    console.print(f"    {p['text']}")
        console.print("\n[yellow]Dry run — exiting.[/yellow]")
        return

    discovery_prompts = [
        DiscoveryPrompt(
            id=f"probe_{i:03d}",
            text=p["text"],
            dimension=Dimension.CUISINE,
            category=f"probe_t{p['tier']}",
            specificity=Specificity.BROAD if p["tier"] == 1
            else Specificity.MEDIUM if p["tier"] == 2
            else Specificity.NARROW,
        )
        for i, p in enumerate(prompts_data)
    ]

    async def _run():
        if not skip_queries and not analyze_only:
            # Run queries
            console.print(f"\n[bold]Running {total_queries} queries...[/bold]")
            results = []
            for i, dp in enumerate(discovery_prompts):
                for model in models:
                    for search in [False, True]:
                        try:
                            r = await query_model(dp, model, search_enabled=search)
                            results.append({
                                "idx": len(results),
                                "prompt_id": dp.id,
                                "tier": prompts_data[i]["tier"],
                                "prompt_text": dp.text,
                                "model": model.value,
                                "search_enabled": search,
                                "raw_response": r.raw_response,
                                "latency_ms": r.latency_ms,
                                "token_usage": r.token_usage,
                                "timestamp": r.timestamp.isoformat(),
                            })
                            if len(results) % 20 == 0:
                                console.print(f"  {len(results)}/{total_queries} done")
                        except Exception as e:
                            console.print(f"  [red]FAIL[/red] {dp.id} / {model.value}: {e}")

            results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            console.print(f"  Saved {len(results)} results to {results_path}")
        else:
            results = json.loads(results_path.read_text())
            console.print(f"  Loaded {len(results)} saved results")

        if not analyze_only:
            # Parse
            query_rows = [
                {"id": r["idx"], "raw_response": r["raw_response"],
                 "model_name": r["model"], "prompt_id": r["prompt_id"]}
                for r in results
            ]
            parsed_responses, in_tok, out_tok = await parse_batch(query_rows)
            parsed_list = []
            for pr in parsed_responses:
                parsed_list.append({
                    "query_result_id": pr.query_result_id,
                    "restaurants": [
                        {"restaurant_name": m.restaurant_name,
                         "rank_position": m.rank_position}
                        for m in pr.restaurants
                    ],
                })
            parsed_path.write_text(json.dumps(parsed_list, indent=2, ensure_ascii=False))
        else:
            parsed_list = json.loads(parsed_path.read_text())

        # Analyze
        parsed_map = {p["query_result_id"]: p for p in parsed_list}
        needle = business.lower()
        detected = 0
        by_tier = {1: [0, 0], 2: [0, 0], 3: [0, 0], 4: [0, 0]}
        by_model = {}
        by_search = {True: [0, 0], False: [0, 0]}
        all_mentioned = {}

        for r in results:
            tier = r["tier"]
            model = r["model"]
            search = r["search_enabled"]
            by_tier[tier][1] += 1
            by_search[search][1] += 1
            by_model.setdefault(model, [0, 0])
            by_model[model][1] += 1

            found = needle in r["raw_response"].lower()
            if found:
                detected += 1
                by_tier[tier][0] += 1
                by_model[model][0] += 1
                by_search[search][0] += 1

            parsed = parsed_map.get(r["idx"])
            if parsed:
                for m in parsed.get("restaurants", []):
                    name = m["restaurant_name"]
                    all_mentioned[name] = all_mentioned.get(name, 0) + 1

        # Report
        lines = [
            f"# AEO Probe Report: {business}",
            f"",
            f"**City:** {city}",
            f"**Queries:** {len(results)}",
            f"**Detection rate:** {detected}/{len(results)} ({detected/max(len(results),1)*100:.1f}%)",
            "",
            "## By Tier",
            "| Tier | Detected | Total | Rate |",
            "|------|----------|-------|------|",
        ]
        for t in sorted(by_tier):
            d, total = by_tier[t]
            lines.append(f"| {t} ({tier_names[t]}) | {d} | {total} | {d/max(total,1)*100:.0f}% |")

        lines.extend(["", "## By Model", "| Model | Detected | Total | Rate |", "|-------|----------|-------|------|"])
        for m, (d, total) in sorted(by_model.items()):
            lines.append(f"| {m} | {d} | {total} | {d/max(total,1)*100:.0f}% |")

        lines.extend(["", "## Search ON vs OFF", "| Mode | Detected | Total | Rate |", "|------|----------|-------|------|"])
        for s in [False, True]:
            d, total = by_search[s]
            lines.append(f"| {'ON' if s else 'OFF'} | {d} | {total} | {d/max(total,1)*100:.0f}% |")

        lines.extend(["", "## Top Competitors (eating your lunch)", "| Rank | Restaurant | Mentions |", "|------|-----------|----------|"])
        top = sorted(all_mentioned.items(), key=lambda x: -x[1])[:20]
        for i, (name, count) in enumerate(top, 1):
            marker = " **<-- TARGET**" if needle in name.lower() else ""
            lines.append(f"| {i} | {name}{marker} | {count} |")

        report = "\n".join(lines)
        report_path.write_text(report)
        console.print(f"\n[green]Report saved to {report_path}[/green]")
        console.print(f"\nDetection rate: [bold]{detected}/{len(results)}[/bold] ({detected/max(len(results),1)*100:.1f}%)")

    asyncio.run(_run())


# ── zombie ───────────────────────────────────────────────────────────


@cli.command()
@click.option("--top", default=50, type=int, help="Show top N zombies by mention count.")
def zombie(top: int):
    """Find zombie restaurants — recommended by AI but closed on Google Places.

    Queries the research database for restaurants with CLOSED status that
    AI models still actively recommend.
    """
    conn = _get_conn()

    rows = conn.execute("""
        SELECT cr.canonical_name, cr.total_mentions, cr.model_count,
               cr.models_mentioning, gp.business_status, gp.rating,
               gp.user_ratings_total
        FROM canonical_restaurants cr
        JOIN google_places gp ON cr.id = gp.canonical_id
        WHERE gp.business_status IN ('CLOSED_PERMANENTLY', 'CLOSED_TEMPORARILY')
          AND cr.model_count > 0
        ORDER BY cr.total_mentions DESC
        LIMIT ?
    """, (top,)).fetchall()

    if not rows:
        console.print("[green]No zombie restaurants found.[/green]")
        return

    table = Table(title=f"Zombie Restaurants (top {top})", show_lines=False)
    table.add_column("Restaurant", width=35)
    table.add_column("Mentions", justify="right", width=9)
    table.add_column("Models", justify="right", width=7)
    table.add_column("Status", width=20)
    table.add_column("Rating", justify="right", width=7)
    table.add_column("Reviews", justify="right", width=8)

    for r in rows:
        status_style = "red" if r["business_status"] == "CLOSED_PERMANENTLY" else "yellow"
        table.add_row(
            r["canonical_name"],
            str(r["total_mentions"]),
            str(r["model_count"]),
            f"[{status_style}]{r['business_status']}[/{status_style}]",
            f"{r['rating']:.1f}" if r["rating"] else "—",
            str(r["user_ratings_total"] or "—"),
        )

    console.print(table)
    console.print(f"\n[bold]{len(rows)}[/bold] zombie restaurants found")

    # Summary
    perm = sum(1 for r in rows if r["business_status"] == "CLOSED_PERMANENTLY")
    temp = sum(1 for r in rows if r["business_status"] == "CLOSED_TEMPORARILY")
    total_mentions = sum(r["total_mentions"] for r in rows)
    console.print(f"  Permanently closed: {perm}")
    console.print(f"  Temporarily closed: {temp}")
    console.print(f"  Total zombie mentions: {total_mentions}")

    conn.close()


# ── stats ────────────────────────────────────────────────────────────


@cli.command()
def stats():
    """Show dataset statistics from the research database."""
    conn = _get_conn()

    queries = conn.execute("SELECT COUNT(*) FROM query_results").fetchone()[0]
    mentions = conn.execute("SELECT COUNT(*) FROM restaurant_mentions").fetchone()[0]
    canonical = conn.execute(
        "SELECT COUNT(*) FROM canonical_restaurants WHERE model_count > 0"
    ).fetchone()[0]
    google = conn.execute("SELECT COUNT(*) FROM google_places").fetchone()[0]
    verified = conn.execute(
        "SELECT COUNT(*) FROM google_places WHERE human_verified = 1"
    ).fetchone()[0]

    models = conn.execute("""
        SELECT model_name, COUNT(*) as cnt,
               AVG(LENGTH(raw_response)) as avg_len
        FROM query_results
        GROUP BY model_name
    """).fetchall()

    table = Table(title="AEO Research Dataset", show_lines=False)
    table.add_column("Metric", style="cyan", width=35)
    table.add_column("Value", justify="right", width=15)

    table.add_row("Total queries", f"{queries:,}")
    table.add_row("Total restaurant mentions", f"{mentions:,}")
    table.add_row("Canonical restaurants (active)", f"{canonical:,}")
    table.add_row("Google Places matches", f"{google:,}")
    table.add_row("Human-verified matches", f"{verified:,}")

    console.print(table)

    console.print("\n[bold]Per-model breakdown:[/bold]")
    for m in models:
        console.print(f"  {m['model_name']}: {m['cnt']:,} queries, avg {m['avg_len']:,.0f} chars")

    conn.close()


# ── entry point ──────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
