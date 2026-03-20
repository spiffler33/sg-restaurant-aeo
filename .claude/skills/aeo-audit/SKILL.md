---
name: aeo-audit
description: Audit a restaurant's web presence — check what AI models see when deciding whether to recommend it. Covers website, Google Business Profile, review platforms, and structured data.
allowed-tools: Bash, Read, Write, WebFetch, WebSearch, Grep, Glob
---

# AEO Audit

Audit a restaurant's online presence to understand why AI models do or don't recommend it. This checks the signals that feed into LLM training data and search-augmented responses.

## Arguments

The user provides a restaurant name and optionally a URL:
- `/aeo-audit "Sabai Fine Thai"` — searches for the business, then audits
- `/aeo-audit https://sabaifinethai.com` — audits starting from the URL

## Your task

### Step 1: Find the business

Search the web for the restaurant to find:
- Official website URL
- Google Maps / Google Business Profile listing
- Major review platform listings (TripAdvisor, Yelp, Burpple, HungryGoWhere, etc.)
- Social media presence (Instagram, Facebook)

### Step 2: Website technical audit

Fetch the restaurant's website and check:

1. **Crawlability:** Can search engines and AI crawlers access the content? Check for:
   - robots.txt restrictions (especially blocks on GPTBot, ClaudeBot, Google-Extended, PerplexityBot)
   - JavaScript-only rendering (content invisible without JS execution)
   - Meta robots noindex/nofollow tags

2. **Structured data:** Look for Schema.org markup:
   - `Restaurant` or `LocalBusiness` schema
   - `Menu` schema with item names and prices
   - `OpeningHoursSpecification`
   - `AggregateRating` and `Review` markup
   - `address`, `geo`, `telephone` properties

3. **Content signals:** What text does the page surface?
   - Restaurant name, cuisine type, location mentioned in headers/title
   - Menu items described in crawlable text (not just images/PDFs)
   - Unique selling points visible in first 500 words
   - About page with story, chef background, sourcing

4. **Technical health:**
   - Page load (is the site up?)
   - Mobile meta viewport tag
   - HTTPS
   - Canonical URL

### Step 3: Google Business Profile check

Search for the restaurant on Google and report:
- Rating and review count
- Business status (open/closed)
- Listed categories
- Photos count
- Recent reviews sentiment
- Completeness of the listing (hours, menu, description)

### Step 4: Platform presence

Check major listing platforms:
- TripAdvisor ranking and review count
- Yelp presence
- Local platforms (Burpple, HungryGoWhere for Singapore; equivalent for other cities)
- Instagram hashtag volume

### Step 5: Competitor benchmarking

If the user provided a category (e.g., "Thai restaurants in Singapore"), identify the top 3-5 competitors that AI models DO recommend (from the research database if available) and note what they do differently online.

### Step 6: Generate report

Write a report at `data/probes/<business_name>/audit.md` with:

1. **Visibility Score:** Rate 1-10 based on overall discoverability
2. **What AI models see:** Summary of crawlable content
3. **What's missing:** Gaps in structured data, content, or platform presence
4. **Intervention hierarchy** (ordered by effort/impact):
   - Quick wins (structured data, Google Business Profile optimization)
   - Medium effort (content additions, platform listings)
   - Long-term (review acquisition, content strategy, PR)
5. **Competitor comparison table**

## Report tone

Factual, not salesy. Present findings as data, not pitches. "Your site blocks GPTBot in robots.txt" not "You're missing out on AI traffic!"
