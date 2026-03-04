"""Consolidate raw LLM-generated prompts into a deduplicated, normalized prompt library.

Reads all JSON files from prompts/raw/, normalizes to the DiscoveryPrompt schema,
performs fuzzy deduplication, and writes the final library to prompts/discovery_prompts.json.
"""

import json
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.models import Dimension, DiscoveryPrompt, Specificity

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
RAW_DIR = PROJECT_ROOT / "prompts" / "raw"
OUTPUT_FILE = PROJECT_ROOT / "prompts" / "discovery_prompts.json"
SIMILARITY_THRESHOLD = 0.62  # prompts above this are considered duplicates

# Map source filenames to display names
SOURCE_NAMES = {
    "claude_profound.json": "Claude",
    "chatgpt_profound.json": "ChatGPT",
    "perplexity_profound.json": "Perplexity",
    "grok_profound.json": "Grok",
    "gemini_profound.json": "Gemini",
}

# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

# Map raw category strings -> normalized snake_case
CATEGORY_NORMALIZE = {
    # Cuisine
    "japanese": "japanese",
    "japanese_sushi": "japanese_sushi",
    "japanese_izakaya": "japanese_izakaya",
    "japanese_wagyu": "japanese_wagyu",
    "chinese_cantonese": "chinese_cantonese",
    "chinese (cantonese)": "chinese_cantonese",
    "cantonese": "chinese_cantonese",
    "chinese_sichuan": "chinese_sichuan",
    "chinese (sichuan)": "chinese_sichuan",
    "sichuan": "chinese_sichuan",
    "chinese_teochew": "chinese_teochew",
    "chinese (teochew)": "chinese_teochew",
    "teochew": "chinese_teochew",
    "chinese": "chinese",
    "chinese_specific_dish": "chinese_specific_dish",
    "indian": "indian",
    "indian_north": "indian_north",
    "indian (north)": "indian_north",
    "north indian": "indian_north",
    "north_indian": "indian_north",
    "indian_south": "indian_south",
    "indian (south)": "indian_south",
    "south indian": "indian_south",
    "south_indian": "indian_south",
    "peranakan": "peranakan",
    "italian": "italian",
    "french": "french",
    "korean": "korean",
    "thai": "thai",
    "vietnamese": "vietnamese",
    "middle_eastern": "middle_eastern",
    "middle eastern": "middle_eastern",
    "mexican": "mexican",
    "fusion": "fusion",
    "malay": "malay",
    # Occasion
    "date_night": "date_night",
    "date night": "date_night",
    "first_date": "first_date",
    "first date": "first_date",
    "first_date_casual": "first_date",
    "first date_casual": "first_date",
    "anniversary": "anniversary",
    "business_lunch": "business_lunch",
    "business lunch": "business_lunch",
    "business_dinner": "business_dinner",
    "business dinner": "business_dinner",
    "family_celebration": "family_celebration",
    "family celebration": "family_celebration",
    "family": "family_celebration",
    "family_casual": "family_casual",
    "family birthday": "family_celebration",
    "family_birthday": "family_celebration",
    "friends_reunion": "friends_reunion",
    "catching_up_friends": "friends_reunion",
    "catching up with old friends": "friends_reunion",
    "friends catchup": "friends_reunion",
    "catching up": "friends_reunion",
    "solo_dining": "solo_dining",
    "solo dining": "solo_dining",
    "solo": "solo_dining",
    "birthday": "birthday",
    "birthday_dinner": "birthday",
    "birthday dinner": "birthday",
    "team_dinner": "team_dinner",
    "work_team_dinner": "team_dinner",
    "work team dinner": "team_dinner",
    "work team": "team_dinner",
    "work_team": "team_dinner",
    "impress_guests": "impress_guests",
    "impress_out_of_town_guests": "impress_guests",
    "impress out-of-town guests": "impress_guests",
    "impressing out-of-town guests": "impress_guests",
    "impressing guests": "impress_guests",
    "out-of-town guests": "impress_guests",
    "breakup": "breakup",
    "breakup_dinner": "breakup",
    "break-up": "breakup",
    "break-up dinner": "breakup",
    "proposal": "proposal",
    "farewell": "farewell",
    "farewell_expat": "farewell",
    "celebration_casual": "celebration_casual",
    "celebration_small_group": "celebration_casual",
    "post_work_quick": "post_work",
    "post_gym_meal": "post_work",
    "parents_in_town": "impress_guests",
    "sunday_brunch": "sunday_brunch",
    "sunday brunch": "sunday_brunch",
    # Neighbourhood
    "tiong_bahru": "tiong_bahru",
    "tiong bahru": "tiong_bahru",
    "cbd_raffles_place": "cbd_raffles_place",
    "cbd/raffles place": "cbd_raffles_place",
    "cbd_raffles place": "cbd_raffles_place",
    "cbd": "cbd_raffles_place",
    "dempsey_hill": "dempsey_hill",
    "dempsey hill": "dempsey_hill",
    "holland_village": "holland_village",
    "holland village": "holland_village",
    "joo_chiat_katong": "joo_chiat_katong",
    "joo_chiat/katong": "joo_chiat_katong",
    "joo chiat/katong": "joo_chiat_katong",
    "joo chiat": "joo_chiat_katong",
    "joo_chiat": "joo_chiat_katong",
    "chinatown": "chinatown",
    "little_india": "little_india",
    "little india": "little_india",
    "kampong_glam": "kampong_glam",
    "kampong glam": "kampong_glam",
    "kampong_glam_arab_street": "kampong_glam",
    "kampong glam/arab street": "kampong_glam",
    "arab_street": "kampong_glam",
    "orchard": "orchard",
    "sentosa": "sentosa",
    "east_coast": "east_coast",
    "east coast": "east_coast",
    "tanjong_pagar": "tanjong_pagar",
    "tanjong pagar": "tanjong_pagar",
    "keong_saik": "keong_saik",
    "keong saik": "keong_saik",
    "duxton_hill": "duxton_hill",
    "duxton hill": "duxton_hill",
    "robertson_quay": "robertson_quay",
    "robertson quay": "robertson_quay",
    "clarke_quay": "clarke_quay",
    "clarke quay": "clarke_quay",
    "bukit_timah": "bukit_timah",
    "bukit timah": "bukit_timah",
    "novena_thomson": "novena_thomson",
    "novena/thomson": "novena_thomson",
    "novena": "novena_thomson",
    "marina_bay": "marina_bay",
    "marina bay": "marina_bay",
    # Vibe
    "romantic": "romantic",
    "cozy": "cozy",
    "lively_buzzy": "lively_buzzy",
    "lively": "lively_buzzy",
    "lively/buzzy": "lively_buzzy",
    "lively hawker": "lively_buzzy",
    "quiet_conversation": "quiet_conversation",
    "quiet": "quiet_conversation",
    "people_watching": "people_watching",
    "people-watching": "people_watching",
    "outdoor_seating": "outdoor_seating",
    "outdoor": "outdoor_seating",
    "outdoor/greenery": "garden_greenery",
    "rooftop": "rooftop",
    "rooftop romantic": "rooftop",
    "hidden_speakeasy": "hidden_speakeasy",
    "hidden": "hidden_speakeasy",
    "hidden/speakeasy": "hidden_speakeasy",
    "speakeasy": "hidden_speakeasy",
    "instagrammable": "instagrammable",
    "instagram_worthy": "instagrammable",
    "instagram-worthy": "instagrammable",
    "instagram": "instagrammable",
    "old_school_charm": "old_school_charm",
    "old-school": "old_school_charm",
    "old-school charm": "old_school_charm",
    "heritage": "old_school_charm",
    "modern_minimalist": "modern_minimalist",
    "modern minimalist": "modern_minimalist",
    "modern": "modern_minimalist",
    "minimalist": "modern_minimalist",
    "hawker_elevated": "hawker_elevated",
    "hawker_but_aircon": "hawker_elevated",
    "hawker aircon": "hawker_elevated",
    "hawker-style but air-conditioned": "hawker_elevated",
    "modern hawker": "hawker_elevated",
    "late_night": "late_night",
    "late night": "late_night",
    "sunday_brunch": "sunday_brunch",
    "sunday_brunch_energy": "sunday_brunch",
    "sunday brunch energy": "sunday_brunch",
    "brunch": "sunday_brunch",
    "garden_greenery": "garden_greenery",
    "live_music": "live_music",
    "music_lounge": "live_music",
    "waterfront": "waterfront",
    "transportive": "transportive",
    "chef_interaction": "chef_interaction",
    "casual_hip": "casual_hip",
    "view": "waterfront",
    # Price
    "budget": "budget",
    "budget_under_20": "budget",
    "budget-casual": "budget",
    "student_budget": "budget",
    "mid_range": "mid_range",
    "mid-range": "mid_range",
    "mid_30_60": "mid_range",
    "mid-range halal": "mid_range",
    "splurge": "splurge",
    "splurge_100_plus": "splurge",
    "best_value": "best_value",
    "value_for_money": "best_value",
    "best value for money": "best_value",
    "value": "best_value",
    "worth_the_price": "best_value",
    "worth the price": "best_value",
    "worth price": "best_value",
    "omakase_value": "omakase_value",
    "omakase that isn't overpriced": "omakase_value",
    "omakase": "omakase_value",
    "cheap_good": "cheap_good",
    "cheap_but_good": "cheap_good",
    "cheap but actually good": "cheap_good",
    "cheap but good": "cheap_good",
    "cheap": "cheap_good",
    "most_expensive": "most_expensive",
    "set_lunch_deal": "set_lunch_deal",
    "fixed_budget": "fixed_budget",
    "tasting_menu_value": "tasting_menu_value",
    "value_casual": "value_casual",
    "michelin_cheap": "michelin_value",
    "no_hidden_costs": "best_value",
    # Constraint
    "vegetarian": "vegetarian",
    "vegetarian/vegan": "vegetarian",
    "vegan": "vegan",
    "halal": "halal",
    "halal_fine_dining": "halal_fine_dining",
    "halal large": "halal",
    "halal_large": "halal",
    "gluten_free": "gluten_free",
    "gluten-free": "gluten_free",
    "kid_friendly": "kid_friendly",
    "kid-friendly": "kid_friendly",
    "wheelchair_accessible": "wheelchair_accessible",
    "wheelchair": "wheelchair_accessible",
    "accessibility": "wheelchair_accessible",
    "large_group": "large_group",
    "large group": "large_group",
    "large_group_10_plus": "large_group",
    "large group 10+": "large_group",
    "private_dining": "private_dining",
    "private_dining_room": "private_dining",
    "private dining room": "private_dining",
    "private room": "private_dining",
    "late_night_dining": "late_night_dining",
    "late_night_after_10": "late_night_dining",
    "late night": "late_night_dining",
    "open_monday": "open_monday",
    "open_on_monday": "open_monday",
    "open on monday": "open_monday",
    "open monday": "open_monday",
    "opening hours": "open_monday",
    "walk_in": "walk_in",
    "walk-in": "walk_in",
    "walk_in_no_reservation": "walk_in",
    "walk-in_no_reservation": "walk_in",
    "no-reservation walk-in": "walk_in",
    "no_reservation": "walk_in",
    "dog_friendly": "dog_friendly",
    "takeaway_catering": "takeaway_catering",
    "keto": "keto",
    "no_pork_no_lard": "no_pork_no_lard",
    # Comparison
    "head_to_head": "head_to_head",
    "head_to_head_multi": "head_to_head",
    "better x or y": "head_to_head",
    "what's better, x or y": "head_to_head",
    "x_vs_y": "head_to_head",
    "comparison": "head_to_head",
    "top_ranking": "top_ranking",
    "top5_by_cuisine": "top_ranking",
    "top 5": "top_ranking",
    "top5_hawker_vs_restaurant": "top_ranking",
    "top 3": "top_ranking",
    "top_5_for_z": "top_ranking",
    "top 5 for z": "top_ranking",
    "rank_by_neighbourhood": "top_ranking",
    "ranking": "top_ranking",
    "ranking_specific": "top_ranking",
    "worth_it": "worth_it",
    "worth_it_specific": "worth_it",
    "is [specific restaurant] worth it": "worth_it",
    "overrated": "overrated",
    "what's overrated": "overrated",
    "underrated": "underrated",
    "what's underrated": "underrated",
    "michelin_value": "michelin_value",
    "michelin_worth_it": "michelin_value",
    "michelin worth": "michelin_value",
    "michelin star restaurants that are actually worth it": "michelin_value",
    "michelin_budget": "michelin_value",
    "best_new": "best_new",
    "global_comparison": "global_comparison",
    "gone_downhill": "gone_downhill",
    "meta_ranking": "meta_ranking",
    "best_in_category": "best_in_category",
    # Experiential
    "meal_planning_tourist": "meal_planning",
    "multi-day plan": "meal_planning",
    "itinerary_3_days": "meal_planning",
    "multi_day_plan": "meal_planning",
    "itinerary_budget_mix": "meal_planning",
    "itinerary": "meal_planning",
    "compromise_query": "compromise",
    "compromise_cuisines": "compromise",
    "compromise on cuisine": "compromise",
    "compromise": "compromise",
    "similar_to": "similar_to",
    "similar to past experience": "similar_to",
    "based_on_like": "similar_to",
    "recommendation": "similar_to",
    "insider_knowledge": "insider_knowledge",
    "insider": "insider_knowledge",
    "chef_eats": "insider_knowledge",
    "chefs choice": "insider_knowledge",
    "chefs_choice": "insider_knowledge",
    "where chefs eat": "insider_knowledge",
    "where_chefs_eat": "insider_knowledge",
    "professional_specific": "professional_specific",
    "progressive_dinner": "food_crawl",
    "heritage_trail": "heritage_trail",
    "emotional_journey": "emotional_journey",
    "thematic_research": "thematic_research",
    "complex_constraint": "complex_constraint",
    "beyond_obvious": "beyond_obvious",
    "avoid_tourist_traps": "beyond_obvious",
    "wine_journey": "food_crawl",
    "lifestyle_constraint": "lifestyle_constraint",
    "guided_food_crawl": "food_crawl",
    "walkable_food_crawl": "food_crawl",
    "neighbourhood_food_trail": "food_crawl",
    "narrative_dining": "narrative_dining",
    "experience": "narrative_dining",
    "food_tour": "food_crawl",
    "food tour": "food_crawl",
    "multi_attribute": "multi_attribute",
    "multi-attribute": "multi_attribute",
    "family_trip": "family_trip",
    "family trip": "family_trip",
    "family_plus_views": "family_trip",
    "after_work": "multi_attribute",
    "after-work": "multi_attribute",
    "vegan_special": "multi_attribute",
    "vegan special": "multi_attribute",
    "locals_brunch": "multi_attribute",
    "locals brunch": "multi_attribute",
    "impress_guests": "impress_guests",
    "impress guests": "impress_guests",
    "solo_traveler": "multi_attribute",
    "solo traveler": "multi_attribute",
    "late_night_plan": "multi_attribute",
    "late night plan": "multi_attribute",
    "decision_helper": "decision_helper",
    "taste_profile": "multi_attribute",
    "taste profile": "multi_attribute",
    "diet_plus_vibe": "multi_attribute",
    "diet plus vibe": "multi_attribute",
}

