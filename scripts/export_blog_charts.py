#!/usr/bin/env python3
"""Export all 16 blog charts as high-resolution PNGs for Substack.

Generates 16 charts to assets/charts/blog/:
  Main body (9):
    01_model_coverage.png    — Distribution of restaurants by model count
    02_model_breadth.png     — Per-model unique restaurant count
    03_rank_disagreement.png — Top 15 most controversial restaurants (rank spread)
    04_search_overlap.png    — Search ON vs OFF restaurant overlap
    05_zombie_restaurants.png — Top closed restaurants still recommended
    06_jaccard_stability.png — Distribution of Jaccard similarities
    07_stability_by_model.png — Per-model Jaccard box plots
    08_specificity_paradox.png — Jaccard by prompt specificity
    09_reviews_vs_mentions.png — Google reviews vs AI mention frequency
  Appendix (7):
    a1_overlap_heatmap.png   — Pairwise model overlap matrix
    a2_avg_mentions.png      — Avg restaurants per response by model
    a3_search_mentions.png   — Search ON vs OFF mentions per response
    a4_closed_by_model.png   — Zombie mentions by model
    a5_core_stochastic.png   — Presence/absence matrix for one prompt
    a6_rating_vs_mentions.png — Google rating vs AI mentions
    a7_price_effect.png      — AI mentions by Google price level

Usage:
    python scripts/export_blog_charts.py
"""

import sqlite3
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import Patch
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

# ── Config ───────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aeo.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "charts" / "blog"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 200  # 200 DPI × 10" width = 2000px — crisp on retina, under 1MB

# ── Muted palette ────────────────────────────────────────────────────────────
MODEL_COLORS = {
    "openai/gpt-4o": "#6a9a78",                      # sage green
    "anthropic/claude-sonnet-4-20250514": "#c4956a",  # warm amber
    "google/gemini-2.5-flash": "#6b8ba4",             # steel blue
    "perplexity/sonar": "#9b8bb4",                    # muted mauve
}
MODEL_SHORT = {
    "openai/gpt-4o": "GPT-4o",
    "anthropic/claude-sonnet-4-20250514": "Claude",
    "google/gemini-2.5-flash": "Gemini",
    "perplexity/sonar": "Perplexity",
}
MODEL_ORDER = [
    "openai/gpt-4o",
    "anthropic/claude-sonnet-4-20250514",
    "google/gemini-2.5-flash",
    "perplexity/sonar",
]

# Accent colors
C_RED = "#b55a5a"
C_ORANGE = "#c9956b"
C_GREEN = "#7a9e7a"
C_BLUE = "#7393a7"
C_GRAY = "#8c8c8c"
C_LIGHT = "#d5d5d5"
C_TEXT = "#3d3d3d"
C_ANNOT = "#5a5a5a"


def model_short(name: str) -> str:
    return MODEL_SHORT.get(name, name)


def model_color(name: str) -> str:
    return MODEL_COLORS.get(name, C_GRAY)


def setup_style():
    """Muted, journal-style chart aesthetics for Substack."""
    sns.set_theme(style="white", font_scale=1.1)
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": C_LIGHT,
        "axes.linewidth": 0.6,
        "axes.titlesize": 14,
        "axes.titleweight": "medium",
        "axes.titlecolor": C_TEXT,
        "axes.labelsize": 11,
        "axes.labelcolor": C_ANNOT,
        "xtick.color": C_ANNOT,
        "ytick.color": C_ANNOT,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "xtick.major.width": 0.4,
        "ytick.major.width": 0.4,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "grid.color": C_LIGHT,
        "grid.linewidth": 0.4,
        "grid.alpha": 0.7,
        "legend.fontsize": 10,
        "legend.framealpha": 0.8,
        "legend.edgecolor": C_LIGHT,
        "font.family": "sans-serif",
        "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial",
                            "DejaVu Sans", "sans-serif"],
        "text.color": C_TEXT,
    })


def save(fig, name: str):
    path = OUT_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white",
                edgecolor="none")
    plt.close(fig)
    size_kb = path.stat().st_size / 1024
    print(f"  ✓ {name:<32} ({size_kb:.0f} KB)")


def light_grid(ax, axis="y"):
    """Subtle gridlines."""
    if axis in ("y", "both"):
        ax.yaxis.grid(True, linewidth=0.3, color=C_LIGHT, alpha=0.8)
    if axis in ("x", "both"):
        ax.xaxis.grid(True, linewidth=0.3, color=C_LIGHT, alpha=0.8)
    ax.set_axisbelow(True)


# ── Shared data loaders ─────────────────────────────────────────────────────

