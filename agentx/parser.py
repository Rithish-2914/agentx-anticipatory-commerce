"""Incremental filter parser for shopping requests that arrive one word at a time.

parse(words) reads the words so far and returns a Reading:
    filters  - {category, colour, size, brand, max_price}, the latest mention of each wins,
               which is how "black, no wait, white" and "size M, oops, XS" resolve
    pending  - fields whose value may still change with the next word(s)
               ("running ..." -> shoes or sneakers? "two thousand ..." -> 2000 or 2500?)
    open_correction - a correction marker was just said ("sorry, I meant ...") and its new
               value has not arrived yet
    mentions - every (field, value, token index) found, for analysis and confidence

Vocabulary (brands, colours, sizes) is read from catalogue.csv once at start-up; synonyms,
number words (English and Hindi) and phrasing rules are hand-written.
"""
import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

CATALOGUE = Path(__file__).resolve().parent.parent / "catalogue.csv"

# ---------------------------------------------------------------- vocabularies

# phrase (tuple of tokens) -> category.  Longest match wins, so "running sneakers" beats
# "sneakers" and "t shirt" beats "shirt".
CATEGORY_PHRASES = {
    "running shoes": ["running shoes", "running shoe", "running sneakers", "running sneaker",
                      "runners", "runner shoes", "jogging shoes", "jogging shoe", "sports shoes",
                      "sport shoes", "trainers", "training shoes", "marathon shoes", "running"],
    "sneakers": ["sneakers", "sneaker", "casual shoes", "casual shoe", "casual sneakers",
                 "casual sneaker", "kicks", "canvas shoes", "lifestyle shoes", "shoes", "joote", "jootey"],
    "sandals": ["sandals", "sandal", "slides", "slide", "floaters", "floater", "flip flops",
                "flip-flops", "flipflops", "slippers", "slipper", "chappal", "chappals", "chappals"],
    "t-shirts": ["t-shirt", "t-shirts", "tshirt", "tshirts", "t shirt", "t shirts", "tee", "tees",
                 "tee shirt", "polo", "polo shirt", "polos"],
    "shirts": ["shirt", "shirts", "casual shirt", "casual shirts", "formal shirt", "formal shirts",
               "button down", "button-down"],
    "jeans": ["jeans", "jean", "denims", "denim", "pair of jeans", "denim jeans"],
    "dresses": ["dress", "dresses", "frock", "frocks", "gown", "gowns", "one piece", "one-piece"],
    "kurtas": ["kurta", "kurtas", "kurti", "kurtis"],
    "hoodies": ["hoodie", "hoodies", "hooded sweatshirt", "hooded sweatshirts", "sweatshirt",
                "sweatshirts", "hoody", "hooded"],
    "jackets": ["jacket", "jackets", "windcheater", "bomber", "bomber jacket", "puffer",
                "blazer"],
    "track pants": ["track pants", "track pant", "trackpants", "trackpant", "joggers", "jogger",
                    "trackies", "sweatpants", "track", "lowers", "jogger pants"],
    "backpacks": ["backpack", "backpacks", "rucksack", "rucksacks", "bag pack", "bagpack",
                  "school bag", "laptop bag", "college bag", "bag", "bags", "daypack"],
    "caps": ["cap", "caps", "baseball cap", "hat", "hats", "topi"],
    "headphones": ["headphones", "headphone", "headset", "headsets", "earphones", "earphone",
                   "earbuds", "over ear", "over-ear"],
    "watches": ["watch", "watches", "wrist watch", "wristwatch", "wristwatches", "wrist", "ghadi",
                "ghari"],
    "wallets": ["wallet", "wallets", "purse", "billfold", "card holder"],
}
# single words that are only the start of a category phrase: wait for the next word
CATEGORY_PREFIXES = {"running", "jogging", "casual", "t", "tee", "track", "bag", "wrist",
                     "hooded", "pair", "sports", "sport", "flip", "school", "laptop", "college",
                     "formal", "polo", "baseball", "denim", "training", "jogger"}

