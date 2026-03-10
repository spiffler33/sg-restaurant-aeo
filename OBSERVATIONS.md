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

---

*Last updated: 2026-03-10, after Sabai Fine Thai probe. 3,666 canonical restaurants (2,991 active research set). 1,266 Google Places verified, 30 closed. 160 targeted probe queries (separate from main dataset). 16 figures in flagship notebook.*
