# What Does AI Think About Singapore Restaurants?

*We asked four AI models 1,120 questions about where to eat in Singapore. Here's what they got right — and what they got spectacularly wrong.*

---

## The Experiment

Here's a question nobody seems to be asking: when someone asks ChatGPT, Claude, Gemini, or Perplexity "where should I eat in Singapore?", what do they actually say? And more importantly — are they right?

We decided to find out. We built a pipeline that fires 140 carefully designed restaurant discovery prompts at four leading AI models — OpenAI's GPT-4o, Anthropic's Claude Sonnet, Google's Gemini 2.5 Flash, and Perplexity Sonar — both with and without web search enabled. That's 1,120 queries in the main sweep, plus another 570 stability tests where we asked the same questions repeatedly to see how consistent the answers were.

Then we parsed every response into structured data, deduplicated the restaurant names (more on that mess later), and checked each one against Google Places to see if it's still open.

The result: **3,666 unique restaurants mentioned**, **12,256 individual recommendations**, and a dataset that tells a surprisingly uncomfortable story about how AI thinks about food.

![INSERT CHART: 01_model_coverage.png]
*Only 5% of restaurants are recognized by all four AI models. Nearly three-quarters are known by just one.*

---

## There's a Top 5% Everyone Agrees On

The first thing that jumps out: there's a clear AI restaurant canon. **152 restaurants** — just 5.1% of the total — are mentioned by all four models. These are the Odettes, the Burnt Ends, the Candlenuts. They sit at the intersection of Michelin guides, food blogs, travel publications, and review sites. If it's in the AI canon, it's because the English-language food media already agreed on it, and every model absorbed that consensus during training.

But that's 152 out of 2,991. The other 95% is a chaotic long tail. **2,155 restaurants (72%) are mentioned by only one model.** Ask GPT-4o and Claude the same question, and most of their answers don't overlap.

The top 5 by total mentions: Odette (100), Burnt Ends (98), PS.Cafe (95), Violet Oon (71), and Tian Tian Hainanese Chicken Rice (70). These restaurants have crossed a threshold — enough online discussion, enough awards, enough review volume that they've become knowledge every model possesses.

![INSERT CHART: 02_model_breadth.png]
*Gemini surfaces 2.6x more restaurants than GPT-4o. The breadth gap is enormous.*

The discovery gap between models is striking. Gemini mentions **1,591 unique restaurants** — more than the other three models combined (after deduplication). GPT-4o mentions just 616. This isn't Gemini being "better" — it's a stylistic choice. Gemini produces exhaustive, structured lists averaging 10.9 restaurants per response. GPT-4o gives you a curated 5.6. If you're a lesser-known restaurant, Gemini is your best friend. If you care about being a "top pick," GPT-4o's selectivity means each mention carries more weight.

---

## Each AI Has a Personality

This was one of the more fascinating findings. The models don't just differ in *which* restaurants they recommend — they differ in *how* they talk about them.

Ask all four about Labyrinth (a modern Singaporean restaurant) and you get four distinct voices:

- **GPT-4o**: "modern take on Singaporean classics" — factual, brief
- **Claude**: "chef LG Han's playground" — personality-driven, opinionated, scattered with emoji
- **Gemini**: "Michelin 1-Star, deconstructs classic Singaporean dishes, degustation experience" — credential-first, structured
- **Perplexity**: concise blurb with citation markers linking to sources

Some restaurants are exclusive to a single model. The Black Swan appears 8 times but only from GPT-4o. Ce La Vie is Claude's exclusive (7 mentions). Founder Bak Kut Teh appears only in Gemini, possibly reflecting Google's access to its own Maps data during training.

And they disagree on rankings. Take **Din Tai Fung**: GPT-4o ranks it #2.6 on average, Claude #2.2 — but Gemini pushes it all the way down to #9.4. Same story with **Maxwell Food Centre**: GPT-4o and Perplexity both rank it around #3.7, but Gemini buries it at #10.9. **The Coconut Club** sits at #3.0 for Perplexity but #11.0 for Claude.

The pattern is clear. **Gemini consistently pushes casual and chain restaurants down.** It has what we'd call a fine-dining bias. GPT-4o and Perplexity, on the other hand, often agree on ranks, suggesting they may share more overlapping training sources.

