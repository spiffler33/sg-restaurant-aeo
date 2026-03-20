# Next Steps — Pick Up Here

Last updated: 2026-03-15

---

## 1. Sabai Fine Thai Intervention (Active)

We've studied why Sabai is invisible to AI (§18-§20 in OBSERVATIONS.md). Now implement the fixes and measure the before/after.

**What's done:**
- 160-query targeted probe (data in `data/raw/sabai_probe/`)
- Full web presence audit (`data/sabai_intervention/web_audit.md`)
- Intervention hierarchy ranked by ROI (§20)
- Baseline detection rate: 45% (72/160 queries)

**What's next:**
- Implement website fixes (schema.org markup, meta tags, "Marina Bay" on homepage)
- Track blog coverage / listicle placement if any happens
- Re-run the probe after interventions to measure lift
- Potential second Substack post: "We tried to make a restaurant visible to AI"

**Key files:** `scripts/sabai_probe.py`, `data/processed/sabai_probe_report.md`

---

## 2. Phase 4 Analysis Notebooks (Pending)

The flagship notebook (`notebooks/01_exploratory.ipynb`) is done. Two deeper notebooks are stubs:

**`notebooks/02_model_comparison.ipynb`** — Deep model comparison
- Per-model Michelin bias (does Gemini weight stars more than GPT-4o?)
- Cuisine-dimension breakdowns (which model is best for Japanese vs hawker queries?)
- Model-exclusive restaurants deep dive (why does only GPT-4o know The Black Swan?)
- How each model frames the same restaurant differently

**`notebooks/03_signal_analysis.ipynb`** — Predictive signal analysis
- What predicts which *specific* model recommends you?
- Michelin status, Instagram presence, Google Maps categories as features
- Neighbourhood-level analysis (do models know Tiong Bahru better than Jurong?)
- Cuisine type as a predictor of mention frequency

---

## 3. Streamlit Dashboard (Pending)

**`dashboard/app.py`** — currently a placeholder.

Planned features:
- Search for any restaurant → see which models know it
- Per-restaurant detail: how they describe it, core vs stochastic
- Model comparison view
- Zombie restaurant browser

---

## 4. Substack Blog Published

The first post is live. Blog draft at `blog/what_does_ai_think.md`, charts at `assets/charts/blog/` (16 PNGs, muted palette).

**Lesson learned:** Markdown doesn't paste well into Substack. Next post, explore Substack API or generate clean HTML instead.

---

## 5. DefaultTaste-Inspired Ideas (New)

Detailed writeup: [IDEAS_FROM_DEFAULTTASTE.md](IDEAS_FROM_DEFAULTTASTE.md)

Key ideas to try, in priority order:
1. **Negation prompts for Sabai** — generate correction prompts that steer away from the AI Canon, measure if Sabai surfaces. Low effort, high value, feeds Substack #2.
2. **Model taste radar charts** — per-model cuisine/price/neighbourhood bias profiles. Data exists, just needs visualization. Fits Notebook 02.
3. **High-N probing (50-100x)** — run targeted prompts 50-100 times for true frequency distributions instead of 5-run Jaccard.
4. **"Default restaurant" framing** — recast the AI Canon as "default taste" in the DefaultTaste sense.

---

## 6. Related Work / Community

- **[DefaultTaste](https://github.com/ilhamfp/DefaultTaste)** — Winner at the Gemini 3 Singapore hackathon (March 7, 2026). Explores AI and default taste formation. Worth reviewing for overlapping methodology or collaboration opportunities.

---

## Priority Order

If you have limited time, go in this order:

1. **Sabai intervention** — most interesting, active experiment, potential blog post
2. **Notebook 02** (model comparison) — builds on existing data, no new queries needed
3. **Notebook 03** (signal analysis) — requires more thought on feature engineering
4. **Dashboard** — nice to have, not urgent
