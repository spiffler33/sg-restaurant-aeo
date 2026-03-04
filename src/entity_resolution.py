"""Entity resolution for restaurant names.

Collapses 3,000+ raw name variants into canonical restaurant entries using
a three-stage pipeline:
  Stage 1: Exact normalized match (case, unicode, punctuation)
  Stage 2: Base name match (strips location qualifiers, "Restaurant" prefix/suffix)
  Stage 3: Fuzzy match (rapidfuzz token_sort_ratio ≥ threshold)

Uses Union-Find for transitive closure: if A≈B and B≈C, all three merge.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz


# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """Normalize a restaurant name for comparison.

    Handles: unicode, case, punctuation, ampersands, "Singapore" suffix.
    Does NOT strip structural words like "Restaurant" or "The" — that's
    extract_base_name's job.
    """
    # Unicode normalize (café → cafe, smart quotes → ascii)
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    # Lowercase
    name = name.lower().strip()

    # Normalize ampersand
    name = name.replace(" & ", " and ")

    # Remove "singapore" / "sg" suffix
    for suffix in [" singapore", " (singapore)", " - singapore", " sg"]:
        if name.endswith(suffix):
            name = name[: -len(suffix)].rstrip()

    # Normalize dots/periods (PS.Cafe → ps cafe)
    name = name.replace(".", " ")

    # Remove apostrophes and quotes
    name = re.sub(r"['''\"\u201c\u201d`]", "", name)

    # Normalize dashes to space
    name = re.sub(r"[–—-]", " ", name)

    # Remove other punctuation except alphanumeric and spaces
    name = re.sub(r"[^\w\s]", "", name)

    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name


def extract_base_name(normalized: str) -> str:
    """Extract base restaurant name, stripping location qualifiers.

    Handles:
    - "X at Y" → "X" (chain location pattern)
    - "X one fullerton" / "X harding road" → stripped if after known base
    - "Restaurant X" / "X restaurant" → "X"
    - Parenthetical content → removed
    """
    base = normalized

    # Strip "at <location>" suffix
    base = re.sub(r"\s+at\s+\w.*$", "", base)

    # Strip parenthetical content
    base = re.sub(r"\s*\(.*?\)\s*", " ", base).strip()

    # Handle "restaurant X" ↔ "X restaurant" ↔ "X"
    base = re.sub(r"^restaurant\s+", "", base)
    base = re.sub(r"\s+restaurant$", "", base)

    # Handle "The X" → "X" (almost never changes restaurant identity)
    base = re.sub(r"^the\s+", "", base)

    # Collapse whitespace
    base = re.sub(r"\s+", " ", base).strip()

    return base


# ---------------------------------------------------------------------------
# Union-Find for clustering
# ---------------------------------------------------------------------------


class UnionFind:
    """Disjoint set with path compression and union by rank."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.rank: dict[str, int] = {}

    def find(self, x: str) -> str:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: str, y: str) -> None:
        px, py = self.find(x), self.find(y)
        if px == py:
            return
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1

    def get_clusters(self) -> dict[str, list[str]]:
        """Return {root: [members]} for all clusters."""
        clusters: dict[str, list[str]] = defaultdict(list)
        for x in self.parent:
            clusters[self.find(x)].append(x)
        return dict(clusters)


# ---------------------------------------------------------------------------
# Smart similarity scoring
# ---------------------------------------------------------------------------


