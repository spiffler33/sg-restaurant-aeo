#!/usr/bin/env python3
"""Phase 2c: Recommendation Stability Test.

Measures how reproducible LLM restaurant recommendations are by re-running
a stratified subset of 15 prompts multiple times.

Design:
  - 15 prompts (5 broad, 5 medium, 5 narrow) across 5+ dimensions
  - 5 runs per prompt × model × search mode (3 for Claude search ON)
  - Total: 570 queries
  - Same parameters as original sweep (temp=0.7, same system prompts)

Usage:
    python scripts/stability_test.py --select-only   # Print prompts + cost estimate
    python scripts/stability_test.py                  # Run everything
    python scripts/stability_test.py --skip-queries   # Skip queries, just parse + analyze
    python scripts/stability_test.py --analyze-only   # Skip queries + parsing, just analyze
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.db import (
    create_tables,
    get_connection,
    init_db,
    insert_parsed_response,
    insert_prompts_bulk,
    insert_stability_result,
)
from src.entity_resolution import normalize_name
from src.models import DiscoveryPrompt, ModelName
from src.query_runner import query_model

console = Console()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

N_RUNS_DEFAULT = 5
N_RUNS_CLAUDE_ON = 3  # Reduced due to 51K avg tokens/query with web search

# Per-provider concurrency limits (same as sweep scripts)
PROVIDER_CONCURRENCY = {
    ModelName.GPT_4O: 4,
    ModelName.CLAUDE_SONNET: 4,
    ModelName.GEMINI_PRO: 3,
    ModelName.PERPLEXITY_SONAR: 2,  # Rate limit safe
}

# Cost estimation rates (blended $/1K tokens)
COST_PER_1K = {
    ModelName.GPT_4O: 0.006,
    ModelName.CLAUDE_SONNET: 0.009,
    ModelName.GEMINI_PRO: 0.0004,
    ModelName.PERPLEXITY_SONAR: 0.001,
}

# Average tokens from original sweep (for cost estimation)
AVG_TOKENS = {
    (ModelName.GPT_4O, False): 400,
    (ModelName.GPT_4O, True): 631,
    (ModelName.CLAUDE_SONNET, False): 392,
    (ModelName.CLAUDE_SONNET, True): 51_357,
    (ModelName.GEMINI_PRO, False): 1_344,
    (ModelName.GEMINI_PRO, True): 826,
    (ModelName.PERPLEXITY_SONAR, False): 487,
    (ModelName.PERPLEXITY_SONAR, True): 674,
}

# Priority dimensions for stratified sampling
PRIORITY_DIMS = ["cuisine", "neighbourhood", "vibe", "occasion", "price"]


# ---------------------------------------------------------------------------
# Prompt selection
# ---------------------------------------------------------------------------


def select_prompts(all_prompts: list[DiscoveryPrompt]) -> list[DiscoveryPrompt]:
    """Select 15 prompts: 5 broad, 5 medium, 5 narrow.

    Each group of 5 covers at least 5 different dimensions, prioritizing
    cuisine, neighbourhood, vibe, occasion, price. Selection is deterministic.
    """
    by_spec: dict[str, list[DiscoveryPrompt]] = defaultdict(list)
    for p in all_prompts:
        by_spec[p.specificity.value].append(p)

    selected: list[DiscoveryPrompt] = []

    for spec in ["broad", "medium", "narrow"]:
        pool = by_spec[spec]
        # Group by dimension
        by_dim: dict[str, list[DiscoveryPrompt]] = defaultdict(list)
        for p in pool:
            by_dim[p.dimension.value].append(p)

        picked: list[DiscoveryPrompt] = []
        used_dims: set[str] = set()

        # First pass: one from each priority dimension
        for dim in PRIORITY_DIMS:
            if dim in by_dim and by_dim[dim] and len(picked) < 5:
                picked.append(by_dim[dim][0])
                used_dims.add(dim)

        # If we still need more (some priority dims may be empty for this spec)
        if len(picked) < 5:
            for dim in sorted(by_dim.keys()):
                if dim not in used_dims and by_dim[dim] and len(picked) < 5:
                    picked.append(by_dim[dim][0])
                    used_dims.add(dim)

        selected.extend(picked)

    return selected


# ---------------------------------------------------------------------------
# Cost estimation
# ---------------------------------------------------------------------------


def estimate_cost(prompts: list[DiscoveryPrompt]) -> dict:
    """Estimate total cost for the stability test."""
    n_prompts = len(prompts)
    models = list(ModelName)
    breakdown = {}
    total = 0.0
    total_queries = 0

    for model in models:
        for search in [False, True]:
            if model == ModelName.CLAUDE_SONNET and search:
                n_runs = N_RUNS_CLAUDE_ON
            else:
                n_runs = N_RUNS_DEFAULT

            n_queries = n_prompts * n_runs
            avg_tok = AVG_TOKENS.get((model, search), 500)
            rate = COST_PER_1K.get(model, 0.005)
            cost = n_queries * avg_tok / 1000 * rate

            key = f"{model.value} (search={'ON' if search else 'OFF'})"
            breakdown[key] = {
                "queries": n_queries,
                "avg_tokens": avg_tok,
                "runs": n_runs,
                "cost": cost,
            }
            total += cost
            total_queries += n_queries

    # Parsing cost (Haiku)
    parse_cost = total_queries * 2.5 / 1000 * 0.003  # ~$1/M in, $5/M out blended
    breakdown["Parsing (Haiku)"] = {
        "queries": total_queries,
        "avg_tokens": 2500,
        "runs": "-",
        "cost": parse_cost,
    }
    total += parse_cost

    return {"breakdown": breakdown, "total": total, "total_queries": total_queries}


# ---------------------------------------------------------------------------
# Build task list for all queries
# ---------------------------------------------------------------------------


def build_query_tasks(
    prompts: list[DiscoveryPrompt],
    existing: set[tuple[str, str, int, int]],
) -> list[tuple[DiscoveryPrompt, ModelName, bool, int]]:
    """Build the full list of (prompt, model, search, run_number) tasks.

    Args:
        prompts: Selected prompts
        existing: Set of (prompt_id, model_name, search_enabled, run_number)
                  already in DB.

    Returns:
        List of tasks to run, skipping existing.
    """
    tasks = []
    models = list(ModelName)

    for prompt in prompts:
        for model in models:
            for search in [False, True]:
                n_runs = N_RUNS_CLAUDE_ON if (model == ModelName.CLAUDE_SONNET and search) else N_RUNS_DEFAULT
                for run_num in range(1, n_runs + 1):
                    key = (prompt.id, model.value, int(search), run_num)
                    if key not in existing:
                        tasks.append((prompt, model, search, run_num))

    return tasks


def get_existing_stability_combos(conn) -> set[tuple[str, str, int, int]]:
    """Return set of (prompt_id, model_name, search_enabled, run_number) already done."""
    rows = conn.execute(
        """
        SELECT DISTINCT prompt_id, model_name, search_enabled, run_number
        FROM query_results
        WHERE is_stability_test = 1
        """
    ).fetchall()
    return {(r["prompt_id"], r["model_name"], r["search_enabled"], r["run_number"]) for r in rows}


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


async def run_stability_queries(
    tasks: list[tuple[DiscoveryPrompt, ModelName, bool, int]],
    conn,
) -> tuple[int, int, dict]:
    """Execute all stability test queries.

    Returns: (successes, failures, {model: token_total})
    """
    start_time = time.monotonic()
    provider_semas = {
        model: asyncio.Semaphore(limit)
        for model, limit in PROVIDER_CONCURRENCY.items()
    }

    completed = 0
    total = len(tasks)
    successes = 0
    failure_count = 0
    failures_log: list[str] = []
    model_tokens: dict[str, int] = defaultdict(int)
    lock = asyncio.Lock()

    async def run_one(
        prompt: DiscoveryPrompt, model: ModelName, search: bool, run_num: int
    ) -> None:
        nonlocal completed, successes, failure_count
        sema = provider_semas[model]
        async with sema:
            try:
                result = await query_model(prompt, model, search_enabled=search)
                async with lock:
                    insert_stability_result(conn, result, run_num)
                    model_tokens[model.value] += result.token_usage or 0
                    successes += 1
                    completed += 1
                    if completed % 25 == 0:
                        elapsed = time.monotonic() - start_time
                        rate = completed / elapsed * 60
                        console.print(
                            f"  [dim]Progress: {completed}/{total} "
                            f"({completed/total*100:.0f}%) | "
                            f"{rate:.0f} q/min | "
                            f"{elapsed/60:.1f}m[/dim]"
                        )
            except Exception as e:
                async with lock:
                    failure_count += 1
                    completed += 1
                    msg = f"{model.value} | {prompt.id} | run={run_num} | search={search}: {e}"
                    failures_log.append(msg)
                    console.print(f"  [red]FAIL[/red] {msg[:120]}")

    console.print(f"\n[bold]Starting stability test: {total} queries...[/bold]\n")
    await asyncio.gather(*[run_one(p, m, s, r) for p, m, s, r in tasks])

    elapsed = time.monotonic() - start_time
    console.print(f"\n[bold green]Done in {elapsed/60:.1f} minutes[/bold green]")
    console.print(f"  Success: {successes}/{total}  |  Failures: {failure_count}")

    if failures_log:
        console.print("\n[red bold]Failed queries:[/red bold]")
        for msg in failures_log[:20]:
            console.print(f"  [red]•[/red] {msg[:120]}")

    return successes, failure_count, dict(model_tokens)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


async def parse_stability_results(conn) -> int:
    """Parse all unparsed stability test responses. Returns count parsed."""
    from src.response_parser import parse_batch

    # Get stability test query results
    rows = conn.execute(
        """
        SELECT id, raw_response, model_name, prompt_id, search_enabled
        FROM query_results
        WHERE is_stability_test = 1
        ORDER BY id
        """
    ).fetchall()
    query_rows = [dict(r) for r in rows]

    if not query_rows:
        console.print("[yellow]No stability test results to parse.[/yellow]")
        return 0

    # Check what's already parsed
    already = set()
    parsed_rows = conn.execute("SELECT query_result_id FROM parsed_responses").fetchall()
    already = {r[0] for r in parsed_rows}

    console.print(f"\n[bold]Parsing stability test responses...[/bold]")
    console.print(f"  Total stability results: {len(query_rows)}")
    console.print(f"  Already parsed: {len([r for r in query_rows if r['id'] in already])}")

    parsed_list, total_in, total_out = await parse_batch(
        query_rows, max_concurrent=10, already_parsed=already
    )

    # Save to DB
    saved = 0
    for parsed in parsed_list:
        try:
            insert_parsed_response(conn, parsed)
            saved += 1
        except Exception as e:
            console.print(f"  [red]DB error for qr_id={parsed.query_result_id}: {e}[/red]")

    console.print(f"[bold green]Parsed and saved: {saved} responses[/bold green]")

    # Cost estimate
    haiku_cost = (total_in / 1_000_000 * 1.0) + (total_out / 1_000_000 * 5.0)
    console.print(f"  Parsing tokens: {total_in:,} in + {total_out:,} out = ${haiku_cost:.2f}")

    return saved


# ---------------------------------------------------------------------------
# Lightweight entity resolution for stability test
# ---------------------------------------------------------------------------


def link_stability_mentions(conn) -> tuple[int, int]:
    """Link stability test restaurant mentions to canonical IDs.

    Uses exact + normalized matching against the existing canonical registry.
    New names that don't match get new canonical IDs (no fuzzy merge).

    Returns: (linked_count, new_canonical_count)
    """
    console.print("\n[bold]Linking stability mentions to canonical restaurants...[/bold]")

    # Load existing canonical registry: {normalized_name: canonical_id}
    canonical_rows = conn.execute(
        "SELECT id, canonical_name, variant_names FROM canonical_restaurants"
    ).fetchall()

    # Build lookup: normalized variant -> canonical_id
    norm_to_canonical: dict[str, int] = {}
    for row in canonical_rows:
        cid = row["id"]
        variants = json.loads(row["variant_names"])
        for v in variants:
            norm_to_canonical[normalize_name(v)] = cid
        # Also add canonical name itself
        norm_to_canonical[normalize_name(row["canonical_name"])] = cid

    # Get unlinked stability test mentions
    unlinked = conn.execute(
        """
        SELECT rm.id, rm.restaurant_name
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 1
          AND rm.canonical_id IS NULL
        """
    ).fetchall()

    if not unlinked:
        console.print("  All stability mentions already linked!")
        return 0, 0

    console.print(f"  Unlinked mentions to resolve: {len(unlinked)}")

    linked = 0
    new_names: dict[str, list[int]] = defaultdict(list)  # norm_name -> [mention_ids]

    for row in unlinked:
        mid = row["id"]
        name = row["restaurant_name"]
        norm = normalize_name(name)

        if norm in norm_to_canonical:
            # Exact/normalized match found
            conn.execute(
                "UPDATE restaurant_mentions SET canonical_id = ? WHERE id = ?",
                (norm_to_canonical[norm], mid),
            )
            linked += 1
        else:
            new_names[norm].append(mid)

    # Create new canonical entries for unmatched names
    new_count = 0
    for norm, mention_ids in new_names.items():
        # Get the most common original name for this normalized form
        names = conn.execute(
            f"SELECT restaurant_name FROM restaurant_mentions WHERE id IN ({','.join('?' for _ in mention_ids)})",
            mention_ids,
        ).fetchall()
        original_name = Counter(r["restaurant_name"] for r in names).most_common(1)[0][0]

        # Insert new canonical entry
        cursor = conn.execute(
            """
            INSERT INTO canonical_restaurants
                (canonical_name, variant_names, total_mentions, model_count, models_mentioning)
            VALUES (?, ?, ?, 0, '[]')
            """,
            (original_name, json.dumps([original_name]), len(mention_ids)),
        )
        new_cid = cursor.lastrowid

        # Link mentions
        for mid in mention_ids:
            conn.execute(
                "UPDATE restaurant_mentions SET canonical_id = ? WHERE id = ?",
                (new_cid, mid),
            )
        linked += len(mention_ids)
        new_count += 1

        # Add to lookup for future mentions
        norm_to_canonical[norm] = new_cid

    conn.commit()

    console.print(f"  Linked to existing canonicals: {linked - sum(len(v) for v in new_names.values())}")
    console.print(f"  New canonical entries created: {new_count}")
    console.print(f"  Total mentions linked: {linked}")

    # Verify no unlinked
    still_unlinked = conn.execute(
        """
        SELECT COUNT(*) FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 1 AND rm.canonical_id IS NULL
        """
    ).fetchone()[0]

    if still_unlinked > 0:
        console.print(f"  [red]WARNING: {still_unlinked} mentions still unlinked![/red]")
    else:
        console.print(f"  [green]All stability mentions resolved![/green]")

    return linked, new_count


# ---------------------------------------------------------------------------
# Summary display
# ---------------------------------------------------------------------------


def print_prompt_table(prompts: list[DiscoveryPrompt]) -> None:
    """Print the 15 selected prompts."""
    table = Table(title="Selected Prompts for Stability Test (15)")
    table.add_column("#", style="dim", width=3)
    table.add_column("ID", style="cyan", width=20)
    table.add_column("Specificity", style="magenta", width=10)
    table.add_column("Dimension", style="green", width=15)
    table.add_column("Prompt Text", max_width=70)

    for i, p in enumerate(prompts, 1):
        text = p.text[:67] + "..." if len(p.text) > 70 else p.text
        table.add_row(str(i), p.id, p.specificity.value, p.dimension.value, text)

    console.print(table)


def print_cost_estimate(estimate: dict) -> None:
    """Print the cost estimate table."""
    table = Table(title="Cost Estimate")
    table.add_column("Component", style="cyan")
    table.add_column("Queries", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Est. Cost", justify="right", style="yellow")

    for name, data in estimate["breakdown"].items():
        table.add_row(
            name,
            str(data["queries"]),
            str(data["runs"]),
            f"{data['avg_tokens']:,}",
            f"${data['cost']:.2f}",
        )

    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{estimate['total_queries']}[/bold]",
        "",
        "",
        f"[bold]${estimate['total']:.2f}[/bold]",
    )
    console.print(table)


def print_stability_report(report, prompts: list[DiscoveryPrompt]) -> None:
    """Print the full stability analysis report."""
    from src.stability_metrics import StabilityReport

    console.print("\n" + "=" * 70)
    console.print("[bold cyan]STABILITY TEST RESULTS[/bold cyan]")
    console.print("=" * 70)

    # ── 1. Per-model summary ──
    console.print(Panel("[bold]1. Per-Model Stability[/bold]", style="cyan"))
    model_table = Table()
    model_table.add_column("Model", style="cyan")
    model_table.add_column("Cells", justify="right")
    model_table.add_column("Mean Jaccard", justify="right", style="green")
    model_table.add_column("Mean Kendall τ", justify="right", style="green")

    for model in sorted(report.by_model.keys()):
        data = report.by_model[model]
        tau_str = f"{data['mean_tau']:.3f}" if data["mean_tau"] is not None else "N/A"
        model_table.add_row(
            model.split("/")[-1],
            str(data["n_cells"]),
            f"{data['mean_jaccard']:.3f}",
            tau_str,
        )
    console.print(model_table)

    # ── 2. By specificity ──
    console.print(Panel("[bold]2. Stability by Specificity Level[/bold]", style="cyan"))
    spec_table = Table()
    spec_table.add_column("Specificity", style="magenta")
    spec_table.add_column("Cells", justify="right")
    spec_table.add_column("Mean Jaccard", justify="right", style="green")
    spec_table.add_column("Mean Kendall τ", justify="right", style="green")

    for spec in ["broad", "medium", "narrow"]:
        if spec in report.by_specificity:
            data = report.by_specificity[spec]
            tau_str = f"{data['mean_tau']:.3f}" if data["mean_tau"] is not None else "N/A"
            spec_table.add_row(
                spec,
                str(data["n_cells"]),
                f"{data['mean_jaccard']:.3f}",
                tau_str,
            )
    console.print(spec_table)

    # ── 3. Search ON vs OFF ──
    console.print(Panel("[bold]3. Search ON vs OFF Stability[/bold]", style="cyan"))
    search_table = Table()
    search_table.add_column("Search Mode", style="cyan")
    search_table.add_column("Cells", justify="right")
    search_table.add_column("Mean Jaccard", justify="right", style="green")
    search_table.add_column("Mean Kendall τ", justify="right", style="green")

    for mode in ["OFF", "ON"]:
        if mode in report.by_search:
            data = report.by_search[mode]
            tau_str = f"{data['mean_tau']:.3f}" if data["mean_tau"] is not None else "N/A"
            search_table.add_row(
                f"Search {mode}",
                str(data["n_cells"]),
                f"{data['mean_jaccard']:.3f}",
                tau_str,
            )
    console.print(search_table)

    # ── 4. Core vs stochastic breakdown ──
    console.print(Panel("[bold]4. Core vs Stochastic Breakdown[/bold]", style="cyan"))
    total_core = sum(c.core_count for c in report.cells)
    total_stochastic = sum(c.stochastic_count for c in report.cells)
    total_mid = sum(c.mid_count for c in report.cells)
    total_unique = sum(c.total_unique for c in report.cells)

    console.print(f"  Across all {len(report.cells)} cells:")
    console.print(f"  Core (≥80% of runs):     [green]{total_core:,}[/green] ({total_core/max(total_unique,1)*100:.1f}%)")
    console.print(f"  Mid (40-80%):            [yellow]{total_mid:,}[/yellow] ({total_mid/max(total_unique,1)*100:.1f}%)")
    console.print(f"  Stochastic (≤40%):       [red]{total_stochastic:,}[/red] ({total_stochastic/max(total_unique,1)*100:.1f}%)")
    console.print(f"  Total unique appearances: {total_unique:,}")

    # ── 5. Side-by-side example for one prompt ──
    console.print(Panel("[bold]5. Example: Side-by-Side Restaurant Lists[/bold]", style="cyan"))
    # Pick the first cell with 5 runs for a nice visual
    example_cell = None
    for c in report.cells:
        if c.n_runs >= 5 and not c.search_enabled:
            example_cell = c
            break
    if not example_cell and report.cells:
        example_cell = report.cells[0]

    if example_cell:
        prompt_obj = next((p for p in prompts if p.id == example_cell.prompt_id), None)
        prompt_text = prompt_obj.text[:80] + "..." if prompt_obj and len(prompt_obj.text) > 80 else (prompt_obj.text if prompt_obj else "?")
        console.print(
            f"  Prompt: [cyan]{example_cell.prompt_id}[/cyan] | "
            f"Model: [cyan]{example_cell.model_name.split('/')[-1]}[/cyan] | "
            f"Search: {'ON' if example_cell.search_enabled else 'OFF'}"
        )
        console.print(f"  \"{prompt_text}\"")
        console.print(f"  Jaccard: {example_cell.mean_jaccard:.3f} | "
                      f"Core: {example_cell.core_count} | "
                      f"Stochastic: {example_cell.stochastic_count}")
        console.print()

        # Build side-by-side display
        columns = []
        for run in example_cell.runs:
            lines = [f"[bold]Run {run.run_number}[/bold]"]
            for i, name in enumerate(run.restaurant_names[:10], 1):
                lines.append(f"  {i:2d}. {name}")
            if len(run.restaurant_names) > 10:
                lines.append(f"  ... +{len(run.restaurant_names)-10}")
            columns.append("\n".join(lines))

        # Print runs side by side
        console.print(Columns(columns, padding=(0, 3), equal=True))

    # ── 6. Cost summary ──
    console.print(Panel("[bold]6. Total Cost[/bold]", style="cyan"))
    total_cost = 0.0
    for model_str, data in report.by_model.items():
        pass  # Cost already tracked in token totals

    # Compute from DB
    cost_rows = report.total_tokens
    # Rough estimate: use blended rate
    estimated_cost = cost_rows / 1000 * 0.005  # rough average across models
    console.print(f"  Total queries: {report.total_queries}")
    console.print(f"  Total tokens: {report.total_tokens:,}")
    console.print(f"  Est. query cost: ${estimated_cost:.2f}")


# ---------------------------------------------------------------------------
# Temperature documentation
# ---------------------------------------------------------------------------


def print_temperature_settings():
    """Document the temperature settings used per model."""
    console.print(Panel("[bold]Temperature Settings (identical to original sweep)[/bold]", style="cyan"))
    table = Table()
    table.add_column("Model", style="cyan")
    table.add_column("Temperature", justify="center")
    table.add_column("Max Tokens (OFF)", justify="right")
    table.add_column("Max Tokens (ON)", justify="right")
    table.add_column("System Prompt", max_width=50)

    sys_prompt = "You are a helpful restaurant recommendation assistant specializing in Singapore dining."
    for model in ModelName:
        table.add_row(
            model.value.split("/")[-1],
            "0.7",
            "2000",
            "4096",
            sys_prompt[:50],
        )
    console.print(table)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2c: Stability Test")
    parser.add_argument("--select-only", action="store_true",
                       help="Just print selected prompts and cost estimate")
    parser.add_argument("--skip-queries", action="store_true",
                       help="Skip query execution, just parse + analyze")
    parser.add_argument("--analyze-only", action="store_true",
                       help="Skip queries and parsing, just analyze existing data")
    args = parser.parse_args()

    console.print(Panel(
        "[bold yellow]Phase 2c: Recommendation Stability Test[/bold yellow]\n\n"
        "Measuring LLM recommendation reproducibility across repeated runs.\n"
        "15 prompts × 5 runs × 4 models × 2 search modes = 570 queries\n"
        "(Claude search ON: 3 runs instead of 5 to control cost)",
        title="SG Restaurant AEO Research",
        style="cyan",
    ))

    # ── Load prompts ──
    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    all_prompts = [DiscoveryPrompt(**p) for p in json.loads(prompts_path.read_text())]

    # ── Select 15 prompts ──
    selected = select_prompts(all_prompts)
    prompt_specificities = {p.id: p.specificity.value for p in all_prompts}

    print_prompt_table(selected)

    # ── Cost estimate ──
    estimate = estimate_cost(selected)
    print_cost_estimate(estimate)
    print_temperature_settings()

    if args.select_only:
        console.print("\n[yellow]--select-only mode. Exiting.[/yellow]")
        return

    # ── Init DB ──
    conn = init_db()
    insert_prompts_bulk(conn, all_prompts)

    if not args.skip_queries and not args.analyze_only:
        # ── Phase 1: Run queries ──
        existing = get_existing_stability_combos(conn)
        console.print(f"\n  Already in DB: {len(existing)} stability combos")

        tasks = build_query_tasks(selected, existing)
        console.print(f"  Tasks to run: [bold]{len(tasks)}[/bold]")

        if tasks:
            successes, failures, model_tokens = await run_stability_queries(tasks, conn)

            # Print actual cost
            console.print("\n[bold]Actual token usage:[/bold]")
            for model_str, tokens in sorted(model_tokens.items()):
                rate = 0.005  # default
                for m in ModelName:
                    if m.value == model_str:
                        rate = COST_PER_1K.get(m, 0.005)
                        break
                console.print(f"  {model_str}: {tokens:,} tokens (${tokens/1000*rate:.2f})")
        else:
            console.print("[yellow]All stability queries already in DB.[/yellow]")

    if not args.analyze_only:
        # ── Phase 2: Parse ──
        parsed_count = await parse_stability_results(conn)

        # ── Phase 3: Entity resolution ──
        linked, new_canonicals = link_stability_mentions(conn)

    # ── Phase 4: Compute metrics ──
    from src.stability_metrics import compute_all_metrics

    console.print("\n[bold]Computing stability metrics...[/bold]")
    report = compute_all_metrics(conn, prompt_specificities)

    print_stability_report(report, selected)

    conn.close()
    console.print("\n[bold green]Phase 2c complete![/bold green]\n")


if __name__ == "__main__":
    asyncio.run(main())
