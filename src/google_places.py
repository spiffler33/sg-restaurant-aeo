"""Google Places API integration for ground truth validation.

Searches the Legacy Text Search API to match canonical restaurants against
real Google Places entries. Returns rating, price, location, review count,
and business status for each match.

Architecture:
  - Single API call per restaurant (Text Search gives all needed fields)
  - Async httpx with semaphore for concurrency control
  - Tenacity retries with exponential backoff
  - Match confidence scored via rapidfuzz + Singapore bounding box
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from rapidfuzz import fuzz
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from tenacity import retry, stop_after_attempt, wait_exponential

from .entity_resolution import normalize_name
from .models import GooglePlace, MatchConfidence

console = Console()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Singapore bounding box (generous — covers all islands)
SG_LAT_MIN, SG_LAT_MAX = 1.15, 1.47
SG_LNG_MIN, SG_LNG_MAX = 103.6, 104.1

# Google place types considered food-related
FOOD_TYPES = {
    "restaurant",
    "food",
    "cafe",
    "bar",
    "bakery",
    "meal_takeaway",
    "meal_delivery",
    "night_club",  # some bars classified as nightclubs
    "point_of_interest",  # hawker stalls often only get this
    "establishment",  # generic fallback
}

# Cost per Text Search request (legacy pricing)
COST_PER_REQUEST = 0.032  # $32 per 1,000 requests


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(4),
)
async def search_place(
    query: str,
    api_key: str,
    client: httpx.AsyncClient,
    page_token: Optional[str] = None,
) -> dict:
    """Execute a single Google Text Search API call.

    Returns the raw JSON response dict with keys: results, status,
    next_page_token (optional).
    """
    params: dict[str, str] = {
        "query": query,
        "key": api_key,
    }
    if page_token:
        params = {"pagetoken": page_token, "key": api_key}

    response = await client.get(TEXT_SEARCH_URL, params=params, timeout=30.0)
    response.raise_for_status()
    data = response.json()

    status = data.get("status", "UNKNOWN")
    if status not in ("OK", "ZERO_RESULTS"):
        raise RuntimeError(f"Google Places API error: {status} — {data.get('error_message', '')}")

    # Treat ZERO_RESULTS as retryable when it's a primary search (not pagination).
    # Google sometimes returns empty results transiently under load.
    if status == "ZERO_RESULTS" and not page_token:
        raise RuntimeError("ZERO_RESULTS — retrying (may be transient)")

    return data


# ---------------------------------------------------------------------------
# Match confidence scoring
# ---------------------------------------------------------------------------


def _in_singapore(lat: float, lng: float) -> bool:
    """Check if coordinates fall within Singapore's bounding box."""
    return SG_LAT_MIN <= lat <= SG_LAT_MAX and SG_LNG_MIN <= lng <= SG_LNG_MAX


def compute_match_confidence(
    canonical_name: str,
    google_name: str,
    lat: float,
    lng: float,
) -> tuple[MatchConfidence, float]:
    """Score how well a Google result matches a canonical restaurant.

    Returns (confidence_level, raw_score). Uses normalize_name() from
    entity_resolution for consistent comparison, then the best of
    token_sort_ratio and token_set_ratio for fuzzy matching.

    token_set_ratio handles Google's verbose names: "Fat Cow" matches
    "Fat Cow - Japanese Wagyu @ Camden Medical Centre" at 100% because
    all tokens in the canonical name appear in Google's name.
    """
    norm_canonical = normalize_name(canonical_name)
    norm_google = normalize_name(google_name)

    # Use the best of both: sort_ratio for similar-length names,
    # set_ratio for subset matches (short canonical vs verbose Google name)
    sort_score = fuzz.token_sort_ratio(norm_canonical, norm_google)
    set_score = fuzz.token_set_ratio(norm_canonical, norm_google)
    score = max(sort_score, set_score)

    # Location check: must be in Singapore
    in_sg = _in_singapore(lat, lng)

    if not in_sg:
        return MatchConfidence.UNMATCHED, score

    if score >= 90:
        return MatchConfidence.HIGH, score
    elif score >= 70:
        return MatchConfidence.MEDIUM, score
    else:
        return MatchConfidence.UNMATCHED, score


def _has_food_type(types: list[str]) -> bool:
    """Check if a Google result has at least one food-related type."""
    return bool(set(types) & FOOD_TYPES)


# ---------------------------------------------------------------------------
# Best match selection
# ---------------------------------------------------------------------------


