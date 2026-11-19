"""AgentX anticipatory shopping agent.

Per word:
  1. re-read the whole prefix with the parser -> filters, pending fields, open corrections
  2. retrieve: once the category is settled, one search fetches every product that fits the
     settled filters (category, plus brand/colour if already said). Later words only narrow
     that candidate set locally; a new search runs only if a correction changes a filter the
     candidate set was fetched with.
  3. decide: a confidence score (chance the single fitting product is the final answer)
     decides "commit now" (>= AGENTX_COMMIT_THRESHOLD, default 0.95) or "wait for more words".
finish(): re-read the full request, re-check the answer against every filter, and if the
reading changed, re-search (relaxing filters only if nothing fits at all).
"""
import os
import re

from .backends import make_backend
from .parser import COLOUR_PHRASES, Parser

COLOUR_WORDS = {w for ps in COLOUR_PHRASES.values() for p in ps for w in p.split()}

FIELDS = ("category", "colour", "size", "brand", "max_price")
SEARCH_FIELDS = ("category", "brand", "colour")   # what the candidate fetch is filtered on
K_ALL = 200                                        # larger than any category in the catalogue

# words that start the polite tail of a request ("for my dad", "if you have it", ...):
# once one arrives with the product already pinned down, the shopper is done specifying
TAIL_STARTS = {"for", "if", "as", "need", "thank", "thanks", "please", "nothing", "chahiye",
               "milega", "dikhao", "hai", "kya", "na", "asap", "urgently", "today"}


