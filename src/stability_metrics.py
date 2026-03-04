"""Stability metrics for LLM recommendation reproducibility analysis.

Computes per (prompt × model × search_mode) stability across repeated runs:
  - Jaccard similarity: set overlap between runs
  - Kendall's tau: rank correlation for shared restaurants
  - Core vs stochastic classification: how often each restaurant appears
"""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from typing import Optional

from scipy.stats import kendalltau


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class RunData:
    """Restaurants from one run of a prompt × model × search combo."""

    run_number: int
    canonical_ids: list[int]  # ordered by rank_position
    restaurant_names: list[str]  # ordered by rank_position, for display


@dataclass
class CellMetrics:
    """Stability metrics for one (prompt × model × search_mode) cell."""

    prompt_id: str
    model_name: str
    search_enabled: bool
    n_runs: int
    mean_jaccard: float
    mean_kendall_tau: Optional[float]
    core_count: int  # restaurants in ≥80% of runs
    stochastic_count: int  # restaurants in <40% of runs
    mid_count: int  # restaurants in between
    total_unique: int
    core_pct: float
    runs: list[RunData] = field(default_factory=list)


@dataclass
class StabilityReport:
    """Full stability report with cross-cuts."""

    cells: list[CellMetrics]
    # Aggregated cross-cuts
    by_model: dict[str, dict]  # model -> {mean_jaccard, mean_tau, n_cells}
    by_specificity: dict[str, dict]  # specificity -> {mean_jaccard, mean_tau}
    by_search: dict[str, dict]  # "ON"/"OFF" -> {mean_jaccard, mean_tau}
    total_queries: int
    total_tokens: int


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------


def compute_jaccard(sets: list[set]) -> float:
    """Compute mean pairwise Jaccard similarity across a list of sets.

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    Returns 0.0 if fewer than 2 sets or all empty.
    """
    if len(sets) < 2:
        return 0.0

    total = 0.0
    n_pairs = 0
    for a, b in combinations(sets, 2):
        union = a | b
        if not union:
            continue
        total += len(a & b) / len(union)
        n_pairs += 1

    return total / n_pairs if n_pairs > 0 else 0.0


def compute_kendall_tau(rankings: list[dict[int, int]]) -> Optional[float]:
    """Compute mean pairwise Kendall's tau across rankings.

    Each ranking is a dict {canonical_id: rank_position}. Only restaurants
    appearing in both rankings of a pair are compared.

    Returns None if insufficient shared items for comparison.
    """
    if len(rankings) < 2:
        return None

    taus = []
    for r1, r2 in combinations(rankings, 2):
        shared = set(r1.keys()) & set(r2.keys())
        if len(shared) < 3:
            continue  # Need at least 3 items for meaningful tau

        ordered = sorted(shared)
        ranks_a = [r1[k] for k in ordered]
        ranks_b = [r2[k] for k in ordered]

        tau, p_value = kendalltau(ranks_a, ranks_b)
        if not (tau != tau):  # Check for NaN
            taus.append(tau)

    return sum(taus) / len(taus) if taus else None


def classify_core_stochastic(
    appearance_counts: dict[int, int], n_runs: int
) -> tuple[list[int], list[int], list[int]]:
    """Classify restaurants as core, mid, or stochastic.

    Core: appears in ≥80% of runs (e.g., 4/5 or 3/3)
    Stochastic: appears in ≤40% of runs (e.g., 1/5 or 2/5)
    Mid: everything in between

    Args:
        appearance_counts: {canonical_id: n_appearances}
        n_runs: total number of runs

    Returns:
        (core_ids, mid_ids, stochastic_ids)
    """
    core_threshold = max(1, int(n_runs * 0.8))
    stochastic_threshold = max(1, int(n_runs * 0.4))

    core = []
    mid = []
    stochastic = []

    for cid, count in appearance_counts.items():
        if count >= core_threshold:
            core.append(cid)
        elif count <= stochastic_threshold:
            stochastic.append(cid)
        else:
            mid.append(cid)

    return core, mid, stochastic


# ---------------------------------------------------------------------------
# Main analysis: load stability data and compute all metrics
# ---------------------------------------------------------------------------


def load_stability_runs(conn: sqlite3.Connection) -> dict[tuple, list[RunData]]:
    """Load stability test data grouped by (prompt_id, model_name, search_enabled).

    Returns:
        {(prompt_id, model, search): [RunData, ...]}
    """
    rows = conn.execute(
        """
        SELECT
            qr.prompt_id, qr.model_name, qr.search_enabled, qr.run_number,
            rm.canonical_id, rm.restaurant_name, rm.rank_position
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        WHERE qr.is_stability_test = 1
          AND rm.canonical_id IS NOT NULL
        ORDER BY qr.prompt_id, qr.model_name, qr.search_enabled,
                 qr.run_number, rm.rank_position
        """
    ).fetchall()

    # Group by (prompt, model, search, run)
    run_map: dict[tuple, dict[int, RunData]] = defaultdict(dict)
    for row in rows:
        key = (row["prompt_id"], row["model_name"], bool(row["search_enabled"]))
        rn = row["run_number"]
        if rn not in run_map[key]:
            run_map[key][rn] = RunData(
                run_number=rn, canonical_ids=[], restaurant_names=[]
            )
        run_map[key][rn].canonical_ids.append(row["canonical_id"])
        run_map[key][rn].restaurant_names.append(row["restaurant_name"])

    # Convert to list of RunData per cell
    result: dict[tuple, list[RunData]] = {}
    for key, runs_dict in run_map.items():
        result[key] = [runs_dict[rn] for rn in sorted(runs_dict.keys())]

    return result


