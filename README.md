# What Does AI Think About Singapore Restaurants?

**A systematic study of how large language models recommend restaurants — and what they get wrong.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet)](https://docs.astral.sh/uv/)

---

Ask ChatGPT, Claude, Gemini, or Perplexity: *"Where should I eat in Singapore?"*

You'll get a confident, well-written answer. But is it **good**? Does it match what locals actually recommend? Does it surface the Michelin-starred spots or the hidden hawker gems? Does it have a Western cuisine bias? A tourist trap bias? A recency problem?

**Nobody has systematically studied this. Until now.**

This project queries 4 major LLMs with 100+ carefully designed prompts about Singapore restaurants, parses every recommendation into structured data, and analyzes what patterns emerge. It's open-source research into **Answer Engine Optimization (AEO)** — a field where [companies are raising at $1B+ valuations](https://www.profound.co), but where almost no public, reproducible research exists.

## Why This Matters

LLMs are becoming the **default discovery layer** for restaurants, travel, and local businesses. When someone asks an AI assistant for restaurant recommendations, that response shapes real-world foot traffic, revenue, and reputation.

Yet we have no idea:
- **What signals drive LLM recommendations?** Michelin stars? Google reviews? Media coverage? SEO?
- **Do different models agree?** Or does each AI have its own "taste"?
- **What's missing?** Which beloved local spots are invisible to AI?
- **How stale are the recommendations?** Can AI find restaurants that opened this year?
- **Is there bias?** Toward Western cuisine? Tourist areas? Higher price points?

This project builds the dataset and analysis to answer these questions — starting with Singapore as a well-scoped, data-rich test case.

## Methodology

### 1. Prompt Library
We designed 140 discovery prompts spanning 8 dimensions, consolidated from 5 LLM brainstorming sessions (Claude, ChatGPT, Gemini, Grok, Perplexity):

| Dimension | Count | Examples |
|-----------|-------|----------|
| **Cuisine** | 25 | "Best ramen in Singapore", "Where to find authentic Peranakan food" |
| **Occasion** | 20 | "Romantic dinner spot", "Best for a business lunch" |
| **Neighbourhood** | 21 | "Good restaurants near Tiong Bahru", "Best eats in Kampong Glam" |
| **Vibe** | 22 | "Cozy cafe with good coffee", "Lively bar with great food" |
| **Price** | 13 | "Cheap and good dinner", "Worth-the-splurge fine dining" |
| **Constraint** | 13 | "Best vegetarian restaurants", "Late night food after midnight" |
| **Comparison** | 13 | "Burnt Ends vs Nouri — which is better?", "Most overrated restaurant?" |
| **Experiential** | 13 | "Plan my 3-day food trip", "Where do chefs eat on their day off?" |

Each prompt is tagged with specificity level (broad/medium/narrow) for controlled variation.

### 2. Multi-Model Querying
Every prompt is sent to **4 models**, each queried twice (search enabled and disabled where supported):

- **OpenAI GPT-4o** — parametric + browsing
- **Anthropic Claude** — parametric only
- **Google Gemini 1.5 Pro** — parametric + grounding
- **Perplexity Sonar** — always search-augmented

### 3. Structured Extraction
Raw responses are parsed into structured data using a dedicated extraction pipeline. For each restaurant mentioned, we capture:
- Name and rank position
- Neighbourhood, cuisine tags, vibe tags
- Price indicator and sentiment
- Whether it's a primary recommendation or just mentioned in passing

### 4. Analysis
We compare AI recommendations against ground truth:
- **Google Maps** ratings and review counts
- **Human panel** of 15-20 Singapore residents
- **Recency tests** with restaurants opened after model training cutoffs

## Key Research Questions

1. Which restaurants do **all models agree** on? Which are model-specific?
2. What **signals predict** whether a restaurant gets recommended?
3. How do **parametric vs. search-augmented** recommendations differ?
4. Is there measurable **bias** toward tourist spots, Western cuisine, or high prices?
5. What do **locals love** that AI completely misses?

## Quick Start

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- API keys for at least one of: OpenAI, Anthropic, Google, Perplexity

### Setup

```bash
# Clone the repo
git clone https://github.com/spiffler33/sg-restaurant-aeo.git
cd sg-restaurant-aeo

# Install dependencies with uv
uv sync

# Or with pip
pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your API keys
```

### Run a Query Sweep

```bash
# Query all models with the full prompt library
python -m src.query_runner

# Parse responses into structured data
python -m src.response_parser

# Launch the dashboard
streamlit run dashboard/app.py
```

## Project Structure

```
sg-restaurant-aeo/
├── CLAUDE.md              # Development instructions
├── PLAN.md                # Phased development plan
├── README.md              # You are here
├── pyproject.toml         # Project config (uv)
├── prompts/
│   ├── discovery_prompts.json    # The master prompt library (140 prompts)
│   ├── extraction_prompt.txt     # System prompt for structured extraction
│   └── raw/                      # Original prompts from 5 LLM brainstorms
├── scripts/
│   └── consolidate_prompts.py    # Prompt dedup & normalization pipeline
├── src/
│   ├── models.py           # Pydantic models / DB schema
│   ├── db.py               # SQLite operations
│   ├── query_runner.py     # Multi-model query execution
│   ├── response_parser.py  # Structured extraction from raw responses
│   └── analysis.py         # Core analysis functions
├── notebooks/
│   ├── 01_exploratory.ipynb
│   ├── 02_model_comparison.ipynb
│   └── 03_signal_analysis.ipynb
├── dashboard/
│   └── app.py              # Streamlit interactive dashboard
├── data/
│   ├── raw/                # Raw API responses (gitignored)
│   └── processed/          # Parsed structured data
└── tests/
```

## Run It for Your City

This project is designed to be forked. To study LLM restaurant recommendations for **your** city:

1. **Fork this repo**
2. **Adapt the prompt library** — Replace "Singapore" with your city in `prompts/discovery_prompts.json`. Update neighbourhood names, local cuisine references, and cultural context.
3. **Run the query sweep** — The query runner works for any city. Just update the prompts.
4. **Build your ground truth** — Swap in local Google Maps data and recruit your own human panel.
5. **Analyze and share** — The analysis notebooks are city-agnostic. Run them on your data and publish your findings.

Cities we'd love to see studied: **Tokyo, Bangkok, London, NYC, Mexico City, Istanbul, Melbourne.**

If you fork this for your city, open a PR to add your repo to a "sister studies" section here.

## Contributing

We welcome contributions at every level:

- **Add prompts** — Think of a restaurant discovery question we missed? Add it to the prompt library.
- **Improve parsing** — The extraction pipeline can always be more accurate. Help us catch edge cases.
- **Analyze the data** — Find interesting patterns in the data? Submit a notebook.
- **Ground truth** — Are you a Singapore local? Help us validate AI recommendations against reality.
- **Fork for your city** — The most impactful contribution is replicating this study elsewhere.

See [PLAN.md](PLAN.md) for the development roadmap and where help is most needed.

## Research Context

**Answer Engine Optimization (AEO)** is the practice of optimizing content to be surfaced by AI-powered answer engines. Companies like [Profound](https://www.profound.co) have raised hundreds of millions to help brands understand and influence their AI visibility.

This project takes the research angle: instead of optimizing *for* AI engines, we're studying *how* they work. The restaurant domain is ideal because:
- Recommendations are subjective (no single "right answer")
- Ground truth is available (Google Maps, Michelin, local knowledge)
- The stakes are real (restaurants live and die by discovery)
- It's universally relatable (everyone eats)

## License

MIT — use this however you want. If you publish research based on this work, a citation would be appreciated.

---

*Built with curiosity about how AI shapes the real world. If you find this interesting, give it a star.*
