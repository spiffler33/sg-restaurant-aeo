# The Packaging Playbook

10 rules. Apply to everything you ship.

---

**1. README is the product.**
Most people will never clone your repo. They'll read the README and leave. Put your best output — a finding, a chart, a screenshot — above the fold. If they can't see the value without running anything, they won't run anything.

**2. Time to first value: under 2 minutes.**
One-line install. One command to see output. Zero config for the first run. Every setup step (API key, database, config file) loses you half your audience. Ship a demo mode with bundled sample data if the real thing needs keys.

**3. Lead with the output, not the process.**
"13% of AI-recommended restaurants are permanently closed" gets clicks. "A multi-model query pipeline with entity resolution" doesn't. Show what you found or what the tool produces. Methodology goes below the fold.

**4. Name it so a stranger gets it in 5 seconds.**
Say the name to someone who's never seen your work. If they can guess what it does, it works. "humanizer" works. "geo-seo-claude" works. Clever acronyms and abstract nouns don't.

**5. One package per audience.**
A research dataset, a CLI tool, and a Claude Code skill serve different people. Ship them separately. A monorepo that does everything confuses everyone. Pick one audience per package.

**6. Frame the value for that audience.**
Same work, different pitch. Pick one per package:
- *Business ROI*: "Agencies charge $X/month for this."
- *Research*: "We measured X across N samples. Here's what we found."
- *Anti-establishment*: "Everyone's guessing. We measured."
- *Social proof*: "Used by engineers at [company]."

**7. Distribution is not optional.**
Building it is half the work. The other half:
- Reply to viral threads in your space (ride existing waves)
- Submit to awesome-lists (they're 10K-80K star aggregators)
- Post to HN ("Show HN"), Reddit, Twitter — with different framings
- Announce more than once. Updates, findings, blog posts — each is a new reason to share.

**8. Ship pre-computed artifacts.**
Charts, sample reports, example output — include them in the repo so the visitor sees results before deciding to run the process. Research repos: embed key charts in README. Tools: include a sample report. Datasets: show 5 interesting rows.

**9. Set the social preview.**
When someone shares your GitHub link on Twitter, what image shows? Default GitHub card = invisible. A custom card with your key chart or finding = clicks. Set it in repo settings. Takes 30 seconds.

**10. The pre-launch gate.**
Don't ship until you can check all of these:
- [ ] One-sentence description, no jargon
- [ ] One-line install works on a fresh machine
- [ ] First run produces output with zero config
- [ ] Key finding or output visible in README without running anything
- [ ] At least one visual (chart, screenshot, or GIF)
- [ ] MIT license
- [ ] Social preview image set
- [ ] Tweet drafted, linking to repo + blog

---

*Written 2026-03-20. Derived from studying geo-seo-claude (3.2K stars), humanizer (10K stars), planning-with-files (16K stars), get-shit-done (36K stars), and others.*
