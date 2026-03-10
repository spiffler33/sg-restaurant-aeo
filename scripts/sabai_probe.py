#!/usr/bin/env python3
"""Sabai Fine Thai on the Bay — Targeted AEO Probe.

Tests how specific a prompt must be for LLMs to surface a restaurant
with zero mentions across the main 1,690-query dataset.

Target:  Sabai Fine Thai on the Bay
Address: 70 Collyer Quay, Customs House, Marina Bay, Singapore

Methodology: 20 prompts in 4 tiers (generic → near-name) × 4 models × 2 search modes = 160 queries.
Results are kept separate from the main dataset.

Usage:
    python scripts/sabai_probe.py --dry-run       # Show prompts + cost estimate
    python scripts/sabai_probe.py                  # Full run: query + parse + analyze
    python scripts/sabai_probe.py --skip-queries   # Re-parse + re-analyze saved results
    python scripts/sabai_probe.py --analyze-only   # Re-analyze saved parsed results
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.models import DiscoveryPrompt, Dimension, ModelName, Specificity
from src.query_runner import query_model
from src.response_parser import parse_batch

console = Console()

# ─── Paths ──────────────────────────────────────────────────────────
RAW_DIR = Path(__file__).parent.parent / "data" / "raw" / "sabai_probe"
REPORT_PATH = Path(__file__).parent.parent / "data" / "processed" / "sabai_probe_report.md"
RESULTS_PATH = RAW_DIR / "results.json"
PARSED_PATH = RAW_DIR / "parsed.json"

# ─── Model display names ────────────────────────────────────────────
MODEL_SHORT = {
    "openai/gpt-4o": "GPT-4o",
    "anthropic/claude-sonnet-4-20250514": "Claude",
    "google/gemini-2.5-flash": "Gemini",
    "perplexity/sonar": "Pplx",
}

MODELS = list(ModelName)

# Concurrency limits (matching existing sweep scripts)
PROVIDER_CONCURRENCY = {
    ModelName.GPT_4O: 4,
    ModelName.CLAUDE_SONNET: 4,
    ModelName.GEMINI_PRO: 3,
    ModelName.PERPLEXITY_SONAR: 2,
}

# Cost per query estimates (from main sweep actual costs)
# Search OFF: $0.97 / 560 queries, broken down by model
# Search ON: $65.38 / 560 queries, Claude dominates ($64.71)
COST_PER_QUERY = {
    (ModelName.GPT_4O, False): 0.0024,
    (ModelName.GPT_4O, True): 0.0048,
    (ModelName.CLAUDE_SONNET, False): 0.0035,
    (ModelName.CLAUDE_SONNET, True): 0.462,  # web_search tool fetches full pages
    (ModelName.GEMINI_PRO, False): 0.0006,
    (ModelName.GEMINI_PRO, True): 0.001,
    (ModelName.PERPLEXITY_SONAR, False): 0.0005,
    (ModelName.PERPLEXITY_SONAR, True): 0.001,
}
PARSE_COST_PER_QUERY = 0.006  # Haiku parsing cost

# Location keywords for name confusion detection
SABAI_KEYWORDS = ["customs house", "collyer quay", "70 collyer", "marina bay"]
SARAI_KEYWORDS = ["tanglin", "tanglin mall", "tanglin road", "163 tanglin"]


# ═══════════════════════════════════════════════════════════════════
# Probe Prompts — 4 tiers, 20 prompts
# ═══════════════════════════════════════════════════════════════════

TIER_NAMES = {
    1: "Generic",
    2: "Location-narrowed",
    3: "Attribute-specific",
    4: "Near-name",
}

PROBE_PROMPTS = [
    # Tier 1 — Generic: Sabai could appear but probably won't
    {"id": "sabai_t1_001", "tier": 1, "text": "Best Thai restaurants in Singapore"},
    {"id": "sabai_t1_002", "tier": 1, "text": "Upscale Thai dining in Singapore"},
    {"id": "sabai_t1_003", "tier": 1, "text": "Thai restaurant recommendations Singapore"},
    {"id": "sabai_t1_004", "tier": 1, "text": "Where to eat Thai food in Singapore that's a step above casual"},
    {"id": "sabai_t1_005", "tier": 1, "text": "Fine dining Thai food Singapore"},
    # Tier 2 — Location-narrowed: Add Sabai's geographic differentiators
    {"id": "sabai_t2_001", "tier": 2, "text": "Good Thai restaurant near Marina Bay Singapore"},
    {"id": "sabai_t2_002", "tier": 2, "text": "Restaurants at Customs House Collyer Quay Singapore"},
    {"id": "sabai_t2_003", "tier": 2, "text": "Thai food near Raffles Place / CBD area Singapore"},
    {"id": "sabai_t2_004", "tier": 2, "text": "Waterfront restaurants near Marina Bay with Asian food"},
    {"id": "sabai_t2_005", "tier": 2, "text": "Where to eat near Fullerton Hotel Singapore"},
    # Tier 3 — Attribute-specific: Target Sabai's unique selling points
    {"id": "sabai_t3_001", "tier": 3, "text": "Thai restaurant with a bay view in Singapore"},
    {"id": "sabai_t3_002", "tier": 3, "text": "Royal Thai cuisine in Singapore"},
    {"id": "sabai_t3_003", "tier": 3, "text": "Upscale Thai restaurant with set lunch near Raffles Place"},
    {"id": "sabai_t3_004", "tier": 3, "text": "Thai restaurant Singapore with chef trained in Thai royal palace cooking"},
    {"id": "sabai_t3_005", "tier": 3, "text": "Romantic Thai restaurant with waterfront view Singapore"},
    # Tier 4 — Near-name: Test name recognition and Sabai/Sarai confusion
    {"id": "sabai_t4_001", "tier": 4, "text": "Is Sabai Fine Thai on the Bay any good?"},
    {"id": "sabai_t4_002", "tier": 4, "text": "Sabai vs Sarai Thai restaurant Singapore — what's the difference?"},
    {"id": "sabai_t4_003", "tier": 4, "text": "Tell me about Sabai Fine Thai Singapore"},
    {"id": "sabai_t4_004", "tier": 4, "text": "Thai restaurants in Singapore with 'Sabai' in the name"},
    {"id": "sabai_t4_005", "tier": 4, "text": "What's the Thai restaurant at Customs House Singapore?"},
]


def make_discovery_prompts() -> list[DiscoveryPrompt]:
    """Convert probe prompts to DiscoveryPrompt objects for query_model."""
    tier_to_specificity = {
        1: Specificity.BROAD,
        2: Specificity.MEDIUM,
        3: Specificity.NARROW,
        4: Specificity.NARROW,
    }
    return [
        DiscoveryPrompt(
            id=p["id"],
            text=p["text"],
            dimension=Dimension.CUISINE,
            category=f"sabai_probe_t{p['tier']}",
            specificity=tier_to_specificity[p["tier"]],
        )
        for p in PROBE_PROMPTS
    ]


# ═══════════════════════════════════════════════════════════════════
# Cost Estimation
# ═══════════════════════════════════════════════════════════════════

def estimate_cost(n_prompts: int) -> dict:
    """Estimate total cost based on historical per-query costs."""
    breakdown = {}
    for model in MODELS:
        for search in [False, True]:
            key = (model, search)
            cost = n_prompts * COST_PER_QUERY[key]
            breakdown[key] = cost

    query_cost = sum(breakdown.values())
    total_queries = n_prompts * len(MODELS) * 2  # 2 search modes
    parse_cost = total_queries * PARSE_COST_PER_QUERY
    claude_on = n_prompts * COST_PER_QUERY[(ModelName.CLAUDE_SONNET, True)]

    return {
        "total_queries": total_queries,
        "query_cost": query_cost,
        "parse_cost": parse_cost,
        "total_cost": query_cost + parse_cost,
        "claude_search_on_cost": claude_on,
        "breakdown": breakdown,
    }


def print_cost_estimate(est: dict):
    """Print formatted cost estimate to console."""
    table = Table(title="Cost Estimate", show_lines=False)
    table.add_column("Component", style="cyan")
    table.add_column("Amount", justify="right", style="yellow")

    table.add_row("Total queries", str(est["total_queries"]))
    table.add_row("Query cost", f"${est['query_cost']:.2f}")
    table.add_row("  Claude search ON (dominates)", f"${est['claude_search_on_cost']:.2f}")
    table.add_row("  All other queries", f"${est['query_cost'] - est['claude_search_on_cost']:.2f}")
    table.add_row("Parse cost (Haiku)", f"${est['parse_cost']:.2f}")
    table.add_row("[bold]Total estimated[/bold]", f"[bold]${est['total_cost']:.2f}[/bold]")
    console.print(table)


# ═══════════════════════════════════════════════════════════════════
# Query Execution
# ═══════════════════════════════════════════════════════════════════

async def run_probe_queries(prompts: list[DiscoveryPrompt]) -> list[dict]:
    """Run all probe queries across all models and search modes.

    Returns list of result dicts with idx, prompt metadata, model, search,
    raw_response, latency, tokens, timestamp. Also saves to results.json.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    lock = asyncio.Lock()
    start_time = time.monotonic()

    provider_semas = {
        model: asyncio.Semaphore(limit)
        for model, limit in PROVIDER_CONCURRENCY.items()
    }

    # Build task list: every prompt × model × search mode
    task_list: list[tuple[DiscoveryPrompt, ModelName, bool]] = []
    prompt_lookup = {p.id: p for p in prompts}
    for p in PROBE_PROMPTS:
        dp = prompt_lookup[p["id"]]
        for model in MODELS:
            for search in [False, True]:
                task_list.append((dp, model, search))

    total = len(task_list)
    completed = 0
    failed = 0

    async def run_one(prompt: DiscoveryPrompt, model: ModelName, search: bool) -> None:
        nonlocal completed, failed
        async with provider_semas[model]:
            try:
                result = await query_model(prompt, model, search_enabled=search)
                entry = {
                    "prompt_id": prompt.id,
                    "tier": int(prompt.id.split("_")[1][1]),  # "sabai_t1_001" -> 1
                    "prompt_text": prompt.text,
                    "model": model.value,
                    "search_enabled": search,
                    "raw_response": result.raw_response,
                    "latency_ms": result.latency_ms,
                    "token_usage": result.token_usage,
                    "timestamp": result.timestamp.isoformat(),
                }
                async with lock:
                    entry["idx"] = len(results)
                    results.append(entry)
                    completed += 1
                    if completed % 10 == 0 or completed == total:
                        elapsed = time.monotonic() - start_time
                        rate = completed / elapsed * 60 if elapsed > 0 else 0
                        console.print(
                            f"  [dim]{completed}/{total} done "
                            f"({completed/total*100:.0f}%) | "
                            f"{rate:.0f} q/min | "
                            f"{elapsed/60:.1f}m elapsed | "
                            f"{failed} failed[/dim]"
                        )
            except Exception as e:
                async with lock:
                    failed += 1
                    completed += 1
                    console.print(
                        f"  [red]FAIL[/red] {prompt.id} / "
                        f"{MODEL_SHORT.get(model.value, model.value)} / "
                        f"{'ON' if search else 'OFF'}: {e}"
                    )

    console.print(f"\n[bold]Running {total} probe queries...[/bold]")
    await asyncio.gather(*[run_one(p, m, s) for p, m, s in task_list])

    elapsed = time.monotonic() - start_time
    console.print(
        f"\n[green]Done.[/green] {completed - failed} succeeded, "
        f"{failed} failed in {elapsed/60:.1f} minutes"
    )

    # Save all results
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    console.print(f"Saved {len(results)} results to {RESULTS_PATH}")

    return results