def load_jaccard_data(conn):
    """Compute pairwise Jaccard for all stability test cells."""
    stability = pd.read_sql_query("""
        SELECT
            qr.prompt_id,
            qr.model_name,
            qr.search_enabled,
            qr.run_number,
            rm.canonical_id,
            dp.specificity
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        JOIN discovery_prompts dp ON dp.id = qr.prompt_id
        WHERE qr.is_stability_test = 1 AND rm.canonical_id IS NOT NULL
    """, conn)

    records = []
    cells = stability.groupby(
        ["prompt_id", "model_name", "search_enabled", "specificity"]
    )
    for (pid, model, search, spec), group in cells:
        runs = group.groupby("run_number")["canonical_id"].apply(set).to_dict()
        run_nums = sorted(runs.keys())
        for i, j in combinations(run_nums, 2):
            s1, s2 = runs[i], runs[j]
            union = len(s1 | s2)
            inter = len(s1 & s2)
            jac = inter / union if union > 0 else 0
            records.append({
                "jaccard": jac,
                "model_name": model,
                "specificity": spec,
                "prompt_id": pid,
                "search_enabled": search,
            })
    return pd.DataFrame(records)


def load_ground_truth(conn):
    """Load verified operational restaurants with Google Places data."""
    return pd.read_sql_query("""
        SELECT
            cr.canonical_name,
            cr.total_mentions,
            cr.model_count,
            gp.user_ratings_total AS reviews,
            gp.rating,
            gp.price_level
        FROM canonical_restaurants cr
        JOIN google_places gp ON gp.canonical_id = cr.id
        WHERE gp.human_verified = 1 AND cr.model_count > 0
          AND gp.business_status = 'OPERATIONAL'
    """, conn)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BODY CHARTS (9)
# ═══════════════════════════════════════════════════════════════════════════════

def chart_01_model_coverage(conn):
    """Distribution of restaurants by model count."""
    model_dist = pd.read_sql_query("""
        SELECT model_count, COUNT(*) AS restaurants
        FROM canonical_restaurants
        WHERE model_count > 0
        GROUP BY model_count
        ORDER BY model_count
    """, conn)

    fig, ax = plt.subplots(figsize=(10, 5.5))
    colors = [C_RED, C_ORANGE, "#a8b07a", C_GREEN]
    bars = ax.bar(model_dist["model_count"], model_dist["restaurants"],
                  color=colors, edgecolor="white", linewidth=0.8, width=0.7)

    total = model_dist["restaurants"].sum()
    for bar, val in zip(bars, model_dist["restaurants"]):
        pct = val / total * 100
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15,
                f"{val:,}\n({pct:.0f}%)", ha="center", va="bottom",
                fontsize=10, color=C_ANNOT)

    ax.set_xlabel("Number of models mentioning the restaurant")
    ax.set_ylabel("Restaurants")
    ax.set_title("How many AI models know each restaurant?")
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["1 model\n(long tail)", "2 models",
                        "3 models", "4 models\n(consensus)"])
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "01_model_coverage.png")


def chart_02_model_breadth(conn):
    """Per-model unique restaurant count."""
    per_model = pd.read_sql_query("""
        SELECT qr.model_name, COUNT(DISTINCT rm.canonical_id) AS unique_restaurants
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 0 AND rm.canonical_id IS NOT NULL
        GROUP BY qr.model_name
        ORDER BY unique_restaurants DESC
    """, conn)

    fig, ax = plt.subplots(figsize=(10, 4))
    bar_colors = [model_color(m) for m in per_model["model_name"]]
    bars = ax.barh(
        [model_short(m) for m in per_model["model_name"]],
        per_model["unique_restaurants"],
        color=bar_colors, edgecolor="white", linewidth=0.8, height=0.6,
    )
    for bar, val in zip(bars, per_model["unique_restaurants"]):
        ax.text(bar.get_width() + 12, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=10.5, color=C_ANNOT)

    ax.set_xlabel("Unique restaurants mentioned")
    ax.set_title("Restaurant knowledge breadth by model")
    ax.set_xlim(0, per_model["unique_restaurants"].max() * 1.12)
    ax.invert_yaxis()
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "02_model_breadth.png")