![INSERT CHART: 03_rank_disagreement.png]
*Even when all four models mention the same restaurant, they disagree on where to rank it. Each dot is one model's average rank for that restaurant.*

---

## Turn On Web Search and You Get Different Restaurants

This is a headline finding. We ran every prompt twice — once relying purely on the model's training data (search OFF), once with live web search enabled (search ON). The overlap between the two?

**Just 24%.**

![INSERT CHART: 04_search_overlap.png]
*Toggling one setting — web search — changes three-quarters of the recommendation set.*

Out of 2,991 restaurants in our active set:
- **720** appear in both modes (the robust core)
- **1,351** appear only with search ON (likely newer places or those with recent press)
- **920** appear only with search OFF (training data artifacts — places with historical coverage that don't rank in current search results)

Search ON yields slightly more restaurants per response (7.7 vs 7.0 average) but the composition shifts dramatically. Places like VUE Bar & Grill, Liao Fan Hawker Chan, and Wakuda only surface with search enabled — likely newer openings or recently reviewed spots not yet in the models' frozen memory.

The implication: if you're asking AI for restaurant advice and the model has search capabilities, *use it*. The training-data-only version is recommending based on a snapshot of the internet from months (or years) ago.

---

## One in Three Recommended Restaurants Is Closed

This is the finding that made us wince.

We matched our AI-recommended restaurants against Google Places and checked their business status. After human verification: **of 1,266 verified restaurants, 441 are closed** — 23 permanently, 7 temporarily in our deep-verified set, but the broader picture includes hundreds more flagged by Google.

![INSERT CHART: 05_zombie_restaurants.png]
*The top 15 closed restaurants that AI models still confidently recommend. Some have been shut for over a year.*

These aren't obscure picks. Open Farm Community has 44 mentions across all four models. Corner House — Michelin-starred — has 33 mentions despite closing in 2024. Lolla, Esora, Hashida Sushi — all consensus recommendations, all permanently shut.

**13 of the top 100 most-mentioned verified restaurants are zombies.** They persist as ghosts in the training data. The models don't know they've closed and recommend them with full confidence.

Web search partially helps — search-augmented responses are less likely to surface closed places. But even with search ON, some zombies slip through. This is the clearest evidence that **LLM training data is stale for local business recommendations**.

A restaurant that closes doesn't disappear from AI. It haunts the training data for years.

---

## Ask Twice, Get Different Answers

Here's something that surprised us more than the zombie problem. We ran 15 prompts five times each across all models and search modes — 570 stability queries — to test reproducibility.

The headline: **only 26% of recommended restaurants overlap between any two runs of the same prompt.** Ask GPT-4o "best mod-Sin restaurants?" twice, and roughly three out of four suggestions will be different.

![INSERT CHART: 06_jaccard_stability.png]
*The distribution of pairwise overlap between repeated runs. Most cluster well below 0.5, meaning answers change more than they stay the same.*

That's the set overlap. The rank story is more encouraging — when the same restaurants *do* appear, their relative ordering is moderately consistent (Kendall's tau 0.571). The model "knows" Labyrinth should rank above Cheek Bistro. It just can't reliably decide whether to include Cheek Bistro at all.

**79.5% of restaurant appearances are stochastic** — showing up in 2 or fewer of 5 runs. Only 12.7% are "core" recommendations that appear reliably.

![INSERT CHART: 07_stability_by_model.png]
*GPT-4o gives the most consistent answers. Gemini is the most volatile — its longer lists mean more room for variation.*

The models differ in stability:

- **GPT-4o** — most stable sets (0.317 overlap). Its shorter lists mean a tighter "core" that repeats reliably.
- **Claude** — moderate on both measures (0.253 set overlap, 0.601 rank consistency).
- **Perplexity** — volatile sets (0.228) but the best rank consistency (0.610). It shuffles *which* restaurants appear, but when they do, they land in the same order.
- **Gemini** — least stable on both measures (0.224 set overlap, 0.499 rank). Its long lists mean lots of room for variation.

Then there's the specificity paradox.

![INSERT CHART: 08_specificity_paradox.png]
*Narrow prompts have the worst set overlap but the best rank consistency. Broader prompts are more stable in what they include but messier in ordering.*

Narrow prompts ("best xiao long bao in Singapore") produce the **least stable** recommendation sets but the **most stable** rankings. There are fewer "obvious" candidates for very specific queries, so each run draws different restaurants — but when two runs agree on one, they agree on where to put it.

