---
name: aeo-compare
description: Compare how AI models rank and describe specific restaurants or categories. Queries the existing AEO research database (1,690 queries, 12,256 mentions, 4 models).
allowed-tools: Bash, Read, Grep, Glob
---

# AEO Compare

Compare how GPT-4o, Claude, Gemini, and Perplexity rank and describe restaurants or categories from the existing research dataset.

## Arguments

The user provides one of:
- A restaurant name: `/aeo-compare Odette` — how do models differ on this restaurant?
- Two restaurants: `/aeo-compare "Burnt Ends" vs "Nouri"` — head-to-head comparison
- A category: `/aeo-compare "hawker food"` — which restaurants dominate this category across models?

## Your task

### Step 1: Query the database

Connect to the SQLite database at `data/aeo.db` and run analysis queries.

```python
import sqlite3, json

conn = sqlite3.connect("data/aeo.db")
conn.row_factory = sqlite3.Row

# For a single restaurant — find all mentions across models and prompts
rows = conn.execute("""
    SELECT rm.restaurant_name, rm.rank_position, rm.cuisine_tags, rm.vibe_tags,
           rm.price_indicator, rm.sentiment, rm.descriptors,
           qr.model_name, qr.search_enabled, dp.text as prompt_text,
           dp.dimension, dp.specificity
    FROM restaurant_mentions rm
    JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
    JOIN query_results qr ON pr.query_result_id = qr.id
    JOIN discovery_prompts dp ON qr.prompt_id = dp.id
    WHERE rm.canonical_id = (
        SELECT id FROM canonical_restaurants
        WHERE canonical_name LIKE ?
    )
""", (f"%{restaurant_name}%",)).fetchall()
```

### Step 2: Analyze and present

For a **single restaurant**, report:
- Total mentions across all queries (and % of queries that mention it)
- Per-model mention count and average rank position
- Search ON vs OFF detection rates
- Which prompt dimensions trigger it most (cuisine? vibe? neighbourhood?)
- How each model describes it (cuisine tags, vibe tags, sentiment)
- Google Places ground truth (if available): rating, review count, operational status

For a **head-to-head comparison**, report:
- Side-by-side mention counts and ranks per model
- Prompts where one appears but not the other
- Attribute differences (how models describe each)
- Which model "prefers" which restaurant

For a **category query**, report:
- Top 20 restaurants mentioned for related prompts
- Model agreement/disagreement on the category
- Surprising inclusions or omissions

### Step 3: Format output

Present results as a clean markdown summary with tables. Use the project's muted visual tone — numbers first, no editorializing.

## Important

- Database path: `data/aeo.db`
- The DB has 6 tables: discovery_prompts, query_results, parsed_responses, restaurant_mentions, canonical_restaurants, google_places
- `restaurant_mentions.canonical_id` links to `canonical_restaurants.id`
- `canonical_restaurants` with `model_count > 0` = active research set (2,991 restaurants)
- JSON fields stored as TEXT: cuisine_tags, vibe_tags, descriptors, variant_names, models_mentioning
