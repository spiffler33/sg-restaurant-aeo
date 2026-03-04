"""Full sweep: 140 prompts × 4 models × search OFF = 560 queries.

Runs all discovery prompts against all models with search disabled.
Uses per-provider concurrency limits to avoid rate limiting.
Skips prompt/model combos that already exist in the database.

Usage:
    python scripts/full_sweep.py
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
PROVIDER_CONCURRENCY = {
    ModelName.GPT_4O: 4,
    ModelName.CLAUDE_SONNET: 4,
    ModelName.GEMINI_PRO: 3,       # Gemini is slower, be gentler
    ModelName.PERPLEXITY_SONAR: 5,  # Fastest provider
}

# Approximate cost per 1K tokens (combined input+output estimate)
# These are rough blended rates for cost estimation
COST_PER_1K_TOKENS = {
    ModelName.GPT_4O: 0.006,            # ~$2.50/1M in + $10/1M out, blended
    ModelName.CLAUDE_SONNET: 0.009,     # ~$3/1M in + $15/1M out, blended
    ModelName.GEMINI_PRO: 0.0004,       # Very cheap (Flash tier)
    ModelName.PERPLEXITY_SONAR: 0.001,  # ~$1/1M tokens
}


def get_existing_combos(conn) -> set[tuple[str, str]]:
    """Return set of (prompt_id, model_name) already in the DB for search=False."""
    rows = conn.execute(
        "SELECT DISTINCT prompt_id, model_name FROM query_results WHERE search_enabled = 0"
    ).fetchall()
    return {(r["prompt_id"], r["model_name"]) for r in rows}


def extract_restaurant_names(text: str) -> list[str]:
    """Naive regex extraction of restaurant names from LLM response text.

    Handles common patterns:
    - Numbered lists: "1. **Restaurant Name** -"
    - Bold items: "**Restaurant Name**"
    - Dash lists: "- Restaurant Name:"
    - Section headers with ### are excluded
    """
    names = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        # Pattern: numbered list "1. **Name**" or "1. Name -"
        m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*[\-–—:\(]', line)
        if not m:
            m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*$', line)
        if not m:
            # Pattern: bullet list "- **Name**" or "* **Name**"
            m = re.match(r'^[\-\*]+\s*\**(.+?)\**\s*[\-–—:\(]', line)
        if not m:
            m = re.match(r'^[\-\*]+\s*\**(.+?)\**\s*$', line)
        if m:
            name = m.group(1).strip().strip('*').strip()
            # Filter out generic phrases and too-short/long strings
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

    console.print(f"\n[bold]Full sweep: {len(all_prompts)} prompts × 4 models × search OFF[/bold]")

    # ── Init DB + insert all prompts ──
    conn = init_db()
    insert_prompts_bulk(conn, all_prompts)

    # ── Check what's already done ──
    existing = get_existing_combos(conn)
    console.print(f"  Already in DB: {len(existing)} prompt/model combos")

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
        console.print("[yellow]Nothing to do — all queries already in DB.[/yellow]")
        conn.close()
        return

    # ── Per-provider semaphores ──
    provider_semas = {model: asyncio.Semaphore(limit) for model, limit in PROVIDER_CONCURRENCY.items()}

    # ── Tracking state ──
    completed = 0
    successes: dict[ModelName, int] = defaultdict(int)
    failures: dict[ModelName, list[str]] = defaultdict(list)
    all_results: list[QueryResult] = []
    lock = asyncio.Lock()

    async def run_one(prompt: DiscoveryPrompt, model: ModelName) -> None:
        nonlocal completed
        sema = provider_semas[model]
        async with sema:
            try:
                result = await query_model(prompt, model, search_enabled=False)
                # Save to DB immediately (thread-safe with lock)
                async with lock:
                    insert_query_result(conn, result)
                    all_results.append(result)
                    successes[model] += 1
                    completed += 1
                    # Progress summary every 20 queries
                    if completed % 20 == 0:
                        elapsed = time.monotonic() - start_time
                        rate = completed / elapsed * 60
                        console.print(
                            f"  [dim]Progress: {completed}/{total} done "
                            f"({completed/total*100:.0f}%) | "
                            f"{rate:.0f} queries/min | "
                            f"elapsed {elapsed/60:.1f}m[/dim]"
                        )
            except Exception as e:
                async with lock:
                    failures[model].append(f"{prompt.id}: {e}")
                    completed += 1
                    console.print(
                        f"  [red]FAIL[/red] {model.value} | {prompt.id}: {type(e).__name__}: {e}"
                    )

    # ── Launch all tasks ──
    console.print("[bold]Starting sweep...[/bold]\n")
    await asyncio.gather(*[run_one(p, m) for p, m in tasks])

    elapsed_total = time.monotonic() - start_time
    console.print(f"\n[bold green]Sweep complete in {elapsed_total/60:.1f} minutes[/bold green]\n")

    # Also load the pre-existing results for analysis
    from src.db import get_query_results
    all_db_results = get_query_results(conn)
    # Filter to search_enabled=False only
    all_db_results = [r for r in all_db_results if not r.search_enabled]

    conn.close()

    # =====================================================================
    # POST-RUN ANALYSIS
    # =====================================================================

    # ── 1. Success/failure count per model ──
    console.print(Panel("[bold]1. Success / Failure Count per Model[/bold]", style="cyan"))
    table = Table()
    table.add_column("Model", style="cyan")
    table.add_column("Success (this run)", justify="right", style="green")
    table.add_column("Failed (this run)", justify="right", style="red")
    table.add_column("Total in DB", justify="right")
    table.add_column("Avg Latency (ms)", justify="right")
    table.add_column("Avg Tokens", justify="right")

    for model in models:
        model_results = [r for r in all_db_results if r.model_name == model]
        avg_lat = int(sum(r.latency_ms or 0 for r in model_results) / max(len(model_results), 1))
        avg_tok = int(sum(r.token_usage or 0 for r in model_results) / max(len(model_results), 1))
        table.add_row(
            model.value,
            str(successes.get(model, 0)),
            str(len(failures.get(model, []))),
            str(len(model_results)),
            str(avg_lat),
            str(avg_tok) if avg_tok > 0 else "N/A",
        )
    console.print(table)

    if any(failures.values()):
        console.print("\n[red bold]Failed queries:[/red bold]")
        for model, errs in failures.items():
            for err in errs:
                console.print(f"  [red]•[/red] {model.value} | {err[:120]}")
        console.print()

    # ── 2. Total cost estimate ──
    console.print(Panel("[bold]2. Cost Estimate from Token Usage[/bold]", style="cyan"))
    total_cost = 0.0
    cost_table = Table()
    cost_table.add_column("Model", style="cyan")
    cost_table.add_column("Total Tokens", justify="right")
    cost_table.add_column("Rate ($/1K)", justify="right")
    cost_table.add_column("Est. Cost", justify="right", style="yellow")

    for model in models:
        model_results = [r for r in all_db_results if r.model_name == model]
        total_tokens = sum(r.token_usage or 0 for r in model_results)
        rate = COST_PER_1K_TOKENS.get(model, 0.005)
        cost = total_tokens / 1000 * rate
        total_cost += cost
        cost_table.add_row(
            model.value,
            f"{total_tokens:,}",
            f"${rate:.4f}",
            f"${cost:.2f}",
        )
    cost_table.add_row("[bold]TOTAL[/bold]", "", "", f"[bold]${total_cost:.2f}[/bold]")
    console.print(cost_table)

    # ── 3. Total unique restaurant names (naive) ──
    console.print(Panel("[bold]3. Unique Restaurant Names (naive regex)[/bold]", style="cyan"))
    all_mentions: list[str] = []
    response_mention_counts: dict[str, int] = {}  # prompt_id -> avg mention count

    for r in all_db_results:
        names = extract_restaurant_names(r.raw_response)
        all_mentions.extend(names)
        key = r.prompt_id
        if key not in response_mention_counts:
            response_mention_counts[key] = 0
        response_mention_counts[key] += len(names)

    unique_names = set(all_mentions)
    console.print(f"  Total mentions (with duplicates): [bold]{len(all_mentions):,}[/bold]")
    console.print(f"  Unique restaurant names:          [bold]{len(unique_names):,}[/bold]")

    # ── 4. Top 10 most-mentioned restaurant names ──
    console.print(Panel("[bold]4. Top 10 Most-Mentioned Restaurants[/bold]", style="cyan"))
    name_counts = Counter(all_mentions)
    top_table = Table()
    top_table.add_column("Rank", justify="right", style="dim")
    top_table.add_column("Restaurant Name", style="bold")
    top_table.add_column("Mentions", justify="right", style="green")

    for i, (name, count) in enumerate(name_counts.most_common(10), 1):
        top_table.add_row(str(i), name, str(count))
    console.print(top_table)

    # ── 5. Prompt with most restaurant mentions on average ──
    console.print(Panel("[bold]5. Prompt with Most Mentions (avg across models)[/bold]", style="cyan"))

    # Count per-prompt, averaging across the 4 models
    prompt_avg_mentions: list[tuple[str, float]] = []
    for prompt_id, total_mentions in response_mention_counts.items():
        model_count = len([r for r in all_db_results if r.prompt_id == prompt_id])
        avg = total_mentions / max(model_count, 1)
        prompt_avg_mentions.append((prompt_id, avg))

    prompt_avg_mentions.sort(key=lambda x: x[1], reverse=True)

    mention_table = Table()
    mention_table.add_column("Rank", justify="right", style="dim")
    mention_table.add_column("Prompt ID", style="cyan")
    mention_table.add_column("Dimension", style="magenta")
    mention_table.add_column("Avg Mentions/Model", justify="right", style="green")
    mention_table.add_column("Prompt Text (truncated)")

    for i, (pid, avg) in enumerate(prompt_avg_mentions[:10], 1):
        prompt = prompt_lookup.get(pid)
        dim = prompt.dimension.value if prompt else "?"
        text = (prompt.text[:60] + "...") if prompt and len(prompt.text) > 60 else (prompt.text if prompt else "?")
        mention_table.add_row(str(i), pid, dim, f"{avg:.1f}", text)

    console.print(mention_table)

    # ── Final summary ──
    console.print(f"\n[bold]Total elapsed time: {elapsed_total/60:.1f} minutes[/bold]")
    console.print(f"[bold]Total queries in DB (search=OFF): {len(all_db_results)}[/bold]")
    console.print(f"[bold]Estimated total cost: ${total_cost:.2f}[/bold]\n")


if __name__ == "__main__":
    asyncio.run(main())
