# Sabai Fine Thai — Detailed Probe Observations

A deep-dive companion to `sabai_probe_report.md` and OBSERVATIONS.md §18.

---

## 1. The 366-Review Blindspot

Sabai Fine Thai on the Bay has 366 Google reviews and a 4.1 rating. By any human measure, this is a real, established restaurant. For context:

- **Median Google reviews** across our 2,200 OPERATIONAL matched restaurants: ~500
- **Restaurants known to all 4 models**: avg ~3,000+ reviews
- **Sabai's review count**: higher than ~35% of our matched operational set

So Sabai isn't *unknown* — it's mid-pack. Yet it produced zero mentions across 1,690 queries. This isn't a one-off anomaly; it likely applies to hundreds of similar mid-tier restaurants. Our main dataset's 964 unmatched canonical restaurants (no Google Places match at all) suggests many AI-mentioned restaurants may actually have *fewer* reviews than Sabai.

**The paradox:** The AI recommendation ecosystem may systematically exclude restaurants that are perfectly good and reasonably well-known, while occasionally mentioning more obscure places that happened to be featured in a food blog that entered the training corpus.

**Open question:** Is there a review-count threshold below which restaurants effectively don't exist in LLM parametric memory? Our data suggests it's somewhere between 300-1,000 reviews, but this needs more probes to establish.

## 2. The Two-Attribute Rule

Sabai only surfaces reliably when the prompt combines **at least two** of its unique attributes:

| Single Attribute | Detection | Example |
|---|---|---|
| Thai | Low (25%) | "Best Thai restaurants Singapore" — too competitive |
| Marina Bay | Low-Med | "Where to eat near Fullerton" — too broad (not Thai-specific) |
| Bay view | Low alone | "Waterfront restaurants Marina Bay Asian food" — 0/8 (!!) |

| Two Attributes | Detection | Example |
|---|---|---|
| Thai + Marina Bay | High | "Good Thai near Marina Bay" — **#1 on 5/8 combos** |
| Thai + Bay view | High | "Thai with bay view" — **#1 on 5/8 combos** |
| Thai + Romantic + Waterfront | Medium | "Romantic Thai waterfront" — 4/8 |

| Three+ Attributes | Detection | Example |
|---|---|---|
| Thai + set lunch + Raffles Place | Low (1/8) | Only Gemini ON finds it |
| Thai + royal palace chef | Low (1/8) | Only Gemini ON, and it may be hallucinating |

**The sweet spot is two attributes — not three.** Adding a third attribute (set lunch, royal cuisine) over-constrains the query. The model may not have training data linking Sabai to these specific features, even if they're true.

## 3. Perplexity's Search-ON Paradox

Perplexity is the only model where search ON *hurts* Sabai detection:

| Mode | Pplx Sabai Detections (T1-T3) |
|---|---|
| Search OFF | 5/15 |
| Search ON | 0/15 |

For every other model, search ON helps. Perplexity is inherently search-augmented (both modes use search), but the ON mode adds `search_recency_filter="month"`. This recency filter may *exclude* Sabai's older reviews and articles, replacing them with more recently-discussed restaurants.

This is a counterintuitive AEO finding: recency filtering can make a stable restaurant *less* visible. If Sabai hasn't been in the news recently, the recency filter effectively deletes it from Perplexity's search-ON results.

## 4. Claude's Parametric Memory Gap

Claude's detection pattern is binary:

| Condition | Sabai Detections |
|---|---|
| Search OFF, T1-T3 | **1/15** (a single T2 hit) |
| Search ON, T1-T3 | **8/15** |
| Search OFF, T4 (name mentioned) | **3/5** |
| Search ON, T4 (name mentioned) | **4/5** |

Claude almost certainly does not have Sabai in its parametric memory. The single search-OFF detection (T2, "Good Thai near Marina Bay", rank #3) may be a stochastic anomaly. When web search is enabled, Claude can find Sabai through live retrieval — but this costs ~$0.46/query due to the web_search tool fetching full page content as input tokens.

**Implication:** For restaurants below the AI awareness threshold, Claude's parametric recommendations are essentially worthless. Only Claude + web search has a chance of surfacing them.

## 5. Gemini's Comprehensive Knowledge

Gemini detected Sabai in **24/40 queries** — 60%, far ahead of other models. More notably, Gemini search-ON found Sabai even in generic T1 queries:

- "Best Thai restaurants Singapore" → Sabai at **#3**
- "Upscale Thai dining" → Sabai at **#2**
- "Fine dining Thai" → Sabai at **#2**

No other model surfaces Sabai for these generic prompts. Gemini's google_search grounding tool appears to be more effective at pulling in mid-tier restaurants from live search results, possibly because it has privileged access to Google's own restaurant data (Places, Maps, reviews).

**This connects to Observation §9 (The Long Tail):** Gemini knows 1,591 canonical restaurants vs GPT-4o's 616. The Sabai probe confirms this isn't just volume — Gemini's broader knowledge base includes restaurants that other models completely miss.

## 6. The Sarai Inversion

The Sabai/Sarai asymmetry is the cleanest finding from this probe:

- **Generic Thai queries**: Sarai wins (14 detections vs Sabai's 10)
- **Location-specific queries**: Sabai wins (11 vs 0)
- **Attribute queries**: Sabai wins (14 vs 5)
- **Name queries**: Both present when explicitly compared

Sarai Fine Thai (Tanglin Mall) has a stronger "generic Thai" brand in LLM knowledge — likely due to more media coverage, a Tanglin Road location associated with established dining, and possibly more total reviews. But Sarai's location advantage disappears the moment you mention Marina Bay, CBD, or Customs House.

**No actual name confusion detected.** Despite the similar names, no model described Sabai using Sarai's address or vice versa. The 17 "confusion" hits in the report are all "mentions both" — and they concentrate on the explicit comparison prompt ("Sabai vs Sarai") and Gemini search-ON's thorough responses. The models can distinguish them; they just default to Sarai when the prompt is generic.

## 7. Limitations of This Probe

**Sample size:** 160 queries is informative but not statistically powerful. Each cell in the detection matrix has exactly 1 observation. The stability test (§10) showed that LLM responses are ~74% stochastic — meaning any single query is a noisy measurement. Ideally, each prompt × model × search cell would have 3-5 repetitions.

**Prompt bias:** The prompts were designed to progressively target Sabai's attributes. This creates an inherent bias — T1 prompts are genuinely generic, but T3 prompts were crafted knowing Sabai's features. A different restaurant with different attributes (e.g., a hawker stall in Chinatown) would need entirely different T3 prompts.

**Single restaurant:** Sabai is one data point. To establish the "366-review blindspot" as a general finding, we'd need to probe 20-30 restaurants at various review counts and measure the detection threshold. This is a case study, not a statistical conclusion.

**Name contamination:** The Tier 4 prompts contain "Sabai" in the text, which is essentially giving the model the answer. T4 detection rates (93%) tell us about model recall when given the name, not about organic discoverability. The real finding is in T1-T3.

---

*Generated 2026-03-10 from 160 probe queries. See `sabai_probe_report.md` for the raw detection matrices and frequency tables. Raw data in `data/raw/sabai_probe/`.*