def chart_03_rank_disagreement(conn):
    """Top 15 restaurants with biggest rank spread across models."""
    rank_data = pd.read_sql_query("""
        SELECT
            cr.canonical_name,
            qr.model_name,
            AVG(rm.rank_position) AS avg_rank,
            COUNT(*) AS appearances
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        JOIN canonical_restaurants cr ON rm.canonical_id = cr.id
        WHERE qr.is_stability_test = 0
          AND cr.model_count = 4
          AND rm.canonical_id IS NOT NULL
        GROUP BY cr.canonical_name, qr.model_name
    """, conn)

    rank_pivot = rank_data.pivot_table(
        index="canonical_name", columns="model_name", values="avg_rank"
    ).dropna()

    rank_pivot["spread"] = rank_pivot.max(axis=1) - rank_pivot.min(axis=1)
    top = rank_pivot.nlargest(15, "spread").drop(columns=["spread"])
    restaurants = top.index.tolist()[::-1]

    fig, ax = plt.subplots(figsize=(10, 7))

    # Connect dots with spread lines
    for i, r in enumerate(restaurants):
        vals = [top.loc[r, m] for m in MODEL_ORDER if m in top.columns]
        ax.plot([min(vals), max(vals)], [i, i],
                color=C_LIGHT, linewidth=1.8, zorder=1)

    for m in MODEL_ORDER:
        if m in top.columns:
            vals = [top.loc[r, m] for r in restaurants]
            ax.scatter(vals, range(len(restaurants)), color=model_color(m),
                       s=90, zorder=3, label=model_short(m),
                       edgecolors="white", linewidth=0.5)

    ax.set_yticks(range(len(restaurants)))
    ax.set_yticklabels(restaurants, fontsize=9.5)
    ax.set_xlabel("Average rank position (lower = ranked higher)")
    ax.set_title("Biggest rank disagreements across models")
    ax.legend(loc="lower right", framealpha=0.9)
    light_grid(ax, "x")
    sns.despine()
    plt.tight_layout()
    save(fig, "03_rank_disagreement.png")


def chart_04_search_overlap(conn):
    """Search ON vs OFF restaurant overlap."""
    search_overlap = pd.read_sql_query("""
        WITH on_set AS (
            SELECT DISTINCT rm.canonical_id
            FROM restaurant_mentions rm
            JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
            JOIN query_results qr ON pr.query_result_id = qr.id
            WHERE qr.is_stability_test = 0 AND qr.search_enabled = 1
              AND rm.canonical_id IS NOT NULL
        ),
        off_set AS (
            SELECT DISTINCT rm.canonical_id
            FROM restaurant_mentions rm
            JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
            JOIN query_results qr ON pr.query_result_id = qr.id
            WHERE qr.is_stability_test = 0 AND qr.search_enabled = 0
              AND rm.canonical_id IS NOT NULL
        )
        SELECT
            (SELECT COUNT(*) FROM on_set
             WHERE canonical_id IN (SELECT canonical_id FROM off_set)) AS both,
            (SELECT COUNT(*) FROM on_set
             WHERE canonical_id NOT IN (SELECT canonical_id FROM off_set))
                AS search_on_only,
            (SELECT COUNT(*) FROM off_set
             WHERE canonical_id NOT IN (SELECT canonical_id FROM on_set))
                AS search_off_only
    """, conn)

    both = search_overlap["both"].values[0]
    on_only = search_overlap["search_on_only"].values[0]
    off_only = search_overlap["search_off_only"].values[0]
    total = both + on_only + off_only

    fig, ax = plt.subplots(figsize=(10, 4))
    categories = ["Both modes", "Search ON only", "Search OFF only"]
    values = [both, on_only, off_only]
    colors_v = [C_GREEN, C_BLUE, C_ORANGE]
    bars = ax.barh(categories, values, color=colors_v, edgecolor="white",
                   linewidth=0.8, height=0.6)
    for bar, val in zip(bars, values):
        pct = val / total * 100
        ax.text(bar.get_width() + 8, bar.get_y() + bar.get_height() / 2,
                f"{val:,} ({pct:.0f}%)", va="center", fontsize=10,
                color=C_ANNOT)

    ax.set_xlabel("Unique restaurants")
    ax.set_title("Restaurant overlap: search ON vs OFF")
    ax.set_xlim(0, max(values) * 1.18)
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "04_search_overlap.png")


