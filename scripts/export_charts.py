#!/usr/bin/env python3
"""Export key charts from the analysis as high-resolution PNGs for README.

Generates 6 charts to assets/charts/ at 300 DPI:
  1. model_coverage.png    — Distribution of restaurants by how many models mention them
  2. model_breadth.png     — Per-model unique restaurant count
  3. zombie_status.png     — Business status of AI-recommended restaurants
  4. jaccard_stability.png — Distribution of Jaccard similarities (recommendation stability)
  5. search_overlap.png    — Search ON vs OFF restaurant overlap
  6. reviews_vs_mentions.png — Google review count vs AI mention frequency
"""

import sqlite3
from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

# ── Config ───────────────────────────────────────────────────────────────────
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aeo.db"
OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DPI = 300

MODEL_COLORS = {
    "openai/gpt-4o": "#2ca02c",
    "anthropic/claude-sonnet-4-20250514": "#ff7f0e",
    "google/gemini-2.5-flash": "#1f77b4",
    "perplexity/sonar": "#9467bd",
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


def model_short(name: str) -> str:
    return MODEL_SHORT.get(name, name)


def model_color(name: str) -> str:
    return MODEL_COLORS.get(name, "#999999")


def setup_style():
    sns.set_theme(style="whitegrid", font_scale=1.1)
    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["axes.titlesize"] = 13
    plt.rcParams["axes.labelsize"] = 11


def save(fig, name: str):
    path = OUT_DIR / name
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved {path}")


# ── Chart 1: Model coverage distribution ─────────────────────────────────────
def chart_model_coverage(conn):
    model_dist = pd.read_sql_query("""
        SELECT model_count, COUNT(*) AS restaurants
        FROM canonical_restaurants
        WHERE model_count > 0
        GROUP BY model_count
        ORDER BY model_count
    """, conn)

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#d62728", "#ff7f0e", "#ffbb78", "#2ca02c"]
    bars = ax.bar(model_dist["model_count"], model_dist["restaurants"],
                  color=colors, edgecolor="white", linewidth=0.5)

    for bar, val in zip(bars, model_dist["restaurants"]):
        pct = val / model_dist["restaurants"].sum() * 100
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 20,
                f"{val:,}\n({pct:.1f}%)", ha="center", va="bottom", fontsize=10)

    ax.set_xlabel("Number of models that mention the restaurant")
    ax.set_ylabel("Number of restaurants")
    ax.set_title("How many models know each restaurant?")
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["1 model\n(long tail)", "2 models", "3 models",
                        "4 models\n(consensus)"])
    sns.despine()
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

    fig, ax = plt.subplots(figsize=(8, 5))
    bar_colors = [model_color(m) for m in per_model["model_name"]]
    bars = ax.barh(
        [model_short(m) for m in per_model["model_name"]],
        per_model["unique_restaurants"],
        color=bar_colors, edgecolor="white",
    )
    for bar, val in zip(bars, per_model["unique_restaurants"]):
        ax.text(bar.get_width() + 15, bar.get_y() + bar.get_height() / 2,
                f"{val:,}", va="center", fontsize=11, fontweight="bold")

    ax.set_xlabel("Unique restaurants mentioned (main sweep)")
    ax.set_title("Restaurant knowledge breadth by model")
    ax.set_xlim(0, per_model["unique_restaurants"].max() * 1.15)
    ax.invert_yaxis()
    sns.despine()
    plt.tight_layout()
    save(fig, "model_breadth.png")


