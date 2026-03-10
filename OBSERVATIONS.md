# Observations: How LLMs Think About Restaurants

A running log of what the data reveals about LLM recommendation behavior. These are empirical observations from 1,690 queries across 4 models (GPT-4o, Claude Sonnet, Gemini 2.5 Flash, Perplexity Sonar) x 140 prompts x search ON/OFF, plus 570 stability test queries.

---

## 1. The AI Canon Is Real

The top 20 restaurants are recommended by **all four models**. Odette (100 mentions), Burnt Ends (98), Candlenut (63) — these aren't just popular, they're *consensus*. No model disagrees on their inclusion.

This suggests a shared "canonical knowledge" baked into training data — likely driven by the same media sources (Michelin guides, Eater, food blogs) that all models ingested. The AI restaurant canon is essentially a reflection of the English-language food media canon.

## 2. Verbosity ≠ Quality, But It Shapes Discovery

Gemini produces **10.9 restaurants per response** — nearly double GPT-4o's 5.6. This isn't Gemini being "better" at recommendations; it's a stylistic choice toward exhaustive lists vs. curated picks.

The implication for AEO: a restaurant has roughly **2x the chance of appearing** in a Gemini response compared to GPT-4o, simply because Gemini casts a wider net. If you're a lesser-known restaurant, Gemini is your friend. If you're optimizing for "top pick" status, GPT-4o's selectivity means each mention carries more weight.

| Model | Avg Restaurants/Response | Style |
|---|---|---|
| Gemini 2.5 Flash | 10.9 | Exhaustive lists, structured headers |
| Claude Sonnet | 7.1 | Conversational, emoji-heavy |
| Perplexity Sonar | 6.0 | Concise with citation markers |
| GPT-4o | 5.6 | Curated, shorter prose |

## 3. Models Have Favorites the Others Ignore

Some restaurants appear 5+ times but from **only one model**:

- **The Black Swan** — GPT-4o mentions it 8 times, no other model does
- **Ce La Vie** — Claude's exclusive (7 mentions)
- **Euphoria** — only Perplexity (6 mentions)
- **Founder Bak Kut Teh** — Gemini-only (5 mentions)

These aren't obscure places — they're well-known Singapore restaurants. The exclusivity suggests that each model has "pockets" of knowledge from different training data distributions. Founder Bak Kut Teh being Gemini-only may reflect Google's access to its own Maps/reviews data during training.

## 4. Same Restaurant, Different Story

All four models recommend Labyrinth for the same prompt (cuisine_001), but describe it differently:

- **GPT-4o**: "modern take on Singaporean classics" — factual, brief
- **Claude**: "chef LG Han's playground", "creative but respectful to the originals" — personality-driven, opinionated
- **Gemini**: "Michelin 1-Star", "deconstructs classic Singaporean dishes", "degustation experience" — credential-heavy, structured

The models agree on *what* to recommend but diverge on *how* they frame it. Claude anthropomorphizes ("playground"), Gemini credentializes (Michelin stars first), GPT-4o summarizes.

## 5. Rank Disagreement Reveals Model Personality

The most "controversial" restaurants — biggest rank spread across models:

| Restaurant | GPT-4o Rank | Claude Rank | Gemini Rank | Perplexity Rank |
|---|---|---|---|---|
| The Coconut Club | 3.6 | 11.0 | 10.7 | 3.0 |
| Nouri | 5.2 | 3.8 | 12.5 | 5.2 |
| Maxwell Food Centre | 3.7 | 5.3 | 10.9 | 3.7 |
| Din Tai Fung | 2.6 | 2.2 | 9.4 | 5.4 |

**Gemini consistently ranks popular/casual spots lower** — Maxwell Food Centre at 10.9 vs GPT-4o's 3.7, Din Tai Fung at 9.4 vs 2.6. Gemini appears to have a fine-dining / upscale bias, pushing casual and chain restaurants down its lists.

GPT-4o and Perplexity often agree on ranks (both put Maxwell at 3.7, Coconut Club around 3-3.6). They may share more overlapping training sources.

## 6. Web Search Changes What Gets Recommended

Search ON yields **7.7 avg restaurants per response** vs 7.0 with search OFF — slightly more, not fewer. But the composition shifts dramatically.

**Search-only restaurants** (appear 5+ times with search ON, zero with OFF):
- VUE Bar & Grill (8 mentions)
- Liao Fan Hawker Chan (7)
- Rumah Makan Minang (7)
- Wakuda (5)
- HighHouse (5)

These are likely newer openings or places with recent press coverage that aren't in the models' parametric memory. This is the clearest signal of **training data staleness** — and the strongest argument for search-augmented recommendations.

## 7. Prestige Bias Is Universal (But Varies in Degree)