def chart_05_zombie_restaurants(conn):
    """Top closed restaurants still recommended by AI."""
    closed = pd.read_sql_query("""
        SELECT cr.canonical_name, cr.total_mentions, cr.model_count,
               gp.business_status
        FROM canonical_restaurants cr
        JOIN google_places gp ON gp.canonical_id = cr.id
        WHERE gp.human_verified = 1 AND cr.model_count > 0
          AND gp.business_status LIKE 'CLOSED%'
        ORDER BY cr.total_mentions DESC
    """, conn)

    if len(closed) == 0:
        print("  SKIP 05_zombie_restaurants — no closed restaurants found")
        return

    top = closed.head(15).copy().iloc[::-1]
    status_colors = {
        "CLOSED_PERMANENTLY": C_RED,
        "CLOSED_TEMPORARILY": C_ORANGE,
    }

    fig, ax = plt.subplots(figsize=(10, 7))
    colors = [status_colors.get(s, C_GRAY) for s in top["business_status"]]
    bars = ax.barh(range(len(top)), top["total_mentions"], color=colors,
                   edgecolor="white", linewidth=0.8, height=0.7)

    labels = [f"{name}  ({mc}/4 models)"
              for name, mc in zip(top["canonical_name"], top["model_count"])]
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(labels, fontsize=9.5)

    for bar, val in zip(bars, top["total_mentions"]):
        ax.text(bar.get_width() + 0.4, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=9.5, color=C_ANNOT)

    legend_elements = [
        Patch(facecolor=C_RED, edgecolor="white", label="Permanently closed"),
        Patch(facecolor=C_ORANGE, edgecolor="white", label="Temporarily closed"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", framealpha=0.9)

    ax.set_xlabel("Total AI mentions")
    ax.set_title(f"Closed restaurants still recommended by AI\n"
                 f"{len(closed)} zombie restaurants, "
                 f"{closed['total_mentions'].sum():,} total mentions")
    ax.set_xlim(0, top["total_mentions"].max() * 1.12)
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "05_zombie_restaurants.png")


def chart_06_jaccard_stability(jac_df):
    """Distribution of Jaccard similarities (histogram)."""
    mean_j = jac_df["jaccard"].mean()
    median_j = jac_df["jaccard"].median()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.hist(jac_df["jaccard"], bins=30, color=C_BLUE, edgecolor="white",
            linewidth=0.5, alpha=0.75)
    ax.axvline(mean_j, color=C_RED, linestyle="--", linewidth=1.4,
               label=f"Mean = {mean_j:.3f}")
    ax.axvline(median_j, color=C_ORANGE, linestyle=":", linewidth=1.4,
               label=f"Median = {median_j:.3f}")
    ax.set_xlabel("Pairwise Jaccard similarity")
    ax.set_ylabel("Count")
    ax.set_title("How stable are LLM restaurant recommendations?")
    ax.legend(framealpha=0.9, fontsize=10)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "06_jaccard_stability.png")


def chart_07_stability_by_model(jac_df):
    """Per-model Jaccard box plots."""
    fig, ax = plt.subplots(figsize=(10, 5.5))
    model_labels = [model_short(m) for m in MODEL_ORDER]
    model_data = [
        jac_df.loc[jac_df["model_name"] == m, "jaccard"].values
        for m in MODEL_ORDER
    ]

    bp = ax.boxplot(model_data, tick_labels=model_labels, patch_artist=True,
                    widths=0.6, medianprops={"color": C_TEXT, "linewidth": 2})

    for patch, m in zip(bp["boxes"], MODEL_ORDER):
        patch.set_facecolor(model_color(m))
        patch.set_alpha(0.7)
        patch.set_edgecolor("white")

    means = [d.mean() if len(d) > 0 else 0 for d in model_data]
    ax.scatter(range(1, 5), means, marker="D", color="white",
               edgecolors=C_TEXT, s=55, zorder=5, label="Mean")

    ax.set_ylabel("Pairwise Jaccard similarity")
    ax.set_title("Recommendation stability by model")
    ax.legend(loc="upper right", framealpha=0.9)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "07_stability_by_model.png")


def chart_08_specificity_paradox(jac_df):
    """Jaccard by prompt specificity level."""
    spec_order = ["broad", "medium", "narrow"]
    spec_colors = [C_GREEN, C_ORANGE, C_RED]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    spec_data = [
        jac_df.loc[jac_df["specificity"] == s, "jaccard"].values
        for s in spec_order
    ]
    spec_means = [d.mean() if len(d) > 0 else 0 for d in spec_data]

    bp = ax.boxplot(spec_data,
                    tick_labels=[s.title() for s in spec_order],
                    patch_artist=True, widths=0.6,
                    medianprops={"color": C_TEXT, "linewidth": 2})

    for patch, c in zip(bp["boxes"], spec_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.7)
        patch.set_edgecolor("white")

    ax.scatter(range(1, 4), spec_means, marker="D", color="white",
               edgecolors=C_TEXT, s=55, zorder=5, label="Mean")

    # Annotate the paradox
    ax.annotate("Worst set overlap\nbut best rank order",
                xy=(3, spec_means[2]), xytext=(2.2, spec_means[2] + 0.12),
                fontsize=9, color=C_ANNOT, ha="center",
                arrowprops=dict(arrowstyle="->", color=C_ANNOT, lw=1.0))

    ax.set_ylabel("Pairwise Jaccard similarity")
    ax.set_title("The Specificity Paradox: set stability by prompt type")
    ax.legend(loc="upper right", framealpha=0.9)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "08_specificity_paradox.png")


