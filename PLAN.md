# Development Plan

## Phase 1: Prompt Library + First Data Pull (Week 1)
**Goal:** Build the research instrument and collect first dataset.

### 1a: Prompt Library
- [x] Consolidate prompts from 5 LLM brainstorming sessions (Claude, ChatGPT, Gemini, Grok, Perplexity) into `prompts/discovery_prompts.json`
- [x] Structure: each prompt has `id`, `text`, `dimension` (8 dimensions), `category`, `specificity` (broad/medium/narrow)
- [x] 140 prompts covering the full matrix (581 raw → 140 after fuzzy dedup & thinning)
- [ ] Include both "tourist" and "local" framings for comparable prompts

### 1b: Query Runner
- [x] Build `src/query_runner.py` — takes a prompt, queries N models, returns structured results
- [x] Models: GPT-4o, Claude Sonnet, Gemini 1.5 Pro, Perplexity (sonar)
- [x] For each model, query with search/browsing OFF where possible (parametric only)
- [x] Then query with search ON where available
- [x] Store: raw response, model name, search_enabled flag, timestamp, prompt_id
- [x] Rate limiting + retry logic + progress bar (rich)
- [x] Save all raw responses to `data/raw/` as JSON

### 1c: First Pull
- [ ] Run full prompt library × all models × search on/off
- [ ] Estimated API cost: ~$30-50
- [ ] Store everything in SQLite

## Phase 2: Response Parser (Week 2)
**Goal:** Extract structured restaurant data from raw LLM responses.

### 2a: Extraction Pipeline
- [ ] Build `src/response_parser.py`
- [ ] Use Claude API to parse each raw response into structured data
- [ ] Extract per response: list of restaurants mentioned, each with:
  - `name` (normalized — handle spelling variations)
  - `rank_position` (order mentioned in response, 1-indexed)
  - `neighbourhood` mentioned
  - `cuisine_tags` 
  - `vibe_tags` (romantic, casual, lively, quiet, etc.)
  - `price_indicator` if mentioned
  - `descriptors` (raw adjectives/phrases used)
  - `sentiment_score` (positive/neutral/negative)
  - `is_primary_recommendation` vs just mentioned
- [ ] Build restaurant name normalization (fuzzy matching to canonical names)
- [ ] Store parsed data in SQLite

### 2b: Entity Resolution
- [ ] Build a canonical restaurant registry from all parsed mentions
- [ ] Fuzzy match variants ("Burnt Ends" / "Burnt Ends Singapore" / "burnt ends")
- [ ] Manual review pass for ambiguous cases

## Phase 3: Ground Truth + Validation (Week 3)
**Goal:** Build comparison datasets independent of LLM training data.

### 3a: Google Maps Data
- [ ] Use Google Places API to get structured data for every restaurant in our parsed dataset
- [ ] Pull: rating, review_count, price_level, category, location, photos_count
- [ ] Also pull for top-100 Singapore restaurants by review count (the "popular consensus" set)

### 3b: Human Panel
- [ ] Build Google Form for friends panel (15-20 Singapore residents)
- [ ] Rate restaurants on: food quality, vibe, value, service (1-5)
- [ ] Tag each restaurant for: date night? business lunch? family? casual hangout? special occasion?
- [ ] Free text: "what restaurant do you recommend that nobody knows about?"
- [ ] Import results into SQLite

### 3c: Recency Test
- [ ] Identify 20+ restaurants that opened in 2025-2026 (after training cutoffs)
- [ ] Test which models find them (search on vs off)
- [ ] Measure "new restaurant discovery latency"

## Phase 4: Analysis + Visualization (Week 4)
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