DIMENSION_NORMALIZE = {
    "cuisine": "cuisine",
    "occasion": "occasion",
    "neighbourhood": "neighbourhood",
    "vibe": "vibe",
    "price": "price",
    "constraint": "constraint",
    "comparison": "comparison",
    "experiential": "experiential",
}


def normalize_text_for_comparison(text: str) -> str:
    """Strip a prompt to its essential words for similarity comparison."""
    text = text.lower().strip()
    # Remove common filler words that don't affect semantic meaning
    text = re.sub(r"[?!.,;:'\"()\[\]{}]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_similarity(a: str, b: str) -> float:
    """Compute similarity between two prompt texts."""
    na = normalize_text_for_comparison(a)
    nb = normalize_text_for_comparison(b)
    return SequenceMatcher(None, na, nb).ratio()


def prompt_naturalness_score(text: str) -> float:
    """Score how natural/conversational a prompt sounds. Higher = more natural."""
    score = 0.0
    # Longer prompts tend to be more natural/conversational
    words = text.split()
    score += min(len(words) / 10, 3.0)
    # Conversational markers
    if any(w in text.lower() for w in ["i'm", "i want", "i need", "i love", "i've", "my "]):
        score += 2.0
    if "?" in text:
        score += 0.5
    # Singlish / local flavor
    if any(w in text.lower() for w in ["lah", "shiok", "atas", "ang moh", "dabao"]):
        score += 1.0
    # Specific details suggest more natural query
    if "$" in text or any(c.isdigit() for c in text):
        score += 0.5
    # Very short/terse prompts are likely less natural
    if len(words) < 6:
        score -= 2.0
    return score


def load_all_raw_prompts() -> list[tuple[dict, str]]:
    """Load all prompts from raw files. Returns list of (prompt_dict, source_name)."""
    all_prompts = []
    for filename, source_name in SOURCE_NAMES.items():
        filepath = RAW_DIR / filename
        if not filepath.exists():
            print(f"  WARNING: {filepath} not found, skipping")
            continue
        raw_text = filepath.read_text(encoding="utf-8")
        # Fix common Unicode issues from LLM-generated JSON
        raw_text = raw_text.replace("\u2028", " ")  # Unicode line separator
        raw_text = raw_text.replace("\u2029", " ")  # Unicode paragraph separator
        raw_text = raw_text.replace("\u201c", '"')   # Left smart quote
        raw_text = raw_text.replace("\u201d", '"')   # Right smart quote
        raw_text = raw_text.replace("\u2018", "'")   # Left single smart quote
        raw_text = raw_text.replace("\u2019", "'")   # Right single smart quote
        raw_text = raw_text.strip()
        # Handle trailing garbage (e.g. Grok file has a trailing "c")
        idx = raw_text.rfind("]")
        if idx != -1 and idx < len(raw_text) - 1:
            raw_text = raw_text[: idx + 1]
        data = json.loads(raw_text)
        print(f"  Loaded {len(data):>3d} prompts from {source_name}")
        for p in data:
            all_prompts.append((p, source_name))
    return all_prompts


def normalize_prompt(raw: dict, source: str) -> dict:
    """Normalize a raw prompt dict to schema-compatible form."""
    dimension = raw.get("dimension", "").lower().strip()
    dimension = DIMENSION_NORMALIZE.get(dimension, dimension)

    category = raw.get("category", "").lower().strip()
    category = CATEGORY_NORMALIZE.get(category, category)
    # Final cleanup: ensure snake_case
    category = re.sub(r"[\s/\-()]+", "_", category).strip("_")

    specificity = raw.get("specificity", "medium").lower().strip()
    if specificity not in ("broad", "medium", "narrow"):
        specificity = "medium"

    return {
        "text": raw["text"].strip(),
        "dimension": dimension,
        "category": category,
        "specificity": specificity,
        "source": source,
    }


def deduplicate(prompts: list[dict]) -> list[dict]:
    """Fuzzy-deduplicate prompts. When duplicates are found, keep the more natural one."""
    # Group by dimension for efficiency
    by_dimension: dict[str, list[dict]] = defaultdict(list)
    for p in prompts:
        by_dimension[p["dimension"]].append(p)

    kept: list[dict] = []
    total_dupes = 0

    for dim, group in by_dimension.items():
        # Track which prompts in this group have been merged away
        merged = [False] * len(group)

        for i in range(len(group)):
            if merged[i]:
                continue
            best = group[i]
            best_score = prompt_naturalness_score(best["text"])
            sources = {best["source"]}

            for j in range(i + 1, len(group)):
                if merged[j]:
                    continue
                sim = text_similarity(best["text"], group[j]["text"])
                if sim >= SIMILARITY_THRESHOLD:
                    merged[j] = True
                    total_dupes += 1
                    sources.add(group[j]["source"])
                    candidate_score = prompt_naturalness_score(group[j]["text"])
                    if candidate_score > best_score:
                        best = group[j]
                        best_score = candidate_score

            best["sources"] = sources
            kept.append(best)

    print(f"\n  Fuzzy duplicates removed: {total_dupes}")
    print(f"  Unique prompts after dedup: {len(kept)}")
    return kept


def thin_to_target(prompts: list[dict], target: int = 140) -> list[dict]:
    """Thin prompts to ~target count while maintaining dimension and specificity coverage.

    Strategy:
    1. Keep only the best prompt per (dimension, category, specificity) slot
    2. Cap at 2 per (dimension, category), preferring specificity diversity
    3. Proportionally trim oversized dimensions, preserving specificity coverage
    """
    MIN_PER_DIM = 13
    SPECS = ["broad", "medium", "narrow"]

    # Phase 1: Best prompt per (dimension, category, specificity) slot
    slots: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for p in prompts:
        key = (p["dimension"], p["category"], p["specificity"])
        slots[key].append(p)

    best_per_slot: list[dict] = []
    for key, group in slots.items():
        group.sort(key=lambda p: prompt_naturalness_score(p["text"]), reverse=True)
        best_per_slot.append(group[0])

    print(f"  After slot dedup (best per dim+cat+spec): {len(best_per_slot)}")

    if len(best_per_slot) <= target:
        return best_per_slot

    # Phase 2: Cap at 2 per (dimension, category), preferring specificity diversity
    cat_groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in best_per_slot:
        cat_groups[(p["dimension"], p["category"])].append(p)

    kept: list[dict] = []
    for key, group in cat_groups.items():
        if len(group) <= 2:
            kept.extend(group)
        else:
            group.sort(key=lambda p: prompt_naturalness_score(p["text"]), reverse=True)
            broad_med = [p for p in group if p["specificity"] in ("broad", "medium")]
            narrow = [p for p in group if p["specificity"] == "narrow"]
            selected = []
            if broad_med:
                selected.append(broad_med[0])
            if narrow:
                selected.append(narrow[0])
            for p in group:
                if p not in selected and len(selected) < 2:
                    selected.append(p)
            kept.extend(selected)

    print(f"  After category thinning (max 2 per cat): {len(kept)}")

    if len(kept) <= target:
        return kept

    # Phase 3: Proportional trimming, but protect specificity coverage per dimension
    for p in kept:
        p["_score"] = prompt_naturalness_score(p["text"])

    # Identify protected prompts: for each dimension, protect at least 1 prompt per specificity
    protected = set()
    dim_prompts_map: dict[str, list[dict]] = defaultdict(list)
    for p in kept:
        dim_prompts_map[p["dimension"]].append(p)

    for dim, dp_list in dim_prompts_map.items():
        for spec in SPECS:
            spec_prompts = [p for p in dp_list if p["specificity"] == spec]
            if spec_prompts:
                # Protect the best one
                spec_prompts.sort(key=lambda p: p["_score"], reverse=True)
                protected.add(id(spec_prompts[0]))

    # Trim from oversized dimensions, largest first
    dim_live = Counter(p["dimension"] for p in kept)
    excess = len(kept) - target
    to_remove = set()

    while len(to_remove) < excess:
        made_progress = False
        for dim, _ in sorted(dim_live.items(), key=lambda x: x[1], reverse=True):
            if len(to_remove) >= excess:
                break
            if dim_live[dim] <= MIN_PER_DIM:
                continue
            removable = [
                p for p in kept
                if p["dimension"] == dim
                and id(p) not in to_remove
                and id(p) not in protected
            ]
            if not removable:
                continue
            removable.sort(key=lambda p: p["_score"])
            to_remove.add(id(removable[0]))
            dim_live[dim] -= 1
            made_progress = True

        if not made_progress:
            break

    result = [p for p in kept if id(p) not in to_remove]
    for p in result:
        p.pop("_score", None)

    print(f"  After proportional trimming: {len(result)}")
    return result


def assign_ids(prompts: list[dict]) -> list[dict]:
    """Assign new IDs in format dimension_NNN, sorted by dimension then specificity."""
    specificity_order = {"broad": 0, "medium": 1, "narrow": 2}
    prompts.sort(
        key=lambda p: (p["dimension"], specificity_order.get(p["specificity"], 1), p["category"])
    )

    counters: dict[str, int] = defaultdict(int)
    for p in prompts:
        counters[p["dimension"]] += 1
        p["id"] = f"{p['dimension']}_{counters[p['dimension']]:03d}"

    return prompts


def validate_and_build(prompts: list[dict]) -> list[DiscoveryPrompt]:
    """Validate all prompts against the Pydantic model."""
    validated = []
    errors = []
    for p in prompts:
        try:
            dp = DiscoveryPrompt(
                id=p["id"],
                text=p["text"],
                dimension=Dimension(p["dimension"]),
                category=p["category"],
                specificity=Specificity(p["specificity"]),
            )
            validated.append(dp)
        except Exception as e:
            errors.append((p, str(e)))

    if errors:
        print(f"\n  VALIDATION ERRORS ({len(errors)}):")
        for p, err in errors[:5]:
            print(f"    {p.get('id', '???')}: {err}")
    else:
        print(f"\n  All {len(validated)} prompts validated against DiscoveryPrompt schema")

    return validated


def print_stats(prompts: list[dict], validated: list[DiscoveryPrompt]) -> None:
    """Print dimension coverage and source contribution stats."""
    print("\n" + "=" * 60)
    print("DIMENSION COVERAGE")
    print("=" * 60)

    dim_counts: dict[str, int] = Counter()
    dim_specificity: dict[str, Counter] = defaultdict(Counter)
    dim_categories: dict[str, set] = defaultdict(set)

    for p in prompts:
        dim_counts[p["dimension"]] += 1
        dim_specificity[p["dimension"]][p["specificity"]] += 1
        dim_categories[p["dimension"]].add(p["category"])

    # Sort by dimension enum order
    dim_order = [d.value for d in Dimension]
    for dim in dim_order:
        count = dim_counts.get(dim, 0)
        specs = dim_specificity.get(dim, Counter())
        cats = dim_categories.get(dim, set())
        bar = "#" * count
        print(f"\n  {dim:<15s}  {count:>3d}  {bar}")
        print(f"    Specificity: broad={specs.get('broad',0)}, medium={specs.get('medium',0)}, narrow={specs.get('narrow',0)}")
        print(f"    Categories ({len(cats)}): {', '.join(sorted(cats)[:8])}", end="")
        if len(cats) > 8:
            print(f" ... +{len(cats)-8} more", end="")
        print()

    total = sum(dim_counts.values())
    print(f"\n  {'TOTAL':<15s}  {total:>3d}")

    # Source contribution
    print("\n" + "=" * 60)
    print("SOURCE CONTRIBUTIONS TO FINAL SET")
    print("=" * 60)

    source_counts: Counter = Counter()
    for p in prompts:
        for s in p.get("sources", {p.get("source", "unknown")}):
            source_counts[s] += 1

    for source, count in source_counts.most_common():
        bar = "#" * (count // 2)
        print(f"  {source:<12s}  {count:>3d} prompts contributed  {bar}")

    # Gap analysis
    print("\n" + "=" * 60)
    print("GAP ANALYSIS")
    print("=" * 60)

    for dim in dim_order:
        count = dim_counts.get(dim, 0)
        if count < 8:
            print(f"  LOW: {dim} has only {count} prompts")
        specs = dim_specificity.get(dim, Counter())
        for spec in ["broad", "medium", "narrow"]:
            if specs.get(spec, 0) == 0:
                print(f"  MISSING: {dim} has no '{spec}' prompts")

    print()


def main():
    print("=" * 60)
    print("SG Restaurant AEO — Prompt Consolidation")
    print("=" * 60)

    # 1. Load
    print("\n[1/5] Loading raw prompts...")
    all_raw = load_all_raw_prompts()
    print(f"  Total raw prompts: {len(all_raw)}")

    # 2. Normalize
    print("\n[2/5] Normalizing...")
    normalized = [normalize_prompt(raw, source) for raw, source in all_raw]
    print(f"  Normalized {len(normalized)} prompts")

    # 3. Deduplicate
    print("\n[3/5] Fuzzy deduplication (threshold={:.0%})...".format(SIMILARITY_THRESHOLD))
    deduped = deduplicate(normalized)

    # 4. Thin to target range
    print("\n[4/6] Thinning to 120-150 target...")
    thinned = thin_to_target(deduped, target=140)

    # 5. Assign IDs
    print("\n[5/6] Assigning IDs...")
    thinned = assign_ids(thinned)

    # 6. Validate
    print("\n[6/6] Validating against Pydantic model...")
    validated = validate_and_build(thinned)

    # Write output
    output_data = [dp.model_dump() for dp in validated]
    OUTPUT_FILE.write_text(json.dumps(output_data, indent=2, ensure_ascii=False) + "\n")
    print(f"\n  Wrote {len(validated)} prompts to {OUTPUT_FILE}")

    # Stats
    print_stats(thinned, validated)


if __name__ == "__main__":
    main()