def chart_09_reviews_vs_mentions(gt):
    """Google review count vs AI mention frequency (log scale)."""
    gt_r = gt.dropna(subset=["reviews"]).copy()
    gt_r = gt_r[gt_r["reviews"] > 0]
    gt_r["log_reviews"] = np.log10(gt_r["reviews"])

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(gt_r["log_reviews"], gt_r["total_mentions"],
               alpha=0.35, s=18, c=C_BLUE, edgecolors="none")

    z = np.polyfit(gt_r["log_reviews"], gt_r["total_mentions"], 1)
    p = np.poly1d(z)
    x_line = np.linspace(gt_r["log_reviews"].min(),
                         gt_r["log_reviews"].max(), 100)
    ax.plot(x_line, p(x_line), "--", color=C_RED, linewidth=1.3, alpha=0.8)

    r, pval = stats.spearmanr(gt_r["log_reviews"], gt_r["total_mentions"])
    ax.text(0.04, 0.94, f"Spearman r = {r:.3f}\np = {pval:.1e}",
            transform=ax.transAxes, fontsize=10, va="top", color=C_ANNOT,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f0eb",
                      edgecolor=C_LIGHT, linewidth=0.5, alpha=0.9))

    top_mentions = gt_r.nlargest(5, "total_mentions")
    for _, row in top_mentions.iterrows():
        ax.annotate(row["canonical_name"],
                    (row["log_reviews"], row["total_mentions"]),
                    fontsize=8, color=C_ANNOT, ha="left", va="bottom",
                    xytext=(5, 4), textcoords="offset points")

    ax.set_xlabel("Google review count (log₁₀ scale)")
    ax.set_ylabel("Total AI mentions")
    ax.set_title("Review volume predicts AI mentions more than rating does")
    light_grid(ax, "both")
    sns.despine()
    plt.tight_layout()
    save(fig, "09_reviews_vs_mentions.png")


# ═══════════════════════════════════════════════════════════════════════════════
# APPENDIX CHARTS (7)
# ═══════════════════════════════════════════════════════════════════════════════

def chart_a1_overlap_heatmap(conn):
    """Pairwise model overlap matrix (4x4 heatmap)."""
    model_sets_df = pd.read_sql_query("""
        SELECT DISTINCT qr.model_name, rm.canonical_id
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 0 AND rm.canonical_id IS NOT NULL
    """, conn)

    model_sets = {}
    for m in MODEL_ORDER:
        model_sets[m] = set(
            model_sets_df.loc[model_sets_df["model_name"] == m, "canonical_id"]
        )

    labels = [model_short(m) for m in MODEL_ORDER]
    n = len(MODEL_ORDER)
    matrix = np.zeros((n, n), dtype=int)
    for i, m1 in enumerate(MODEL_ORDER):
        for j, m2 in enumerate(MODEL_ORDER):
            matrix[i, j] = len(model_sets[m1] & model_sets[m2])

    fig, ax = plt.subplots(figsize=(8, 7))

    # Custom muted blue colormap
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list(
        "muted_blue", ["#f7f3ef", "#c9d6e0", "#7393a7", "#4a6a7f"]
    )

    sns.heatmap(matrix, annot=True, fmt=",", cmap=cmap,
                xticklabels=labels, yticklabels=labels, ax=ax,
                linewidths=1.0, linecolor="white",
                cbar_kws={"label": "Shared restaurants"})
    ax.set_title("Pairwise restaurant overlap between models")
    plt.tight_layout()
    save(fig, "a1_overlap_heatmap.png")


