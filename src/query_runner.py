"""Multi-model async query runner for SG Restaurant AEO.

Queries multiple LLM APIs with discovery prompts and stores raw responses.
Uses native API clients (no LiteLLM) with retry logic and rich progress display.

Supported models:
    - openai/gpt-4o
    - anthropic/claude-sonnet-4-20250514
    - google/gemini-1.5-pro
    - perplexity/sonar

Usage:
    python -m src.query_runner
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import DiscoveryPrompt, ModelName, QueryResult

load_dotenv()

console = Console()

# Raw response storage
RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def _save_raw_response(result: QueryResult) -> Path:
    """Save a raw API response to data/raw/ as JSON for archival."""
    filename = f"{result.prompt_id}__{result.model_name.value.replace('/', '_')}__{result.timestamp.strftime('%Y%m%d_%H%M%S')}.json"
    path = RAW_DIR / filename
    path.write_text(
        json.dumps(
            {
                "prompt_id": result.prompt_id,
                "model_name": result.model_name.value,
                "search_enabled": result.search_enabled,
                "raw_response": result.raw_response,
                "timestamp": result.timestamp.isoformat(),
                "latency_ms": result.latency_ms,
                "token_usage": result.token_usage,
            },
            indent=2,
        )
    )
    return path


# ---------------------------------------------------------------------------
# Model-specific query functions
# ---------------------------------------------------------------------------


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
async def _query_openai(prompt: str, search_enabled: bool = False) -> tuple[str, Optional[int]]:
    """Query OpenAI GPT-4o. Returns (response_text, token_usage).

    When search_enabled=True, uses the Responses API (not Chat Completions)
    because web_search_preview is only supported there. When search is off,
    uses the standard Chat Completions API for backward compatibility.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if search_enabled:
        # Responses API — required for web_search_preview tool
        response = await client.responses.create(
            model="gpt-4o",
            tools=[{"type": "web_search_preview"}],
            input=[
                {"role": "system", "content": "You are a helpful restaurant recommendation assistant specializing in Singapore dining."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_output_tokens=4096,
        )
        text = response.output_text or ""
        usage = response.usage.total_tokens if response.usage else None
    else:
        # Standard Chat Completions API
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful restaurant recommendation assistant specializing in Singapore dining."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=2000,
        )
        text = response.choices[0].message.content or ""
        usage = response.usage.total_tokens if response.usage else None

    return text, usage


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
async def _query_anthropic(prompt: str, search_enabled: bool = False) -> tuple[str, Optional[int]]:
    """Query Anthropic Claude Sonnet. Returns (response_text, token_usage).

    When search_enabled=True, uses the web_search_20250305 server-side tool.
    Claude will autonomously search the web and include results in its response.
    The response content may contain text, tool_use, and tool_result blocks;
    we extract and concatenate only the text blocks.
    """
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    kwargs: dict = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096 if search_enabled else 2000,
        "system": "You are a helpful restaurant recommendation assistant specializing in Singapore dining.",
        "messages": [{"role": "user", "content": prompt}],
    }

    if search_enabled:
        # Server-side web search tool — Claude decides when/what to search
        kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]

    response = await client.messages.create(**kwargs)

    # Extract text from response — with search enabled, content may include
    # server_tool_use and web_search_tool_result blocks alongside text blocks
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    text = "\n".join(text_parts) if text_parts else ""

    usage = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else None
    return text, usage


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
async def _query_gemini(prompt: str, search_enabled: bool = False) -> tuple[str, Optional[int]]:
    """Query Google Gemini 1.5 Pro. Returns (response_text, token_usage)."""
    from google import genai

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    config: dict = {}
    if search_enabled:
        config["tools"] = [{"google_search": {}}]

    # google-genai uses sync API; run in executor for async compatibility
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config if config else None,
        ),
    )
    text = response.text or ""
    usage = None
    if response.usage_metadata:
        usage = (
            (response.usage_metadata.prompt_token_count or 0)
            + (response.usage_metadata.candidates_token_count or 0)
        )
    return text, usage


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5))
async def _query_perplexity(prompt: str, search_enabled: bool = True) -> tuple[str, Optional[int]]:
    """Query Perplexity Sonar. Returns (response_text, token_usage).

    Perplexity Sonar is ALWAYS search-augmented by design — there is no way
    to disable web search. Both search_enabled=False and search_enabled=True
    runs are effectively "search on". When search_enabled=True explicitly,
    we add search_recency_filter="month" to see if temporal filtering shifts
    the recommendations. This asymmetry is itself a research finding.
    """
    import httpx

    body: dict = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": "You are a helpful restaurant recommendation assistant specializing in Singapore dining."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.7,
        "max_tokens": 2000,
    }

    if search_enabled:
        # Add recency filter to see if temporal freshness shifts recommendations
        body["search_recency_filter"] = "month"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {os.environ['PERPLEXITY_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}).get("total_tokens")
        return text, usage


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_MODEL_HANDLERS = {
    ModelName.GPT_4O: _query_openai,
    ModelName.CLAUDE_SONNET: _query_anthropic,
    ModelName.GEMINI_PRO: _query_gemini,
    ModelName.PERPLEXITY_SONAR: _query_perplexity,
}


async def query_model(
    prompt: DiscoveryPrompt,
    model: ModelName,
    search_enabled: bool = False,
) -> QueryResult:
    """Query a single model with a discovery prompt and return the result.

    This is the main entry point for running a single query. It handles
    timing, error wrapping, and raw response archival.
    """
    handler = _MODEL_HANDLERS[model]
    start = time.monotonic()

    text, token_usage = await handler(prompt.text, search_enabled)

    latency_ms = int((time.monotonic() - start) * 1000)

    result = QueryResult(
        prompt_id=prompt.id,
        model_name=model,
        search_enabled=search_enabled,
        raw_response=text,
        timestamp=datetime.utcnow(),
        latency_ms=latency_ms,
        token_usage=token_usage,
    )

    _save_raw_response(result)
    return result


async def run_sweep(
    prompts: list[DiscoveryPrompt],
    models: Optional[list[ModelName]] = None,
    search_modes: Optional[list[bool]] = None,
    max_concurrent: int = 5,
) -> list[QueryResult]:
    """Run a full query sweep: all prompts x all models x search modes.

    Uses a semaphore to limit concurrent API calls and displays a rich
    progress bar. Returns all results.
    """
    if models is None:
        models = list(ModelName)
    if search_modes is None:
        search_modes = [False, True]

    semaphore = asyncio.Semaphore(max_concurrent)
    results: list[QueryResult] = []

    # Build the task list
    tasks = [
        (prompt, model, search)
        for prompt in prompts
        for model in models
        for search in search_modes
    ]

    total = len(tasks)
    console.print(f"\n[bold]Running sweep:[/bold] {len(prompts)} prompts x {len(models)} models x {len(search_modes)} search modes = {total} queries\n")

    async def _run_one(prompt: DiscoveryPrompt, model: ModelName, search: bool) -> Optional[QueryResult]:
        async with semaphore:
            try:
                return await query_model(prompt, model, search)
            except Exception as e:
                console.print(f"[red]ERROR[/red] {model.value} | {prompt.id} | search={search}: {e}")
                return None

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Querying models...", total=total)

        async def _tracked(prompt: DiscoveryPrompt, model: ModelName, search: bool) -> Optional[QueryResult]:
            result = await _run_one(prompt, model, search)
            progress.advance(task)
            return result

        gathered = await asyncio.gather(
            *[_tracked(p, m, s) for p, m, s in tasks]
        )

    results = [r for r in gathered if r is not None]
    console.print(f"\n[bold green]Completed:[/bold green] {len(results)}/{total} queries successful\n")
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Load prompts from JSON and run the full sweep."""
    from .db import init_db, insert_query_result

    prompts_path = Path(__file__).parent.parent / "prompts" / "discovery_prompts.json"
    if not prompts_path.exists():
        console.print("[red]No prompts found.[/red] Populate prompts/discovery_prompts.json first.")
        return

    raw_prompts = json.loads(prompts_path.read_text())
    if not raw_prompts:
        console.print("[yellow]Prompt library is empty.[/yellow] Add prompts to prompts/discovery_prompts.json first.")
        return

    prompts = [DiscoveryPrompt(**p) for p in raw_prompts]
    console.print(f"Loaded {len(prompts)} prompts from {prompts_path}")

    conn = init_db()
    results = await run_sweep(prompts)

    for result in results:
        insert_query_result(conn, result)

    conn.close()
    console.print(f"[bold green]All results saved to database.[/bold green]")


if __name__ == "__main__":
    asyncio.run(main())