# ── Chart 3: Zombie restaurant status ────────────────────────────────────────
def chart_zombie_status(conn):
    status_data = pd.read_sql_query("""
        SELECT gp.business_status, COUNT(*) AS count
        FROM google_places gp
        JOIN canonical_restaurants cr ON gp.canonical_id = cr.id
        WHERE gp.human_verified = 1 AND cr.model_count > 0
        GROUP BY gp.business_status
        ORDER BY count DESC
    """, conn)

    if len(status_data) == 0:
        print("  SKIP zombie_status — no verified Google Places data")
        return

    total_verified = status_data["count"].sum()
    status_colors = {
        "OPERATIONAL": "#2ca02c",
        "CLOSED_PERMANENTLY": "#d62728",
        "CLOSED_TEMPORARILY": "#ff7f0e",
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                    gridspec_kw={"width_ratios": [1, 1.3]})

    pie_colors = [status_colors.get(s, "#999") for s in status_data["business_status"]]
    pie_labels = [s.replace("_", " ").title() for s in status_data["business_status"]]
    wedges, texts, autotexts = ax1.pie(
        status_data["count"], labels=pie_labels, colors=pie_colors,
        autopct="%1.1f%%", startangle=90, textprops={"fontsize": 10},
    )
    for t in autotexts:
        t.set_fontweight("bold")
    ax1.set_title(f"Business status of AI-recommended restaurants\n"
                  f"(n={total_verified:,} verified)")

    bars = ax2.barh(pie_labels[::-1], status_data["count"].values[::-1],
                     color=pie_colors[::-1], edgecolor="white")
    for bar, val in zip(bars, status_data["count"].values[::-1]):
        ax2.text(bar.get_width() + 5, bar.get_y() + bar.get_height() / 2,
                 f"{val:,}", va="center", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Number of restaurants")
    ax2.set_title("Count by status")
    sns.despine(ax=ax2)

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
    cells = stability_mentions.groupby(["prompt_id", "model_name", "search_enabled"])

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

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(jac_df["jaccard"], bins=30, color="#1f77b4", edgecolor="white", alpha=0.8)
    ax.axvline(jac_df["jaccard"].mean(), color="#d62728", linestyle="--", linewidth=2,
               label=f'Mean = {jac_df["jaccard"].mean():.3f}')
    ax.axvline(jac_df["jaccard"].median(), color="#ff7f0e", linestyle=":", linewidth=2,
               label=f'Median = {jac_df["jaccard"].median():.3f}')
    ax.set_xlabel("Pairwise Jaccard similarity")
    ax.set_ylabel("Count")
    ax.set_title("How stable are LLM restaurant recommendations?")
    ax.legend()
    sns.despine()
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
             WHERE canonical_id NOT IN (SELECT canonical_id FROM off_set)) AS search_on_only,
            (SELECT COUNT(*) FROM off_set
             WHERE canonical_id NOT IN (SELECT canonical_id FROM on_set)) AS search_off_only
    """, conn)

    both = search_overlap["both"].values[0]
    on_only = search_overlap["search_on_only"].values[0]
    off_only = search_overlap["search_off_only"].values[0]

    fig, ax = plt.subplots(figsize=(8, 4))
    categories = ["Both modes", "Search ON only", "Search OFF only"]
    values = [both, on_only, off_only]
    colors_v = ["#2ca02c", "#1f77b4", "#ff7f0e"]
    bars = ax.barh(categories, values, color=colors_v, edgecolor="white")
    for bar, val in zip(bars, values):
        total = sum(values)
        pct = val / total * 100
        ax.text(bar.get_width() + 10, bar.get_y() + bar.get_height() / 2,
                f"{val:,} ({pct:.0f}%)", va="center", fontsize=11, fontweight="bold")

    ax.set_xlabel("Number of unique restaurants")
    ax.set_title("Restaurant overlap: Search ON vs OFF")
    ax.set_xlim(0, max(values) * 1.2)
    sns.despine()
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

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(ground_truth["log_reviews"], ground_truth["total_mentions"],
               alpha=0.4, s=20, c="#9467bd", edgecolors="none")

    z = np.polyfit(ground_truth["log_reviews"], ground_truth["total_mentions"], 1)
    p = np.poly1d(z)
    x_line = np.linspace(ground_truth["log_reviews"].min(),
                         ground_truth["log_reviews"].max(), 100)
    ax.plot(x_line, p(x_line), "--", color="#d62728", linewidth=2)

    r, pval = stats.spearmanr(ground_truth["log_reviews"],
                              ground_truth["total_mentions"])
    ax.text(0.05, 0.95, f"Spearman r = {r:.3f}\np = {pval:.2e}",
            transform=ax.transAxes, fontsize=10, va="top",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.8))

    top_mentions = ground_truth.nlargest(5, "total_mentions")
    for _, row in top_mentions.iterrows():
        ax.annotate(row["canonical_name"],
                    (row["log_reviews"], row["total_mentions"]),
                    fontsize=7, ha="left", va="bottom",
                    xytext=(5, 5), textcoords="offset points")

    ax.set_xlabel("Google review count (log10 scale)")
    ax.set_ylabel("Total AI mentions")
    ax.set_title("Review volume predicts AI mentions more than rating does")
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