def chart_a2_avg_mentions(conn):
    """Avg restaurants per response by model (with std dev error bars)."""
    verbosity = pd.read_sql_query("""
        SELECT qr.id, qr.model_name, COUNT(rm.id) AS n_mentions
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        LEFT JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        WHERE qr.is_stability_test = 0
        GROUP BY qr.id
    """, conn)

    verb_stats = (verbosity.groupby("model_name")["n_mentions"]
                  .agg(["mean", "std"]).reset_index())
    verb_stats = verb_stats.sort_values("mean", ascending=True)

    fig, ax = plt.subplots(figsize=(10, 4.5))
    bar_colors = [model_color(m) for m in verb_stats["model_name"]]
    bars = ax.barh(
        [model_short(m) for m in verb_stats["model_name"]],
        verb_stats["mean"],
        xerr=verb_stats["std"],
        color=bar_colors, edgecolor="white", linewidth=0.8,
        capsize=5, error_kw={"linewidth": 1.2, "color": C_ANNOT},
        height=0.6,
    )
    for bar, mean, std in zip(bars, verb_stats["mean"], verb_stats["std"]):
        ax.text(bar.get_width() + std + 0.4,
                bar.get_y() + bar.get_height() / 2,
                f"{mean:.1f} ± {std:.1f}", va="center",
                fontsize=10, color=C_ANNOT)

    ax.set_xlabel("Restaurants per response")
    ax.set_title("Model verbosity: restaurants per response (mean ± std dev)")
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "a2_avg_mentions.png")


def chart_a3_search_mentions(conn):
    """Search ON vs OFF mentions per response by model (grouped bars)."""
    search_verb = pd.read_sql_query("""
        SELECT qr.model_name, qr.search_enabled, qr.id AS query_id,
               COUNT(rm.id) AS n_mentions
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        LEFT JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        WHERE qr.is_stability_test = 0
        GROUP BY qr.id
    """, conn)

    sv_stats = (search_verb.groupby(["model_name", "search_enabled"])
                ["n_mentions"].mean().reset_index())
    sv_stats["model"] = sv_stats["model_name"].map(model_short)
    sv_stats["search"] = sv_stats["search_enabled"].map(
        {0: "Search OFF", 1: "Search ON"}
    )

    sv_pivot = sv_stats.pivot(index="model", columns="search",
                              values="n_mentions")
    sv_pivot = sv_pivot.reindex([model_short(m) for m in MODEL_ORDER])

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(sv_pivot))
    width = 0.35

    bars_off = ax.bar(x - width / 2, sv_pivot["Search OFF"], width,
                      label="Search OFF",
                      color=[model_color(m) for m in MODEL_ORDER],
                      alpha=0.5, edgecolor="white")
    bars_on = ax.bar(x + width / 2, sv_pivot["Search ON"], width,
                     label="Search ON",
                     color=[model_color(m) for m in MODEL_ORDER],
                     alpha=1.0, edgecolor="white")

    for bar in list(bars_off) + list(bars_on):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.15,
                f"{bar.get_height():.1f}", ha="center", va="bottom",
                fontsize=9, color=C_ANNOT)

    ax.set_xticks(x)
    ax.set_xticklabels(sv_pivot.index)
    ax.set_ylabel("Avg restaurants per response")
    ax.set_title("Response volume: Search OFF (faded) vs ON (solid)")
    ax.legend(framealpha=0.9)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "a3_search_mentions.png")


def chart_a4_closed_by_model(conn):
    """Zombie mentions by model and search mode."""
    closed_ids_df = pd.read_sql_query("""
        SELECT cr.id AS canonical_id
        FROM canonical_restaurants cr
        JOIN google_places gp ON gp.canonical_id = cr.id
        WHERE gp.human_verified = 1
          AND gp.business_status LIKE 'CLOSED%'
          AND cr.model_count > 0
    """, conn)
    closed_ids = closed_ids_df["canonical_id"].tolist()

    if not closed_ids:
        print("  SKIP a4_closed_by_model — no closed restaurants")
        return

    placeholders = ",".join(["?"] * len(closed_ids))
    closed_by_model = pd.read_sql_query(f"""
        SELECT qr.model_name, qr.search_enabled,
               COUNT(rm.id) AS closed_mentions
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 0
          AND rm.canonical_id IN ({placeholders})
        GROUP BY qr.model_name, qr.search_enabled
    """, conn, params=closed_ids)

    closed_by_model["model"] = closed_by_model["model_name"].map(model_short)
    closed_by_model["search"] = closed_by_model["search_enabled"].map(
        {0: "Search OFF", 1: "Search ON"}
    )

    cbm_pivot = closed_by_model.pivot(
        index="model", columns="search", values="closed_mentions"
    ).fillna(0)
    cbm_pivot = cbm_pivot.reindex([model_short(m) for m in MODEL_ORDER])

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(cbm_pivot))
    width = 0.35

    ax.bar(x - width / 2, cbm_pivot.get("Search OFF", 0), width,
           label="Search OFF", color=C_RED, alpha=0.5, edgecolor="white")
    ax.bar(x + width / 2, cbm_pivot.get("Search ON", 0), width,
           label="Search ON", color=C_RED, alpha=1.0, edgecolor="white")

    for bars in ax.containers:
        for bar in bars:
            if bar.get_height() > 0:
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 1,
                        f"{int(bar.get_height())}", ha="center",
                        va="bottom", fontsize=9, color=C_ANNOT)

    ax.set_xticks(x)
    ax.set_xticklabels(cbm_pivot.index)
    ax.set_ylabel("Mentions of closed restaurants")
    ax.set_title("Zombie restaurant mentions by model and search mode")
    ax.legend(framealpha=0.9)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "a4_closed_by_model.png")


