# AgentX: Anticipatory Commerce agent: architecture note

**Challenge 1: Anticipatory Commerce** (Techfest, IIT Bombay 2026-27)

## Pipeline (runs once per word)

```
word ─▶ Parser (re-reads whole prefix) ─▶ Reading{filters, pending fields, open correction}
                                              │
          category settled? ──▶ Retrieval: ONE search filtered on category (+ brand/colour if said)
                                              │  candidate set cached
                                              ▼
                     Local narrowing by every settled filter (colour, size, brand, max price)
                                              │
              Confidence = P(the single fitting product is the final answer)
                                              │
                  ≥ 0.95 ──▶ {"commit": product_id}          < 0.95 ──▶ wait for more words
finish() ─▶ re-parse the full request ─▶ re-check the answer against ALL filters (re-search only if a
            filter the candidates were fetched with changed; relax filters only if nothing fits)
```

## 1. Filter prediction from a partial request (`agentx/parser.py`)
- Deterministic, about 0.1 ms per word, no model calls, standard library only. Brands, colours and sizes come from `catalogue.csv`. Synonyms are hand-written: *runners / jogging shoes → running shoes, floaters / slides → sandals, tee → t-shirts, hooded sweatshirt → hoodies, rucksack / bag pack → backpacks…*
- Numbers in English and Hindi: *forty five hundred, one thousand five hundred, 1.5k, ₹1,500, a thousand, saadhe teen hazaar, pandrah sau, dhai hazaar, das number*. Whether a number is a size or a price is decided from context (*size / UK / waist / number* vs *under / max / tak / se kam*).
- **Pending fields** are fields whose value may still change with the next word. Examples: *running…* (shoes or sneakers?), *two thousand…* (2,000 or 2,500?), *size…*, *Kesar…*, or a correction marker with no new value yet. Pending fields are never used to retrieve or commit.
- **Corrections and late constraints**: the latest mention of each field wins, which resolves *black — no wait, white*, *Northweft, or rather Tanaro* and *size M, oops, XS*. A bare value after a marker (*size eight actually six*) takes the type of the value it corrects.

## 2. Early search, checked against the full request
- One search per request, made when the category is settled. Every later word narrows the cached candidates locally. A new search runs only when a correction changes a filter the candidates were fetched with.
- On dev this averages **1.04 searches per request** (0.04 wasted).
- `finish()` re-reads the whole request and re-checks the answer against every filter before it becomes final.
- If a search backend caps its page size, "one candidate left" is no longer proof. The agent then confirms with an exact search before committing. A simulated 20-result cap keeps 100% accuracy and 0 wrong commits (`tests/capped_agent.py`).
- `AGENTX_MAX_SEARCHES` is a tunable limit on wasted searches per request (stretch goal).

## 3. Confidence score: "commit now" or "wait for more words" (`agentx/agent.py`)
**Key observation:** a late constraint can only narrow a unique match, never change it. Only a correction can make it wrong. So once exactly one product fits, confidence is the chance that no correction is still coming, and the shopper's position in the sentence predicts that:

| Situation when one product fits | Right on dev | Confidence |
|---|---|---|
| Flowing: no clause break, no suffix expected | 179 / 179 | 0.99 |
| Polite tail started (*for my dad, if you have it, chahiye*) | 90 / 90 | 0.99 |
| Already corrected once, new value in | 52 / 52 | 0.98 |
| A suffix may follow (*size 8 → UK?*, *Loomsy → brand?*, *in navy → blue? / make that red?*) | 114 / 123 | 0.92 |
| The value ended a clause ("," or ".") | 18 / 30 | 0.59 |

Confidence values are smoothed rates, (right + 1) / (total + 2), printed by `tools/calibrate.py`. While several products fit, or a field is pending, confidence is at most 0.5.

**The threshold comes from the score formula.** A commit that is right with probability p, with share e of the request still to come, gains 0.6·e·p and risks 1.0·(1−p). That pays off only when p > 1 / (1 + 0.6·e), which is about **0.95** at a typical e ≈ 0.1. Setting `AGENTX_COMMIT_THRESHOLD=0.9` would commit earlier (14.7% vs 11.0%) but make 9 wrong commits on dev, and the score drops from 46.5 to 45.8.

## Results on `dev.jsonl` (300 requests, `python evaluate.py --agent my_agent.py`)
| | Baseline | AgentX |
|---|---|---|
| Accuracy | 0.527 | **1.000** |
| Wrong commits | 0 | **0** |
| Earliness (share of the request still to come) | 0% | **11.0%** (best possible 16.3%) |
| Searches per request | 1.53 | **1.04** |
| Latency | | 0.1 ms/word |
| **Score** | 20.0 | **46.5** (ceiling about 49.8) |

By tag: plain 47.1 · corrections 47.0 · late constraints 43.2 · Hindi–English 48.0, all with 0 wrong commits.

**Generalisation:** `tools/make_stress.py` generates requests in wording `dev.jsonl` never uses (*trainers, flip flops, charcoal, scratch that, hold on, ₹ / Rs / k / spoken prices*). Across 6 seeds × 300 requests, the parser reads 100% of filters correctly and the agent scores 47.7–48.3 with 0 wrong commits.