def compute_similarity(norm_a: str, norm_b: str) -> float:
    """Compute similarity with a penalty for scores inflated by shared generic words.

    Naïve token_sort_ratio gives "Ocean Restaurant" vs "Chang Restaurant" ~87%
    because the shared word "restaurant" dominates. This function detects when
    the unique (non-shared) parts of two names are very different and penalizes
    the score accordingly.

    Examples:
      "ocean restaurant" vs "chang restaurant" → ~87% raw, ~57% adjusted (NO merge)
      "komala vilas" vs "komala villas" → ~92% raw, ~92% adjusted (merge)
      "burnt ends" vs "burnt ends bakery" → ~85% raw, ~85% adjusted (merge)
    """
    raw_score = fuzz.token_sort_ratio(norm_a, norm_b)

    # Decompose into shared and unique words
    words_a = set(norm_a.split())
    words_b = set(norm_b.split())
    shared = words_a & words_b
    unique_a = words_a - shared
    unique_b = words_b - shared

    # If one side has no unique words (e.g., "burnt ends" vs "burnt ends bakery"),
    # the match is likely genuine — the shorter name is contained in the longer
    if not unique_a or not unique_b:
        return raw_score

    # Compare the unique (distinguishing) parts
    unique_str_a = " ".join(sorted(unique_a))
    unique_str_b = " ".join(sorted(unique_b))
    unique_score = fuzz.ratio(unique_str_a, unique_str_b)

    # If the unique parts are similar, no penalty needed
    # (e.g., "vilas" vs "villas" → unique_score ~91%)
    # Threshold 70 avoids false positives on short unrelated words:
    # "ocean" vs "chang" = 60%, "azmi" vs "bam" = 57% (should be penalized)
    # "vilas" vs "villas" = 91%, "nonya" vs "nyonya" = 91% (should NOT be penalized)
    if unique_score >= 70:
        return raw_score

    # The unique parts are very different — shared words are inflating the score.
    # Apply a penalty proportional to how much the shared words dominate.
    shared_ratio = len(shared) / max(len(words_a), len(words_b))
    penalty = shared_ratio * 0.5  # Up to 50% penalty when shared words dominate
    return raw_score * (1.0 - penalty)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class NameInfo:
    """Metadata for a restaurant name from the DB."""

    original_name: str
    mention_count: int
    models: set[str]
    neighbourhoods: set[str]
    normalized: str = ""
    base_name: str = ""


@dataclass
class MergeRecord:
    """Auditable record of a merge decision."""

    canonical_name: str
    merged_name: str
    merge_reason: str  # "exact_normalized", "base_name_fuzzy_NN", "fuzzy_NN"
    similarity_score: float


@dataclass
class CanonicalEntry:
    """A resolved canonical restaurant."""

    canonical_id: int
    canonical_name: str
    variant_names: list[str]
    total_mentions: int
    model_count: int
    models_mentioning: list[str]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_name_metadata(conn: sqlite3.Connection) -> dict[str, NameInfo]:
    """Load all unique restaurant names with aggregated metadata."""
    rows = conn.execute(
        """
        SELECT
            rm.restaurant_name,
            COUNT(*) as total_mentions,
            GROUP_CONCAT(DISTINCT qr.model_name) as models,
            GROUP_CONCAT(DISTINCT rm.neighbourhood) as neighbourhoods
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        GROUP BY rm.restaurant_name
        """
    ).fetchall()

    result: dict[str, NameInfo] = {}
    for row in rows:
        name = row["restaurant_name"]
        models_str = row["models"]
        hoods_str = row["neighbourhoods"]

        info = NameInfo(
            original_name=name,
            mention_count=row["total_mentions"],
            models=set(models_str.split(",")) if models_str else set(),
            neighbourhoods=set(h for h in (hoods_str or "").split(",") if h),
        )
        info.normalized = normalize_name(name)
        info.base_name = extract_base_name(info.normalized)
        result[name] = info

    return result


# ---------------------------------------------------------------------------
# Resolution pipeline
# ---------------------------------------------------------------------------