# ═══════════════════════════════════════════════════════════════════
# Parsing
# ═══════════════════════════════════════════════════════════════════

async def parse_probe_responses(results: list[dict]) -> list[dict]:
    """Parse all probe responses using the existing Haiku-based parser.

    Does NOT write to the main database. Returns parsed dicts and saves
    to parsed.json for re-analysis.
    """
    # Build query_rows in the format parse_batch expects
    query_rows = [
        {
            "id": r["idx"],
            "raw_response": r["raw_response"],
            "model_name": r["model"],
            "prompt_id": r["prompt_id"],
        }
        for r in results
    ]

    parsed_responses, in_tokens, out_tokens = await parse_batch(
        query_rows, max_concurrent=10
    )

    parse_cost = (in_tokens + out_tokens) / 1_000_000 * 1.0  # ~$1/M for Haiku
    console.print(
        f"  Parsing tokens: {in_tokens:,} input + {out_tokens:,} output "
        f"(~${parse_cost:.2f})"
    )

    # Serialize to dicts
    parsed_dicts = []
    for pr in parsed_responses:
        parsed_dicts.append({
            "query_result_id": pr.query_result_id,
            "restaurants": [
                {
                    "restaurant_name": m.restaurant_name,
                    "rank_position": m.rank_position,
                    "neighbourhood": m.neighbourhood,
                    "cuisine_tags": m.cuisine_tags,
                    "vibe_tags": m.vibe_tags,
                    "price_indicator": m.price_indicator.value
                    if hasattr(m.price_indicator, "value")
                    else str(m.price_indicator),
                    "descriptors": m.descriptors,
                    "sentiment": m.sentiment.value
                    if hasattr(m.sentiment, "value")
                    else str(m.sentiment),
                    "is_primary_recommendation": m.is_primary_recommendation,
                }
                for m in pr.restaurants
            ],
            "parse_model": pr.parse_model,
            "parsed_at": pr.parsed_at.isoformat(),
        })

    PARSED_PATH.write_text(json.dumps(parsed_dicts, indent=2, ensure_ascii=False))
    console.print(f"Saved {len(parsed_dicts)} parsed responses to {PARSED_PATH}")

    return parsed_dicts