class Agent:
    def __init__(self, tools, threshold=None, parser=None):
        self.tools = tools
        self.backend = make_backend(tools)
        self.parser = parser or Parser()
        # Commit when confidence >= threshold. From the score: committing p-likely-right with
        # share e of the request left gains 0.6*e*p and risks 1.0*(1-p), so it pays when
        # p > 1 / (1 + 0.6*e); with e ~ 0.1 that is ~0.95.
        self.threshold = float(os.environ.get("AGENTX_COMMIT_THRESHOLD", 0.95)) if threshold is None else threshold
        # tunable limit on searches per request (each one beyond the first is "wasted")
        self.max_searches = int(os.environ.get("AGENTX_MAX_SEARCHES", 4))

    # ------------------------------------------------------------ protocol
    def start(self, request_id):
        self.words = []
        self.fetched_with = None      # filters the candidate set was fetched with
        self.candidates = []
        self.searches = 0
        self.committed = None
        self.unique_streak = (None, 0)
        self.truncated = False
        self.verified = {}
        self.reading = None

    def observe(self, word):
        self.words.append(word)
        r = self.parser.parse(self.words)
        self.reading = r
        f = r.filters
        settled = {k: f[k] for k in FIELDS if f[k] is not None and k not in r.pending}

        if "category" in settled:
            self._ensure_candidates(settled)
        pool = self._narrow(settled) if self.fetched_with else []
        unique = pool[0]["product_id"] if len(pool) == 1 else None
        stable = unique and not r.pending and not r.open_correction and "number" not in r.pending

        pid, streak = self.unique_streak
        if stable and pid == unique:
            streak += 1
        elif stable:
            streak = 1
        else:
            streak = 0
        self.unique_streak = (unique if stable else None, streak)

        # ---- confidence: how likely is the one fitting product to be the final answer?
        # A late constraint can only narrow a unique match, never change it; only a
        # correction can. So confidence is the chance that no correction is still coming,
        # read from where the shopper is in their sentence. Values are the commit success
        # rates measured on dev.jsonl for each situation (tools/calibrate.py).
        tail = _clean(word) in TAIL_STARTS and streak >= 1
        corrected = r.corrections > 0
        clause_end = bool(re.search(r"[,.;!?]$", word.strip()))
        suffix_risk = _suffix_may_follow(self.words, r)
        evidence, conf = self._confidence(r, pool, stable, corrected, tail, clause_end, suffix_risk)
        out = {"filters": dict(f), "confidence": conf}
        if self.committed is None and stable and conf >= self.threshold and (
                not self.truncated or self._verify_unique(settled, unique)):
            self.committed = unique
            out["commit"] = unique
        self.evidence = evidence
        self.last_step = self._explain(r, pool, unique, stable, out.get("commit"),
                                       tail, corrected, clause_end, suffix_risk)
        return out

    def _explain(self, r, pool, unique, stable, commit, tail, corrected, clause_end, suffix_risk):
        """Plain-language account of this word's decision (for the demo and logs)."""
        if commit:
            why = ("the shopper already corrected themselves and the new value is in" if corrected
                   else "the closing phrase has started" if tail
                   else "one product fits and no correction is signalled")
            conf = self.CONFIDENCE.get(self.evidence, 1.0)
            state, text = "commit", f"Commit: {why} (confidence {conf:.2f} ≥ {self.threshold:.2f})"
        elif self.committed:
            state, text = "committed", "Already committed; later words only confirm it"
        elif self.fetched_with is None:
            state, text = "wait", "Waiting for the product type before searching"
        elif r.open_correction:
            state, text = "wait", "A correction has started; holding until the new value arrives"
        elif r.pending - {"number"} or "number" in r.pending:
            fields = ", ".join(sorted(p.replace("max_price", "budget") for p in r.pending))
            state, text = "wait", f"Waiting: {fields} may still change with the next word"
        elif not pool:
            state, text = "wait", "Nothing fits yet"
        elif len(pool) > 1:
            state, text = "wait", f"{len(pool)} products still fit; need more detail"
        elif clause_end:
            state, text = "hold", (f"One match, but a comma or full stop here often comes before a "
                                   f"correction: confidence {self.CONFIDENCE['clause_end']:.2f} < {self.threshold:.2f}")
        elif suffix_risk:
            state, text = "hold", (f"One match, but the next word may still qualify or correct it: "
                                   f"confidence {self.CONFIDENCE['suffix_may_follow']:.2f} < {self.threshold:.2f}")
        else:
            state, text = "hold", "One match; holding"
        return {"state": state, "text": text, "pool": [
            {k: p.get(k) for k in ("product_id", "title", "brand", "colour", "size", "price")}
            for p in pool[:6]], "pool_size": len(pool) if self.fetched_with else None,
            "pending": sorted(r.pending), "searches": self.searches}

    def finish(self):
        r = self.parser.parse(self.words)
        f = {k: v for k, v in r.filters.items() if v is not None}
        if "category" not in f:
            return self.committed or self._fallback(f)
        self._ensure_candidates(f, final=True)
        pool = self._narrow(f)
        if self.truncated and len(pool) != 1:
            # the candidate page was capped: ask the backend with every filter instead
            if self.committed and pool and pool[0]["product_id"] == self.committed:
                return self.committed
            hits = self.backend.search(" ".join(str(v) for v in f.values()), f, 2)
            self.searches += 1
            pool = hits or pool
        if len(pool) >= 1:
            return pool[0]["product_id"]
        return self._fallback(f)

    # ------------------------------------------------------------ retrieval
    def _ensure_candidates(self, settled, final=False):
        want = {k: settled[k] for k in SEARCH_FIELDS if k in settled}
        if self.fetched_with is not None:
            # still valid if every filter we fetched with is still asked for, unchanged
            if all(settled.get(k) == v for k, v in self.fetched_with.items()):
                return
        if self.searches >= self.max_searches and not final:
            return
        query = " ".join(str(v) for v in want.values())
        k = min(K_ALL, getattr(self.backend, "max_k", K_ALL))
        self.candidates = self.backend.search(query, want, k)
        self.searches += 1
        self.fetched_with = want
        # a full page may mean the backend capped the results: then "one candidate left"
        # is not proof of uniqueness, and observe() verifies with an exact search first
        self.truncated = len(self.candidates) >= k
        self.verified = {}

    def _verify_unique(self, settled, pid):
        """Exact search with every settled filter (only needed when results were capped)."""
        key = tuple(sorted((k, str(v)) for k, v in settled.items()))
        if key not in self.verified:
            hits = self.backend.search(" ".join(str(v) for v in settled.values()), settled, 2)
            self.searches += 1
            self.verified[key] = hits[0]["product_id"] if len(hits) == 1 else None
        return self.verified[key] == pid

    def _narrow(self, f):
        out = []
        for p in self.candidates:
            ok = True
            for k in ("category", "colour", "size", "brand"):
                if f.get(k) is not None and str(p.get(k, "")).lower() != str(f[k]).lower():
                    ok = False
                    break
            if ok and f.get("max_price") is not None and int(p["price"]) > f["max_price"]:
                ok = False
            if ok:
                out.append(p)
        out.sort(key=lambda p: int(p["price"]))
        return out

    def _fallback(self, f):
        """Nothing fits the full reading: relax the least reliable filters one at a time."""
        f = dict(f)
        for drop in ("max_price", "size", "brand", "colour", "category"):
            f.pop(drop, None)
            hits = self.backend.search(" ".join(self.words), f, 1)
            self.searches += 1
            if hits:
                return hits[0]["product_id"]
        return self.committed

    # How often "one product fits" was the right answer in each situation on dev.jsonl,
    # smoothed as (right + 1) / (total + 2); tools/calibrate.py prints these.
    CONFIDENCE = {"flowing": 0.99, "tail": 0.99, "corrected": 0.98,
                  "suffix_may_follow": 0.92, "clause_end": 0.59}

    def _confidence(self, r, pool, stable, corrected, tail, clause_end, suffix_risk):
        """(situation, confidence that the single fitting product is the final answer)."""
        if not pool:
            return "no_candidates", 0.0
        if not stable:
            # several products fit, or the reading may still change with the next word
            c = 1.0 / len(pool)
            if r.pending or r.open_correction:
                c *= 0.5
            return ("several_fit" if len(pool) > 1 else "pending"), round(min(c, 0.5), 3)
        for name, hit in (("corrected", corrected), ("tail", tail),
                          ("clause_end", clause_end), ("suffix_may_follow", suffix_risk)):
            if hit:
                return name, self.CONFIDENCE[name]
        return "flowing", self.CONFIDENCE["flowing"]


def _suffix_may_follow(words, r):
    """The value just said often takes a trailing word ("size 8 | UK", "M | size",
    "Loomsy | brand"). Wait for it so the punctuation after it can be seen."""
    if not r.mentions:
        return False
    fld, val, _ = r.mentions[-1]
    last = _clean(words[-1])
    prev = _clean(words[-2]) if len(words) > 1 else ""
    if fld == "size":
        if last.isdigit() and prev in ("size", "number"):
            return True          # "size 8" -> "UK"?
        if last in ("s", "m", "l", "xs", "xl", "xxl", "2xl") and prev not in ("size",):
            return True          # "M" -> "size"?
    if fld == "brand" and last == str(val).split()[-1].lower():
        return True              # "Loomsy" -> "brand"?
    if fld == "colour" and last in COLOUR_WORDS:
        return True              # "in navy" -> "blue"? or "in white make that red"
    if last in ("only", "by", "from", "in", "of", "with", "and", "also", "ka", "wala"):
        return True              # a value is about to be named
    return False


def _clean(word):
    return re.sub(r"[^\w']", "", word.lower())