def resolve(
    name_infos: dict[str, NameInfo],
    fuzzy_threshold: int = 85,
    borderline_threshold: int = 75,
) -> tuple[dict[str, list[str]], list[MergeRecord], list[tuple[str, str, float]]]:
    """Run the three-stage entity resolution pipeline.

    Args:
        name_infos: {original_name: NameInfo} from load_name_metadata
        fuzzy_threshold: minimum score for auto-merge in Stage 3
        borderline_threshold: minimum score for borderline flagging

    Returns:
        canonical_clusters: {canonical_name: [all_variant_names]}
        merge_log: list of MergeRecord for auditing
        borderline_pairs: list of (name_a, name_b, score) for LLM review
    """
    uf = UnionFind()
    merge_log: list[MergeRecord] = []
    names = list(name_infos.keys())

    # Initialize all names in union-find
    for name in names:
        uf.find(name)

    # -------------------------------------------------------------------
    # Stage 1: Exact normalized match
    # -------------------------------------------------------------------
    normalized_groups: dict[str, list[str]] = defaultdict(list)
    for name, info in name_infos.items():
        normalized_groups[info.normalized].append(name)

    stage1_merges = 0
    for norm, group in normalized_groups.items():
        if len(group) > 1:
            # Anchor = most mentioned variant
            group.sort(key=lambda n: name_infos[n].mention_count, reverse=True)
            anchor = group[0]
            for other in group[1:]:
                uf.union(anchor, other)
                merge_log.append(
                    MergeRecord(
                        canonical_name=anchor,
                        merged_name=other,
                        merge_reason="exact_normalized",
                        similarity_score=100.0,
                    )
                )
                stage1_merges += 1

    # -------------------------------------------------------------------
    # Stage 2: Base name match
    # Handles "PS.Cafe at Dempsey Hill" → base "ps cafe" merging with "PS.Cafe"
    # -------------------------------------------------------------------
    base_groups: dict[str, list[str]] = defaultdict(list)
    for name, info in name_infos.items():
        base_groups[info.base_name].append(name)

    stage2_merges = 0
    for base, group in base_groups.items():
        if len(group) <= 1 or len(base) < 4:
            continue
        # Sort by mention count — most mentioned first
        group.sort(key=lambda n: name_infos[n].mention_count, reverse=True)
        anchor = group[0]
        for other in group[1:]:
            if uf.find(anchor) == uf.find(other):
                continue
            # Sanity check: fuzzy match between normalized forms
            score = fuzz.token_sort_ratio(
                name_infos[anchor].normalized,
                name_infos[other].normalized,
            )
            if score >= 60:
                uf.union(anchor, other)
                merge_log.append(
                    MergeRecord(
                        canonical_name=anchor,
                        merged_name=other,
                        merge_reason=f"base_name_fuzzy_{score:.0f}",
                        similarity_score=score,
                    )
                )
                stage2_merges += 1

    # -------------------------------------------------------------------
    # Stage 3: Fuzzy matching between cluster representatives
    # -------------------------------------------------------------------
    # Get current cluster representatives
    clusters = uf.get_clusters()
    rep_to_root: dict[str, str] = {}
    for root, members in clusters.items():
        rep = max(members, key=lambda n: name_infos[n].mention_count)
        rep_to_root[rep] = root

    rep_names = list(rep_to_root.keys())
    rep_normalized = {name: name_infos[name].normalized for name in rep_names}

    stage3_merges = 0
    borderline_pairs: list[tuple[str, str, float]] = []

    # Compare all pairs (with length filter for speed)
    for i in range(len(rep_names)):
        name_a = rep_names[i]
        norm_a = rep_normalized[name_a]
        len_a = len(norm_a)

        for j in range(i + 1, len(rep_names)):
            name_b = rep_names[j]

            # Skip if already in same cluster (could have merged transitively)
            if uf.find(name_a) == uf.find(name_b):
                continue

            norm_b = rep_normalized[name_b]
            len_b = len(norm_b)

            # Length filter: skip if lengths differ by >50%
            if abs(len_a - len_b) > max(len_a, len_b) * 0.5:
                continue

            # Skip very short names (avoid false merges on "Bar", "Wok")
            if min(len_a, len_b) < 5:
                continue

            score = compute_similarity(norm_a, norm_b)

            if score >= fuzzy_threshold:
                uf.union(name_a, name_b)
                # Canonical = higher mention count
                canonical = max(
                    name_a, name_b, key=lambda n: name_infos[n].mention_count
                )
                merged = min(
                    name_a, name_b, key=lambda n: name_infos[n].mention_count
                )
                merge_log.append(
                    MergeRecord(
                        canonical_name=canonical,
                        merged_name=merged,
                        merge_reason=f"fuzzy_{score:.0f}",
                        similarity_score=score,
                    )
                )
                stage3_merges += 1
            elif score >= borderline_threshold:
                borderline_pairs.append((name_a, name_b, score))

    # -------------------------------------------------------------------
    # Stage 4: Manual merges for known cases
    # -------------------------------------------------------------------
    manual_count = apply_manual_merges(uf, MANUAL_MERGES, name_infos, merge_log)

    # -------------------------------------------------------------------
    # Build final clusters with canonical names
    # -------------------------------------------------------------------
    final_clusters = uf.get_clusters()
    canonical_clusters: dict[str, list[str]] = {}

    for root, members in final_clusters.items():
        # Check if any manual merge specifies a canonical name for this cluster
        manual_canonical = None
        for canonical_name, names_to_merge in MANUAL_MERGES:
            if canonical_name in members:
                manual_canonical = canonical_name
                break

        if manual_canonical:
            canonical = manual_canonical
        else:
            # Default: most mentioned variant
            canonical = max(
                members, key=lambda n: (name_infos[n].mention_count, -len(n))
            )

        canonical_clusters[canonical] = sorted(
            members, key=lambda n: -name_infos[n].mention_count
        )

    return canonical_clusters, merge_log, borderline_pairs, manual_count


