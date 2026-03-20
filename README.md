# What Does AI Think About Singapore Restaurants?

**13% of AI-recommended restaurants are permanently closed.** We asked GPT-4o, Claude, Gemini, and Perplexity 1,690 times and checked their answers against Google Places.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet)](https://docs.astral.sh/uv/)

![Zombie restaurants recommended by AI](assets/charts/zombie_status.png)

---

## Install

```bash
pip install -e .    # or: uv sync
```

## Use

```bash
# Check what AI says about a specific restaurant
aeo probe "Din Tai Fung" --city Singapore

# Browse the dataset
aeo stats
aeo zombie --top 20

# Run your own sweep (requires API keys)
aeo sweep --test          # 5 prompts x 4 models (quick test)
aeo sweep                 # 140 prompts x 4 models
aeo sweep --search-on     # same, with web search enabled
aeo parse                 # extract structured data from responses
aeo resolve               # deduplicate restaurant names
```

### Claude Code Skills

If you use [Claude Code](https://claude.ai/code), this repo ships with built-in skills:

```
/aeo-probe Sabai Fine Thai        # targeted probe: 20 prompts x 4 models x 2 search
/aeo-compare Odette               # how do models differ on a restaurant?
/aeo-compare "Burnt Ends" vs "Nouri"
/aeo-audit https://example.com    # web presence audit
/aeo-zombie                       # find AI-recommended restaurants that are closed
```

### No API keys? Browse the data

The full dataset is in the repo — no setup needed:
- **[Flagship notebook](notebooks/01_exploratory.ipynb)** — 16 figures, renders on GitHub
- **`data/aeo.db`** — SQLite database, open with any SQLite client
- **`data/processed/`** — exported CSVs

---

## Key Findings

### 1. The AI Canon: Only 5% consensus, 72% known to just one model

Only **152 restaurants (5.1%)** are recommended by all four models. **2,155 (72%)** are mentioned by just one. The shared canon — Odette, Burnt Ends, Candlenut, Lau Pa Sat, Hawker Chan — looks a lot like the English-language food media canon. Everything else is model-specific.

![Model coverage distribution](assets/charts/model_coverage.png)

### 2. Model Personalities: Gemini surfaces 2.6x more restaurants than GPT-4o

Gemini mentions **1,591 unique restaurants** across the main sweep. GPT-4o: **616**. This tracks with verbosity — Gemini averages 10.9 restaurants per response vs GPT-4o's 5.6. More output means more surface area for lesser-known places.

![Per-model restaurant knowledge breadth](assets/charts/model_breadth.png)

### 3. The Zombie Restaurant Problem

Of ~1,266 restaurants verified against Google Places, **30 are permanently or temporarily closed**. Among the top 100 most-mentioned, **13% are zombies**. Open Farm Community (44 mentions, all 4 models), Corner House (33 mentions, Michelin-starred) — closed, still recommended. Training data staleness in practice.

![Zombie restaurant status](assets/charts/zombie_status.png)

### 4. Recommendation Instability: ~75% of picks differ between identical queries

Same prompt, same model, five runs. Mean Jaccard similarity: **0.256**. Roughly 3 out of 4 picks change between runs. Only 12.7% of appearances are core (4+ out of 5 runs). Single-query AEO studies are measuring noise.

![Jaccard stability distribution](assets/charts/jaccard_stability.png)

### 5. Search Changes Everything: Only 24% overlap between search ON and OFF

Toggle web search and three-quarters of the restaurant set changes. Search ON surfaces **1,351 restaurants** absent from parametric memory — newer openings, recent press.

![Search ON vs OFF overlap](assets/charts/search_overlap.png)

### 6. Fame Beats Quality: Review volume predicts AI mentions, not rating

Google rating has **no correlation** with AI mention frequency (Spearman r = -0.070). Review *count* does (r = 0.279, p < 10^-23). It's not how good the reviews are — it's how many exist.

![Review count vs AI mentions](assets/charts/reviews_vs_mentions.png)

---

## Dataset

| Metric | Value |
|--------|-------|
| Total queries | 1,690 (1,120 main + 570 stability test) |
| Models | GPT-4o, Claude Sonnet, Gemini 2.5 Flash, Perplexity Sonar |
| Prompts | 140 across 8 dimensions |
| Restaurant mentions | 12,256 (100% entity-linked) |
| Canonical restaurants | 2,991 (active set) |
| Google Places verified | 1,266 |

## Methodology

**140 discovery prompts** across 8 dimensions (cuisine, occasion, neighbourhood, vibe, price, constraint, comparison, experiential), each sent to 4 models with search ON and OFF. Responses parsed via Claude Haiku into structured mentions. 3,332 raw names collapsed to 2,991 canonical restaurants through three-stage entity resolution. Ground-truthed against Google Places API with human triage.

Full methodology and analysis in [the notebook](notebooks/01_exploratory.ipynb). Research log in [OBSERVATIONS.md](OBSERVATIONS.md).

## Run It for Your City

This project is designed to be forked. Replace "Singapore" in `prompts/discovery_prompts.json`, run the sweep, build your ground truth.

```bash
# 1. Fork and clone
git clone https://github.com/YOUR_USERNAME/sg-restaurant-aeo.git
cd sg-restaurant-aeo && pip install -e .

# 2. Edit prompts for your city
# Update prompts/discovery_prompts.json

# 3. Run
cp .env.example .env   # add your API keys
aeo sweep --test       # test with 5 prompts first
aeo sweep              # full 140-prompt sweep
aeo parse && aeo resolve
```

Interesting cities to replicate: **Tokyo, Bangkok, London, NYC, Mexico City, Istanbul, Melbourne.**

If you fork this for your city, open a PR to add your repo to the list below.

## Project Structure

```
sg-restaurant-aeo/
├── src/
│   ├── cli.py              # `aeo` CLI entry point
│   ├── query_runner.py      # Multi-model async query execution
│   ├── response_parser.py   # Structured extraction (Claude Haiku)
│   ├── entity_resolution.py # Three-stage name deduplication
│   ├── google_places.py     # Google Places API matching
│   ├── models.py            # Pydantic data contracts
│   ├── db.py                # SQLite operations (6 tables)
│   └── stability_metrics.py # Jaccard, Kendall's tau
├── .claude/skills/          # Claude Code skills (aeo-probe, compare, audit, zombie)
├── prompts/
│   └── discovery_prompts.json  # 140 prompts, 8 dimensions
├── notebooks/
│   └── 01_exploratory.ipynb    # Flagship analysis (16 figures)
├── scripts/                    # Sweep, parsing, and analysis scripts
├── data/
│   ├── aeo.db                  # SQLite database
│   └── raw/                    # Raw API responses (JSON)
└── assets/charts/              # High-res chart PNGs
```

## Contributing

- **Add prompts** — restaurant discovery questions we missed
- **Improve parsing** — edge cases in the extraction pipeline
- **Analyze the data** — find patterns, submit a notebook
- **Fork for your city** — the most useful contribution

See [PLAN.md](PLAN.md) for the roadmap.

## Research Context

**Answer Engine Optimization (AEO)** is the practice of optimizing content to be surfaced by AI answer engines. Companies like [Profound](https://www.profound.co) have raised hundreds of millions doing this for brands. Almost no public, reproducible research exists.

This project takes the research angle: instead of optimizing *for* AI engines, studying *how* they work. Restaurants are a good domain because recommendations are subjective, ground truth exists, stakes are real, and it's universally relatable.

## Related Work

- **[DefaultTaste](https://github.com/ilhamfp/DefaultTaste)** — Winner at the Gemini 3 Singapore hackathon (March 7, 2026). Explores AI and default taste formation in food recommendations.

## License

MIT — use this however you want. If you publish research based on this work, a citation would be appreciated.