# ═══════════════════════════════════════════════════════════════════
# Analysis Functions
# ═══════════════════════════════════════════════════════════════════

def _short(model_value: str) -> str:
    """Model value → short display name."""
    return MODEL_SHORT.get(model_value, model_value.split("/")[1])


def _col_keys() -> list[tuple[str, str]]:
    """Generate ordered (model_value, search_label) column keys."""
    keys = []
    for model in MODELS:
        for search_label in ["OFF", "ON"]:
            keys.append((model.value, search_label))
    return keys


def _search_label(enabled: bool) -> str:
    return "ON" if enabled else "OFF"


def _find_rank(parsed: dict | None, needle: str) -> int | None:
    """Find a restaurant's rank in parsed mentions by substring match."""
    if not parsed:
        return None
    for m in parsed.get("restaurants", []):
        if needle.lower() in m["restaurant_name"].lower():
            return m["rank_position"]
    return None


def build_detection_matrix(
    results: list[dict],
    parsed_map: dict[int, dict],
    target: str,
) -> list[dict]:
    """Build a detection matrix: rows = prompts, columns = model × search.

    Cell values:
        '#N'  — detected at rank N in structured parse
        'Yes*' — found in raw text but not in structured parse
        '—'   — not detected
    """
    prompt_order = {p["id"]: i for i, p in enumerate(PROBE_PROMPTS)}

    by_prompt: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_prompt[r["prompt_id"]].append(r)

    rows = []
    for prompt_id in sorted(by_prompt, key=lambda x: prompt_order.get(x, 999)):
        items = by_prompt[prompt_id]
        tier = items[0]["tier"]
        text = items[0]["prompt_text"]
        row = {"prompt_id": prompt_id, "tier": tier, "prompt_text": text}

        for r in items:
            col = (r["model"], _search_label(r["search_enabled"]))
            in_raw = target.lower() in r["raw_response"].lower()
            parsed = parsed_map.get(r["idx"])
            rank = _find_rank(parsed, target)

            if in_raw and rank:
                row[col] = f"#{rank}"
            elif in_raw:
                row[col] = "Yes*"
            else:
                row[col] = "—"

        rows.append(row)
    return rows