def chart_a5_core_stochastic(conn):
    """Presence/absence matrix for cuisine_001 × Claude × Search OFF."""
    example = pd.read_sql_query("""
        SELECT qr.run_number, cr.canonical_name, rm.rank_position
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        JOIN canonical_restaurants cr ON rm.canonical_id = cr.id
        WHERE qr.is_stability_test = 1
          AND qr.prompt_id = 'cuisine_001'
          AND qr.model_name = 'anthropic/claude-sonnet-4-20250514'
          AND qr.search_enabled = 0
        ORDER BY qr.run_number, rm.rank_position
    """, conn)

    if len(example) == 0:
        print("  SKIP a5_core_stochastic — no data for example cell")
        return

    runs = sorted(example["run_number"].unique())
    n_runs = len(runs)
    appearances = example.groupby("canonical_name")["run_number"].nunique()
    first_rank = example.groupby("canonical_name")["rank_position"].min()
    sort_df = pd.DataFrame({
        "appearances": appearances, "first_rank": first_rank
    })
    sort_df = sort_df.sort_values(
        ["appearances", "first_rank"], ascending=[False, True]
    )
    restaurants = sort_df.index.tolist()

    # Build presence matrix
    matrix = np.zeros((len(restaurants), len(runs)))
    for _, row in example.iterrows():
        ri = restaurants.index(row["canonical_name"])
        ci = runs.index(row["run_number"])
        matrix[ri, ci] = 1

    # Classify each restaurant
    class_colors = {"Core": C_GREEN, "Mid": C_ORANGE, "Stochastic": C_RED}
    classifications = []
    for r in restaurants:
        n = appearances[r]
        if n >= n_runs * 0.8:
            classifications.append("Core")
        elif n >= n_runs * 0.6:
            classifications.append("Mid")
        else:
            classifications.append("Stochastic")

    # Build colored image
    colored = np.ones((*matrix.shape, 3)) * 0.95  # light gray background
    for i, cls in enumerate(classifications):
        hex_c = class_colors[cls]
        rgb = [int(hex_c[k:k+2], 16) / 255 for k in (1, 3, 5)]
        for j in range(matrix.shape[1]):
            if matrix[i, j] > 0:
                colored[i, j] = rgb

    fig_h = max(6, len(restaurants) * 0.35)
    fig, ax = plt.subplots(figsize=(8, fig_h))
    ax.imshow(colored, aspect="auto", interpolation="nearest")

    ax.set_xticks(range(len(runs)))
    ax.set_xticklabels([f"Run {r}" for r in runs])
    ax.set_yticks(range(len(restaurants)))
    y_labels = [f"{r}  [{c[0]}]" for r, c in
                zip(restaurants, classifications)]
    ax.set_yticklabels(y_labels, fontsize=8.5)

    legend_elements = [
        Patch(facecolor=C_GREEN, label=f"Core (4+/{n_runs} runs)"),
        Patch(facecolor=C_ORANGE, label=f"Mid (3/{n_runs} runs)"),
        Patch(facecolor=C_RED, label=f"Stochastic (1-2/{n_runs} runs)"),
    ]
    ax.legend(handles=legend_elements, loc="lower right",
              framealpha=0.9, fontsize=9)

    core_n = classifications.count("Core")
    stoch_n = classifications.count("Stochastic")
    ax.set_title(
        f"Presence matrix: cuisine_001 × Claude × Search OFF\n"
        f"{core_n} core, {classifications.count('Mid')} mid, "
        f"{stoch_n} stochastic — most recommendations are coin flips"
    )
    ax.set_xlabel("Stability test runs")
    plt.tight_layout()
    save(fig, "a5_core_stochastic.png")


