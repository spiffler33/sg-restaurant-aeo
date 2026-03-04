"""Search ON sweep: 140 prompts × 4 models × search ON = 560 queries.

Runs all discovery prompts against all models with web search/grounding ENABLED.
This is the second half of Phase 1c data collection. The first half (search OFF,
560 queries) is already in the database.

Per-model search behavior:
    - GPT-4o: web_search_preview tool (model autonomously searches when helpful)
    - Claude Sonnet: web_search_20250305 server-side tool (Claude searches the web)
    - Gemini 2.5 Flash: google_search grounding tool (responses grounded via Google)
    - Perplexity Sonar: ALWAYS search-augmented (no "off" mode); we add
      search_recency_filter="month" for this run to see if temporal freshness
      shifts recommendations. Both runs are effectively "search on" for Perplexity.

Usage:
    python scripts/search_on_sweep.py
"""

import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.db import init_db, insert_prompt, insert_prompts_bulk, insert_query_result
from src.models import DiscoveryPrompt, ModelName, QueryResult
from src.query_runner import query_model

console = Console()

# Per-provider concurrency limits
# Perplexity at 2 — we hit 429s at 5 during the search OFF sweep
PROVIDER_CONCURRENCY = {
    ModelName.GPT_4O: 4,
    ModelName.CLAUDE_SONNET: 4,
    ModelName.GEMINI_PRO: 3,
    ModelName.PERPLEXITY_SONAR: 2,  # Reduced from 5 — rate limit safe
}

# Approximate cost per 1K tokens (blended input+output)
# Search-enabled queries may use more tokens due to citations/grounding
COST_PER_1K_TOKENS = {
    ModelName.GPT_4O: 0.006,
    ModelName.CLAUDE_SONNET: 0.009,
    ModelName.GEMINI_PRO: 0.0004,
    ModelName.PERPLEXITY_SONAR: 0.001,
}


def get_existing_search_on_combos(conn) -> set[tuple[str, str]]:
    """Return set of (prompt_id, model_name) already in DB for search_enabled=True."""
    rows = conn.execute(
        "SELECT DISTINCT prompt_id, model_name FROM query_results WHERE search_enabled = 1"
    ).fetchall()
    return {(r["prompt_id"], r["model_name"]) for r in rows}