def build_summary(results: list[dict], target: str) -> dict:
    """Count detections by tier, model, search mode."""
    counts = {
        "by_tier": Counter(),
        "by_model": Counter(),
        "by_search": Counter(),
        "total": 0,
        "total_queries": len(results),
    }
    for r in results:
        if target.lower() in r["raw_response"].lower():
            counts["total"] += 1
            counts["by_tier"][r["tier"]] += 1
            counts["by_model"][_short(r["model"])] += 1
            counts["by_search"][_search_label(r["search_enabled"])] += 1
    return counts


def build_thai_frequency(parsed_list: list[dict]) -> list[tuple[str, int]]:
    """Count all restaurant mentions across probe responses."""
    counter = Counter()
    for p in parsed_list:
        for m in p.get("restaurants", []):
            counter[m["restaurant_name"]] += 1
    return counter.most_common(30)


def build_name_confusion(results: list[dict]) -> list[dict]:
    """Detect Sabai/Sarai name confusion — wrong location attributed to wrong name."""
    confusions = []
    for r in results:
        raw_lower = r["raw_response"].lower()
        has_sabai = "sabai" in raw_lower
        has_sarai = "sarai" in raw_lower

        if not has_sabai and not has_sarai:
            continue

        sabai_locs = [kw for kw in SABAI_KEYWORDS if kw in raw_lower]
        sarai_locs = [kw for kw in SARAI_KEYWORDS if kw in raw_lower]

        confusion = None
        if has_sabai and has_sarai:
            confusion = "Mentions both Sabai and Sarai"
        elif has_sabai and sarai_locs and not sabai_locs:
            confusion = f"Says 'Sabai' but gives Sarai's location ({', '.join(sarai_locs)})"
        elif has_sarai and sabai_locs and not sarai_locs:
            confusion = f"Says 'Sarai' but gives Sabai's location ({', '.join(sabai_locs)})"

        if confusion:
            confusions.append({
                "prompt_id": r["prompt_id"],
                "tier": r["tier"],
                "model": _short(r["model"]),
                "search": _search_label(r["search_enabled"]),
                "confusion": confusion,
                "sabai_locs": sabai_locs,
                "sarai_locs": sarai_locs,
            })
    return confusions