def compute_cell_metrics(
    prompt_id: str,
    model_name: str,
    search_enabled: bool,
    runs: list[RunData],
) -> CellMetrics:
    """Compute all stability metrics for one (prompt × model × search) cell."""
    n_runs = len(runs)

    # Build sets and rankings for each run
    sets = [set(r.canonical_ids) for r in runs]
    rankings = [
        {cid: rank for rank, cid in enumerate(r.canonical_ids, 1)}
        for r in runs
    ]

    # Jaccard
    mean_jaccard = compute_jaccard(sets)

    # Kendall's tau
    mean_tau = compute_kendall_tau(rankings)

    # Core/stochastic classification
    appearance_counts: dict[int, int] = defaultdict(int)
    for s in sets:
        for cid in s:
            appearance_counts[cid] += 1

    core, mid, stochastic = classify_core_stochastic(appearance_counts, n_runs)
    total_unique = len(appearance_counts)

    return CellMetrics(
        prompt_id=prompt_id,
        model_name=model_name,
        search_enabled=search_enabled,
        n_runs=n_runs,
        mean_jaccard=mean_jaccard,
        mean_kendall_tau=mean_tau,
        core_count=len(core),
        stochastic_count=len(stochastic),
        mid_count=len(mid),
        total_unique=total_unique,
        core_pct=len(core) / total_unique * 100 if total_unique > 0 else 0.0,
        runs=runs,
    )


def compute_all_metrics(
    conn: sqlite3.Connection,
    prompt_specificities: dict[str, str],
) -> StabilityReport:
    """Compute stability metrics for all (prompt × model × search) cells.

    Args:
        conn: SQLite connection with stability test data
        prompt_specificities: {prompt_id: specificity} for cross-cut analysis

    Returns:
        StabilityReport with per-cell and aggregated metrics
    """
    runs_by_cell = load_stability_runs(conn)

    cells = []
    for (prompt_id, model, search), runs in runs_by_cell.items():
        cell = compute_cell_metrics(prompt_id, model, search, runs)
        cells.append(cell)

    # Aggregate by model
    by_model: dict[str, dict] = defaultdict(lambda: {"jaccards": [], "taus": []})
    for c in cells:
        by_model[c.model_name]["jaccards"].append(c.mean_jaccard)
        if c.mean_kendall_tau is not None:
            by_model[c.model_name]["taus"].append(c.mean_kendall_tau)

    by_model_agg = {}
    for model, data in by_model.items():
        j = data["jaccards"]
        t = data["taus"]
        by_model_agg[model] = {
            "mean_jaccard": sum(j) / len(j) if j else 0.0,
            "mean_tau": sum(t) / len(t) if t else None,
            "n_cells": len(j),
        }

    # Aggregate by specificity
    by_spec: dict[str, dict] = defaultdict(lambda: {"jaccards": [], "taus": []})
    for c in cells:
        spec = prompt_specificities.get(c.prompt_id, "unknown")
        by_spec[spec]["jaccards"].append(c.mean_jaccard)
        if c.mean_kendall_tau is not None:
            by_spec[spec]["taus"].append(c.mean_kendall_tau)

    by_spec_agg = {}
    for spec, data in by_spec.items():
        j = data["jaccards"]
        t = data["taus"]
        by_spec_agg[spec] = {
            "mean_jaccard": sum(j) / len(j) if j else 0.0,
            "mean_tau": sum(t) / len(t) if t else None,
            "n_cells": len(j),
        }

    # Aggregate by search mode
    by_search: dict[str, dict] = defaultdict(lambda: {"jaccards": [], "taus": []})
    for c in cells:
        mode = "ON" if c.search_enabled else "OFF"
        by_search[mode]["jaccards"].append(c.mean_jaccard)
        if c.mean_kendall_tau is not None:
            by_search[mode]["taus"].append(c.mean_kendall_tau)

    by_search_agg = {}
    for mode, data in by_search.items():
        j = data["jaccards"]
        t = data["taus"]
        by_search_agg[mode] = {
            "mean_jaccard": sum(j) / len(j) if j else 0.0,
            "mean_tau": sum(t) / len(t) if t else None,
            "n_cells": len(j),
        }

    # Total queries and tokens
    stats = conn.execute(
        """
        SELECT COUNT(*) as n, COALESCE(SUM(token_usage), 0) as tokens
        FROM query_results WHERE is_stability_test = 1
        """
    ).fetchone()

    return StabilityReport(
        cells=cells,
        by_model=by_model_agg,
        by_specificity=by_spec_agg,
        by_search=by_search_agg,
        total_queries=stats["n"],
        total_tokens=stats["tokens"],
    )
