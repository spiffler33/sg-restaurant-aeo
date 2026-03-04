"""Response parser — extracts structured restaurant data from raw LLM responses.

Uses Claude Haiku to parse raw text responses into RestaurantMention records.
The extraction prompt (prompts/extraction_prompt.txt) defines the schema
and rules for extraction.

Key design choices:
- Claude Haiku for cost efficiency (~$4 for 1,120 responses)
- Async batch processing with configurable concurrency
- Idempotent: skips already-parsed query_result_ids
- Strips Perplexity citation markers [1], [2] before parsing
- Rich progress bar for monitoring
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from anthropic import AsyncAnthropic
from dotenv import load_dotenv
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    ParsedResponse,
    PriceIndicator,
    RestaurantMention,
    Sentiment,
)

load_dotenv()

console = Console()

EXTRACTION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extraction_prompt.txt"
PARSE_MODEL = "claude-haiku-4-5-20251001"


def get_extraction_prompt() -> str:
    """Load the extraction system prompt from disk."""
    return EXTRACTION_PROMPT_PATH.read_text()


def clean_response_text(raw: str) -> str:
    """Clean raw response text before sending to the parser.

    - Strips Perplexity citation markers like [1], [2], [1][2]
    - Removes excessive whitespace
    """
    # Remove citation markers: [1], [2], [1][2], etc.
    cleaned = re.sub(r"\[\d+\]", "", raw)
    # Collapse multiple blank lines into one
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _parse_price(val: str) -> PriceIndicator:
    """Convert a price string to PriceIndicator enum, with fallback."""
    mapping = {
        "$": PriceIndicator.BUDGET,
        "$$": PriceIndicator.MODERATE,
        "$$$": PriceIndicator.UPSCALE,
        "$$$$": PriceIndicator.FINE_DINING,
        "unknown": PriceIndicator.UNKNOWN,
    }
    return mapping.get(val, PriceIndicator.UNKNOWN)


def _parse_sentiment(val: str) -> Sentiment:
    """Convert a sentiment string to Sentiment enum, with fallback."""
    mapping = {
        "positive": Sentiment.POSITIVE,
        "neutral": Sentiment.NEUTRAL,
        "negative": Sentiment.NEGATIVE,
    }
    return mapping.get(val.lower(), Sentiment.POSITIVE)


def _extract_json(text: str) -> dict:
    """Extract JSON from Haiku's response, handling markdown code fences."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        return json.loads(text)

    # Try extracting from ```json ... ``` code fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Last resort: find first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start : end + 1])

    raise ValueError(f"No valid JSON found in response: {text[:200]}")


@retry(wait=wait_exponential(multiplier=1, min=2, max=30), stop=stop_after_attempt(4))
async def parse_response(
    query_result_id: int,
    raw_response: str,
    client: AsyncAnthropic,
    extraction_prompt: str,
) -> ParsedResponse:
    """Parse a raw LLM response into structured restaurant data.

    Sends the cleaned response text to Claude Haiku with the extraction
    system prompt. Parses the JSON response and validates against
    the RestaurantMention schema.

    Args:
        query_result_id: The DB ID of the query result being parsed.
        raw_response: The raw text from an LLM's restaurant recommendation.
        client: Anthropic async client instance (shared across batch).
        extraction_prompt: The system prompt for extraction.

    Returns:
        ParsedResponse with extracted restaurant mentions.
    """
    cleaned = clean_response_text(raw_response)

    # Use higher max_tokens for long responses (verbose Gemini outputs can
    # yield 30+ restaurants, producing JSON > 4K tokens)
    max_tokens = 8192 if len(cleaned) > 5000 else 4096

    response = await client.messages.create(
        model=PARSE_MODEL,
        max_tokens=max_tokens,
        system=extraction_prompt,
        messages=[{"role": "user", "content": cleaned}],
        temperature=0.0,
    )

    response_text = response.content[0].text
    data = _extract_json(response_text)

    # Parse each restaurant entry into a validated RestaurantMention
    restaurants: list[RestaurantMention] = []
    for entry in data.get("restaurants", []):
        mention = RestaurantMention(
            restaurant_name=entry.get("restaurant_name", "Unknown"),
            rank_position=entry.get("rank_position", len(restaurants) + 1),
            neighbourhood=entry.get("neighbourhood"),
            cuisine_tags=entry.get("cuisine_tags", []),
            vibe_tags=entry.get("vibe_tags", []),
            price_indicator=_parse_price(entry.get("price_indicator", "unknown")),
            descriptors=entry.get("descriptors", []),
            sentiment=_parse_sentiment(entry.get("sentiment", "positive")),
            is_primary_recommendation=entry.get("is_primary_recommendation", True),
        )
        restaurants.append(mention)

    input_tokens = response.usage.input_tokens if response.usage else 0
    output_tokens = response.usage.output_tokens if response.usage else 0

    return ParsedResponse(
        query_result_id=query_result_id,
        restaurants=restaurants,
        parse_model=PARSE_MODEL,
        parsed_at=datetime.utcnow(),
    ), input_tokens, output_tokens  # type: ignore[return-value]