def chart_a6_rating_vs_mentions(gt):
    """Google rating vs AI mention frequency."""
    gt_r = gt.dropna(subset=["rating"]).copy()

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(gt_r["rating"], gt_r["total_mentions"],
               alpha=0.35, s=18, c=C_BLUE, edgecolors="none")

    z = np.polyfit(gt_r["rating"], gt_r["total_mentions"], 1)
    p = np.poly1d(z)
    x_line = np.linspace(gt_r["rating"].min(), gt_r["rating"].max(), 100)
    ax.plot(x_line, p(x_line), "--", color=C_RED, linewidth=1.3, alpha=0.8)

    r, pval = stats.spearmanr(gt_r["rating"], gt_r["total_mentions"])
    ax.text(0.04, 0.94, f"Spearman r = {r:.3f}\np = {pval:.2e}",
            transform=ax.transAxes, fontsize=10, va="top", color=C_ANNOT,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f0eb",
                      edgecolor=C_LIGHT, linewidth=0.5, alpha=0.9))

    top_mentions = gt_r.nlargest(5, "total_mentions")
    for _, row in top_mentions.iterrows():
        ax.annotate(row["canonical_name"],
                    (row["rating"], row["total_mentions"]),
                    fontsize=8, color=C_ANNOT, ha="left", va="bottom",
                    xytext=(5, 4), textcoords="offset points")

    ax.set_xlabel("Google star rating")
    ax.set_ylabel("Total AI mentions")
    ax.set_title("Google rating vs AI mention frequency")
    light_grid(ax, "both")
    sns.despine()
    plt.tight_layout()
    save(fig, "a6_rating_vs_mentions.png")


def chart_a7_price_effect(gt):
    """AI mentions by Google price level."""
    gt_p = gt.dropna(subset=["price_level"]).copy()
    gt_p["price_level"] = gt_p["price_level"].astype(int)

    if len(gt_p) == 0 or gt_p["price_level"].nunique() < 2:
        print("  SKIP a7_price_effect — insufficient price data")
        return

    price_labels = {0: "Free", 1: "Budget", 2: "Moderate",
                    3: "Expensive", 4: "Premium"}
    price_colors = {0: C_LIGHT, 1: C_GREEN, 2: C_BLUE,
                    3: C_ORANGE, 4: "#9b8bb4"}
    price_levels = sorted(gt_p["price_level"].unique())
    price_data = [
        gt_p.loc[gt_p["price_level"] == p, "total_mentions"].values
        for p in price_levels
    ]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    bp = ax.boxplot(
        price_data,
        tick_labels=[price_labels.get(p, str(p)) for p in price_levels],
        patch_artist=True, widths=0.6,
        medianprops={"color": C_TEXT, "linewidth": 2},
    )

    for patch, p in zip(bp["boxes"], price_levels):
        patch.set_facecolor(price_colors.get(p, C_GRAY))
        patch.set_alpha(0.7)
        patch.set_edgecolor("white")

    for i, p in enumerate(price_levels):
        n = len(gt_p[gt_p["price_level"] == p])
        ymax = ax.get_ylim()[1]
        ax.text(i + 1, ymax * 0.95, f"n={n}", ha="center",
                fontsize=9, color=C_ANNOT)

    ax.set_xlabel("Google price level")
    ax.set_ylabel("Total AI mentions")
    ax.set_title("AI mentions by Google price level")
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "a7_price_effect.png")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    setup_style()
    conn = sqlite3.connect(str(DB_PATH))
    print(f"Connected to {DB_PATH}")
    print(f"Exporting 16 blog charts to {OUT_DIR}/\n")

    # Preload shared data
    print("Loading Jaccard stability data...")
    jac_df = load_jaccard_data(conn)
    print(f"  {len(jac_df)} pairwise comparisons loaded")

    print("Loading ground truth data...")
    gt = load_ground_truth(conn)
    print(f"  {len(gt)} verified operational restaurants\n")

    # Main body (9)
    print("── Main Body Charts ──────────────────────────")
    chart_01_model_coverage(conn)
    chart_02_model_breadth(conn)
    chart_03_rank_disagreement(conn)
    chart_04_search_overlap(conn)
    chart_05_zombie_restaurants(conn)
    chart_06_jaccard_stability(jac_df)
    chart_07_stability_by_model(jac_df)
    chart_08_specificity_paradox(jac_df)
    chart_09_reviews_vs_mentions(gt)

    # Appendix (7)
    print("\n── Appendix Charts ───────────────────────────")
    chart_a1_overlap_heatmap(conn)
    chart_a2_avg_mentions(conn)
    chart_a3_search_mentions(conn)
    chart_a4_closed_by_model(conn)
    chart_a5_core_stochastic(conn)
    chart_a6_rating_vs_mentions(gt)
    chart_a7_price_effect(gt)

    conn.close()
    print(f"\nDone! 16 charts exported to {OUT_DIR}/")


if __name__ == "__main__":
    main()