# ═══════════════════════════════════════════════════════════════════
# Console Output (Rich tables)
# ═══════════════════════════════════════════════════════════════════

def print_detection_matrix(title: str, matrix: list[dict]) -> None:
    """Print a detection matrix as a Rich table."""
    table = Table(title=title, show_lines=True, title_style="bold")
    table.add_column("Tier", style="bold", width=5)
    table.add_column("Prompt", width=55, no_wrap=False)

    cols = _col_keys()
    for model_val, search in cols:
        table.add_column(f"{_short(model_val)}\n{search}", justify="center", width=8)

    current_tier = None
    for row in matrix:
        tier_label = f"T{row['tier']}" if row["tier"] != current_tier else ""
        current_tier = row["tier"]

        cells = [tier_label, row["prompt_text"][:55]]
        for col in cols:
            val = row.get(col, "—")
            if val.startswith("#"):
                cells.append(f"[green bold]{val}[/green bold]")
            elif val.startswith("Yes"):
                cells.append(f"[yellow]{val}[/yellow]")
            else:
                cells.append(f"[dim]{val}[/dim]")
        table.add_row(*cells)

    console.print(table)


def print_summary(title: str, counts: dict) -> None:
    """Print detection summary."""
    console.print(f"\n[bold]{title}[/bold]")
    console.print(
        f"  Total: {counts['total']} / {counts['total_queries']} queries "
        f"({counts['total']/max(counts['total_queries'],1)*100:.1f}%)"
    )
    if counts["by_tier"]:
        tier_str = ", ".join(
            f"T{t}: {c}" for t, c in sorted(counts["by_tier"].items())
        )
        console.print(f"  By tier:   {tier_str}")
    if counts["by_model"]:
        console.print(f"  By model:  {dict(counts['by_model'])}")
    if counts["by_search"]:
        console.print(f"  By search: {dict(counts['by_search'])}")


# ═══════════════════════════════════════════════════════════════════
# Markdown Report
# ═══════════════════════════════════════════════════════════════════

def _md_matrix(matrix: list[dict]) -> str:
    """Convert detection matrix to a markdown table."""
    cols = _col_keys()
    headers = ["Tier", "Prompt"] + [f"{_short(m)} {s}" for m, s in cols]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["------"] * len(headers)) + "|",
    ]

    current_tier = None
    for row in matrix:
        tier_label = (
            f"**T{row['tier']}: {TIER_NAMES[row['tier']]}**"
            if row["tier"] != current_tier
            else ""
        )
        current_tier = row["tier"]
        cells = [tier_label, row["prompt_text"]]
        for col in cols:
            cells.append(row.get(col, "—"))
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def _md_summary(summary: dict) -> str:
    """Convert summary counts to markdown."""
    lines = ["\n| Breakdown | Count |", "|-----------|-------|"]
    for tier in sorted(summary["by_tier"]):
        lines.append(f"| Tier {tier} ({TIER_NAMES[tier]}) | {summary['by_tier'][tier]} |")
    for model, count in summary["by_model"].items():
        lines.append(f"| {model} | {count} |")
    for search, count in summary["by_search"].items():
        lines.append(f"| Search {search} | {count} |")
    return "\n".join(lines)


