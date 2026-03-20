---
name: aeo-probe
description: Run a targeted AEO probe — ask 4 AI models about a specific business and report what they say, how often they mention it, and what competitors they surface instead.
allowed-tools: Bash, Read, Write, Grep, Glob
---

# AEO Probe

Run a targeted Answer Engine Optimization probe for a specific business. This queries GPT-4o, Claude, Gemini, and Perplexity with discovery prompts across 4 specificity tiers, then analyzes detection rates, competitor mentions, and model agreement.

## Arguments

The user should provide: `<business_name>` and optionally `<city>` (defaults to Singapore).

Example: `/aeo-probe Sabai Fine Thai` or `/aeo-probe "Joe's Pizza" New York`

## Your task

### Step 1: Generate probe prompts

Create a Python script at `data/probes/<sanitized_business_name>/probe.py` that generates 20 discovery prompts in 4 tiers:

- **Tier 1 (Generic, 5 prompts):** Broad category queries where the business *could* appear but probably won't. E.g., "Best [cuisine] in [city]"
- **Tier 2 (Location-narrowed, 5 prompts):** Add the business's geographic area. E.g., "Good [cuisine] near [neighbourhood]"
- **Tier 3 (Attribute-specific, 5 prompts):** Target the business's unique selling points. E.g., "[cuisine] with [unique feature] in [city]"
- **Tier 4 (Near-name, 5 prompts):** Test name recognition directly. E.g., "Is [business name] any good?", "Tell me about [business name]"

Before generating prompts, search the web for the business to understand its cuisine, location, unique attributes, and competitors. Use this context to write prompts that test real discovery paths.

### Step 2: Run queries

Use the project's query runner to execute all prompts across 4 models x 2 search modes (ON/OFF) = 160 queries.

```bash
cd /Users/coddiwomplers/Desktop/Python/profound
python -c "
import asyncio, json, sys
sys.path.insert(0, '.')
from src.models import DiscoveryPrompt, Dimension, ModelName, Specificity
from src.query_runner import query_model

# ... load prompts from the generated probe script
# ... run all queries with proper concurrency limits
# Perplexity: max 2 concurrent, Others: max 4
"
```

Save raw results to `data/probes/<business_name>/results.json`.

### Step 3: Parse responses

Use the project's response parser (Claude Haiku) to extract structured restaurant mentions:

```bash
python -c "
import asyncio, json, sys
sys.path.insert(0, '.')
from src.response_parser import parse_batch
# ... parse all results
"
```

Save parsed results to `data/probes/<business_name>/parsed.json`.

### Step 4: Analyze and report

Generate a markdown report at `data/probes/<business_name>/report.md` with:

1. **Detection rate:** X/160 queries mentioned the business (Y%)
2. **Tier breakdown:** Detection rate per tier (Generic vs Location vs Attribute vs Near-name)
3. **Model breakdown:** Which models mention it most/least
4. **Search ON vs OFF:** Does web search help or hurt?
5. **Detection matrix:** Full prompt x model x search grid showing rank position or "not found"
6. **Competitor analysis:** Top 20 businesses mentioned instead (these are "eating your lunch")
7. **Breakout prompts:** Which prompts surface the business most reliably (best angles for content strategy)
8. **Recommendations:** 3-5 actionable suggestions based on the data

Present the report to the user after generation. Highlight the most surprising findings.

## Cost estimate

Inform the user before running: ~160 queries costs approximately $10-12 (Claude search ON dominates at ~$0.46/query). Ask for confirmation before proceeding.

## Important

- Use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `PERPLEXITY_API_KEY` from the `.env` file
- Perplexity max 2 concurrent queries (rate limited)
- Save all raw responses before parsing (audit trail)
- Do NOT write to the main `data/aeo.db` database — probes are standalone