def _status_rank(result: dict) -> int:
    """Rank business_status: OPERATIONAL > CLOSED_TEMPORARILY > CLOSED_PERMANENTLY."""
    status = result.get("business_status", "OPERATIONAL")
    return {"OPERATIONAL": 2, "CLOSED_TEMPORARILY": 1}.get(status, 0)


def select_best_match(
    canonical_name: str,
    results: list[dict],
) -> Optional[tuple[dict, MatchConfidence, float]]:
    """Pick the best Google result for a canonical restaurant name.

    Iterates all results, scores each, and returns the highest-confidence
    match that has a food-related type. Returns None if no suitable match.

    Selection priority (each level is a tiebreaker for the previous):
      1. Higher confidence level (HIGH > MEDIUM)
      2. OPERATIONAL > CLOSED_TEMPORARILY > CLOSED_PERMANENTLY
      3. Higher raw fuzzy score
      4. Higher review count (catches main branch of chain restaurants)
    """
    best: Optional[tuple[dict, MatchConfidence, float]] = None
    confidence_rank = {
        MatchConfidence.HIGH: 2,
        MatchConfidence.MEDIUM: 1,
        MatchConfidence.UNMATCHED: 0,
    }

    for result in results:
        lat = result.get("geometry", {}).get("location", {}).get("lat", 0)
        lng = result.get("geometry", {}).get("location", {}).get("lng", 0)
        types = result.get("types", [])
        google_name = result.get("name", "")

        # Must be food-related
        if not _has_food_type(types):
            continue

        confidence, score = compute_match_confidence(
            canonical_name, google_name, lat, lng
        )

        if confidence == MatchConfidence.UNMATCHED:
            continue

        # Compare against current best using (confidence, status, score, reviews) tuple
        if best is None:
            best = (result, confidence, score)
        else:
            best_result, best_conf, best_score = best
            new_key = (
                confidence_rank[confidence],
                _status_rank(result),
                score,
                result.get("user_ratings_total", 0),
            )
            best_key = (
                confidence_rank[best_conf],
                _status_rank(best_result),
                best_score,
                best_result.get("user_ratings_total", 0),
            )
            if new_key > best_key:
                best = (result, confidence, score)

    return best


# ---------------------------------------------------------------------------
# Query building
# ---------------------------------------------------------------------------


def build_search_query(canonical_name: str) -> str:
    """Build the Google Text Search query for a restaurant.

    Appends 'Singapore restaurant' to disambiguate from global results.
    """
    return f"{canonical_name} Singapore restaurant"


# ---------------------------------------------------------------------------
# Batch fetching
# ---------------------------------------------------------------------------


def _result_to_google_place(
    result: dict,
    canonical_id: Optional[int],
    confidence: MatchConfidence,
    score: float,
    is_baseline: bool = False,
) -> GooglePlace:
    """Convert a raw Google API result dict to a GooglePlace model."""
    location = result.get("geometry", {}).get("location", {})
    return GooglePlace(
        canonical_id=canonical_id,
        place_id=result["place_id"],
        google_name=result.get("name", ""),
        formatted_address=result.get("formatted_address", ""),
        lat=location.get("lat", 0.0),
        lng=location.get("lng", 0.0),
        rating=result.get("rating"),
        user_ratings_total=result.get("user_ratings_total"),
        price_level=result.get("price_level"),
        types=result.get("types", []),
        business_status=result.get("business_status"),
        match_confidence=confidence,
        match_score=score,
        is_popular_baseline=is_baseline,
        fetched_at=datetime.utcnow(),
    )


def _sanitize_filename(name: str) -> str:
    """Convert a restaurant name to a safe filename component."""
    return re.sub(r"[^\w\-]", "_", name)[:80]


