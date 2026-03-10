# Sabai Fine Thai on the Bay — AEO Probe Report

Generated: 2026-03-10 10:35 UTC

**Target:** Sabai Fine Thai on the Bay, 70 Collyer Quay, Customs House, Marina Bay
**Queries:** 160 (20 prompts x 4 models x 2 search modes)
**Hypothesis:** Zero mentions in 1,690-query main dataset. How specific must a prompt be to surface it?

---

## Table 1: Sabai Detection Matrix

| Tier | Prompt | GPT-4o OFF | GPT-4o ON | Claude OFF | Claude ON | Gemini OFF | Gemini ON | Pplx OFF | Pplx ON |
|------|------|------|------|------|------|------|------|------|------|
| **T1: Generic** | Best Thai restaurants in Singapore | #7 | — | — | — | #9 | #3 | #10 | — |
|  | Upscale Thai dining in Singapore | — | — | — | — | — | #2 | #1 | — |
|  | Thai restaurant recommendations Singapore | — | — | — | — | — | — | — | — |
|  | Where to eat Thai food in Singapore that's a step above casual | — | — | — | #3 | — | #2 | — | — |
|  | Fine dining Thai food Singapore | — | — | — | #3 | — | #2 | — | — |
| **T2: Location-narrowed** | Good Thai restaurant near Marina Bay Singapore | — | #1 | #3 | #1 | #1 | #1 | #1 | — |
|  | Restaurants at Customs House Collyer Quay Singapore | — | — | — | #5 | — | #6 | — | — |
|  | Thai food near Raffles Place / CBD area Singapore | — | #5 | — | #7 | #1 | — | — | — |
|  | Waterfront restaurants near Marina Bay with Asian food | — | — | — | — | — | — | — | — |
|  | Where to eat near Fullerton Hotel Singapore | — | — | — | — | — | — | — | — |
| **T3: Attribute-specific** | Thai restaurant with a bay view in Singapore | #1 | #1 | — | #1 | #1 | #1 | #1 | — |
|  | Royal Thai cuisine in Singapore | #2 | — | — | — | — | #4 | — | — |
|  | Upscale Thai restaurant with set lunch near Raffles Place | — | — | — | — | — | #2 | — | — |
|  | Thai restaurant Singapore with chef trained in Thai royal palace cooking | — | — | — | — | — | #1 | — | — |
|  | Romantic Thai restaurant with waterfront view Singapore | #1 | #1 | — | — | — | #1 | #1 | — |
| **T4: Near-name** | Is Sabai Fine Thai on the Bay any good? | #1 | #1 | Yes* | #1 | Yes* | #1 | #1 | #1 |
|  | Sabai vs Sarai Thai restaurant Singapore — what's the difference? | #1 | #1 | #1 | #1 | #1 | #1 | #1 | #1 |
|  | Tell me about Sabai Fine Thai Singapore | #1 | #1 | #1 | #1 | #1 | #1 | #1 | #1 |
|  | Thai restaurants in Singapore with 'Sabai' in the name | #1 | #1 | #1 | #1 | #1 | #1 | #1 | Yes* |
|  | What's the Thai restaurant at Customs House Singapore? | #1 | #1 | — | #1 | — | #1 | #1 | — |

> `#N` = detected at rank N | `Yes*` = in raw text but not parsed as structured mention | `—` = not detected

---

## Table 2: Sarai Detection Matrix

| Tier | Prompt | GPT-4o OFF | GPT-4o ON | Claude OFF | Claude ON | Gemini OFF | Gemini ON | Pplx OFF | Pplx ON |
|------|------|------|------|------|------|------|------|------|------|
| **T1: Generic** | Best Thai restaurants in Singapore | — | — | — | #2 | — | #1 | #1 | — |
|  | Upscale Thai dining in Singapore | — | — | — | #5 | — | #1 | — | — |
|  | Thai restaurant recommendations Singapore | — | — | — | #2 | — | #15 | #1 | — |
|  | Where to eat Thai food in Singapore that's a step above casual | — | — | — | #2 | — | #1 | #5 | — |
|  | Fine dining Thai food Singapore | — | — | — | #1 | — | #4 | #9 | — |
| **T2: Location-narrowed** | Good Thai restaurant near Marina Bay Singapore | — | — | — | — | — | — | — | — |
|  | Restaurants at Customs House Collyer Quay Singapore | — | — | — | — | — | — | — | — |
|  | Thai food near Raffles Place / CBD area Singapore | — | — | — | — | — | — | — | — |
|  | Waterfront restaurants near Marina Bay with Asian food | — | — | — | — | — | — | — | — |
|  | Where to eat near Fullerton Hotel Singapore | — | — | — | — | — | — | — | — |
| **T3: Attribute-specific** | Thai restaurant with a bay view in Singapore | — | — | — | — | — | — | — | — |
|  | Royal Thai cuisine in Singapore | — | — | — | — | — | #1 | — | — |
|  | Upscale Thai restaurant with set lunch near Raffles Place | — | — | — | — | #1 | — | — | — |
|  | Thai restaurant Singapore with chef trained in Thai royal palace cooking | — | #2 | — | — | — | #2 | #1 | — |
|  | Romantic Thai restaurant with waterfront view Singapore | — | — | — | — | — | — | — | — |
| **T4: Near-name** | Is Sabai Fine Thai on the Bay any good? | — | — | — | — | — | — | — | — |
|  | Sabai vs Sarai Thai restaurant Singapore — what's the difference? | #2 | #2 | #2 | #3 | #2 | #2 | Yes* | #4 |
|  | Tell me about Sabai Fine Thai Singapore | — | — | — | — | — | — | — | — |
|  | Thai restaurants in Singapore with 'Sabai' in the name | — | — | — | — | — | — | — | — |
|  | What's the Thai restaurant at Customs House Singapore? | — | — | — | — | — | — | — | — |

