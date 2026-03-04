"""Response parser — extracts structured restaurant data from raw LLM responses.

Uses Claude to parse raw text responses into RestaurantMention records.
The extraction prompt (prompts/extraction_prompt.txt) defines the schema
and rules for extraction.

This module will be fully implemented in Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from .models import ParsedResponse

EXTRACTION_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "extraction_prompt.txt"


def get_extraction_prompt() -> str:
    """Load the extraction system prompt from disk."""
    return EXTRACTION_PROMPT_PATH.read_text()


async def parse_response(query_result_id: int, raw_response: str) -> ParsedResponse:
    """Parse a raw LLM response into structured restaurant data.

    Uses Claude API with the extraction prompt to convert free-text
    restaurant recommendations into structured RestaurantMention records.

    Args:
        query_result_id: The DB ID of the query result being parsed.
        raw_response: The raw text from an LLM's restaurant recommendation.

    Returns:
        ParsedResponse with extracted restaurant mentions.
    """
    # TODO: Phase 2 — implement extraction pipeline
    raise NotImplementedError("Response parsing will be implemented in Phase 2")
