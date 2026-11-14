# AgentX: Anticipatory Commerce agent: architecture note

**Challenge 1: Anticipatory Commerce** (Rezolve AI × Techfest IIT Bombay 2026-27)

## Pipeline (runs once per spoken word)

```
word ─▶ Parser (re-reads whole prefix) ─▶ Reading{filters, pending, open_correction}
                                              │
          category settled? ──▶ Retrieval: ONE search (Rezolve semantic product search, or local)
                                   filtered on category (+ brand/colour if already said)
                                              │  candidate set cached
                                              ▼
                          Local narrowing by every settled filter (colour, size, brand, max price)
                                              │
                         exactly 1 left AND commit gate open? ──▶ {"commit": product_id}
finish() ─▶ re-parse full request ─▶ re-check answer against ALL filters (re-search only if a
            filter the candidate set was fetched with changed; relax filters only if nothing fits)
```

## 1. Filter prediction from a partial request (`agentx/parser.py`)
- Deterministic, about 0.1 ms per word, no model calls. Vocabulary (brands, colours, sizes) comes from `catalogue.csv`. Synonyms are hand-written: *runners / jogging shoes → running shoes, floaters / slides → sandals, tee → t-shirts, hooded sweatshirt → hoodies, rucksack / bag pack → backpacks…*
- Numbers in English and Hindi: *forty five hundred, one thousand five hundred, 1.5k, ₹1,500, saadhe teen hazaar, pandrah sau, dhai hazaar, das number*. Whether a number is a size or a price is decided from context (*size / UK / waist / number* vs *under / max / tak / se kam*).
- **Pending fields**: a field whose value may still change with the next word. Examples: *running…*, *two thousand…*, *size…*, *Kesar…*, or a correction marker with no new value yet. Pending fields are never used for retrieval or commits.
- **Corrections and late constraints**: the latest mention of each field wins. That resolves *black — no wait, white*, *Northweft, or rather Tanaro* and *size M, oops, XS*. A bare value after a marker (*size eight actually six*) takes the type of the value it corrects.

## 2. Early search, checked against the full request
- One search per request, at the moment the category is settled. Every later word narrows the cached candidates locally. A new search runs only when a correction changes a filter the candidates were fetched with.
- On dev this averages **1.04 searches per request** (0.04 wasted).
- If a backend caps its page size, "one candidate left" is no longer proof. The agent then confirms with an exact search before committing, and again in `finish()`. A simulated 20-result cap keeps 100% accuracy and 0 wrong commits.
- `AGENTX_MAX_SEARCHES` sets a tunable limit on wasted searches (stretch goal).

## 3. Commit-or-wait decision (`agentx/agent.py`)
A late constraint can only narrow a unique match. Only a correction can make it wrong. So the agent commits when **exactly one product fits the settled filters**, nothing is pending, and one of these holds:

1. **Flow**: the value that pinned the product was not followed by a clause break ("," or "."), and no suffix is expected next (*size 8 → UK?*, *M → size?*, *Loomsy → brand?*, *in navy → blue? / make that red?*, *only → [brand]*). On dev, clause breaks right after the deciding value preceded about half of all corrections.
2. **Polite tail**: the shopper starts the closing phrase (*for my dad, if you have it, thanks, chahiye…*).
3. **Already corrected**: the shopper has corrected once and the new value has arrived. No dev request corrects twice.

A confidence score (1 ÷ candidate count, discounted while fields are pending) is reported every word for analysis.

## Rezolve Labs capabilities used
| Capability | Where |
|---|---|
| **Managed knowledge retrieval**: knowledge base holding `catalogue.csv` | `tools/rezolve_setup.py` creates it and uploads the catalogue |
| **Semantic product search** (`/product-discovery/search`, filters plus `price_lte`) | `agentx/backends.py` `RezolveBackend`: serves the early candidate search and the confirming searches. Every call is counted with `tools.record_search()` |

Set `REZOLVE_API_KEY` and `REZOLVE_KB_ID` to switch the agent from the local `search.py` to Rezolve. No other code changes.

## Results on `dev.jsonl` (300 requests, `python evaluate.py --agent my_agent.py`)
| | Baseline | AgentX |
|---|---|---|
| Accuracy | 0.527 | **1.000** |
| Wrong commits | 0 | **0** |
| Earliness (share of the request still to come) | 0% | **11.0%** (best possible 16.3%) |
| Searches per request | 1.53 | **1.04** |
| Latency | | 0.1 ms/word (local) |
| **Score** | 20.0 | **46.5** (ceiling about 49.8) |

Generalisation check: `tools/make_stress.py` generates requests with wording that `dev.jsonl` does not use, for example *trainers, flip flops, charcoal, scratch that, hold on, I mean, ₹ / Rs / k / spoken prices*. Over 6 seeds × 300 requests the parser reads 100% of filters correctly. The agent scores 47.8–48.8 with at most 1 wrong commit (found and fixed).