This has a practical implication: **any AEO study that queries each model only once per prompt is measuring signal mixed with substantial noise.** You need 3-5 runs to separate core recommendations from stochastic ones.

---

## Fame Beats Quality

Among 1,235 operational, verified restaurants, we checked which measurable signal best predicts whether AI will recommend a place. The answer is clear — and slightly depressing.

Google **star rating** has essentially zero correlation with AI mention frequency. The relationship is actually slightly *negative* (Spearman r = -0.070). Higher-rated restaurants are, if anything, marginally *less* likely to be heavily mentioned.

Google **review count**, however, has a significant positive correlation (Spearman r = 0.279). Review volume is a proxy for online presence, media coverage, and brand awareness — the signals that actually get baked into LLM training data.

![INSERT CHART: 09_reviews_vs_mentions.png]
*Review volume (how much people talk about you) predicts AI recommendations. Rating (how good you are) doesn't.*

The practical takeaway: a 4.1-star restaurant with 10,000 reviews will outperform a 4.8-star restaurant with 200 reviews in the AI recommendation game. LLMs don't read star ratings — they absorb the *volume* of discussion about a place.

Visibility beats quality. Being talked about matters more than being liked.

---

## The Name Problem (A Brief Aside)

Before we could analyze any of this, we had to solve a surprisingly messy problem: LLMs don't spell restaurant names consistently.

We started with **3,332 raw name strings** from the parsed responses. After three rounds of automated matching (exact normalization, base name grouping, fuzzy matching) plus human review and Google Places cross-referencing, we collapsed these into **3,032 canonical restaurants** — 339 merges total.

Some examples of the chaos:

- **CÉ LA VI** appeared as 7 different strings: CÉ LA VI, Ce La Vi, Ce La Vie, Cé La Vi, CE LA VI, Ce La Vié, CÉ LA VIE
- **Mr & Mrs Mohgan's** had 7 variants, including creative misspellings like "Moghan's"
- **PS.Cafe** showed up 6 ways: PS.Cafe, P.S. Cafe, PS. Cafe, P.S. Café, PS Cafe, PS. Café

43% of merges were Unicode/punctuation issues, 22% structural reordering ("Restaurant Labyrinth" vs "Labyrinth Restaurant"), 18% location qualifiers being included or dropped, and 17% genuine spelling differences.

We also caught 33 hidden duplicates that *no* string matching could find — pairs like "Violet Oon Singapore" and "National Kitchen by Violet Oon" that resolved to the same Google Places ID. Or "Zen" and "Restaurant Zén." External identifiers beat string similarity every time.

This matters for restaurants: your *exact name* as each AI knows it determines whether your mentions get counted together or scattered across variants.

---

## The Invisible Restaurant

Here's where the research gets personal. **Sabai Fine Thai on the Bay** — a real restaurant at 70 Collyer Quay, Marina Bay — has 366 Google reviews, a 4.1 rating, and a waterfront location. It is not obscure.

Yet across all 1,690 queries in our main dataset, it appeared **zero times**.

We ran a targeted probe: 160 queries across four tiers of increasing specificity. The detection pattern was sharp:

- **"Best Thai restaurants in Singapore"** → Sabai detected 25% of the time
- **"Thai near Marina Bay"** → 28%
- **"Thai with a bay view"** → 35%
- **"Tell me about Sabai Fine Thai"** → 93%

Sabai only reliably surfaces when you mention it *by name*. For generic Thai queries, it loses to the established canon — Patara, Thanying, Long Chim. But here's the twist: when the prompt precisely matches Sabai's niche — "Thai restaurant with a bay view in Singapore" — it ranks **#1** on 5 of 8 model-search combinations.

The restaurant has a niche. The AI knows it. But you have to phrase the question exactly right to unlock it.

Gemini was Sabai's best friend (24/40 detections), likely because Google's grounding pulls structured data from Google Business Profile rather than parsing web pages. Claude was worst — its training data appears to lack Sabai entirely; it only surfaces with web search or direct name mention.

An interesting competitor pattern emerged: **Sarai Fine Thai** (different restaurant, similar name) dominates generic Thai queries but vanishes when you add location specificity. Geography is Sabai's moat; generic fame is Sarai's.

---

## What Search Models Actually See

The Sabai probe revealed *why* web search helps some models more than others. When a search-augmented model fetches Sabai's website, it gets almost nothing.

