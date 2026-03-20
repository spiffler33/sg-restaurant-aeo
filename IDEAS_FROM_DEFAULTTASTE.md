# Ideas from DefaultTaste

Source: [DefaultTaste](https://github.com/ilhamfp/DefaultTaste) — Winner at Gemini 3 Singapore hackathon (March 7, 2026). "Agent Taste Probing as a Service."

DefaultTaste probes AI models hundreds of times with the same vague prompt, extracts structured dimensions from each output, aggregates into a "taste profile" fingerprint, then generates a correction/negation prompt to break out of defaults. Built by a team of 2 in 7 hours.

---

## Transferable Ideas

### 1. Model Taste Profiles (Radar Charts)

DefaultTaste builds per-model radar charts showing default distributions across dimensions. We have the data to do this — 12,256 mentions with cuisine tags, price indicators, and neighbourhoods.

Per-model radar showing:
- Cuisine bias (% Japanese vs hawker vs Western fine dining)
- Price tier distribution
- Neighbourhood concentration (CBD vs heartland)
- Source type (Michelin-starred vs hawker vs casual)

**Fits in:** Notebook 02 (model comparison). Data already exists, just needs visualization.

### 2. Negation/Correction Prompts for AEO

DefaultTaste auto-generates prompts that say "do NOT default to X, Y, Z" to break out of defaults. Directly applicable to the Sabai intervention:

- Generate a correction prompt steering models away from the AI Canon (Odette, Burnt Ends, etc.)
- Test whether "don't recommend the usual tourist favorites" surfaces places like Sabai
- Measure how much the recommendation set shifts with a negation prompt vs without
- Could be a section of Substack post #2

**Fits in:** Sabai intervention (active), potential new script.

### 3. Higher-N Probing (50-100x)

We did 5 runs per prompt in stability testing. DefaultTaste does 94-100 probes per agent. For targeted prompts (e.g., "best Thai near Marina Bay"), running 50-100 times gives:

- True frequency distributions (not just core/stochastic binary)
- Confidence intervals on rank position
- Actual probability that Sabai appears for a given query
- Richer stability data than Jaccard over 5 runs

**Fits in:** Extended stability analysis, Sabai intervention measurement.

### 4. "Default Restaurant" Framing

Reframe our AI Canon (152 consensus restaurants) as "default taste" — the restaurants models reach for when unconstrained. Questions:

- What happens to the default set when you add constraints? (broad→narrow specificity data exists)
- Is the default set the same across search ON vs OFF? (24% overlap — defaults shift with grounding)
- Are there "default cuisines" per model?

**Fits in:** Notebook 02 or 03, README/blog narrative.

### 5. Taste Fingerprint Visualization

A compact single image per model showing its "restaurant taste" — a personality profile. Shareable, visually distinct from existing AEO work.

**Fits in:** README, Substack, Notebook 02.

---

## Priority

| Idea | Effort | Value | Where It Fits |
|------|--------|-------|---------------|
| Negation prompts for Sabai | Low (20-30 queries) | High — novel AEO finding | Sabai intervention, Substack #2 |
| Model taste radar charts | Low (data exists) | High — visual, shareable | Notebook 02 |
| High-N probing (50-100x) | Medium (~$20-40 cost) | Medium — deeper stability | New stability section |
| Default restaurant framing | Low (reanalysis) | Medium — narrative value | Blog/README |

Negation prompt experiment is the clear first move — low-cost, feeds the Sabai intervention, and makes a compelling story.