Odette (3 Michelin stars) is mentioned 100 times with an average rank of 3.0 — it's almost always near the top. All four models lead with Michelin credentials when describing it.

But GPT-4o ranks it highest (avg 2.6, 29 mentions) while Gemini places it lower (avg 4.2, 22 mentions). GPT-4o appears to have the strongest "prestige pull" — Michelin stars, awards, and media accolades seem to weigh more heavily in its ranking.

## 8. Entity Resolution: The Name Fragmentation Problem

Phase 2b collapsed **3,332 raw name strings → 3,038 canonical restaurants** (294 merges, 8.8% reduction). The automated pipeline used three stages: exact normalized match (140 merges), base name grouping (60), and fuzzy matching with a shared-word penalty (94).

**The naming chaos is real.** LLMs refer to the same restaurant in wildly different ways:

| Restaurant | Variant Count | Example Variants |
|---|---|---|
| CÉ LA VI | 7 | CÉ LA VI, Ce La Vi, Ce La Vie, Cé La Vi, CE LA VI, Ce La Vié, CÉ LA VIE |
| Mr & Mrs Mohgan's | 7 | Mr & Mrs Mohgan's Super Crispy Prata, Mr and Mrs Moghan's Super Crispy Prata, ... |
| PS.Cafe | 6 | PS.Cafe, P.S. Cafe, PS. Cafe, P.S. Café, PS Cafe, PS. Café |
| Liao Fan / Hawker Chan | 5 | Liao Fan Hong Kong Soya Sauce Chicken Rice & Noodle, Hawker Chan (Liao Fan...) |

**Variant patterns by type:**
- **Unicode/punctuation** (43% of merges): CÉ vs Ce, PS.Cafe vs PS Cafe, & vs and
- **Structural reordering** (22%): "Restaurant Labyrinth" vs "Labyrinth Restaurant"
- **Location qualifiers** (18%): "Jumbo Seafood at Dempsey Hill" vs "Jumbo Seafood"
- **Spelling variations** (17%): "Komala Vilas" vs "Komala Villas", "Moghan's" vs "Mohgan's"

**AEO implication:** If you're a restaurant optimizing for LLM recommendations, your *exact name* as recognized by each model matters. CÉ LA VI has 43 total mentions but they're scattered across 7 spelling variants — a brand consistency problem that didn't exist in the Google Search era.

## 9. The Long Tail Is Enormous

Post all entity resolution stages (automated + human triage + place_id dedup): **152 restaurants (5.1%)** are mentioned by all 4 models, while **2,155 (72.0%)** are mentioned by only one. Gemini alone "knows" 1,591 canonical restaurants — more than the other three models combined (if deduplicated).

| Model | Unique Restaurants Known | % of All 2,991 |
|---|---|---|
| Gemini 2.5 Flash | 1,591 | 53.2% |
| Claude Sonnet | 1,102 | 36.8% |
| Perplexity Sonar | 1,037 | 34.7% |
| GPT-4o | 616 | 20.6% |

**The discovery gap is 2.6x** — Gemini surfaces 2.6x more unique restaurants than GPT-4o. For a lesser-known restaurant, being in Gemini's knowledge base is table stakes; being in GPT-4o's curated list is the prize.

The 152 "consensus restaurants" (known to all 4 models) likely represent the ~5% of Singapore's dining scene that has crossed the AI awareness threshold — sufficient English-language media coverage, review density, and brand recognition to appear in every model's training data.

## 10. Recommendation Stability: Most Suggestions Are Coin Flips

Phase 2c re-ran 15 prompts 5 times each (3 for Claude search ON) across all models — 570 queries total — to measure how reproducible LLM recommendations are at temperature=0.7.

**The headline: only ~26% of recommended restaurants overlap between any two runs of the same prompt.** Mean pairwise Jaccard similarity across all 118 (prompt × model × search) cells is just 0.256. This means if you ask GPT-4o "best mod-Sin restaurants?" twice, roughly 3 out of 4 restaurants in each response will be different.

**79.5% of restaurant appearances are stochastic** — appearing in 2 or fewer out of 5 runs. Only **12.7% are core** (appearing in 4+ runs). The remaining 7.8% are "mid" (appearing in 3 runs).

### Set Stability vs Rank Stability

The rank story is more encouraging. Mean Kendall's tau is 0.571 — when the same restaurants *do* appear across runs, their relative ordering is moderately consistent. The model "knows" Labyrinth should rank above Cheek Bistro; it just can't reliably decide whether to include Cheek Bistro at all.

### Per-Model Stability