COLOUR_PHRASES = {
    "black": ["black", "kaala", "kala", "kaali", "kali", "jet black"],
    "white": ["white", "safed", "safaid", "off white", "off-white"],
    "navy": ["navy", "navy blue", "dark blue", "midnight blue"],
    "blue": ["blue", "neela", "nila", "neeli", "sky blue", "light blue", "royal blue"],
    "red": ["red", "laal", "lal"],
    "green": ["green", "hara", "hari", "dark green", "light green"],
    "grey": ["grey", "gray", "charcoal", "slate", "ash", "dark grey", "dark gray", "light grey",
             "light gray", "grey colour", "sleti"],
    "beige": ["beige", "cream", "off beige"],
    "olive": ["olive", "olive green", "army green"],
    "brown": ["brown", "bhura", "bhoora", "chocolate", "dark brown", "coffee"],
    "maroon": ["maroon", "burgundy", "wine", "wine red"],
    "yellow": ["yellow", "peela", "pila", "peeli", "mustard"],
    "pink": ["pink", "gulabi", "baby pink"],
    "gold": ["gold", "golden", "sunehra", "sunehri"],
    "silver": ["silver", "chandi", "chaandi", "silvery"],
    "tan": ["tan", "camel"],
}
COLOUR_PREFIXES = {"dark", "light", "sky", "royal", "off", "jet", "army", "baby", "wine", "midnight"}

LETTER_SIZES = {
    "xs": "XS", "s": "S", "m": "M", "l": "L", "xl": "XL", "xxl": "XXL", "2xl": "XXL",
    "small": "S", "medium": "M", "large": "L", "extra small": "XS", "extra large": "XL",
    "x large": "XL", "x-large": "XL", "double xl": "XXL", "double extra large": "XXL",
    "xx large": "XXL", "xx-large": "XXL", "xxs": "XS", "x small": "XS", "x-small": "XS",
    "chhota": "S", "bada": "L", "medium size": "M",
}
SIZE_PREFIXES = {"extra", "double", "x", "xx"}

# ---------------------------------------------------------------- number words

EN_UNITS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
            "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
            "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
            "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
            "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "a": None}
HI_UNITS = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
            "chhe": 6, "chheh": 6, "chah": 6, "che": 6, "saat": 7, "sat": 7, "aath": 8, "aat": 8,
            "nau": 9, "das": 10, "dus": 10, "gyarah": 11, "gyaarah": 11, "barah": 12, "baarah": 12,
            "terah": 13, "chaudah": 14, "pandrah": 15, "pandrah": 15, "pandra": 15, "solah": 16,
            "satrah": 17, "satra": 17, "atharah": 18, "athara": 18, "unnees": 19, "bees": 20,
            "bis": 20, "pachees": 25, "pachchees": 25, "pachis": 25, "tees": 30, "chalis": 40,
            "chaalis": 40, "pachaas": 50, "pachas": 50}
HI_FRACTION = {"saadhe": 0.5, "sadhe": 0.5, "saade": 0.5, "sawa": 0.25, "savaa": 0.25,
               "paune": -0.25, "pone": -0.25}