The homepage? Hero images, no text. The about page? A founding story that mentions "Thai fine dining" but not "Marina Bay." The menu? PDF links — zero crawlable dish names. "Marina Bay" — the keyword behind Sabai's strongest queries — appears **nowhere on the website**.

This explains the model-by-model differences:
- **Gemini** performs best because it uses Google's structured knowledge graph (rating, address, category) rather than parsing web pages
- **Perplexity** performs worst because its recency filter narrows results to recent content — and Sabai has almost no recent press coverage. The filter actively excludes the few mentions that exist
- **GPT-4o and Claude** depend on which pages their search tools happen to fetch. If they hit TripAdvisor (which has the address), they learn about Sabai. If they hit the official website, they learn almost nothing

For generic "best Thai" queries, the models don't visit restaurant websites at all. They fetch listicles, TripAdvisor roundups, and food blog posts — then parrot back what those pages say. Sabai appears in 1 of 10 major "best Thai Singapore" listicles we checked.

Here's a detail that surprised us: **none of the five Thai fine-dining competitors we audited** (Sabai, Sarai, Patara, Thanying, Long Chim) have proper `schema.org/Restaurant` markup on their websites. The first mover to add it would have uncontested structured signal in an otherwise signal-sparse segment — particularly relevant for Gemini.

---

## So How Do You Actually Get Noticed by AI?

Using the Sabai data as a case study, we estimated the impact of different interventions for a restaurant sitting below the "AI awareness threshold."

The counterintuitive finding: **the easiest fix (website improvements) has the lowest impact on the queries that matter most.** The hierarchy, ranked by return on effort:

**1. Blog coverage** (3+ food bloggers) — *Highest impact, 2-4 weeks.* The only intervention that works both channels: blog posts appear in live search results *and* enter training data for future model versions.

**2. Listicle placement** (appear in "best of" roundup articles) — *Highest impact for generic queries, 1-4 weeks.* These are literally the pages models read when answering "best Thai restaurant Singapore."

**3. Review volume** (grow from 350 to 1,000+) — *High impact but slow, 3-6 months.* More reviews = higher ranking on TripAdvisor/Google = more likely to appear in search results that models fetch.

**4. Website fixes** (schema markup, meta tags, homepage text) — *Lowest effort but lowest impact, days.* Only helps when a model happens to fetch your site — which rarely happens for generic queries.

Blog coverage is the sweet spot because it's the only intervention that works both channels: blog posts appear in live search results *and* enter the training data for future model versions. Listicle placement directly targets the pages that models actually read when answering "best Thai restaurant in Singapore." Website fixes only help when a model happens to fetch your site — which rarely happens for generic queries.

**The website is the last thing to fix, not the first.** Because models mostly don't read restaurant websites. They read TripAdvisor, food blogs, and Google's structured data.

This framework likely applies to any restaurant in the threshold zone — roughly 200-500 Google reviews with 1-3 blog mentions. Above the threshold, you're already in the AI canon. Below it, no amount of schema markup will help; you need fundamental brand-building first.

---

## Assumptions and Next Steps

### What We Assumed

This study rests on several assumptions worth stating plainly.

**The prompts represent real queries.** Our 140 prompts span 8 dimensions (cuisine, occasion, neighbourhood, vibe, price, constraints, comparisons, experiential) at three specificity levels. They were co-developed across multiple LLMs and consolidated from 581 raw candidates. But they're in English, skewing toward an expat/tourist perspective. We haven't tested Mandarin, Malay, or Tamil queries — and Singapore is multilingual. The AI canon we found may be the *English-language* AI canon.

**Temperature 0.7 is representative.** We used the same temperature across all models for comparability. Real-world deployments vary. Some applications use temperature 0 for determinism; others go higher. Our stability findings (26% overlap) apply specifically to this temperature — deterministic settings would show higher stability, higher temperatures even less.

**Four models are the landscape.** We tested the four most widely used commercial models for consumer queries. We didn't test Meta's Llama, Mistral, or any open-source models. The landscape is moving fast — these results are a snapshot of early 2026.

**Google Places is ground truth.** We treat Google's business status as fact. It's generally accurate but not infallible — some listings may be outdated, and "temporarily closed" can be ambiguous. Our human verification pass on the top 1,267 entries helps, but the remaining ~1,700 canonical restaurants have unverified status.