def extract_restaurant_names(text: str) -> list[str]:
    """Naive regex extraction of restaurant names from LLM response text.

    Same logic as full_sweep.py for consistency across sweeps.
    """
    names = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*[\-–—:\(]', line)
        if not m:
            m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*$', line)
        if not m:
            m = re.match(r'^[\-\*]+\s*\**(.+?)\**\s*[\-–—:\(]', line)
        if not m:
            m = re.match(r'^[\-\*]+\s*\**(.+?)\**\s*$', line)
        if m:
            name = m.group(1).strip().strip('*').strip()
            if (
                2 < len(name) < 80
                and not name.lower().startswith((
                    'the best', 'here are', 'for a', 'if you', 'this is',
                    'note', 'keep in', 'i recommend', 'you can', 'these',
                    'some', 'while', 'remember', 'disclaimer', 'important',
                    'pro tip', 'tip:', 'also', 'bonus',
                ))
            ):
                names.append(name)
    return names


async def main() -> None:
    start_time = time.monotonic()

    # ── Load prompts ──
    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    all_prompts = [DiscoveryPrompt(**p) for p in json.loads(prompts_path.read_text())]
    prompt_lookup = {p.id: p for p in all_prompts}

    console.print(Panel(
        "[bold yellow]Search ON Sweep[/bold yellow]\n"
        f"140 prompts × 4 models × search ON = 560 queries\n\n"
        f"[dim]GPT-4o: web_search_preview tool[/dim]\n"
        f"[dim]Claude: web_search_20250305 server tool[/dim]\n"
        f"[dim]Gemini: google_search grounding[/dim]\n"
        f"[dim]Perplexity: always search + recency_filter=month[/dim]",
        title="Phase 1c — Second Half",
        style="cyan",
    ))

    # ── Init DB + ensure prompts exist ──
    conn = init_db()
    insert_prompts_bulk(conn, all_prompts)

    # ── Check what's already done ──
    existing = get_existing_search_on_combos(conn)
    console.print(f"  Already in DB (search ON): {len(existing)} prompt/model combos")

    # ── Build task list, skipping existing ──
    models = list(ModelName)
    tasks: list[tuple[DiscoveryPrompt, ModelName]] = []
    for prompt in all_prompts:
        for model in models:
            if (prompt.id, model.value) not in existing:
                tasks.append((prompt, model))

    total = len(tasks)
    skipped = len(all_prompts) * len(models) - total
    console.print(f"  Skipping: {skipped} (already completed)")
    console.print(f"  To run: [bold]{total}[/bold] queries\n")

    if total == 0:
        console.print("[yellow]Nothing to do — all search ON queries already in DB.[/yellow]")
        # Still run the post-analysis
    else:
        # ── Per-provider semaphores ──
        provider_semas = {
            model: asyncio.Semaphore(limit)
            for model, limit in PROVIDER_CONCURRENCY.items()
        }

        # ── Tracking state ──
        completed = 0
        successes: dict[ModelName, int] = defaultdict(int)
        failures: dict[ModelName, list[str]] = defaultdict(list)
        new_results: list[QueryResult] = []
        lock = asyncio.Lock()

        async def run_one(prompt: DiscoveryPrompt, model: ModelName) -> None:
            nonlocal completed
            sema = provider_semas[model]
            async with sema:
                try:
                    result = await query_model(prompt, model, search_enabled=True)
                    async with lock:
                        insert_query_result(conn, result)
                        new_results.append(result)
                        successes[model] += 1
                        completed += 1
                        if completed % 20 == 0:
                            elapsed = time.monotonic() - start_time
                            rate = completed / elapsed * 60
                            # Per-model progress
                            model_progress = "  ".join(
                                f"{m.value.split('/')[1][:6]}={successes.get(m, 0)}"
                                for m in models
                            )
                            console.print(
                                f"  [dim]Progress: {completed}/{total} done "
                                f"({completed/total*100:.0f}%) | "
                                f"{rate:.0f} q/min | "
                                f"{elapsed/60:.1f}m | "
                                f"{model_progress}[/dim]"
                            )
                except Exception as e:
                    async with lock:
                        failures[model].append(f"{prompt.id}: {e}")
                        completed += 1
                        console.print(
                            f"  [red]FAIL[/red] {model.value} | {prompt.id}: "
                            f"{type(e).__name__}: {str(e)[:120]}"
                        )

        # ── Launch all tasks ──
        console.print("[bold]Starting search ON sweep...[/bold]\n")
        await asyncio.gather(*[run_one(p, m) for p, m in tasks])

        elapsed_total = time.monotonic() - start_time
        console.print(
            f"\n[bold green]Sweep complete in {elapsed_total/60:.1f} minutes[/bold green]\n"
        )

        # Print failure summary if any
        if any(failures.values()):
            console.print("[red bold]Failed queries:[/red bold]")
            for model, errs in failures.items():
                for err in errs:
                    console.print(f"  [red]•[/red] {model.value} | {err[:120]}")
            console.print()

    # =====================================================================
    # POST-RUN ANALYSIS (includes all search ON data, not just this run)
    # =====================================================================
    from src.db import get_query_results

    all_search_on = [r for r in get_query_results(conn) if r.search_enabled]
    all_search_off = [r for r in get_query_results(conn) if not r.search_enabled]

    elapsed_total = time.monotonic() - start_time

    # ── 1. Success count per model (search ON) ──
    console.print(Panel("[bold]1. Search ON — Results per Model[/bold]", style="cyan"))
    table = Table()
    table.add_column("Model", style="cyan")
    table.add_column("Total in DB", justify="right", style="green")
    table.add_column("Avg Latency (ms)", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Avg Tokens (OFF)", justify="right", style="dim")
    table.add_column("Δ Tokens", justify="right", style="yellow")

    for model in models:
        on_results = [r for r in all_search_on if r.model_name == model]
        off_results = [r for r in all_search_off if r.model_name == model]
        avg_lat = int(sum(r.latency_ms or 0 for r in on_results) / max(len(on_results), 1))
        avg_tok_on = int(sum(r.token_usage or 0 for r in on_results) / max(len(on_results), 1))
        avg_tok_off = int(sum(r.token_usage or 0 for r in off_results) / max(len(off_results), 1))
        delta = avg_tok_on - avg_tok_off if avg_tok_on > 0 and avg_tok_off > 0 else 0
        delta_str = f"+{delta}" if delta > 0 else str(delta)
        table.add_row(
            model.value,
            str(len(on_results)),
            str(avg_lat),
            str(avg_tok_on) if avg_tok_on > 0 else "N/A",
            str(avg_tok_off) if avg_tok_off > 0 else "N/A",
            delta_str if delta != 0 else "—",
        )
    console.print(table)

    # ── 2. Cost estimate (search ON only) ──
    console.print(Panel("[bold]2. Cost Estimate — Search ON[/bold]", style="cyan"))
    total_cost_on = 0.0
    total_cost_off = 0.0
    cost_table = Table()
    cost_table.add_column("Model", style="cyan")
    cost_table.add_column("Tokens (ON)", justify="right")
    cost_table.add_column("Cost (ON)", justify="right", style="yellow")
    cost_table.add_column("Cost (OFF)", justify="right", style="dim")
    cost_table.add_column("Δ Cost", justify="right", style="yellow")

    for model in models:
        on_results = [r for r in all_search_on if r.model_name == model]
        off_results = [r for r in all_search_off if r.model_name == model]
        tokens_on = sum(r.token_usage or 0 for r in on_results)
        tokens_off = sum(r.token_usage or 0 for r in off_results)
        rate = COST_PER_1K_TOKENS.get(model, 0.005)
        cost_on = tokens_on / 1000 * rate
        cost_off = tokens_off / 1000 * rate
        total_cost_on += cost_on
        total_cost_off += cost_off
        delta_cost = cost_on - cost_off
        cost_table.add_row(
            model.value,
            f"{tokens_on:,}",
            f"${cost_on:.2f}",
            f"${cost_off:.2f}",
            f"+${delta_cost:.2f}" if delta_cost > 0 else f"${delta_cost:.2f}",
        )
    cost_table.add_row(
        "[bold]TOTAL[/bold]", "", f"[bold]${total_cost_on:.2f}[/bold]",
        f"${total_cost_off:.2f}",
        f"+${total_cost_on - total_cost_off:.2f}" if total_cost_on > total_cost_off else f"${total_cost_on - total_cost_off:.2f}",
    )
    console.print(cost_table)

    # ── 3. Restaurant mentions comparison: Search ON vs OFF ──
    console.print(Panel(
        "[bold]3. Restaurant Mentions — Search ON vs Search OFF[/bold]",
        style="cyan",
    ))

    mentions_on: list[str] = []
    mentions_off: list[str] = []
    for r in all_search_on:
        mentions_on.extend(extract_restaurant_names(r.raw_response))
    for r in all_search_off:
        mentions_off.extend(extract_restaurant_names(r.raw_response))

    unique_on = set(mentions_on)
    unique_off = set(mentions_off)
    only_in_on = unique_on - unique_off
    only_in_off = unique_off - unique_on
    in_both = unique_on & unique_off

    comp_table = Table()
    comp_table.add_column("Metric", style="cyan")
    comp_table.add_column("Search OFF", justify="right", style="dim")
    comp_table.add_column("Search ON", justify="right", style="green")
    comp_table.add_column("Delta", justify="right", style="yellow")
    comp_table.add_row(
        "Total mentions (with dupes)",
        f"{len(mentions_off):,}",
        f"{len(mentions_on):,}",
        f"{len(mentions_on) - len(mentions_off):+,}",
    )
    comp_table.add_row(
        "Unique restaurant names",
        f"{len(unique_off):,}",
        f"{len(unique_on):,}",
        f"{len(unique_on) - len(unique_off):+,}",
    )
    comp_table.add_row("In both ON & OFF", "", "", f"{len(in_both):,}")
    comp_table.add_row("Only in Search ON", "", "", f"{len(only_in_on):,}")
    comp_table.add_row("Only in Search OFF", "", "", f"{len(only_in_off):,}")
    console.print(comp_table)

    # Combined unique
    all_unique = unique_on | unique_off
    console.print(
        f"\n  [bold]Combined unique restaurant names (both sweeps): {len(all_unique):,}[/bold]"
    )

    # ── 4. Top 10 most-mentioned (search ON) ──
    console.print(Panel("[bold]4. Top 10 Most-Mentioned Restaurants (Search ON)[/bold]", style="cyan"))
    name_counts_on = Counter(mentions_on)
    name_counts_off = Counter(mentions_off)
    top_table = Table()
    top_table.add_column("Rank", justify="right", style="dim")
    top_table.add_column("Restaurant Name", style="bold")
    top_table.add_column("Mentions (ON)", justify="right", style="green")
    top_table.add_column("Mentions (OFF)", justify="right", style="dim")
    top_table.add_column("Delta", justify="right", style="yellow")

    for i, (name, count) in enumerate(name_counts_on.most_common(10), 1):
        off_count = name_counts_off.get(name, 0)
        top_table.add_row(
            str(i), name, str(count), str(off_count),
            f"{count - off_count:+d}",
        )
    console.print(top_table)

    # ── 5. Top movers — restaurants that appeared much more with search ON ──
    console.print(Panel("[bold]5. Top Movers — Biggest Gains with Search ON[/bold]", style="cyan"))
    all_names = set(name_counts_on.keys()) | set(name_counts_off.keys())
    deltas = [
        (name, name_counts_on.get(name, 0) - name_counts_off.get(name, 0))
        for name in all_names
    ]
    deltas.sort(key=lambda x: x[1], reverse=True)

    mover_table = Table()
    mover_table.add_column("Restaurant", style="bold")
    mover_table.add_column("OFF", justify="right", style="dim")
    mover_table.add_column("ON", justify="right", style="green")
    mover_table.add_column("Δ", justify="right", style="yellow")

    for name, delta in deltas[:10]:
        mover_table.add_row(
            name,
            str(name_counts_off.get(name, 0)),
            str(name_counts_on.get(name, 0)),
            f"+{delta}" if delta > 0 else str(delta),
        )
    console.print(mover_table)

    # ── 6. Perplexity caveat ──
    console.print(Panel(
        "[yellow]Perplexity Caveat:[/yellow] Sonar is inherently search-augmented.\n"
        "The 'Search OFF' run was already effectively search-enabled.\n"
        "The 'Search ON' run adds search_recency_filter='month'.\n"
        "The delta for Perplexity reflects recency filtering, not search toggling.\n"
        "This asymmetry is itself a research finding worth documenting.",
        title="Research Note",
        style="yellow",
    ))

    conn.close()

    # ── Final summary ──
    console.print(f"\n[bold]Total elapsed time: {elapsed_total/60:.1f} minutes[/bold]")
    console.print(f"[bold]Total queries in DB: {len(all_search_on) + len(all_search_off)} "
                  f"(OFF={len(all_search_off)}, ON={len(all_search_on)})[/bold]")
    console.print(f"[bold]Search ON cost: ${total_cost_on:.2f} | "
                  f"Search OFF cost: ${total_cost_off:.2f} | "
                  f"Combined: ${total_cost_on + total_cost_off:.2f}[/bold]\n")


if __name__ == "__main__":
    asyncio.run(main())