def generate_markdown_report(
    sabai_matrix: list[dict],
    sarai_matrix: list[dict],
    sabai_summary: dict,
    sarai_summary: dict,
    thai_freq: list[tuple[str, int]],
    confusions: list[dict],
    results: list[dict],
) -> str:
    """Generate the full markdown report."""
    lines = [
        "# Sabai Fine Thai on the Bay — AEO Probe Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "**Target:** Sabai Fine Thai on the Bay, 70 Collyer Quay, Customs House, Marina Bay",
        f"**Queries:** {len(results)} ({len(PROBE_PROMPTS)} prompts "
        f"x {len(MODELS)} models x 2 search modes)",
        "**Hypothesis:** Zero mentions in 1,690-query main dataset. "
        "How specific must a prompt be to surface it?",
        "",
        "---",
        "",
        "## Table 1: Sabai Detection Matrix",
        "",
        _md_matrix(sabai_matrix),
        "",
        "> `#N` = detected at rank N | `Yes*` = in raw text but not parsed "
        "as structured mention | `—` = not detected",
        "",
        "---",
        "",
        "## Table 2: Sarai Detection Matrix",
        "",
        _md_matrix(sarai_matrix),
        "",
        "> Shows when the competitor (Sarai Fine Thai, Tanglin Mall) appears instead.",
        "",
        "---",
        "",
        "## Table 3: Sabai Detection Summary",
        "",
        f"**{sabai_summary['total']} / {sabai_summary['total_queries']}** "
        f"queries mentioned Sabai "
        f"({sabai_summary['total']/max(sabai_summary['total_queries'],1)*100:.1f}%)",
        _md_summary(sabai_summary),
        "",
        "### Sarai Detection Summary (for comparison)",
        "",
        f"**{sarai_summary['total']} / {sarai_summary['total_queries']}** "
        f"queries mentioned Sarai",
        _md_summary(sarai_summary),
        "",
        "---",
        "",
        "## Table 4: Thai Restaurant Frequency (Top 30)",
        "",
        "Across all probe responses, which Thai restaurants appeared most? "
        "These are the restaurants eating Sabai's lunch.",
        "",
        "| Rank | Restaurant | Mentions |",
        "|------|-----------|----------|",
    ]

    for i, (name, count) in enumerate(thai_freq, 1):
        marker = ""
        if "sabai" in name.lower():
            marker = " **<-- TARGET**"
        elif "sarai" in name.lower():
            marker = " *(competitor)*"
        lines.append(f"| {i} | {name}{marker} | {count} |")

    lines.extend([
        "",
        "---",
        "",
        "## Table 5: Name Confusion Check",
        "",
    ])

    if confusions:
        lines.append(
            f"**{len(confusions)} potential confusion(s) detected** "
            "between Sabai and Sarai:"
        )
        lines.extend([
            "",
            "| Prompt | Model | Search | Issue |",
            "|--------|-------|--------|-------|",
        ])
        for c in confusions:
            lines.append(
                f"| {c['prompt_id']} | {c['model']} | {c['search']} | {c['confusion']} |"
            )
    else:
        lines.append("No name confusion detected between Sabai and Sarai.")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