| Model | Mean Jaccard | Mean Kendall's τ | Interpretation |
|---|---|---|---|
| GPT-4o | **0.317** | 0.574 | Most stable sets — fewest restaurants per response means a tighter "core" |
| Claude Sonnet | 0.253 | 0.601 | Moderate — good rank stability |
| Perplexity Sonar | 0.228 | **0.610** | Unstable sets but best rank consistency |
| Gemini 2.5 Flash | 0.224 | 0.499 | Least stable on both measures |

GPT-4o's higher Jaccard likely traces to its shorter lists (5.6 avg/response). With fewer recommendations, each pick is more "committed." Gemini's 10.9 recommendations per response means more room for stochastic variation — each run pulls different items from a large pool.

### The Specificity Paradox

| Specificity | Jaccard (sets) | Kendall's τ (rank) |
|---|---|---|
| Broad | 0.257 | 0.519 |
| Medium | **0.282** | 0.567 |
| Narrow | 0.227 | **0.640** |

Narrow prompts ("best xiao long bao in Singapore") have the **worst set overlap** but the **best rank correlation**. There are fewer "obvious" candidates for very specific queries, so each run draws different restaurants — but when two runs agree on a restaurant, they agree on where to rank it.

Medium-specificity prompts hit the sweet spot for set stability — specific enough to constrain the candidate pool, but broad enough that multiple "obvious" picks exist.

### Search Adds Noise

| Mode | Jaccard | Kendall's τ |
|---|---|---|
| Search OFF | 0.264 | 0.574 |
| Search ON | 0.247 | 0.566 |

Web search makes recommendations slightly *less* stable. Each search run may retrieve different pages, introducing additional variance. This is expected — search-augmented responses blend parametric memory with live retrieval, and the retrieval component is inherently non-deterministic.

### AEO Implications

1. **Confidence intervals matter.** Saying "Odette was mentioned 100 times" is more meaningful now — we know the top restaurants are genuinely in the models' core knowledge, not flukes. But a restaurant mentioned 3 times across the original sweep might just be a stochastic artifact.

2. **Repeat querying is essential methodology.** Any AEO study that queries each model only once per prompt is measuring signal + substantial noise. Our stability data suggests you need 3-5 runs per prompt to separate core recommendations from stochastic ones.

3. **Model choice affects reliability.** If you want consistent recommendations, GPT-4o gives the most reproducible results. If you want broad discovery (at the cost of stability), Gemini surfaces the most diverse set.

### Example: cuisine_001 × Claude × Search OFF

Five runs of "What are the best mod-Sin or fusion restaurants in Singapore?"

- **Core (4+/5 runs):** Labyrinth, Burnt Ends, Cloudstreet, Cheek Bistro
- **Mid (3/5):** Meta, Thevar, Preludio, Birds of a Feather
- **Stochastic (1-2/5):** Kotuwa, Nae:um, Skai, Artemis Grill, Super Loco, Wild Rocket, JL Studio, Whitegrass, Pangium, Violet Oon, Shinji by Kanesaka, Restaurant Zen, Candlenut, Native, Restaurant Ibid

The 4 core restaurants are genuine Claude-knowledge anchors for this prompt. The 15 stochastic restaurants are drawn from a much larger implicit distribution — they're "known" but not reliably surfaced.

## 11. Ground Truth: LLMs Recommend Dead Restaurants

