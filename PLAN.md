# Development Plan

## Phase 1: Prompt Library + First Data Pull ✅ COMPLETE
**Goal:** Build the research instrument and collect first dataset.

### 1a: Prompt Library ✅
- [x] Consolidate prompts from 5 LLM brainstorming sessions (Claude, ChatGPT, Gemini, Grok, Perplexity) into `prompts/discovery_prompts.json`
- [x] Structure: each prompt has `id`, `text`, `dimension` (8 dimensions), `category`, `specificity` (broad/medium/narrow)
- [x] 140 prompts covering the full matrix (581 raw → 140 after fuzzy dedup & thinning)
- [ ] Include both "tourist" and "local" framings for comparable prompts *(deferred — not needed for core analysis)*

### 1b: Query Runner ✅
- [x] Build `src/query_runner.py` — takes a prompt, queries N models, returns structured results
- [x] Models: GPT-4o, Claude Sonnet, Gemini 2.5 Flash, Perplexity Sonar
- [x] For each model, query with search/browsing OFF where possible (parametric only)
- [x] Then query with search ON where available
- [x] Store: raw response, model name, search_enabled flag, timestamp, prompt_id
- [x] Rate limiting + retry logic + progress bar (rich)
- [x] Save all raw responses to `data/raw/` as JSON

### 1c: First Pull ✅
- [x] Run full prompt library × all models × search on/off
- [x] **Search OFF sweep:** 140 prompts × 4 models = 560 queries, cost $0.97
- [x] **Search ON sweep:** 140 prompts × 4 models = 560 queries, cost $65.38
- [x] **Total: 1,120 queries** stored in SQLite (`data/aeo.db`) + individual JSON files in `data/raw/`
- [x] Combined API cost: **$66.36** (Claude search ON dominated at $64.71 due to web_search tool fetching full page content as input tokens)

## Phase 2: Response Parser ✅ COMPLETE
**Goal:** Extract structured restaurant data from raw LLM responses.

**Summary:** 1,690 total queries, 12,256 mentions, 3,666 canonical restaurants (after all merges). Stability test (570 queries) confirmed LLM recommendations are surprisingly unstable (mean Jaccard 0.256).

### 2a: Extraction Pipeline ✅
- [x] Build `src/response_parser.py` — uses Claude Haiku 4.5 for structured extraction
- [x] Use Claude API to parse each raw response into structured data
- [x] Extract per response: list of restaurants mentioned, each with name, rank_position, neighbourhood, cuisine_tags, vibe_tags, price_indicator, descriptors, sentiment_score, is_primary_recommendation
- [x] Build restaurant name normalization (fuzzy matching to canonical names)
- [x] Store parsed data in SQLite
- [x] **Results:** 1,120/1,120 parsed, **7,893 mentions**, **3,266 unique names**, avg 7.0 mentions/response
- [x] Parsing cost: ~$7.10

### 2b: Entity Resolution ✅
- [x] Build a canonical restaurant registry from all parsed mentions (`src/entity_resolution.py`)
- [x] Three-stage pipeline: exact normalized → base name → fuzzy match with shared-word penalty (rapidfuzz + Union-Find)
- [x] **3,266 unique names → 3,038 canonicals** (294 automated merges + 6 manual)
- [x] 7,893/7,893 mentions linked to canonical_id (zero unlinked)
- [x] 148 restaurants mentioned by all 4 models (consensus set), 2,175 by only 1 model (long tail)
- [x] 183 borderline pairs saved for future review (`data/borderline_pairs.json`)

### 2c: Recommendation Stability Test ✅
- [x] 15 prompts stratified: 5 broad, 5 medium, 5 narrow across cuisine/neighbourhood/vibe/occasion/price
- [x] 570 queries (15 prompts × 5 runs × 4 models × 2 search modes; Claude ON = 3 runs to control cost)
- [x] **Key finding: LLM recommendations are surprisingly unstable**
  - Mean Jaccard similarity: 0.256 (only ~26% set overlap between runs)
  - Mean Kendall's tau: 0.571 (moderate rank correlation when items do overlap)
  - 79.5% of appearances are stochastic (≤2/5 runs), only 12.7% are core (≥4/5)
- [x] GPT-4o most stable (Jaccard 0.317), Gemini least (0.224)
- [x] Search OFF slightly more stable than ON (0.264 vs 0.247)
- [x] Cost: $22.87 (queries $19.04 + parsing $3.83)
- [x] Added 679 new canonical entries (restaurants seen only in stability runs, `model_count=0`)

