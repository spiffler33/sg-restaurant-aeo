---
name: aeo-zombie
description: Find zombie restaurants — businesses that AI models actively recommend but that are permanently closed, relocated, or unverifiable on Google Places.
allowed-tools: Bash, Read, Grep, Glob
---

# AEO Zombie Check

Find "zombie restaurants" — places that AI models confidently recommend but that are actually closed, relocated, or can't be verified. This is one of the most striking findings from the research: 13% of the top 100 most-mentioned verified restaurants are zombies.

## Arguments

Optional:
- `/aeo-zombie` — show all zombies from the Singapore research dataset
- `/aeo-zombie --top 50` — limit to top N most-mentioned zombies
- `/aeo-zombie --model claude` — filter to a specific model's zombies

## Your task

### Step 1: Query the database

Connect to `data/aeo.db` and find restaurants that are mentioned by AI but flagged as closed or unverifiable.

```python
import sqlite3, json

conn = sqlite3.connect("data/aeo.db")
conn.row_factory = sqlite3.Row

# Zombie restaurants: mentioned by AI but closed on Google Places
zombies = conn.execute("""
    SELECT cr.canonical_name, cr.total_mentions, cr.model_count,
           cr.models_mentioning, gp.business_status, gp.rating,
           gp.user_ratings_total, gp.google_name, gp.formatted_address,
           gp.match_confidence
    FROM canonical_restaurants cr
    JOIN google_places gp ON cr.id = gp.canonical_id
    WHERE gp.business_status IN ('CLOSED_PERMANENTLY', 'CLOSED_TEMPORARILY')
      AND cr.model_count > 0
    ORDER BY cr.total_mentions DESC
""").fetchall()

# Also find high-mention restaurants with NO Google match (unverifiable)
unmatched = conn.execute("""
    SELECT cr.canonical_name, cr.total_mentions, cr.model_count,
           cr.models_mentioning
    FROM canonical_restaurants cr
    LEFT JOIN google_places gp ON cr.id = gp.canonical_id
    WHERE gp.id IS NULL
      AND cr.model_count > 0
      AND cr.total_mentions >= 5
    ORDER BY cr.total_mentions DESC
""").fetchall()
```

### Step 2: Analyze

For each zombie, determine:
- **Mention count:** How often AI recommends it
- **Model coverage:** Which models mention it (all 4 = stronger zombie signal)
- **Last known status:** CLOSED_PERMANENTLY vs CLOSED_TEMPORARILY
- **Former rating:** Google rating before closure (high-rated zombies = bigger gap)
- **Zombie risk score:** `total_mentions * model_count` — higher = more people getting bad recommendations

### Step 3: Present findings

Output a markdown table sorted by zombie risk:

```
| Restaurant | Mentions | Models | Status | Former Rating | Risk |
```

Then summarize:
- Total zombie count and % of verified restaurants
- Which models have the worst zombie problem
- Search ON vs OFF: does web search catch closures?
- Notable zombies (famous restaurants that closed recently)

### Step 4: Search ON/OFF comparison

Query the database to check if search-enabled queries still recommend zombies:

```python
# Do search-ON queries still recommend closed restaurants?
search_zombies = conn.execute("""
    SELECT rm.restaurant_name, qr.search_enabled, COUNT(*) as mentions
    FROM restaurant_mentions rm
    JOIN parsed_responses pr ON rm.parsed_response_id = pr.id
    JOIN query_results qr ON pr.query_result_id = qr.id
    JOIN canonical_restaurants cr ON rm.canonical_id = cr.id
    JOIN google_places gp ON cr.id = gp.canonical_id
    WHERE gp.business_status = 'CLOSED_PERMANENTLY'
    GROUP BY rm.canonical_id, qr.search_enabled
    ORDER BY mentions DESC
""").fetchall()
```

Report whether web search reduces zombie recommendations.

## Important

- Database path: `data/aeo.db`
- Only analyze restaurants with `model_count > 0` (active research set)
- Google Places data is in the `google_places` table, linked via `canonical_id`
- `business_status` values: 'OPERATIONAL', 'CLOSED_PERMANENTLY', 'CLOSED_TEMPORARILY'