Phase 3a matched canonical restaurants against Google Places and flagged business status. After human triage and corrections (including the Komala's multi-branch fix in §15), the verified set contains **30 closed restaurants** — 23 permanently closed, 7 temporarily.

These aren't obscure picks. **13 of the 30 closed restaurants are mentioned by all 4 models**, and closed restaurants account for **506 total mentions** across the dataset. Among the top 100 most-mentioned verified restaurants, **13% are zombies**. Some highlights:

| Restaurant | Mentions | Models | Status | Notes |
|---|---|---|---|---|
| Open Farm Community | 44 | 4/4 | CLOSED_PERMANENTLY | Was a top-50 restaurant by mentions |
| Corner House | 33 | 4/4 | CLOSED_PERMANENTLY | Michelin-starred, closed 2024 |
| Lolla | 23 | 4/4 | CLOSED_PERMANENTLY | |
| Esora | 16 | 4/4 | CLOSED_PERMANENTLY | |
| Hashida Sushi | 16 | 4/4 | CLOSED_PERMANENTLY | |
| Sushi Kimura | 13 | 4/4 | CLOSED_PERMANENTLY | |
| Tippling Club | 11 | 3/4 | CLOSED_PERMANENTLY | |

**This is the strongest evidence yet that LLM training data is stale for local business recommendations.** These restaurants existed in the Michelin guide, food blogs, and review sites that formed the training corpus, but closed between training cutoff and query time. Web search partially mitigates this (search ON is less likely to surface closed places), but even search-augmented responses still recommend some.

**AEO implication:** A restaurant that closes doesn't disappear from AI recommendations — it persists as a ghost in the training data, potentially for years. This creates a "zombie restaurant" problem: users get confidently recommended to places that no longer exist.

## 12. The Review Anomaly: Franchises vs Flagships

Google Places matching revealed a subtle bug: automated matching picked **franchise branches** over **flagship locations** when the branch name was a closer string match.

**The Swee Choon case:** "Swee Choon Tim Sum Restaurant" matched to "Swee Choon Tim Sum Restaurant (Express) - AMK Hub" (369 reviews, perfect name match score) instead of "Swee Choon Jalan Besar" (11,448 reviews, 67% name match). The algorithm optimized for name similarity, but any Singaporean knows Swee Choon *is* the Jalan Besar original.

Similarly, "Plain Vanilla Bakery" matched to "Plain Vanilla" at Bukit Timah (201 reviews) instead of "Plain Vanilla Tiong Bahru" (1,145 reviews) — the iconic original location.

**Lesson for entity matching:** Review count is a critical signal for identifying the "canonical" branch of a multi-location restaurant. A simple heuristic — prefer 5x+ reviews at ≥55% name match over 100% name match with fewer reviews — would have caught all three anomaly cases.

**Fix applied:** `_review_count_override()` in `src/google_places.py` now implements this heuristic (≥5x reviews + ≥55% name similarity → prefer the high-review candidate). Code fix only — not re-run on existing data, but available for future matching passes.

## 13. Human Review Catches What Algorithms Miss

The triage process discovered **10 additional entity resolution merges** that Phase 2b's fuzzy matching couldn't detect. These were "obvious to a human, hard for a computer" cases:

| Old Name → New Name | Why Fuzzy Matching Failed |
|---|---|
| Meta → Meta Restaurant | Short name, "Restaurant" adds >50% to token length |
| Born → Restaurant Born | Same issue |
| Bar Cicheti → Cicheti | "Bar" prefix changes fuzzy ratio |
| Wild Rocket → Relish by Wild Rocket | Restaurant rebranded |
| Komala Vilas → Komala's | Completely different string after shortening |

Combined with the 2 explicit duplicate merges (Bincho/Bincho at Hua Bee, Euphoria/Restaurant Euphoria), the triage collapsed 12 duplicate canonical entries. Total entity resolution merges at this stage: **306** (294 automated + 12 human triage). This was later increased to **339** after the place_id dedup pass (see §14).

**The pattern:** Automated fuzzy matching handles ~96% of merges. The remaining ~4% require domain knowledge — knowing that a restaurant rebranded, that locals use a shortened name, or that "Bar X" and "X" are the same place.

## 14. Place ID as Entity Resolution Signal: 33 Hidden Duplicates

The place_id dedup pass scanned raw Google Places JSON responses and found **33 pairs of canonical restaurants** that resolved to the same Google place_id — confirmed duplicates invisible to fuzzy name matching.

Some of these were obvious-in-hindsight name variants that no string similarity algorithm could catch:

| Canonical A | Canonical B | Why Fuzzy Matching Missed It |
|---|---|---|
| Violet Oon Singapore | National Kitchen by Violet Oon | Completely different lead word |
| Zen | Restaurant Zén | "Zen" vs "Restaurant Zén" — too short, too different |
| Tian Tian | Tian Tian Hainanese Chicken Rice | Partial vs full name |
| PS.Cafe | PS.Cafe at Harding Road | Location qualifier |
| LAVO | Lavo Italian Restaurant | Brand name vs full name |

**Total entity resolution merges across all stages: 339** (294 Phase 2b automated + 12 Phase 3a human triage + 33 place_id dedup).

**Methodological takeaway:** External identifiers (Google place_id, Michelin URLs, reservation system IDs) are far more reliable than name similarity for entity resolution. If we had place_ids from the start, we could skip fuzzy matching entirely for matched restaurants. This is a strong argument for early ground-truth linking in any entity resolution pipeline.

## 15. Multi-Branch Chains: A Matching Pitfall

Komala's — a well-known South Indian vegetarian chain with multiple Singapore branches — was incorrectly flagged as "temporarily closed" in the zombie restaurant analysis. The automated matching picked **Komala Vilas Restaurant at Serangoon Rd** (6,971 reviews, 68.6% match score, CLOSED_TEMPORARILY) over **Komala's Restaurants at Race Course Rd** (562 reviews, 53.8% match score, OPERATIONAL).

The chain is very much alive. One specific branch (the original Komala Vilas location) happened to be temporarily closed, but this doesn't make "Komala's" a zombie restaurant. This is the multi-branch version of the franchise-vs-flagship problem from §12: when a chain has locations in different states (open vs closed), the highest-scoring match may not be the most representative one.

**Fix applied:** Un-verified the closed Komala Vilas branch entry (`human_verified = 0`), keeping only the OPERATIONAL Komala's Restaurants entry as the verified match.

**General lesson:** For chain restaurants, match-score ranking should prefer OPERATIONAL entries over closed ones, regardless of name similarity score. A closed branch of an open chain is not a zombie restaurant.

## 16. Fame Beats Quality: Review Volume Predicts AI Mentions, Rating Doesn't

Among 1,235 operational, verified restaurants, Google **rating** has essentially zero correlation with AI mention frequency (Spearman r = -0.070, p = 0.015). The sign is actually slightly *negative* — higher-rated restaurants are, if anything, marginally *less* likely to be heavily mentioned.

Google **review count** (log-transformed), however, has a significant positive correlation (Spearman r = 0.279, p < 10^-23). Review volume is a proxy for online presence, media coverage, and brand awareness — the signals that actually get into LLM training data.

**The practical takeaway:** A 4.1-star restaurant with 10,000 reviews will outperform a 4.8-star restaurant with 200 reviews in the AI recommendation game. LLMs don't read ratings — they absorb the *volume* of discussion about a place. This aligns with the AEO insight that visibility (being talked about) matters more than quality (being rated highly).

## 17. Search ON vs OFF: Only 24% Overlap

The restaurant sets recommended with search enabled vs disabled diverge dramatically. Of the 2,991 restaurants in the active research set:

| Category | Count | % |
|---|---|---|
| Both modes | 720 | 24.1% |
| Search ON only | 1,351 | 45.2% |
| Search OFF only | 920 | 30.8% |

Search ON surfaces **1,351 restaurants** (45% of the total) that never appear without search — likely newer openings, recently reviewed places, or establishments with strong current web presence but insufficient historical coverage to be in parametric memory.

Conversely, **920 restaurants** appear only with search OFF. These may be "training data artifacts" — places with historical coverage that don't rank well in current search results (possibly because they've become less prominent, or because search results favor recency).