**Singapore may be special.** Singapore is small, well-documented in English, and has a disproportionately famous food scene. Results in cities with less English-language coverage (say, Chengdu or Porto) might show even larger knowledge gaps and longer zombie persistence.

### What's Next

**More analysis.** We have notebooks planned for deep model comparison and signal analysis (what predicts which *specific* model recommends you — Michelin status? Instagram presence? Google Maps categories?).

**A dashboard.** We're building a Streamlit app for interactive exploration — search for any restaurant and see which models know it, how they describe it, and whether it's a core or stochastic recommendation.

**Longitudinal tracking.** The most interesting question is temporal: if we re-run this study in six months, how much has the zombie problem improved? Which new restaurants have entered the canon? How fast does the training data refresh?

**The Sabai experiment.** We're actively working with a specific restaurant (Sabai Fine Thai, the "invisible restaurant" from our probe) to implement the intervention hierarchy and measure the before/after. If blog coverage and schema markup actually move the needle on AI discoverability, we'll have the data to prove it. That's probably its own post.

**Other cities.** Tokyo, Bangkok, London, New York — the same methodology could reveal whether the patterns we found (5% consensus, 72% single-model, 35% zombie rate) are Singapore-specific or universal features of how LLMs handle local business recommendations.

---

## Methodology Notes

For those who want the technical details:

- **Models**: GPT-4o (Chat Completions + Responses API for search), Claude Sonnet 4 (with web_search tool), Gemini 2.5 Flash (with google_search grounding), Perplexity Sonar (with search_recency_filter)
- **Parsing**: Claude Haiku 4.5 for structured extraction from raw responses (temperature 0)
- **Entity resolution**: Three automated stages (exact normalized, base name grouping, fuzzy matching with shared-word penalty via rapidfuzz) plus human triage and Google Places ID deduplication — 339 total merges from 3,332 → 3,032 canonical restaurants (later expanded to 3,666 with stability test additions)
- **Ground truth**: Google Places Text Search API with manual verification of top 1,267 matches
- **Database**: SQLite, single file, all data queryable
- **Code**: Python, async API calls, Pydantic models for structured data
- **Total cost**: ~$100 in API calls ($66 for queries, $7 for parsing, $23 for stability tests, ~$3 for Google Places)
- **Total queries**: 1,690 (1,120 main + 570 stability) plus 160 targeted probe queries

The full codebase, data, and notebooks are open source.

---

## Appendix: Full Chart Gallery

### A1. Model Overlap Matrix

![INSERT CHART: a1_overlap_heatmap.png]
*Pairwise overlap between models — how many restaurants does each pair share? Gemini-Claude share the most; GPT-4o has the smallest overlap with everyone.*

### A2. Average Mentions Per Response

![INSERT CHART: a2_avg_mentions.png]
*Gemini averages nearly 11 restaurants per response — almost double GPT-4o's 5.6. This verbosity gap directly drives the breadth difference.*

### A3. Search Effect by Model

![INSERT CHART: a3_search_mentions.png]
*How web search changes each model's recommendation volume. GPT-4o and Perplexity give slightly more with search; Gemini actually gives fewer (more focused).*

### A4. Zombie Recommendations by Model

![INSERT CHART: a4_closed_by_model.png]
*Which models recommend the most closed restaurants? All four have the problem, but models with broader knowledge (Gemini) naturally surface more zombies.*

### A5. Core vs Stochastic: An Example

![INSERT CHART: a5_core_stochastic.png]
*Five runs of "best mod-Sin restaurants?" on Claude (search OFF). Green = appeared in 4+ runs (core). Yellow = 3 runs (mid). Red = 1-2 runs (stochastic). Most recommendations are coin flips.*

### A6. Star Rating vs AI Mentions

![INSERT CHART: a6_rating_vs_mentions.png]
*Google star ratings have essentially zero correlation with how often AI mentions a restaurant (Spearman r = -0.070). Being good doesn't make you famous to AI.*

### A7. Price Level and AI Mentions

![INSERT CHART: a7_price_effect.png]
*AI recommendations are fairly balanced across price levels, with a slight lean toward mid-range and upscale. Budget options are underrepresented but not absent.*

---

*This research is part of an ongoing project studying AI-mediated restaurant discovery. The dataset covers Singapore as of early 2026. All code and data are open source.*