async def parse_batch(
    query_rows: list[dict],
    max_concurrent: int = 10,
    already_parsed: Optional[set[int]] = None,
) -> tuple[list[ParsedResponse], int, int]:
    """Parse a batch of query results with concurrency control.

    Args:
        query_rows: List of dicts with keys: id, raw_response, model_name, prompt_id
        max_concurrent: Maximum concurrent API calls.
        already_parsed: Set of query_result_ids to skip (idempotency).

    Returns:
        Tuple of (parsed_responses, total_input_tokens, total_output_tokens)
    """
    if already_parsed is None:
        already_parsed = set()

    # Filter out already-parsed responses
    to_parse = [r for r in query_rows if r["id"] not in already_parsed]
    skipped = len(query_rows) - len(to_parse)

    if skipped > 0:
        console.print(f"[yellow]Skipping {skipped} already-parsed responses[/yellow]")

    if not to_parse:
        console.print("[green]All responses already parsed![/green]")
        return [], 0, 0

    client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    extraction_prompt = get_extraction_prompt()
    semaphore = asyncio.Semaphore(max_concurrent)

    results: list[ParsedResponse] = []
    errors: list[dict] = []
    total_in = 0
    total_out = 0

    async def _parse_one(row: dict) -> Optional[tuple[ParsedResponse, int, int]]:
        async with semaphore:
            try:
                return await parse_response(
                    query_result_id=row["id"],
                    raw_response=row["raw_response"],
                    client=client,
                    extraction_prompt=extraction_prompt,
                )
            except Exception as e:
                errors.append({"id": row["id"], "model": row.get("model_name", "?"), "error": str(e)})
                return None

    console.print(f"\n[bold]Parsing {len(to_parse)} responses[/bold] (concurrency={max_concurrent})\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("({task.completed}/{task.total})"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Parsing...", total=len(to_parse))

        async def _tracked(row: dict) -> Optional[tuple[ParsedResponse, int, int]]:
            result = await _parse_one(row)
            progress.advance(task)
            return result

        gathered = await asyncio.gather(*[_tracked(r) for r in to_parse])

    for item in gathered:
        if item is not None:
            parsed, in_tok, out_tok = item
            results.append(parsed)
            total_in += in_tok
            total_out += out_tok

    console.print(f"\n[bold green]Parsed:[/bold green] {len(results)}/{len(to_parse)} successful")
    if errors:
        console.print(f"[bold red]Errors:[/bold red] {len(errors)}")
        for e in errors[:5]:
            console.print(f"  [red]ID {e['id']} ({e['model']}): {e['error'][:100]}[/red]")

    return results, total_in, total_out