The 720 "both modes" restaurants are the most robust recommendations: present in both the model's frozen knowledge and current web results. This ~24% overlap figure is a headline finding — it means that toggling one parameter (web search) changes three-quarters of the recommendation set.

## 18. The Invisible Restaurant: 366 Reviews, Zero AI Mentions

A targeted probe of **Sabai Fine Thai on the Bay** — a real restaurant at 70 Collyer Quay, Customs House, Marina Bay — revealed a structural blindspot in LLM restaurant knowledge.

**The facts:** Sabai has 366 Google reviews, a 4.1 rating, and sits in a prime Marina Bay waterfront location. It is not obscure. Yet across 1,690 queries in our main dataset (140 prompts × 4 models × 2 search modes + 570 stability queries), it appeared **zero times**.

We ran a targeted probe: 20 prompts in 4 tiers of increasing specificity × 4 models × 2 search modes = 160 queries. Full results in `data/processed/sabai_probe_report.md`.

### The Specificity Threshold

| Tier | Description | Sabai Detection Rate |
|---|---|---|
| T1: Generic | "Best Thai restaurants in Singapore" | 10/40 (25%) |
| T2: Location | "Thai near Marina Bay / Customs House" | 11/40 (28%) |
| T3: Attribute | "Thai with bay view / waterfront / royal cuisine" | 14/40 (35%) |
| T4: Near-name | "Tell me about Sabai Fine Thai" | 37/40 (93%) |

Sabai only reliably surfaces when you mention it by name. For generic or moderately specific Thai queries, it loses to the established canon — Patara, Thanying, Long Chim, Blue Jasmine. The specificity threshold is steep: you need to combine *at least two* of its unique attributes (Thai + Marina Bay, or Thai + bay view) to break through.

### The Breakout Prompts

Two prompts cracked the code:
- **"Thai restaurant with a bay view in Singapore"** → Sabai at **#1** on 5 of 8 model×search combos
- **"Good Thai restaurant near Marina Bay"** → Sabai at **#1** on 5 of 8 combos

When the prompt precisely matches Sabai's unique niche (Thai + waterfront + Marina Bay), it dominates. But "upscale Thai Singapore" or "waterfront Asian food Marina Bay" — slightly broader queries — produce zero Sabai mentions.

### The Competitor Asymmetry: Sarai vs Sabai

The probe also tracked **Sarai Fine Thai** (Tanglin Mall), a similar-named competitor. The detection pattern is the inverse:

| Tier | Sabai | Sarai |
|---|---|---|
| T1: Generic Thai | 10/40 | **14/40** |
| T2: Marina Bay / CBD | **11/40** | 0/40 |
| T3: Bay view / waterfront | **14/40** | 5/40 |
| T4: Near-name | **37/40** | 8/40 |

