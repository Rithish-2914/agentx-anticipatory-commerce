# AgentX: Anticipatory Commerce Agent

A shopping agent that finds the right product **before the shopper finishes the request**, and never commits to a wrong one. Built for **AgentX: The Agentic Commerce Challenge, Challenge 1** (Rezolve AI × Techfest, IIT Bombay 2026-27).

Requests arrive one word at a time. For each word, the agent:
1. predicts the shopper's filters (category, colour, size, brand, budget) from the words so far;
2. searches early;
3. decides whether to commit now or wait.

## Results on `dev.jsonl` (300 requests)

| | Baseline | **AgentX** |
|---|---|---|
| Accuracy | 0.527 | **1.000** |
| Wrong commits | 0 | **0** |
| Earliness (share of the request still to come at commit) | 0% | **11.0%** (best possible 16.3%) |
| Searches per request | 1.53 | **1.04** |
| Latency | | 0.1 ms/word |
| **Score** | 20.0 | **46.5** (ceiling ≈ 49.8) |

By tag: plain 47.1 · corrections 47.0 · late constraints 43.2 · Hindi–English code-mixed 48.0. All have zero wrong commits.

Generalisation: on 1,800 generated requests in wording that `dev.jsonl` never uses, the parser reads 100% of filters correctly and the agent scores 47.8–48.8 (`tools/make_stress.py`).

Per-request outputs: [`runs/dev_results.jsonl`](runs/dev_results.jsonl). Design: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Run it

Python 3.9+, standard library only. Nothing to install.

```bash
python evaluate.py --agent my_agent.py --log runs/dev_results.jsonl   # score on the dev set
python tools/check_parser.py                                          # parser vs gold filters
python tools/make_stress.py --seed 7 --out runs/stress7.jsonl         # unseen-wording stress set
python evaluate.py --agent my_agent.py --data runs/stress7.jsonl
python evaluate.py --agent tests/capped_agent.py                      # backend that caps results at 20
```

## Live demo

```bash
python demo/server.py        # then open http://localhost:8765
```

Type any request, or pick an example: plain, correction, late constraint or Hindi–English. Watch it word by word:
- the five filters fill in, turn pending, and get corrected (*grey, was black*);
- the count of products that still fit drops;
- the agent explains each wait-or-commit decision;
- the product is shown the moment it is safe.

The words the agent no longer needed are underlined in green. The demo runs the same agent code that `evaluate.py` scores. With `REZOLVE_API_KEY` and `REZOLVE_KB_ID` set, its searches go through Rezolve Labs.

## Rezolve Labs capabilities used

| Capability | Used for |
|---|---|
| **Managed knowledge retrieval** | Knowledge base that holds `catalogue.csv` (`tools/rezolve_setup.py`) |
| **Semantic product search** | The early candidate search and the confirming searches (`agentx/backends.py`, `RezolveBackend`). Every call is counted with `tools.record_search()` |

```powershell
$env:REZOLVE_API_KEY="..."
python tools/rezolve_setup.py          # creates the knowledge base, uploads the catalogue, prints its id
$env:REZOLVE_KB_ID="..."
python evaluate.py --agent my_agent.py # now every search goes through Rezolve
```

Optional settings: `REZOLVE_MAX_K` (page cap, default 50) and `AGENTX_MAX_SEARCHES` (search budget per request, default 4).

## How it works

- **Parser** (`agentx/parser.py`): re-reads the whole prefix on every word. It handles:
  - synonyms (*floaters → sandals, runners → running shoes, hooded sweatshirt → hoodies*);
  - English and Hindi numbers (*forty five hundred, 1.5k, ₹1,500, saadhe teen hazaar, das number*);
  - corrections, where the latest mention of a field wins.

  It also marks **pending** fields that the next word may still change (*two thousand… → 2,500?*).
- **Retrieval** (`agentx/agent.py`): one search once the category is settled. Later words narrow the candidates locally, and it searches again only when a correction invalidates them.
- **Commit gate**: a late constraint can only narrow a unique match. Only a correction can make it wrong. The agent commits when exactly one product fits and no correction is likely:
  - the deciding word didn't end a clause, and no suffix such as "UK" or "brand" is expected next;
  - or the polite tail of the request has started;
  - or a correction has already been made and resolved.

## Layout

| Path | What |
|---|---|
| `my_agent.py` | entry point for `evaluate.py` |
| `agentx/` | parser, agent, search backends (local and Rezolve) |
| `tools/` | Rezolve setup, parser check, stress-set generator, adversarial examples |
| `demo/` | live word-by-word demo (`server.py` + `index.html`) |
| `tests/capped_agent.py` | checks behaviour when the search backend caps its results |
| `runs/dev_results.jsonl` | per-request outputs on the dev set |
| `catalogue.csv`, `dev.jsonl`, `search.py`, `evaluate.py` | starter kit from Rezolve AI ([docs/STARTER_KIT.md](docs/STARTER_KIT.md)) |
