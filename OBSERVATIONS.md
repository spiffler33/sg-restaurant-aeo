# Observations: How LLMs Think About Restaurants

A running log of what the data reveals about LLM recommendation behavior. These are empirical observations from 1,120 queries across 4 models (GPT-4o, Claude Sonnet, Gemini 2.5 Flash, Perplexity Sonar) x 140 prompts x search ON/OFF.

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

Post-resolution: **148 restaurants (4.9%)** are mentioned by all 4 models, while **2,175 (71.6%)** are mentioned by only one. Gemini alone "knows" 1,620 canonical restaurants — more than the other three models combined (if deduplicated).

| Model | Unique Restaurants Known | % of All 3,038 |
|---|---|---|
| Gemini 2.5 Flash | 1,620 | 53.3% |
| Claude Sonnet | 1,126 | 37.1% |
| Perplexity Sonar | 1,052 | 34.6% |
| GPT-4o | 632 | 20.8% |

**The discovery gap is 2.6x** — Gemini surfaces 2.6x more unique restaurants than GPT-4o. For a lesser-known restaurant, being in Gemini's knowledge base is table stakes; being in GPT-4o's curated list is the prize.

The 148 "consensus restaurants" (known to all 4 models) likely represent the ~5% of Singapore's dining scene that has crossed the AI awareness threshold — sufficient English-language media coverage, review density, and brand recognition to appear in every model's training data.

---

*Last updated: 2026-03-04, after Phase 2b entity resolution. Next: Phase 3 ground truth validation, Phase 4 deep analysis.*