Sarai dominates generic Thai queries. Sabai dominates location-specific ones. When you say "Thai restaurant" without geographic context, LLMs default to the more generically well-known option. Geography is Sabai's competitive moat in the AI recommendation space.

### Model Behavior

| Model | Sabai Detections (/40) | Notes |
|---|---|---|
| Gemini | **24** | Best friend — surfaces Sabai even in generic T1 queries (search ON) |
| GPT-4o | 18 | Good for attribute-specific prompts |
| Claude | 16 | Almost never surfaces Sabai without search ON or name mention |
| Perplexity | 14 | Worst — search ON actually *hurts* (0 search-ON detections in T1-T3) |

Gemini's verbosity (10.9 restaurants/response) works in Sabai's favor — its longer lists have room for less-famous restaurants. Claude's parametric memory appears to lack Sabai entirely; it only surfaces with web search (T1-T3) or direct name mention (T4).

### Methodological Implications

**This reveals a gap in our main study.** Our 140 prompts are designed to probe broad dimensions (cuisine, vibe, neighbourhood, etc.) — none are specific enough to surface restaurants like Sabai. The main dataset captures the "AI canon" and medium-tier recommendations, but misses the long tail of real, operational, well-reviewed restaurants that simply don't have enough media presence to enter the models' parametric memory.

**366 Google reviews is not enough.** Compare to the consensus restaurants (known to all 4 models): they average thousands of reviews and extensive media coverage. Sabai's 366 reviews place it well below the "AI awareness threshold" for generic discovery — roughly in the same band as our 964 unmatched canonical restaurants.

**Search ON doesn't fully solve this.** Even with web search enabled, Sabai appeared in only 40/80 search-ON queries (50%), and only when the prompt was specific enough. Web search helps but doesn't eliminate the discoverability gap.

**Practical AEO takeaway for restaurants like Sabai:** Optimize for the *specific queries your customers actually ask*. "Thai restaurant Marina Bay" and "Thai with bay view Singapore" are the prompts where Sabai ranks #1 — that's the keyword space to own. Generic "best Thai food Singapore" is a fight against Patara, Thanying, and Long Chim that a 366-review restaurant cannot win.

## 19. What Search-Augmented Models Actually See

The Sabai probe (§18) showed that search ON detection is inconsistent — sometimes helping (Gemini), sometimes hurting (Perplexity), sometimes neutral (GPT-4o). A web presence audit of Sabai's digital footprint reveals *why*: the inconsistency traces directly to what each model retrieves and how it processes it.

### The Empty Homepage Problem

When a search-augmented model fetches `sabaifinethai.com.sg`, it gets almost nothing:

| Page | What the model sees |
|---|---|
| Homepage (`/`) | Hero images, no text. Effectively empty. |
| About (`/about-us/`) | Founding story with "Thai fine dining" and "Singapore" — but not "Marina Bay" |
| Menu (`/menu/`) | PDF links only. Zero crawlable dish names. |
| Contact (`/299-2/`) | Address includes "Customs House, Collyer Quay" — but only here |

"Marina Bay" — the keyword that drives Sabai's strongest detection (T2 queries) — appears **nowhere on the website**. "Bay view" and "waterfront" — the attributes behind Sabai's #1 breakout prompt — are also absent. The only reference to location is "on the Bay" in a 2015 copyright footer.

This is the mechanism behind search ON inconsistency: **when a model happens to fetch the official website, it learns almost nothing useful.** Models that instead fetch TripAdvisor or Google Business Profile (which do have the address and "Marina Bay" association) perform better.

### Gemini's Structural Advantage

Gemini's probe dominance (24/40 detections, best of all models) has a specific technical explanation: Gemini uses **Google Search grounding**, which pulls structured data from Google Business Profile — rating, review count, address, business category — not just web page text. Google knows Sabai is at "Customs House, Marina Bay" even though the website doesn't say so.