> Shows when the competitor (Sarai Fine Thai, Tanglin Mall) appears instead.

---

## Table 3: Sabai Detection Summary

**72 / 160** queries mentioned Sabai (45.0%)

| Breakdown | Count |
|-----------|-------|
| Tier 1 (Generic) | 10 |
| Tier 2 (Location-narrowed) | 11 |
| Tier 3 (Attribute-specific) | 14 |
| Tier 4 (Near-name) | 37 |
| Pplx | 14 |
| Gemini | 24 |
| GPT-4o | 18 |
| Claude | 16 |
| Search OFF | 32 |
| Search ON | 40 |

### Sarai Detection Summary (for comparison)

**27 / 160** queries mentioned Sarai

| Breakdown | Count |
|-----------|-------|
| Tier 1 (Generic) | 14 |
| Tier 3 (Attribute-specific) | 5 |
| Tier 4 (Near-name) | 8 |
| Pplx | 7 |
| Gemini | 10 |
| Claude | 7 |
| GPT-4o | 3 |
| Search OFF | 10 |
| Search ON | 17 |

---

## Table 4: Thai Restaurant Frequency (Top 30)

Across all probe responses, which Thai restaurants appeared most? These are the restaurants eating Sabai's lunch.

| Rank | Restaurant | Mentions |
|------|-----------|----------|
| 1 | Sabai Fine Thai on the Bay **<-- TARGET** | 48 |
| 2 | Sarai Fine Thai *(competitor)* | 20 |
| 3 | Patara Fine Thai Cuisine | 18 |
| 4 | Sawadee Thai Cuisine | 15 |
| 5 | Thanying Restaurant | 15 |
| 6 | Blue Jasmine | 13 |
| 7 | Long Chim | 13 |
| 8 | Sabai Fine Thai **<-- TARGET** | 13 |
| 9 | Yhingthai Palace | 12 |
| 10 | Tamarind Hill | 12 |
| 11 | Nakhon Kitchen | 11 |
| 12 | Un-Yang-Kor-Dai | 10 |
| 13 | Un-Yang-Kor-Dai Singapore | 8 |
| 14 | Kinki Restaurant + Bar | 8 |
| 15 | Siam Kitchen | 7 |
| 16 | Khao Hom by Rung Mama | 7 |
| 17 | Gin Khao | 7 |
| 18 | Town Restaurant | 7 |
| 19 | Sabai Sabai Thai Private Kitchen **<-- TARGET** | 7 |
| 20 | Celadon | 6 |
| 21 | Palm Beach Seafood Restaurant | 6 |
| 22 | Long Beach Seafood | 6 |
| 23 | The Courtyard | 6 |
| 24 | Bangkok Jam | 5 |
| 25 | Soi 47 Thai Food | 5 |
| 26 | Thanying | 5 |
| 27 | MP Thai | 5 |
| 28 | Soi Thai Soi Nice | 5 |
| 29 | Jumbo Seafood | 5 |
| 30 | The Clifford Pier | 5 |

---

## Table 5: Name Confusion Check

**17 potential confusion(s) detected** between Sabai and Sarai:

| Prompt | Model | Search | Issue |
|--------|-------|--------|-------|
| sabai_t1_001 | Pplx | OFF | Mentions both Sabai and Sarai |
| sabai_t1_001 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t1_002 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t1_004 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t1_005 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t1_004 | Claude | ON | Mentions both Sabai and Sarai |
| sabai_t4_002 | GPT-4o | ON | Mentions both Sabai and Sarai |
| sabai_t4_002 | GPT-4o | OFF | Mentions both Sabai and Sarai |
| sabai_t1_005 | Claude | ON | Mentions both Sabai and Sarai |
| sabai_t3_002 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t3_004 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t4_002 | Gemini | OFF | Mentions both Sabai and Sarai |
| sabai_t4_002 | Gemini | ON | Mentions both Sabai and Sarai |
| sabai_t4_002 | Pplx | OFF | Mentions both Sabai and Sarai |
| sabai_t4_002 | Claude | OFF | Mentions both Sabai and Sarai |
| sabai_t4_002 | Pplx | ON | Mentions both Sabai and Sarai |
| sabai_t4_002 | Claude | ON | Mentions both Sabai and Sarai |