#!/usr/bin/env python3
"""Export key charts from the analysis as high-resolution PNGs for README.

Generates 6 charts to assets/charts/ at 300 DPI:
  1. model_coverage.png    — Distribution of restaurants by how many models mention them
  2. model_breadth.png     — Per-model unique restaurant count
  3. zombie_status.png     — Top closed restaurants still recommended by AI
  4. jaccard_stability.png — Distribution of Jaccard similarities (recommendation stability)
  5. search_overlap.png    — Search ON vs OFF restaurant overlap
  6. reviews_vs_mentions.png — Google review count vs AI mention frequency
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
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 300

# ── Muted palette ────────────────────────────────────────────────────────────
# Desaturated, journal-friendly colors. Warm-cool balanced.
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

# Accent colors (muted)
C_RED = "#b55a5a"       # muted rust
C_ORANGE = "#c9956b"    # warm terracotta
C_GREEN = "#7a9e7a"     # sage
C_BLUE = "#7393a7"      # slate blue
C_GRAY = "#8c8c8c"      # neutral gray
C_LIGHT = "#d5d5d5"     # light gray for gridlines
C_TEXT = "#3d3d3d"       # near-black for text
C_ANNOT = "#5a5a5a"     # annotation gray


def model_short(name: str) -> str:
    return MODEL_SHORT.get(name, name)


def model_color(name: str) -> str:
    return MODEL_COLORS.get(name, C_GRAY)


def setup_style():
    """Muted, journal-style chart aesthetics."""
    sns.set_theme(style="white", font_scale=1.0)
    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": C_LIGHT,
        "axes.linewidth": 0.6,
        "axes.titlesize": 12,
        "axes.titleweight": "medium",
        "axes.titlecolor": C_TEXT,
        "axes.labelsize": 10,
        "axes.labelcolor": C_ANNOT,
        "xtick.color": C_ANNOT,
        "ytick.color": C_ANNOT,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "xtick.major.width": 0.4,
        "ytick.major.width": 0.4,
        "xtick.major.size": 3,
        "ytick.major.size": 3,
        "grid.color": C_LIGHT,
        "grid.linewidth": 0.4,
        "grid.alpha": 0.7,
        "legend.fontsize": 9,
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
    print(f"  Saved {path}")


def light_grid(ax, axis="y"):
    """Add subtle horizontal gridlines only."""
    if axis in ("y", "both"):
        ax.yaxis.grid(True, linewidth=0.3, color=C_LIGHT, alpha=0.8)
    if axis in ("x", "both"):
        ax.xaxis.grid(True, linewidth=0.3, color=C_LIGHT, alpha=0.8)
    ax.set_axisbelow(True)


# ── Chart 1: Model coverage distribution ─────────────────────────────────────
def chart_model_coverage(conn):
    model_dist = pd.read_sql_query("""
        SELECT model_count, COUNT(*) AS restaurants
        FROM canonical_restaurants
        WHERE model_count > 0
        GROUP BY model_count
        ORDER BY model_count
    """, conn)

    fig, ax = plt.subplots(figsize=(7, 4.5))

    # Gradient from muted red (1 model) to muted green (4 models)
    colors = ["#b55a5a", "#c9956b", "#a8b07a", "#7a9e7a"]
    bars = ax.bar(model_dist["model_count"], model_dist["restaurants"],
                  color=colors, edgecolor="white", linewidth=0.8, width=0.7)

    total = model_dist["restaurants"].sum()
    for bar, val in zip(bars, model_dist["restaurants"]):
        pct = val / total * 100
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 15,
                f"{val:,}\n({pct:.0f}%)", ha="center", va="bottom",
                fontsize=9, color=C_ANNOT)

    ax.set_xlabel("Number of models mentioning the restaurant")
    ax.set_ylabel("Restaurants")
    ax.set_title("How many models know each restaurant?")
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["1 model\n(long tail)", "2 models",
                        "3 models", "4 models\n(consensus)"])
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "model_coverage.png")


# ── Chart 2: Per-model restaurant count ──────────────────────────────────────
def chart_model_breadth(conn):
    per_model = pd.read_sql_query("""
        SELECT qr.model_name, COUNT(DISTINCT rm.canonical_id) AS unique_restaurants
        FROM restaurant_mentions rm
        JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
        JOIN query_results qr ON pr.query_result_id = qr.id
        WHERE qr.is_stability_test = 0 AND rm.canonical_id IS NOT NULL
        GROUP BY qr.model_name
        ORDER BY unique_restaurants DESC
    """, conn)

    fig, ax = plt.subplots(figsize=(7, 3.5))
    bar_colors = [model_color(m) for m in per_model["model_name"]]
    bars = ax.barh(
        [model_short(m) for m in per_model["model_name"]],
        per_model["unique_restaurants"],
        color=bar_colors, edgecolor="white", linewidth=0.8, height=0.6,
    )
    for bar, val in zip(bars, per_model["unique_restaurants"]):
        ax.text(bar.get_width() + 12, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=9.5, color=C_ANNOT)

    ax.set_xlabel("Unique restaurants mentioned")
    ax.set_title("Restaurant knowledge breadth by model")
    ax.set_xlim(0, per_model["unique_restaurants"].max() * 1.12)
    ax.invert_yaxis()
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "model_breadth.png")


# ── Chart 3: Zombie restaurants — top closed by mention count ────────────────
def chart_zombie_status(conn):
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
        print("  SKIP zombie_status — no closed restaurants found")
        return

    top = closed.head(15).copy()
    top = top.iloc[::-1]

    status_colors = {
        "CLOSED_PERMANENTLY": C_RED,
        "CLOSED_TEMPORARILY": C_ORANGE,
    }

    fig, ax = plt.subplots(figsize=(9, 6.5))
    colors = [status_colors[s] for s in top["business_status"]]

    bars = ax.barh(range(len(top)), top["total_mentions"], color=colors,
                   edgecolor="white", linewidth=0.8, height=0.7)

    labels = [f"{name}  ({mc}/4 models)"
              for name, mc in zip(top["canonical_name"], top["model_count"])]
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(labels, fontsize=8.5)

    for bar, val in zip(bars, top["total_mentions"]):
        ax.text(bar.get_width() + 0.4, bar.get_y() + bar.get_height() / 2,
                str(val), va="center", fontsize=8.5, color=C_ANNOT)

    legend_elements = [
        Patch(facecolor=C_RED, edgecolor="white", label="Permanently closed"),
        Patch(facecolor=C_ORANGE, edgecolor="white", label="Temporarily closed"),
    ]
    ax.legend(handles=legend_elements, loc="lower right", framealpha=0.9,
              fontsize=8.5)

    ax.set_xlabel("Total AI mentions")
    ax.set_title(f"Closed restaurants still recommended by AI\n"
                 f"{len(closed)} zombie restaurants, "
                 f"{closed['total_mentions'].sum():,} total mentions")
    ax.set_xlim(0, top["total_mentions"].max() * 1.12)
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "zombie_status.png")


# ── Chart 4: Jaccard stability histogram ─────────────────────────────────────
def chart_jaccard_stability(conn):
    stability_mentions = pd.read_sql_query("""
        SELECT
            qr.prompt_id,
            qr.model_name,
            qr.search_enabled,
            qr.run_number,
            rm.canonical_id
        FROM query_results qr
        JOIN parsed_responses pr ON pr.query_result_id = qr.id
        JOIN restaurant_mentions rm ON rm.parsed_response_id = pr.id
        WHERE qr.is_stability_test = 1 AND rm.canonical_id IS NOT NULL
    """, conn)

    jaccard_records = []
    cells = stability_mentions.groupby(["prompt_id", "model_name",
                                        "search_enabled"])

    for (pid, model, search), group in cells:
        runs = group.groupby("run_number")["canonical_id"].apply(set).to_dict()
        run_nums = sorted(runs.keys())
        for i, j in combinations(run_nums, 2):
            s1, s2 = runs[i], runs[j]
            union = len(s1 | s2)
            intersection = len(s1 & s2)
            jac = intersection / union if union > 0 else 0
            jaccard_records.append({"jaccard": jac})

    jac_df = pd.DataFrame(jaccard_records)
    mean_j = jac_df["jaccard"].mean()
    median_j = jac_df["jaccard"].median()

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(jac_df["jaccard"], bins=30, color=C_BLUE, edgecolor="white",
            linewidth=0.5, alpha=0.75)
    ax.axvline(mean_j, color=C_RED, linestyle="--", linewidth=1.2,
               label=f"Mean = {mean_j:.3f}")
    ax.axvline(median_j, color=C_ORANGE, linestyle=":", linewidth=1.2,
               label=f"Median = {median_j:.3f}")
    ax.set_xlabel("Pairwise Jaccard similarity")
    ax.set_ylabel("Count")
    ax.set_title("How stable are LLM restaurant recommendations?")
    ax.legend(framealpha=0.9)
    light_grid(ax, "y")
    sns.despine(left=True)
    plt.tight_layout()
    save(fig, "jaccard_stability.png")


# ── Chart 5: Search ON vs OFF overlap ────────────────────────────────────────
def chart_search_overlap(conn):
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

    fig, ax = plt.subplots(figsize=(7, 3.5))
    categories = ["Both modes", "Search ON only", "Search OFF only"]
    values = [both, on_only, off_only]
    colors_v = [C_GREEN, C_BLUE, C_ORANGE]
    bars = ax.barh(categories, values, color=colors_v, edgecolor="white",
                   linewidth=0.8, height=0.6)
    for bar, val in zip(bars, values):
        pct = val / total * 100
        ax.text(bar.get_width() + 8, bar.get_y() + bar.get_height() / 2,
                f"{val:,} ({pct:.0f}%)", va="center", fontsize=9,
                color=C_ANNOT)

    ax.set_xlabel("Unique restaurants")
    ax.set_title("Restaurant overlap: search ON vs OFF")
    ax.set_xlim(0, max(values) * 1.18)
    light_grid(ax, "x")
    sns.despine(bottom=True)
    plt.tight_layout()
    save(fig, "search_overlap.png")


# ── Chart 6: Review count vs AI mentions (log scale) ────────────────────────
def chart_reviews_vs_mentions(conn):
    ground_truth = pd.read_sql_query("""
        SELECT
            cr.canonical_name,
            cr.total_mentions,
            gp.user_ratings_total AS reviews
        FROM canonical_restaurants cr
        JOIN google_places gp ON gp.canonical_id = cr.id
        WHERE gp.human_verified = 1 AND cr.model_count > 0
          AND gp.business_status = 'OPERATIONAL'
          AND gp.user_ratings_total > 0
    """, conn)

    ground_truth["log_reviews"] = np.log10(ground_truth["reviews"])

    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(ground_truth["log_reviews"], ground_truth["total_mentions"],
               alpha=0.35, s=16, c=C_BLUE, edgecolors="none")

    # Trend line
    z = np.polyfit(ground_truth["log_reviews"],
                   ground_truth["total_mentions"], 1)
    p = np.poly1d(z)
    x_line = np.linspace(ground_truth["log_reviews"].min(),
                         ground_truth["log_reviews"].max(), 100)
    ax.plot(x_line, p(x_line), "--", color=C_RED, linewidth=1.2, alpha=0.8)

    # Correlation annotation
    r, pval = stats.spearmanr(ground_truth["log_reviews"],
                              ground_truth["total_mentions"])
    ax.text(0.04, 0.94, f"Spearman r = {r:.3f}\np = {pval:.1e}",
            transform=ax.transAxes, fontsize=9, va="top", color=C_ANNOT,
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#f5f0eb",
                      edgecolor=C_LIGHT, linewidth=0.5, alpha=0.9))

    # Annotate top 5
    top_mentions = ground_truth.nlargest(5, "total_mentions")
    for _, row in top_mentions.iterrows():
        ax.annotate(row["canonical_name"],
                    (row["log_reviews"], row["total_mentions"]),
                    fontsize=7, color=C_ANNOT, ha="left", va="bottom",
                    xytext=(5, 4), textcoords="offset points")

    ax.set_xlabel("Google review count (log10 scale)")
    ax.set_ylabel("Total AI mentions")
    ax.set_title("Review volume predicts AI mentions more than rating does")
    light_grid(ax, "both")
    sns.despine()
    plt.tight_layout()
    save(fig, "reviews_vs_mentions.png")


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    setup_style()
    conn = sqlite3.connect(str(DB_PATH))
    print(f"Connected to {DB_PATH}")
    print(f"Exporting charts to {OUT_DIR}/\n")

    chart_model_coverage(conn)
    chart_model_breadth(conn)
    chart_zombie_status(conn)
    chart_jaccard_stability(conn)
    chart_search_overlap(conn)
    chart_reviews_vs_mentions(conn)

    conn.close()
    print("\nDone! 6 charts exported.")


if __name__ == "__main__":
    main()