The other three models rely on fetching and parsing web pages. When those pages are thin (Sabai's homepage) or entirely image-based (the menu), those models get less signal.

**Generalizable principle:** Models with access to structured knowledge graphs (Google's) outperform models that rely purely on web page text retrieval, especially for entities with poor first-party web presence.

### Why Perplexity Search ON Hurts

Perplexity with `search_recency_filter="month"` narrows results to recent content. Sabai has almost no recent blog posts, articles, or press coverage (2025-2026). The recency filter actively excludes the few mentions that exist, making search ON *worse* than search OFF for Sabai.

The restaurants that benefit from Perplexity's recency filter are ones with active press cycles — new openings, Michelin announcements, viral food blogger posts. Established but under-covered restaurants like Sabai are penalized by recency bias.

### The Aggregator Chain

For generic queries ("best Thai restaurant Singapore"), models don't fetch restaurant websites at all. The retrieval chain is:

```
Query → Search engine → Listicle/TripAdvisor/Yelp → Model reads that page → Recommendation
```

Sabai's website quality is irrelevant for T1 queries because models never visit it. What matters is whether Sabai appears in the aggregator pages that models *do* fetch. Currently, Sabai appears in **1 of 10** major "best Thai Singapore" listicles checked. Sarai appears in multiple. Un-Yang-Kor-Dai (Michelin Bib Gourmand) appears in nearly all.

**This means website SEO fixes help T2/T3 queries (where models might fetch the restaurant's own site) but not T1 queries (where models read aggregators).** The T1 bottleneck is aggregator presence, not website quality.

### Schema.org: An Industry-Wide Gap

None of the five Thai fine-dining competitors audited (Sarai, Patara, Long Chim, Thanying, Blue Jasmine) have `schema.org/Restaurant` JSON-LD markup. Sabai doesn't either.

| Restaurant | Platform | Restaurant Schema? | Meta Title Quality |
|---|---|---|---|
| Sabai | WordPress | No | Fair — omits "Singapore" |
| Sarai | Squarespace | No (auto LocalBusiness only) | Poor — just "SARAI" |
| Thanying | Custom/hotel CMS | Unknown (likely no) | Good — "Authentic Royal Thai Cuisine" |
| Patara | Squarespace | No | Poor — menu page shows "Squarespace" |
| Long Chim | Stub (closed) | No | Minimal |
| Blue Jasmine | Hotel CMS (closed) | No | Poor — hotel parent title |

**This is a first-mover opportunity.** The first Thai restaurant in Singapore to implement proper Restaurant schema would have uncontested structured signal in an otherwise signal-sparse segment. Schema is particularly relevant for Gemini (Google grounding reads structured data) and for future model architectures that may prioritize structured web data over unstructured text.

### The Review Count Gap

| Restaurant | Google Reviews | Rating | Status |
|---|---|---|---|
| Sawadee (Chinatown) | 2,753 | 4.7 | OPEN |
| Sarai Fine Thai | 1,126 | 4.6 | OPEN |
| Blue Jasmine | 471 | 4.1 | CLOSED |
| **Sabai Fine Thai** | **347** | **4.3** | **OPEN** |
| Thanying | 203 | 4.0 | OPEN |
| Long Chim | 197 | 3.9 | CLOSED |

Sabai's 347 reviews place it 4th of 4 among open competitors. Cross-referencing with §16 (review count predicts AI mentions, rating doesn't): review volume is the strongest predictor of AI discoverability, and Sabai is structurally disadvantaged. Sarai has 3.2x more reviews; Sawadee has 8x more.

Two of the top five Thai competitors in our probe data (Long Chim, Blue Jasmine) are **permanently closed**. They continue to occupy AI recommendation slots that Sabai could fill — the zombie restaurant problem from §11, playing out in a specific competitive niche.

## 20. The Intervention Hierarchy: What Actually Moves the Needle for AEO

Using Sabai's probe data, we can estimate the relative impact of different interventions on AI discoverability. This generalizes beyond Sabai to any restaurant below the "AI awareness threshold."

### Current Detection Breakdown

| Tier | Search OFF | Search ON | Total | Rate |
|---|---|---|---|---|
| T1: Generic | 5/20 | 5/20 | 10/40 | 25% |
| T2: Location | 4/20 | 7/20 | 11/40 | 28% |
| T3: Attribute | 6/20 | 8/20 | 14/40 | 35% |
| T4: Near-name | 15/20 | 22/20 | 37/40 | 93% |
| **Total** | **30/80** | **42/80** | **72/160** | **45%** |

88 misses. Where does each intervention type help?

### Intervention 1: Website Technical Fixes (Schema + Meta + Homepage Text)

**Mechanism:** Makes the official website readable when LLM search tools fetch it.
**What it affects:** Search ON queries where the model fetches sabaifinethai.com.sg — primarily T2/T3.

- **Search OFF (80 queries, 30 detected):** ~0 impact. Parametric knowledge is frozen.
- **T1 search ON (20 queries, 5 detected):** ~1-2 gain. Models don't visit the website for generic queries. Only schema helps Gemini grounding.
- **T2 search ON (20 queries, 7 detected):** ~3-4 gain. Adding "Marina Bay" to homepage text directly addresses the location gap.
- **T3 search ON (20 queries, 8 detected):** ~2-3 gain. "Waterfront," "bay view," HTML menu help attribute queries.
- **T4 (40 queries, 37 detected):** ~0 gain. Already 93%.

**Estimated lift: ~8-10 additional detections → 45% → ~50%** (concentrated in T2/T3 search ON)

### Intervention 2: Review Volume (347 → 1,000+)

**Mechanism:** Higher review count → higher ranking on TripAdvisor/Google/Yelp → appears in more search results that models fetch.

- **Search OFF:** Zero immediate impact. Reviews enter training data on next training cycle (6-12 months).
- **T1 search ON:** ~4-6 gain. This is where reviews help most — "best Thai" search results are ordered by review volume and rating on aggregator sites.
- **T2/T3 search ON:** ~2-3 gain. Better aggregator ranking.
- **T4:** No gain needed.

**Estimated lift: ~8-12 additional detections → 45% → ~51%**

Comparable to technical fixes in total, but distributed differently. **Reviews unlock T1 (the hardest tier); technical fixes unlock T2/T3 (the middle tiers).**

### Intervention 3: Blog Coverage (3+ Food Bloggers)

**Mechanism:** Blog posts serve dual purpose — they appear in search results (helping search ON) AND enter training data on the next training cycle (helping search OFF).

- **Search ON (all tiers):** Each blog post is a new, keyword-rich page that search tools can retrieve. A post titled "Sabai Fine Thai — Waterfront Royal Thai Dining at Marina Bay" would directly match T1, T2, and T3 query patterns.
- **Search OFF (future):** Blog posts from DanielFoodDiary, ieatishootipost, MissTamChiak etc. are almost certainly in LLM training corpora. New posts create new parametric knowledge for future model versions.

**Estimated lift: ~10-15 additional detections (near-term search ON) + future parametric impact**

**This is the highest-ROI intervention for AEO.** It's the only one that affects both channels simultaneously.

### Intervention 4: Listicle Placement (Appear in "Best Thai" Roundups)

**Mechanism:** Listicles are literally what models read when processing "best Thai restaurant Singapore." Being in 3+ listicles vs. 1 is the difference between reliable T1 detection and occasional T1 detection.

- **T1 search ON:** This is the targeted intervention. Currently 5/20 detected, and the hits correlate with which listicle the model happens to fetch.
- **T1 search OFF (future):** Listicles also enter training data.

**Estimated T1 lift alone: 25% → ~40-45%** — the most impactful single intervention for generic discoverability.

### The Hierarchy

Ranked by ROI (impact per unit effort) for a restaurant below the AI awareness threshold:

| Rank | Intervention | T1 Impact | Overall Impact | Effort | Time to Effect |
|---|---|---|---|---|---|
| 1 | **Blog coverage** (3+ bloggers) | Medium | **Highest** (dual-channel) | Medium (pitch + host) | 2-4 weeks (search ON), 6-12 months (parametric) |
| 2 | **Listicle placement** | **Highest** for T1 | Medium (T1-only) | Medium (pitch editors) | 1-4 weeks |
| 3 | **Review volume** (3x current) | High | High | Slow (organic) | 3-6 months |
| 4 | **Website technical fixes** | Low | Medium (T2/T3 only) | **Lowest** (1 day) | Days (search ON) |

**The counterintuitive finding:** The easiest intervention (website fixes) has the lowest impact on the queries that matter most (T1 generic). The hardest intervention (building review volume) has the highest impact on T1 but takes months. Blog coverage is the sweet spot — moderate effort, dual-channel impact, fastest time to meaningful results.

### Why This Generalizes

Sabai is a useful case study because it sits right at the boundary: 347 Google reviews, established (since 2004), real location, real quality — but just below the "AI awareness threshold" of ~500-1,000 reviews and 3+ blog mentions that separates the 152 consensus restaurants from the 2,155 single-model long tail.

The intervention hierarchy likely applies to any restaurant in this zone:
- **Above threshold** (~500+ reviews, 5+ blog posts, Michelin/award recognition): already in the AI canon. Website fixes are marginal.
- **At threshold** (~200-500 reviews, 1-3 blog posts): this is where interventions have highest leverage. One ieatishootipost article or 300 more reviews could tip the balance.
- **Below threshold** (<200 reviews, no blog coverage): too far from the canon. No amount of schema markup will help. Need fundamental brand-building first.

**Practical AEO framework for restaurants:**
1. First: check if you're even in the zone (200+ Google reviews, some blog coverage)
2. If yes: blog pitches and listicle placement are highest ROI
3. Meanwhile: do the free technical fixes (schema, meta, homepage text) as table stakes
4. Long game: build review volume organically

The website is the last thing to fix, not the first — because models mostly don't read restaurant websites. They read TripAdvisor, food blogs, and Google structured data.

---

*Last updated: 2026-03-10, after Sabai web presence audit. 3,666 canonical restaurants (2,991 active research set). 1,266 Google Places verified, 30 closed. 160 targeted probe queries (separate from main dataset). Full web audit in `data/sabai_intervention/web_audit.md`. 16 figures in flagship notebook.*
