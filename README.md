# AgentX: Anticipatory Commerce Agent

A shopping agent that finds the right product **before the shopper finishes the request**, and never commits to a wrong one. Built for **AgentX: The Agentic Commerce Challenge, Challenge 1** (Techfest, IIT Bombay 2026-27).

Requests arrive one word at a time. For each word, the agent:
1. predicts the shopper's filters (category, colour, size, brand, budget) from the words so far;
2. searches early;
3. uses a **confidence score** to decide "commit now" or "wait for more words".

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

**Generalisation:** on 1,800 generated requests in wording that `dev.jsonl` never uses, the parser reads 100% of filters correctly and the agent scores 47.7–48.3 with 0 wrong commits (`tools/make_stress.py`).

Per-request outputs: [`runs/dev_results.jsonl`](runs/dev_results.jsonl). Design: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Run it

Python 3.9+, standard library only. Nothing to install.

```bash
python evaluate.py --agent my_agent.py --log runs/dev_results.jsonl   # score on the dev set
python tools/calibrate.py                                             # confidence calibration table
python tools/check_parser.py                                          # parser vs gold filters
python tools/make_stress.py --seed 7 --out runs/stress7.jsonl         # unseen-wording stress set
python evaluate.py --agent my_agent.py --data runs/stress7.jsonl
python evaluate.py --agent tests/capped_agent.py                      # backend that caps results at 20
```

Settings: `AGENTX_COMMIT_THRESHOLD` (default 0.95) and `AGENTX_MAX_SEARCHES` (search budget per request, default 4).

## Live demo

```bash
python demo/server.py        # then open http://localhost:8765
```

Type any request, or pick an example: plain, correction, late constraint or Hindi–English. Watch it word by word:
- the five filters fill in, turn pending, and get corrected (*grey, was black*);
- the count of products that still fit drops;
- the confidence score rises to the threshold, with the agent explaining each wait-or-commit decision;
- the product is shown the moment it is safe.

The demo runs the same agent code that `evaluate.py` scores.

## How it works

- **Parser** (`agentx/parser.py`): re-reads the whole prefix on every word. It handles:
  - synonyms (*floaters → sandals, runners → running shoes, hooded sweatshirt → hoodies*);
  - English and Hindi numbers (*forty five hundred, 1.5k, ₹1,500, saadhe teen hazaar, das number*);
  - corrections, where the latest mention of a field wins.

  It also marks **pending** fields that the next word may still change (*two thousand… → 2,500?*).
- **Retrieval** (`agentx/agent.py`): one search once the category is settled. Later words narrow the candidates locally, and it searches again only when a correction invalidates them.
- **Confidence**: a late constraint can only narrow a unique match. Only a correction can make it wrong. Once one product fits, confidence is the measured chance that no correction follows in the current situation:
  - flowing: 0.99
  - polite tail started: 0.99
  - already corrected: 0.98
  - a suffix may follow: 0.92
  - the value just ended a clause: 0.59

  The agent commits at ≥ 0.95, a threshold derived from the score weights (see `ARCHITECTURE.md`).

## Layout

| Path | What |
|---|---|
| `my_agent.py` | entry point for `evaluate.py` |
| `agentx/` | parser, agent (retrieval and confidence), search backend |
| `demo/` | live word-by-word demo (`server.py` + `index.html`) |
| `tools/` | confidence calibration, parser check, stress-set generator, adversarial examples |
| `tests/capped_agent.py` | checks behaviour when the search backend caps its results |
| `runs/dev_results.jsonl` | per-request outputs on the dev set |
| `catalogue.csv`, `dev.jsonl`, `search.py`, `evaluate.py` | official starter kit ([docs/STARTER_KIT.md](docs/STARTER_KIT.md)) |
