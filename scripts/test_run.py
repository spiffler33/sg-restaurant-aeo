"""Test run: 5 prompts × 4 models × search OFF = 20 queries.

Picks a diverse set of prompts, runs them against all models,
saves results to SQLite + data/raw/, and prints raw responses.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path so we can import src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.db import init_db, insert_prompt, insert_query_result
from src.models import DiscoveryPrompt, ModelName
from src.query_runner import query_model, run_sweep

console = Console()

# The 5 test prompts — one per dimension, mixed specificity
TEST_PROMPT_IDS = [
    "cuisine_001",        # cuisine / broad
    "occasion_015",       # occasion / narrow (Duxton Hill date night)
    "price_002",          # price / broad
    "neighbourhood_009",  # neighbourhood / medium (Joo Chiat)
    "vibe_007",           # vibe / medium (speakeasy)
]


async def main() -> None:
    # Load prompts
    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    all_prompts = [DiscoveryPrompt(**p) for p in json.loads(prompts_path.read_text())]
    prompt_lookup = {p.id: p for p in all_prompts}

    test_prompts = []
    for pid in TEST_PROMPT_IDS:
        if pid not in prompt_lookup:
            console.print(f"[red]Prompt {pid} not found![/red]")
            return
        test_prompts.append(prompt_lookup[pid])

    console.print(f"\n[bold]Test run: {len(test_prompts)} prompts × 4 models × search OFF[/bold]\n")
    for p in test_prompts:
        console.print(f"  {p.id:25s} [{p.dimension.value}/{p.specificity.value}]  {p.text[:60]}...")

    # Init DB and insert prompts
    conn = init_db()
    for p in test_prompts:
        insert_prompt(conn, p)

    # Run sweep — search OFF only
    results = await run_sweep(
        prompts=test_prompts,
        models=list(ModelName),
        search_modes=[False],
        max_concurrent=4,
    )

    # Save to DB
    for result in results:
        insert_query_result(conn, result)

    console.print(f"[bold green]Saved {len(results)} results to SQLite + data/raw/[/bold green]\n")

    # ── Print all raw responses grouped by prompt ──
    for prompt in test_prompts:
        console.print(Panel(
            f"[bold]{prompt.id}[/bold] [{prompt.dimension.value}/{prompt.specificity.value}]\n{prompt.text}",
            title="PROMPT",
            style="cyan",
        ))
        prompt_results = [r for r in results if r.prompt_id == prompt.id]
        for r in sorted(prompt_results, key=lambda x: x.model_name.value):
            console.print(Panel(
                r.raw_response[:3000] + ("..." if len(r.raw_response) > 3000 else ""),
                title=f"{r.model_name.value}  |  {r.latency_ms}ms  |  {r.token_usage or '?'} tokens",
                style="green" if r.raw_response else "red",
                width=100,
            ))
        console.print()

    # ── Quick restaurant name count (naive extraction) ──
    console.print(Panel("[bold]Naive restaurant name count[/bold]", style="yellow"))
    all_names: set[str] = set()
    for r in results:
        # Simple heuristic: lines that look like restaurant names
        # (lines starting with a number, bold markers, or capitalized short phrases)
        for line in r.raw_response.split("\n"):
            line = line.strip()
            # Match patterns like "1. Restaurant Name", "**Restaurant Name**", "- Restaurant Name"
            import re
            # Numbered list items
            m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*[\-–—:]', line)
            if not m:
                m = re.match(r'^\d+[\.\)]\s*\**(.+?)\**\s*$', line)
            if not m:
                # Bold markers
                m = re.match(r'^[\-\*]+\s*\**(.+?)\**\s*[\-–—:]', line)
            if m:
                name = m.group(1).strip().strip('*').strip()
                # Filter out generic phrases
                if len(name) > 2 and len(name) < 80 and not name.lower().startswith(('the best', 'here are', 'for a', 'if you', 'this is')):
                    all_names.add(name)

    console.print(f"  Unique restaurant names (naive regex): [bold]{len(all_names)}[/bold]")
    # Show a sample
    sorted_names = sorted(all_names)
    for name in sorted_names[:30]:
        console.print(f"    • {name}")
    if len(sorted_names) > 30:
        console.print(f"    ... and {len(sorted_names) - 30} more")

    # ── Summary table ──
    console.print()
    table = Table(title="Test Run Summary")
    table.add_column("Model", style="cyan")
    table.add_column("Queries", justify="right")
    table.add_column("Avg Latency (ms)", justify="right")
    table.add_column("Avg Tokens", justify="right")
    table.add_column("Errors", justify="right", style="red")

    for model in ModelName:
        model_results = [r for r in results if r.model_name == model]
        errors = 5 - len(model_results)  # 5 prompts per model
        avg_lat = int(sum(r.latency_ms or 0 for r in model_results) / max(len(model_results), 1))
        avg_tok = int(sum(r.token_usage or 0 for r in model_results) / max(len(model_results), 1))
        table.add_row(
            model.value,
            str(len(model_results)),
            str(avg_lat),
            str(avg_tok) if avg_tok > 0 else "N/A",
            str(errors) if errors > 0 else "0",
        )

    console.print(table)
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