def _save_raw_response(
    raw_dir: Path,
    canonical_id: int,
    canonical_name: str,
    query: str,
    results: list[dict],
) -> None:
    """Save raw Google API results to a JSON file for auditability."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{canonical_id}_{_sanitize_filename(canonical_name)}.json"
    payload = {
        "canonical_id": canonical_id,
        "canonical_name": canonical_name,
        "query": query,
        "results": results,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    (raw_dir / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=False))


async def fetch_restaurant_places(
    restaurants: list[tuple[int, str]],
    api_key: str,
    max_concurrent: int = 10,
    raw_dir: Optional[Path] = None,
) -> tuple[list[GooglePlace], dict]:
    """Fetch Google Places data for a batch of canonical restaurants.

    Args:
        restaurants: list of (canonical_id, canonical_name) tuples
        api_key: Google Places API key
        max_concurrent: max concurrent API calls
        raw_dir: directory to save raw API responses (default: data/raw/google_places)

    Returns:
        (places, stats) where stats is a dict with match distribution counts
    """
    if raw_dir is None:
        raw_dir = Path("data/raw/google_places")

    semaphore = asyncio.Semaphore(max_concurrent)
    places: list[GooglePlace] = []
    stats = {"high": 0, "medium": 0, "unmatched": 0, "errors": 0}

    async def _fetch_one(
        canonical_id: int,
        canonical_name: str,
        client: httpx.AsyncClient,
    ) -> Optional[GooglePlace]:
        async with semaphore:
            try:
                query = build_search_query(canonical_name)
                data = await search_place(query, api_key, client)
                results = data.get("results", [])

                # Always save raw response before selection
                _save_raw_response(raw_dir, canonical_id, canonical_name, query, results)

                if not results:
                    stats["unmatched"] += 1
                    return None

                match = select_best_match(canonical_name, results)
                if match is None:
                    stats["unmatched"] += 1
                    return None

                result, confidence, score = match
                stats[confidence.value] += 1
                return _result_to_google_place(
                    result, canonical_id, confidence, score
                )
            except Exception as e:
                if "ZERO_RESULTS" in str(e):
                    # All retries returned empty — genuinely not on Google
                    stats["unmatched"] += 1
                else:
                    console.print(
                        f"[red]ERROR[/red] {canonical_name}: {e}"
                    )
                    stats["errors"] += 1
                return None

    async with httpx.AsyncClient() as client:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                "Fetching Google Places...", total=len(restaurants)
            )

            async def _tracked(cid: int, name: str) -> Optional[GooglePlace]:
                result = await _fetch_one(cid, name, client)
                progress.advance(task)
                return result

            gathered = await asyncio.gather(
                *[_tracked(cid, name) for cid, name in restaurants]
            )

    places = [p for p in gathered if p is not None]
    return places, stats


# ---------------------------------------------------------------------------
# Popular baseline
# ---------------------------------------------------------------------------

BASELINE_QUERIES = [
    "best restaurants in Singapore",
    "top rated hawker food Singapore",
    "fine dining Singapore",
    "best cafes Singapore",
    "popular bars Singapore",
]


async def fetch_popular_baseline(
    api_key: str,
    max_results: int = 100,
) -> list[GooglePlace]:
    """Fetch the most-reviewed restaurants from diverse Google searches.

    Runs 5 broad queries, paginates up to 3 pages each (60 results/query),
    deduplicates by place_id, and returns the top N by review count.
    This creates an independent "what's actually popular" baseline.
    """
    all_results: dict[str, dict] = {}  # place_id -> result

    async with httpx.AsyncClient() as client:
        for query in BASELINE_QUERIES:
            console.print(f"  Baseline query: [cyan]{query}[/cyan]")
            page_token = None

            for page in range(3):  # up to 3 pages (60 results)
                if page == 0:
                    data = await search_place(query, api_key, client)
                else:
                    if not page_token:
                        break
                    # Google requires ~2s delay before next_page_token works
                    await asyncio.sleep(2.0)
                    data = await search_place(query, api_key, client, page_token)

                for result in data.get("results", []):
                    pid = result.get("place_id")
                    if pid and pid not in all_results:
                        # Only keep Singapore results with food types
                        lat = result.get("geometry", {}).get("location", {}).get("lat", 0)
                        lng = result.get("geometry", {}).get("location", {}).get("lng", 0)
                        if _in_singapore(lat, lng) and _has_food_type(result.get("types", [])):
                            all_results[pid] = result

                page_token = data.get("next_page_token")

    # Sort by review count, take top N
    sorted_results = sorted(
        all_results.values(),
        key=lambda r: r.get("user_ratings_total", 0),
        reverse=True,
    )[:max_results]

    places = [
        _result_to_google_place(
            result,
            canonical_id=None,
            confidence=MatchConfidence.UNMATCHED,  # N/A for baseline
            score=0.0,
            is_baseline=True,
        )
        for result in sorted_results
    ]

    console.print(
        f"  Baseline: {len(all_results)} unique places found, "
        f"returning top {len(places)} by review count"
    )
    return places