# ---------------------------------------------------------------------------
# Manual merges for cases the automated pipeline can't catch
# ---------------------------------------------------------------------------

# Each entry: (canonical_name, [names_to_merge_into_it])
# These are ORIGINAL restaurant_name values from the DB.
MANUAL_MERGES: list[tuple[str, list[str]]] = [
    # Same chain, compound word split (海底捞 = Haidilao)
    ("Hai Di Lao", ["Haidilao"]),
    # Same Michelin-starred hawker stall — Liao Fan is the founder,
    # Hawker Chan is the brand name after Michelin recognition
    (
        "Liao Fan Hong Kong Soya Sauce Chicken Rice & Noodle",
        ["Hawker Chan", "Liao Fan Hawker Chan"],
    ),
    # Same restaurant, abbreviated name
    ("Hashida Sushi", ["Hashida", "Hashida Singapore"]),
    # Same restaurant, space-in-compound-word (凌芝素食)
    ("LingZhi Vegetarian", ["Ling Zhi Vegetarian", "LingZhi Restaurant"]),
]


def apply_manual_merges(
    uf: UnionFind,
    manual_merges: list[tuple[str, list[str]]],
    name_infos: dict[str, NameInfo],
    merge_log: list[MergeRecord],
) -> int:
    """Apply manual merge overrides after automated stages.

    Returns the number of merges applied.
    """
    count = 0
    for canonical_name, names_to_merge in manual_merges:
        if canonical_name not in name_infos:
            continue
        for name in names_to_merge:
            if name not in name_infos:
                continue
            if uf.find(canonical_name) == uf.find(name):
                continue  # Already merged by automated stages
            uf.union(canonical_name, name)
            merge_log.append(
                MergeRecord(
                    canonical_name=canonical_name,
                    merged_name=name,
                    merge_reason="manual",
                    similarity_score=100.0,
                )
            )
            count += 1
    return count


def build_canonical_entries(
    canonical_clusters: dict[str, list[str]],
    name_infos: dict[str, NameInfo],
) -> list[CanonicalEntry]:
    """Build CanonicalEntry objects with aggregated stats."""
    entries: list[CanonicalEntry] = []

    for idx, (canonical_name, variants) in enumerate(
        sorted(
            canonical_clusters.items(),
            key=lambda kv: sum(name_infos[n].mention_count for n in kv[1]),
            reverse=True,
        ),
        start=1,
    ):
        total_mentions = sum(name_infos[n].mention_count for n in variants)
        all_models: set[str] = set()
        for v in variants:
            all_models.update(name_infos[v].models)

        entries.append(
            CanonicalEntry(
                canonical_id=idx,
                canonical_name=canonical_name,
                variant_names=variants,
                total_mentions=total_mentions,
                model_count=len(all_models),
                models_mentioning=sorted(all_models),
            )
        )

    return entries
