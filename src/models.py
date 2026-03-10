"""Pydantic models for the SG Restaurant AEO research project.

These models define the core data structures used throughout the pipeline:
- DiscoveryPrompt: the research instrument (what we ask LLMs)
- QueryResult: raw API response metadata
- RestaurantMention: a single restaurant extracted from an LLM response
- ParsedResponse: the structured extraction from one query result
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Specificity(str, Enum):
    """How specific a discovery prompt is."""

    BROAD = "broad"
    MEDIUM = "medium"
    NARROW = "narrow"


class Dimension(str, Enum):
    """The primary dimension a prompt targets."""

    CUISINE = "cuisine"
    OCCASION = "occasion"
    NEIGHBOURHOOD = "neighbourhood"
    VIBE = "vibe"
    PRICE = "price"
    CONSTRAINT = "constraint"
    COMPARISON = "comparison"
    EXPERIENTIAL = "experiential"


class PriceIndicator(str, Enum):
    """Price level extracted from an LLM response."""

    BUDGET = "$"
    MODERATE = "$$"
    UPSCALE = "$$$"
    FINE_DINING = "$$$$"
    UNKNOWN = "unknown"


class Sentiment(str, Enum):
    """Sentiment of the restaurant mention."""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class ModelName(str, Enum):
    """Supported LLM models."""

    GPT_4O = "openai/gpt-4o"
    CLAUDE_SONNET = "anthropic/claude-sonnet-4-20250514"
    GEMINI_PRO = "google/gemini-2.5-flash"
    PERPLEXITY_SONAR = "perplexity/sonar"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------


class DiscoveryPrompt(BaseModel):
    """A prompt used to query LLMs about Singapore restaurants.

    The prompt library is a first-class research artifact. Each prompt is
    tagged with metadata describing what dimension of restaurant discovery
    it probes and how specific it is.
    """

    id: str = Field(..., description="Unique prompt identifier, e.g. 'cuisine_001'")
    text: str = Field(..., description="The full prompt text sent to the LLM")
    dimension: Dimension = Field(..., description="Primary dimension this prompt targets")
    category: str = Field(
        ..., description="Subcategory within the dimension, e.g. 'japanese' under cuisine"
    )
    specificity: Specificity = Field(
        ..., description="How specific the prompt is: broad, medium, or narrow"
    )


class QueryResult(BaseModel):
    """Metadata and raw response from a single LLM query.

    We always store the full raw response so we can re-parse later
    as our extraction pipeline improves.
    """

    id: Optional[int] = Field(default=None, description="Auto-incremented DB row ID")
    prompt_id: str = Field(..., description="References DiscoveryPrompt.id")
    model_name: ModelName = Field(..., description="Which LLM was queried")
    search_enabled: bool = Field(
        ..., description="Whether the model had web search/browsing enabled"
    )
    raw_response: str = Field(..., description="Full raw text response from the LLM")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When the query was executed"
    )
    latency_ms: Optional[int] = Field(
        default=None, description="Response latency in milliseconds"
    )
    token_usage: Optional[int] = Field(
        default=None, description="Total tokens used (prompt + completion) if available"
    )


class RestaurantMention(BaseModel):
    """A single restaurant extracted from an LLM response.

    This is the atomic unit of our dataset. Every restaurant mentioned
    in every LLM response becomes one of these records.
    """

    restaurant_name: str = Field(..., description="Normalized restaurant name")
    rank_position: int = Field(
        ..., description="Order mentioned in the response (1-indexed)"
    )
    neighbourhood: Optional[str] = Field(
        default=None, description="Neighbourhood mentioned, e.g. 'Tiong Bahru'"
    )
    cuisine_tags: list[str] = Field(
        default_factory=list, description="Cuisine types, e.g. ['japanese', 'ramen']"
    )
    vibe_tags: list[str] = Field(
        default_factory=list,
        description="Vibe descriptors, e.g. ['romantic', 'cozy', 'lively']",
    )
    price_indicator: PriceIndicator = Field(
        default=PriceIndicator.UNKNOWN, description="Price level if mentioned"
    )
    descriptors: list[str] = Field(
        default_factory=list,
        description="Raw adjectives/phrases used to describe the restaurant",
    )
    sentiment: Sentiment = Field(
        default=Sentiment.POSITIVE, description="Sentiment of the mention"
    )
    is_primary_recommendation: bool = Field(
        default=True,
        description="True if this is a primary recommendation, not just mentioned in passing",
    )


class ParsedResponse(BaseModel):
    """Structured extraction from a single LLM query result.

    Links back to the QueryResult it was parsed from, and contains
    the list of all restaurants mentioned in that response.
    """

    id: Optional[int] = Field(default=None, description="Auto-incremented DB row ID")
    query_result_id: int = Field(..., description="References QueryResult.id")
    restaurants: list[RestaurantMention] = Field(
        default_factory=list, description="All restaurants extracted from the response"
    )
    parse_model: str = Field(
        default="anthropic/claude-sonnet-4-20250514",
        description="Which model was used to parse the response",
    )
    parsed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When parsing was performed"
    )


class MatchConfidence(str, Enum):
    """Confidence level for Google Places match to a canonical restaurant."""

    HIGH = "high"          # ≥90% name match + in Singapore
    MEDIUM = "medium"      # 70-89% + in Singapore
    LOW = "low"            # Legacy: exists in DB but no longer assigned (was 50-69%)
    UNMATCHED = "unmatched"


class GooglePlace(BaseModel):
    """A Google Places result matched (or attempted) to a canonical restaurant.

    Stores the raw Google data alongside match metadata. Used for ground truth
    validation: are LLMs recommending real, open, well-reviewed restaurants?
    """

    id: Optional[int] = Field(default=None, description="Auto-incremented DB row ID")
    canonical_id: Optional[int] = Field(
        default=None, description="FK to canonical_restaurants, null for baseline-only"
    )
    place_id: str = Field(..., description="Google's unique place identifier")
    google_name: str = Field(..., description="Name as returned by Google Places")
    formatted_address: str = Field(default="", description="Full address from Google")
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    rating: Optional[float] = Field(default=None, description="Google rating (1.0-5.0)")
    user_ratings_total: Optional[int] = Field(
        default=None, description="Total number of Google reviews"
    )
    price_level: Optional[int] = Field(
        default=None, description="Google price level (0-4)"
    )
    types: list[str] = Field(default_factory=list, description="Google place types (JSON in DB)")
    business_status: Optional[str] = Field(
        default=None, description="OPERATIONAL, CLOSED_TEMPORARILY, CLOSED_PERMANENTLY"
    )
    match_confidence: MatchConfidence = Field(
        default=MatchConfidence.UNMATCHED, description="How well this matches the canonical name"
    )
    match_score: Optional[float] = Field(
        default=None, description="Fuzzy match score (0-100)"
    )
    is_popular_baseline: bool = Field(
        default=False, description="True if from baseline popular search, not canonical match"
    )
    fetched_at: datetime = Field(
        default_factory=datetime.utcnow, description="When the Google Places data was fetched"
    )


class CanonicalRestaurant(BaseModel):
    """A resolved restaurant entity after entity resolution.

    Collapses multiple name variants (e.g. "PS.Cafe", "PS. Café",
    "PS.Cafe at Dempsey Hill") into a single canonical entry with
    aggregated mention stats.
    """

    canonical_id: int = Field(..., description="Unique canonical restaurant ID")
    canonical_name: str = Field(..., description="The chosen canonical name")
    variant_names: list[str] = Field(
        default_factory=list, description="All raw name variants that resolved here"
    )
    total_mentions: int = Field(
        default=0, description="Sum of mentions across all variants"
    )
    model_count: int = Field(
        default=0, description="How many of the 4 models mention this restaurant"
    )
    models_mentioning: list[str] = Field(
        default_factory=list, description="Which models mention it"
    )