## Phase 3: Ground Truth + Validation — PARTIALLY COMPLETE
**Goal:** Build comparison datasets independent of LLM training data.

### 3a: Google Maps Data ✅ (partially complete)
- [x] Use Google Places Text Search API to get structured data for restaurants in parsed dataset
- [x] Pull: rating, review_count, price_level, category, location
- [x] **2,702 Google Places matches** (1,549 HIGH confidence, 605 MEDIUM confidence)
- [x] **1,267 human-verified** entries (top ~300 restaurants triaged manually)
- [x] **2,200 OPERATIONAL**, 441 CLOSED_PERMANENTLY
- [x] **Phase 3a triage:** 1,290 human-verified matches, 12 merges, 3 anomaly patches applied
- [x] **Place ID dedup pass:** 33 additional merges via Google place_id signal (e.g., Violet Oon ↔ National Kitchen, Zen ↔ Restaurant Zén, Tian Tian ↔ Tian Tian Hainanese Chicken Rice)
- [x] **Review anomaly bug fixed** in `select_best_match`: `_review_count_override()` heuristic prefers candidates with ≥5x reviews + ≥55% name similarity (code fix only, not re-run)
- [x] Google API cost: ~$304 SGD
- [ ] ~964 canonical restaurants with no Google match (mostly long-tail, 1-2 mentions) — deferred

**Running totals after all Phase 3a merges:**
- Canonical restaurants: **3,666 total** (3,038 after Phase 2b → +679 from Phase 2c stability → -12 triage merges → -33 place_id dedup → **3,666 confirmed in DB**)
- Of which **675 are stability-test-only** (`model_count=0`, incomplete metadata) — the **active research set is ~2,991**
- Total mentions: **12,256** (all linked)
- Total queries: **1,690** (1,120 original + 570 stability)

### 3b: Human Panel — NOT STARTED
- [ ] Build Google Form for friends panel (15-20 Singapore residents)
- [ ] Rate restaurants on: food quality, vibe, value, service (1-5)
- [ ] Tag each restaurant for: date night? business lunch? family? casual hangout? special occasion?
- [ ] Free text: "what restaurant do you recommend that nobody knows about?"
- [ ] Import results into SQLite

### 3c: Recency Test — NOT STARTED
- [ ] Identify 20+ restaurants that opened in 2025-2026 (after training cutoffs)
- [ ] Test which models find them (search on vs off)
- [ ] Measure "new restaurant discovery latency"

## Phase 4: Analysis + Visualization — IN PROGRESS
**Goal:** Answer the core research questions.

### Key Questions:
1. **Model agreement:** Which restaurants do ALL models recommend? Which are model-specific?
2. **Vibe mapping:** What "vibes" does each model associate with which restaurants? Do models agree on vibes?
3. **Signal importance:** What predicts whether a restaurant gets recommended? (Michelin status, Google rating, review count, media coverage, website quality)
4. **Bias detection:** Tourist vs local bias? Western cuisine bias? Price bias? Recency bias?
5. **Parametric vs RAG:** How different are recommendations with search on vs off?
6. **Human alignment:** Do AI recommendations match what actual Singapore residents prefer?
7. **Blind spots:** Restaurants loved by locals but invisible to all models

### Deliverables:
- [ ] Jupyter notebooks with full analysis (publishable quality)
- [ ] Streamlit dashboard for interactive exploration
- [ ] README with key findings and methodology

## Future / Stretch
- Re-run queries monthly to track changes over time
- Add "intervention test" — modify a restaurant's web presence and measure if AI recommendations change
- Expand to hawker centres
- Fork-friendly design so others can run for their city

## Deferred / Backlog
- **(a) Re-run Google Places matcher on ~964 long-tail restaurants** with fixed `_review_count_override()` algorithm. These are mostly 1-2 mention restaurants — not needed for headline analysis but would improve completeness.
- **(b) Second triage round for long-tail matches.** The current 1,267 human-verified entries cover the top ~300 most-mentioned restaurants. A second pass on MEDIUM/LOW confidence matches in the long tail would catch more errors.
- **(c) Monthly re-query tracking.** Re-run the full prompt library periodically to measure recommendation drift over time. Infrastructure exists (`query_runner.py`), just needs a scheduling wrapper and delta analysis.
