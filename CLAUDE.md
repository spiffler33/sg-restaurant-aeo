# SG Restaurant AEO Research

## What This Project Is
A Karpathy-style research project investigating how LLMs recommend restaurants in Singapore. We systematically query multiple AI models with restaurant discovery prompts, parse their responses into structured data, and analyze what they get right, what they miss, and what signals drive their recommendations.

This is NOT a business/product. It's a public research repo meant to be interesting, shareable, and educational. Think of it as "What Does AI Think About Singapore Restaurants?" — a systematic audit of LLM-mediated restaurant discovery.

## Why This Matters
"Answer Engine Optimization" (AEO) is an emerging field — Profound just raised $96M at a $1B valuation doing this for brands. We're doing the open-source research version for a single, well-scoped domain: Singapore restaurants.

## Tech Stack
- **Language:** Python 3.11+
- **LLM APIs:** OpenAI (GPT-4o), Anthropic (Claude), Google Gemini, Perplexity
- **Database:** SQLite (single file, no server)
- **Parsing:** Pydantic models for structured extraction
- **Visualization:** Streamlit dashboard
- **Analysis:** Jupyter notebooks, pandas, plotly
- **Package management:** uv (preferred) or pip

## Project Structure
```
sg-restaurant-aeo/
├── CLAUDE.md              # This file
├── PLAN.md                # Phased development plan
├── README.md              # Public-facing research description
├── pyproject.toml         # Project config
├── .env.example           # API key template
├── prompts/
│   ├── discovery_prompts.json    # The master prompt library
│   └── extraction_prompt.txt     # System prompt for parsing LLM responses
├── src/
│   ├── __init__.py
│   ├── query_runner.py     # Multi-model query execution
│   ├── response_parser.py  # Extract structured restaurant data from LLM responses
│   ├── models.py           # Pydantic models / DB schema
│   ├── db.py               # SQLite operations
│   └── analysis.py         # Core analysis functions
├── notebooks/
│   ├── 01_exploratory.ipynb
│   ├── 02_model_comparison.ipynb
│   └── 03_signal_analysis.ipynb
├── dashboard/
│   └── app.py              # Streamlit dashboard
├── data/
│   ├── raw/                # Raw API responses (gitignored)
│   └── processed/          # Parsed structured data
└── tests/
```

## Key Design Decisions
1. **Store raw responses.** Always save the full API response before parsing. We'll want to re-parse later as our extraction improves.
2. **Model-agnostic query runner.** Use LiteLLM or a simple adapter pattern so adding a new model is trivial.
3. **Prompt library is first-class.** The prompt library (discovery_prompts.json) is a key research artifact. It should be well-structured with metadata (dimension, category, specificity level).
4. **SQLite for everything.** No Postgres, no Docker. Single file DB. Keep the barrier to contribution as low as possible.
5. **Notebooks for analysis, src/ for reusable code.** Analysis lives in notebooks. Reusable pipeline code lives in src/.

## Coding Conventions
- Type hints everywhere
- Docstrings on public functions
- Use `asyncio` for parallel API calls where possible
- Use `rich` for CLI progress display
- Environment variables for API keys (never hardcoded)
- All API calls should have retry logic with exponential backoff

## Current Phase
Phase 1: Prompt Library + First Data Pull. See PLAN.md for details.

## Important Context
- The prompt library is being co-developed across multiple LLMs (ChatGPT, Gemini, Perplexity, Claude) and will be consolidated here
- The owner (Spiff) has domain expertise in FICC markets/credit risk — the analytical rigor comes from that background
- This is a public repo aiming for GitHub stars — README quality and notebook presentation matter
