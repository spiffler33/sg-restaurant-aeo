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

---

*Last updated: 2026-03-04, after Phase 2a parsing. Will update as entity resolution and deeper analysis proceed.*
