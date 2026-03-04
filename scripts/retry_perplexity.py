"""Retry failed Perplexity queries with lower concurrency (2 at a time).

Finds prompt_ids that are missing Perplexity results (search=OFF) and retries them.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from src.db import init_db, insert_prompt, insert_query_result
from src.models import DiscoveryPrompt, ModelName
from src.query_runner import query_model

console = Console()


async def main() -> None:
    # Load all prompts
    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    all_prompts = [DiscoveryPrompt(**p) for p in json.loads(prompts_path.read_text())]
    prompt_lookup = {p.id: p for p in all_prompts}

    # Find missing Perplexity results
    conn = init_db()
    existing = conn.execute(
        "SELECT DISTINCT prompt_id FROM query_results WHERE model_name = ? AND search_enabled = 0",
        (ModelName.PERPLEXITY_SONAR.value,),
    ).fetchall()
    existing_ids = {r["prompt_id"] for r in existing}

    missing = [p for p in all_prompts if p.id not in existing_ids]
    console.print(f"\n[bold]Perplexity retry: {len(missing)} missing queries[/bold]\n")

    if not missing:
        console.print("[green]All Perplexity queries already complete![/green]")
        conn.close()
        return

    # Use very low concurrency to avoid rate limiting
    semaphore = asyncio.Semaphore(2)
    success = 0
    failed = 0

    async def run_one(prompt: DiscoveryPrompt) -> None:
        nonlocal success, failed
        async with semaphore:
            try:
                result = await query_model(prompt, ModelName.PERPLEXITY_SONAR, search_enabled=False)
                insert_query_result(conn, result)
                success += 1
                console.print(f"  [green]OK[/green] {prompt.id} ({success + failed}/{len(missing)})")
            except Exception as e:
                failed += 1
                console.print(f"  [red]FAIL[/red] {prompt.id}: {e}")

    await asyncio.gather(*[run_one(p) for p in missing])

    console.print(f"\n[bold]Done: {success} success, {failed} failed[/bold]")

    total = conn.execute(
        "SELECT COUNT(*) FROM query_results WHERE model_name = ? AND search_enabled = 0",
        (ModelName.PERPLEXITY_SONAR.value,),
    ).fetchone()[0]
    console.print(f"[bold]Total Perplexity results in DB: {total}/140[/bold]\n")
    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