HI_FIXED = {"dedh": 1.5, "derh": 1.5, "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5}
MULTIPLIERS = {"hundred": 100, "thousand": 1000, "k": 1000, "sau": 100, "hazaar": 1000,
               "hazar": 1000, "hajar": 1000, "grand": 1000, "lakh": 100000}

PRICE_BEFORE = [  # phrases that introduce a maximum price
    "under", "below", "within", "max", "maximum", "upto", "up to", "budget", "budget of",
    "less than", "not more than", "no more than", "not above", "at most", "cheaper than",
    "for under", "for less than", "for below", "price under", "price below", "lesser than",
    "not over", "not exceeding", "under rs", "around", "about", "range", "priced under",
    "max price", "budget is", "budget hai", "tops", "max budget", "rs", "rupees", "inr", "₹",
]
PRICE_AFTER = ["tak", "se kam", "ke andar", "ke neeche", "ke niche", "rupees", "rs", "rupaye",
               "rupay", "rupee", "inr", "max", "budget", "or less", "or below", "tops",
               "ke under", "under", "mein", "me"]
SIZE_BEFORE = ["size", "uk", "waist", "us", "eu", "size uk", "uk size", "waist size", "number",
               "sz"]
SIZE_AFTER = ["uk", "waist", "size", "number", "no", "inch", "inches"]

CORRECTION_MARKERS = [
    "no wait", "no no", "no", "wait", "sorry", "i mean", "i meant", "actually", "make that",
    "make it", "change that to", "change it to", "or rather", "rather", "oops", "scratch that",
    "nahi", "nahin", "matlab", "instead", "not that", "correction", "my bad", "hold on",
    "na na", "nahi nahi",
]
FILLERS = {"um", "uh", "hmm", "umm", "uhh", "er", "erm", "like", "ah", "hm"}


def _tok(word):
    """Split one spoken word into lower-case tokens, keeping ₹ and k-suffixed numbers."""
    w = word.lower().replace("’", "'")
    w = w.replace("₹", " ₹ ")
    w = re.sub(r"\brs\.?(?=\d)", "rs ", w)
    out = []
    for t in w.split():
        t = t.strip(",.?!;:\"()")
        if t.endswith("/-"):
            t = t[:-2]
        if t:
            out.append(t)
    return out


def _num(tok):
    """Digits like 1,500 / 1.5k / 2k / 0.8k / 4500 -> number, else None."""
    m = re.fullmatch(r"(\d+(?:,\d{3})*(?:\.\d+)?)(k|l)?", tok)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    if m.group(2) == "k":
        v *= 1000
    elif m.group(2) == "l":
        v *= 100000
    return v


@dataclass
class Reading:
    filters: dict
    pending: set = field(default_factory=set)
    open_correction: bool = False
    mentions: list = field(default_factory=list)
    corrections: int = 0


class Parser:
    def __init__(self, catalogue_path=CATALOGUE):
        with open(catalogue_path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        self.brands = {}
        for r in rows:
            self.brands[r["brand"].lower()] = r["brand"]
        self.categories = sorted({r["category"] for r in rows})
        self.shoe_sizes = sorted({r["size"] for r in rows
                                  if r["category"] in ("running shoes", "sneakers", "sandals")},
                                 key=lambda s: int(s))
        self.waist_sizes = sorted({r["size"] for r in rows if r["category"] == "jeans"},
                                  key=lambda s: int(s))
        self.sizeless = {c for c in self.categories
                         if all(not r["size"] for r in rows if r["category"] == c)}
        # phrase tables: tuple(tokens) -> (field, value)
        table = {}
        for cat, phrases in CATEGORY_PHRASES.items():
            for p in phrases:
                table[tuple(p.split())] = ("category", cat)
        for col, phrases in COLOUR_PHRASES.items():
            for p in phrases:
                table[tuple(p.split())] = ("colour", col)
        for b_low, b in self.brands.items():
            table[tuple(b_low.split())] = ("brand", b)
        for p, s in LETTER_SIZES.items():
            table[tuple(p.split())] = ("size", s)
        self.table = table
        self.max_len = max(len(k) for k in table)
        self.brand_prefixes = {b.split()[0] for b in self.brands if " " in b}
        self.correction = sorted((tuple(c.split()) for c in CORRECTION_MARKERS), key=len, reverse=True)
        self.price_before = sorted((tuple(c.split()) for c in PRICE_BEFORE), key=len, reverse=True)
        self.price_after = sorted((tuple(c.split()) for c in PRICE_AFTER), key=len, reverse=True)
        self.size_before = sorted((tuple(c.split()) for c in SIZE_BEFORE), key=len, reverse=True)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _match_at(toks, i, phrases):
        for p in phrases:
            if tuple(toks[i:i + len(p)]) == p:
                return len(p)
        return 0

    @staticmethod
    def _ends_with(toks, j, phrases):
        """Does a phrase end right before index j (ignoring fillers)?"""
        k = j
        while k > 0 and toks[k - 1] in FILLERS:
            k -= 1
        for p in phrases:
            if k - len(p) >= 0 and tuple(toks[k - len(p):k]) == p:
                return True
        return False

    def _number_phrase(self, toks, i):
        """Read a spoken number starting at i. Returns (value, length, complete_word_number)
        or None. 'complete' is False when more number words could still follow."""
        n = len(toks)
        j = i
        # Hindi fractional prefixes: saadhe teen hazaar = 3500, dhai hazaar = 2500
        if toks[j] in HI_FIXED:
            base = HI_FIXED[toks[j]]
            j += 1
            if j < n and toks[j] in MULTIPLIERS:
                return base * MULTIPLIERS[toks[j]], j + 1 - i, True
            return base, j - i, False
        frac = 0
        if toks[j] in HI_FRACTION:
            frac = HI_FRACTION[toks[j]]
            j += 1
            if j >= n:
                return None
        total, current, used_word, last_was_mult = 0, 0, False, False
        start = j
        while j < n:
            t = toks[j]
            v = _num(t)
            if v is not None and j == start:
                current = v
                used_word = False
                j += 1
                # 2 thousand / 2 hazaar
                if j < n and toks[j] in MULTIPLIERS:
                    current *= MULTIPLIERS[toks[j]]
                    j += 1
                    last_was_mult = True
                return current, j - i, True
            if j > start and (j - 1) in self._bounds:
                break  # "... five hundred. one more thing": punctuation ends the number
            if j == start and t in ("a", "an", "ek") and j + 1 < n and toks[j + 1] in MULTIPLIERS:
                current, used_word = 1, True            # "a thousand", "ek hazaar"
            elif j == start and t in ("thousand", "hazaar", "hazar", "hajar"):
                total, used_word, last_was_mult = MULTIPLIERS[t], True, True   # bare "hazaar"
            elif t in EN_UNITS and EN_UNITS[t] is not None:
                if last_was_mult and current:
                    break  # "five hundred one" is not how prices are said
                if current and not (current % 10 == 0 and current >= 20 and EN_UNITS[t] < 10):
                    break  # only "forty five" style pairs: "size eight one more thing" is 8
                current += EN_UNITS[t]
                used_word, last_was_mult = True, False
            elif t in HI_UNITS and (used_word is False or t not in ("do", "sat", "che")):
                # Hindi number words only when a multiplier follows, or as "das number"
                nxt = toks[j + 1] if j + 1 < n else None
                if nxt in MULTIPLIERS or nxt in ("number", "no") or nxt is None or frac:
                    current += HI_UNITS[t]
                    used_word, last_was_mult = True, False
                else:
                    break
            elif t in MULTIPLIERS and used_word:
                m = MULTIPLIERS[t]
                if m >= 1000:
                    total += (current or 1) * m
                    current = 0
                else:
                    current = (current or 1) * m
                last_was_mult = True
            elif t == "and" and used_word and last_was_mult:
                pass
            else:
                break
            j += 1
        if not used_word:
            return None
        value = total + current
        if frac:
            # saadhe teen hazaar: (3 + 0.5) * 1000
            mult = 1000 if any(toks[k] in ("hazaar", "hazar", "hajar", "thousand") for k in range(start, j)) else 100
            value += frac * mult
        while j > i and toks[j - 1] == "and":
            j -= 1
        complete = j < n  # a later word that is not a number closed it
        return value, j - i, complete

    # ------------------------------------------------------------ main
    def parse(self, words):
        toks, bounds = [], set()
        for w in words:
            ts = _tok(w)
            toks.extend(ts)
            if ts and re.search(r"[,.?!;:]$", w.strip()):
                bounds.add(len(toks) - 1)
        self._bounds = bounds
        n = len(toks)
        mentions = []          # (field, value, token index)
        pending = set()
        open_correction = False
        corrections = 0
        last_correction_at = -1
        i = 0
        while i < n:
            t = toks[i]
            if t in FILLERS and t != "like":
                i += 1
                continue
            # correction markers
            c = self._match_at(toks, i, self.correction)
            if c:
                # "no" is only a correction when it isn't part of "not/no more than"
                phrase = toks[i:i + c]
                if phrase == ["no"] and i + 1 < n and toks[i + 1] in ("more",):
                    c = 0
                elif phrase == ["rather"] and i > 0 and toks[i - 1] != "or":
                    pass
                if c:
                    corrections += 1
                    last_correction_at = i + c
                    i += c
                    continue
            # numbers: price or size
            nxt = toks[i + 1] if i + 1 < n else None
            starts_number = (
                _num(t) is not None or t in HI_UNITS or t in HI_FRACTION or t in HI_FIXED
                or (t in EN_UNITS and t != "a")
                or (t in ("a", "an") and nxt in MULTIPLIERS)
                or t in ("thousand", "hazaar", "hazar", "hajar"))
            numres = self._number_phrase(toks, i) if starts_number else None
            if numres:
                value, length, complete = numres
                kind = self._classify_number(toks, i, length, value, mentions, last_correction_at)
                if kind:
                    v = int(round(value)) if kind == "max_price" else self._size_value(value)
                    if v is not None:
                        mentions.append((kind, v, i))
                        if i + length >= n and not complete:
                            pending.add(kind)
                        elif i + length >= n and kind == "max_price" and _num(toks[i]) is None:
                            pending.add(kind)
                        i += length
                        continue
                    i += length
                    continue
                if i + length >= n and not complete:
                    pending.add("number")
            # phrases: longest first
            hit = None
            for L in range(min(self.max_len, n - i), 0, -1):
                key = tuple(toks[i:i + L])
                if key in self.table:
                    hit = (L, self.table[key])
                    break
            if hit:
                L, (fld, val) = hit
                if fld == "size" and not self._size_ok(toks, i, L, words):
                    i += 1
                    continue
                mentions.append((fld, val, i))
                if i + L >= n:  # phrase ended at the last token: may still grow
                    last = toks[n - 1]
                    if fld == "category" and (last in CATEGORY_PREFIXES):
                        pending.add("category")
                    if fld == "colour" and last in COLOUR_PREFIXES:
                        pending.add("colour")
                i += L
                continue
            if i == n - 1:
                if t in CATEGORY_PREFIXES:
                    pending.add("category")
                if t in COLOUR_PREFIXES:
                    pending.add("colour")
                if t in SIZE_PREFIXES:
                    pending.add("size")
                if t in self.brand_prefixes:
                    pending.add("brand")
                if (t,) in self.size_before or t in ("size",):
                    pending.add("size")
                if self._ends_with(toks, n, self.price_before) or t in ("than", "to", "of", "up", "less", "more", "not", "for"):
                    pending.add("max_price")
            i += 1

        # a correction marker with nothing after it yet
        if last_correction_at >= 0:
            after = [m for m in mentions if m[2] >= last_correction_at]
            if not after:
                open_correction = True
        # also if the request ends on a marker-ish word like "i", "make", "change", "or"
        if n and toks[-1] in ("i", "make", "change", "or", "that", "to", "scratch", "hold"):
            if any(toks[-1] == p[0] for p in self.correction) or toks[-1] in ("to", "that"):
                open_correction = open_correction or self._partial_correction(toks)

        filters = {"category": None, "colour": None, "size": None, "brand": None, "max_price": None}
        for fld, val, _ in mentions:
            filters[fld] = val
        if filters["category"] in self.sizeless:
            filters["size"] = None
        return Reading(filters, pending, open_correction, mentions, corrections)

    def _partial_correction(self, toks):
        tail = toks[-3:]
        for p in self.correction:
            for k in range(1, len(p)):
                if tuple(tail[-k:]) == p[:k]:
                    return True
        return False

    def _size_ok(self, toks, i, L, words):
        """Single letters s/m/l count as sizes only when written in capitals or next to 'size'."""
        tok = toks[i]
        if L > 1 or tok not in ("s", "m", "l"):
            if tok in ("small", "medium", "large"):
                # "large" in "extra large" is handled by the longer phrase
                return True
            return True
        # find the original word to check capitalisation
        raw = [w for w in words for _ in _tok(w)]
        orig = raw[i] if i < len(raw) else tok
        stripped = orig.strip(",.?!;:")
        if stripped.isupper():
            return True
        nb = toks[i - 1] if i > 0 else ""
        na = toks[i + 1] if i + 1 < len(toks) else ""
        return nb == "size" or na == "size"

    def _size_value(self, value):
        if value != int(value):
            return None
        v = str(int(value))
        if v in self.shoe_sizes or v in self.waist_sizes:
            return v
        return None

    def _classify_number(self, toks, i, length, value, mentions, last_correction_at):
        end = i + length
        before_size = self._ends_with(toks, i, self.size_before)
        before_price = self._ends_with(toks, i, self.price_before)
        after = toks[end:end + 2]
        after1 = after[0] if after else None
        after_price = bool(after) and any(tuple(toks[end:end + len(p)]) == p for p in self.price_after)
        if after1 in ("uk", "waist", "size", "number", "inch", "inches") and value < 100:
            return "size"
        if toks[i] == "₹" or (i > 0 and toks[i - 1] in ("₹", "rs", "inr")):
            return "max_price"
        if before_size and value < 100:
            return "size"
        if before_price or after_price:
            return "max_price"
        if value >= 100:
            return "max_price"
        # a bare small number right after a correction: same field as the last numeric mention
        if last_correction_at >= 0 and i >= last_correction_at:
            for fld, _, _ in reversed(mentions):
                if fld == "max_price" and value >= 50:
                    return fld
                if fld == "size" and self._size_value(value) is not None:
                    return fld
                if fld in ("size", "max_price"):
                    break
        if self._size_value(value) is not None and value < 100:
            # "size seven floaters" handled above; bare "30 waist" handled above;
            # a bare 6..11 or 28..36 next to clothing words is most likely a size
            return "size"
        return None