async def main() -> None:
    parser = argparse.ArgumentParser(description="Sabai Fine Thai AEO Probe")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show prompts + cost estimate without running"
    )
    parser.add_argument(
        "--skip-queries", action="store_true",
        help="Load saved results, re-parse and re-analyze"
    )
    parser.add_argument(
        "--analyze-only", action="store_true",
        help="Load saved parsed data, re-analyze only"
    )
    args = parser.parse_args()

    # ── Show probe prompts ──
    console.print(Panel(
        "[bold]Sabai Fine Thai on the Bay — AEO Probe[/bold]\n"
        "70 Collyer Quay, Customs House, Marina Bay\n\n"
        "Zero mentions in 1,690 queries. Testing the specificity threshold.",
        style="cyan",
    ))

    for tier in sorted(TIER_NAMES):
        console.print(f"  [bold]Tier {tier}: {TIER_NAMES[tier]}[/bold]")
        for p in PROBE_PROMPTS:
            if p["tier"] == tier:
                console.print(f"    {p['id']}: {p['text']}")
        console.print()

    # ── Cost estimate ──
    est = estimate_cost(len(PROBE_PROMPTS))
    print_cost_estimate(est)

    if args.dry_run:
        console.print("[yellow]Dry run — exiting without running queries.[/yellow]")
        return

    # ── Step 1: Run queries ──
    if args.skip_queries or args.analyze_only:
        if not RESULTS_PATH.exists():
            console.print(f"[red]Error: {RESULTS_PATH} not found. Run queries first.[/red]")
            return
        console.print(f"Loading saved results from {RESULTS_PATH}")
        results = json.loads(RESULTS_PATH.read_text())
        console.print(f"  Loaded {len(results)} results")
    else:
        prompts = make_discovery_prompts()
        results = await run_probe_queries(prompts)

    # ── Step 2: Parse responses ──
    if args.analyze_only:
        if not PARSED_PATH.exists():
            console.print(f"[red]Error: {PARSED_PATH} not found. Run parsing first.[/red]")
            return
        console.print(f"Loading saved parsed data from {PARSED_PATH}")
        parsed_list = json.loads(PARSED_PATH.read_text())
        console.print(f"  Loaded {len(parsed_list)} parsed responses")
    else:
        parsed_list = await parse_probe_responses(results)

    # Build lookup: result idx -> parsed dict
    parsed_map: dict[int, dict] = {}
    for p in parsed_list:
        parsed_map[p["query_result_id"]] = p

    # ── Step 3: Analysis ──
    console.print(Panel("[bold]Analysis[/bold]", style="cyan"))

    # Table 1: Sabai detection
    sabai_matrix = build_detection_matrix(results, parsed_map, "sabai")
    print_detection_matrix("Table 1: Sabai Detection Matrix", sabai_matrix)

    # Table 2: Sarai detection
    sarai_matrix = build_detection_matrix(results, parsed_map, "sarai")
    print_detection_matrix("Table 2: Sarai Detection Matrix", sarai_matrix)

    # Table 3: Summaries
    sabai_summary = build_summary(results, "sabai")
    print_summary("Table 3: Sabai Detection Summary", sabai_summary)

    sarai_summary = build_summary(results, "sarai")
    print_summary("Sarai Detection Summary (for comparison)", sarai_summary)

    # Table 4: Thai restaurant frequency
    thai_freq = build_thai_frequency(parsed_list)
    console.print("\n[bold]Table 4: Thai Restaurant Frequency (Top 30)[/bold]")
    freq_table = Table(show_lines=False)
    freq_table.add_column("#", justify="right", width=4)
    freq_table.add_column("Restaurant", width=45)
    freq_table.add_column("Mentions", justify="right", width=8)
    for i, (name, count) in enumerate(thai_freq, 1):
        style = ""
        if "sabai" in name.lower():
            style = "green bold"
        elif "sarai" in name.lower():
            style = "yellow"
        freq_table.add_row(str(i), name, str(count), style=style)
    console.print(freq_table)

    # Table 5: Name confusion
    confusions = build_name_confusion(results)
    console.print(f"\n[bold]Table 5: Name Confusion Check[/bold]")
    if confusions:
        console.print(f"  [yellow]{len(confusions)} potential confusion(s):[/yellow]")
        for c in confusions:
            console.print(
                f"  {c['prompt_id']} / {c['model']} / {c['search']}: {c['confusion']}"
            )
    else:
        console.print("  No name confusion detected.")

    # ── Save report ──
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = generate_markdown_report(
        sabai_matrix, sarai_matrix, sabai_summary, sarai_summary,
        thai_freq, confusions, results,
    )
    REPORT_PATH.write_text(report)
    console.print(f"\n[green]Report saved to {REPORT_PATH}[/green]")


if __name__ == "__main__":
    asyncio.run(main())
