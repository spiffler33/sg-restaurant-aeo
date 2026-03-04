"""Rerun just Gemini queries that failed due to missing SDK."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel

from src.db import init_db, insert_query_result
from src.models import DiscoveryPrompt, ModelName
from src.query_runner import query_model

console = Console()

TEST_PROMPT_IDS = [
    "cuisine_001",
    "occasion_015",
    "price_002",
    "neighbourhood_009",
    "vibe_007",
]


async def main() -> None:
    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    all_prompts = [DiscoveryPrompt(**p) for p in json.loads(prompts_path.read_text())]
    prompt_lookup = {p.id: p for p in all_prompts}
    test_prompts = [prompt_lookup[pid] for pid in TEST_PROMPT_IDS]

    conn = init_db()
    model = ModelName.GEMINI_PRO

    console.print(f"\n[bold]Rerunning Gemini for {len(test_prompts)} prompts...[/bold]\n")

    for prompt in test_prompts:
        try:
            result = await query_model(prompt, model, search_enabled=False)
            insert_query_result(conn, result)
            console.print(Panel(
                result.raw_response[:3000],
                title=f"{model.value} | {prompt.id} | {result.latency_ms}ms | {result.token_usage or '?'} tokens",
                style="green",
                width=100,
            ))
        except Exception as e:
            console.print(f"[red]FAILED[/red] {prompt.id}: {e}")
            import traceback
            traceback.print_exc()

    conn.close()
    console.print("[bold green]Done.[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
