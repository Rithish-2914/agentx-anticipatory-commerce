"""Generate a stress set in dev.jsonl format with wording that dev.jsonl does not use,
to check the parser and commit policy generalise (the hidden test set has new wording).

    python tools/make_stress.py --n 300 --seed 7 --out stress.jsonl
"""
import argparse
import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CAT = {
    "running shoes": ["running shoes", "trainers", "sports shoes", "jogging shoes", "runners", "running sneakers"],
    "sneakers": ["sneakers", "casual shoes", "casual sneakers", "canvas shoes"],
    "sandals": ["sandals", "flip flops", "slippers", "chappals", "slides", "floaters"],
    "t-shirts": ["t-shirt", "tee", "tshirt", "polo", "t shirt"],
    "shirts": ["shirt", "casual shirt", "formal shirt"],
    "jeans": ["jeans", "denim", "pair of jeans", "denims"],
    "dresses": ["dress", "frock", "gown"],
    "kurtas": ["kurta", "kurti"],
    "hoodies": ["hoodie", "sweatshirt", "hooded sweatshirt", "hoody"],
    "jackets": ["jacket", "windcheater", "bomber jacket"],
    "track pants": ["track pants", "joggers", "trackpants", "sweatpants", "lowers"],
    "backpacks": ["backpack", "rucksack", "school bag", "laptop bag", "bagpack"],
    "caps": ["cap", "baseball cap", "hat"],
    "headphones": ["headphones", "headset", "earphones"],
    "watches": ["watch", "wristwatch", "wrist watch"],
    "wallets": ["wallet", "purse"],
}
COL = {"black": ["black", "jet black", "kaala"], "white": ["white", "off white", "safed"],
       "navy": ["navy", "navy blue", "dark blue"], "blue": ["blue", "sky blue", "neela"],
       "red": ["red", "laal"], "green": ["green", "hara"], "grey": ["grey", "gray", "charcoal"],
       "beige": ["beige", "cream"], "olive": ["olive", "olive green", "army green"],
       "brown": ["brown", "chocolate", "bhura"], "maroon": ["maroon", "burgundy", "wine"],
       "yellow": ["yellow", "mustard", "peela"], "pink": ["pink", "gulabi"],
       "gold": ["gold", "golden"], "silver": ["silver"], "tan": ["tan", "camel"]}
LETTER = {"XS": ["XS", "extra small"], "S": ["S", "small"], "M": ["M", "medium"],
          "L": ["L", "large"], "XL": ["XL", "extra large", "x-large"],
          "XXL": ["XXL", "2XL", "double XL", "double extra large"]}
EN = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
      "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
      "nineteen"]
TENS = {20: "twenty", 30: "thirty", 40: "forty", 50: "fifty", 60: "sixty", 70: "seventy",
        80: "eighty", 90: "ninety"}
OPEN = ["", "hello, ", "yo, ", "please find ", "I am searching for ", "could you show me ",
        "I want to buy ", "need ", "any ", "do you sell ", "help me find ", "mujhe chahiye "]
TAIL = ["", "", " for my sister", " for college", " for a trip", " if available", " asap",
        " for daily use", " thanks a lot", " for my mom", " to gift someone", " for travel"]
CORR = ["no wait,", "scratch that,", "hold on, I mean", "sorry, I meant", "actually make it",
        "no no,", "or rather", "I mean", "nahi,", "matlab"]
PRICE_PRE = ["under", "below", "within", "less than", "not more than", "up to", "budget",
             "max", "at most", "no more than", "cheaper than"]


def words_for(n):
    if n < 20:
        return EN[n]
    if n < 100:
        t = TENS[n // 10 * 10]
        return t if n % 10 == 0 else f"{t} {EN[n % 10]}"
    raise ValueError


def say_price(v, rnd):
    style = rnd.choice(["digits", "comma", "k", "words", "rs", "rupee_sign"])
    if style == "digits":
        return str(v)
    if style == "comma":
        return f"{v:,}"
    if style == "k" and v % 100 == 0:
        k = v / 1000
        return f"{k:g}k"
    if style == "words":
        if v % 1000 == 0:
            return f"{words_for(v // 1000)} thousand"
        if v % 100 == 0 and v < 10000:
            h = v // 100
            if h < 100 and rnd.random() < 0.5:
                return f"{words_for(h)} hundred"
            th, rest = divmod(v, 1000)
            return (f"{words_for(th)} thousand " if th else "") + f"{words_for(rest // 100)} hundred"
    if style == "rs":
        return f"Rs {v}"
    return f"₹{v}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(ROOT / "stress.jsonl"))
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    cat = list(csv.DictReader(open(ROOT / "catalogue.csv", encoding="utf-8")))
    for p in cat:
        p["price"] = int(p["price"])
    out = []
    while len(out) < a.n:
        p = rnd.choice(cat)
        use_brand = rnd.random() < 0.85
        use_price = rnd.random() < 0.7
        f = {"category": p["category"], "colour": p["colour"], "size": p["size"] or None,
             "brand": p["brand"] if use_brand else None, "max_price": None}
        if use_price:
            f["max_price"] = int(-(-p["price"] * rnd.uniform(1.0, 1.4) // 100) * 100)
        match = [q for q in cat if all(f[k] is None or q[k] == f[k] for k in ("category", "colour", "brand"))
                 and (f["size"] is None or q["size"] == f["size"])
                 and (f["max_price"] is None or q["price"] <= f["max_price"])]
        if len(match) != 1:
            continue
        parts = {}
        parts["category"] = rnd.choice(CAT[p["category"]])
        parts["colour"] = rnd.choice(["", "in "]) + rnd.choice(COL[p["colour"]])
        if f["brand"]:
            parts["brand"] = rnd.choice(["{b}", "by {b}", "from {b}", "only {b}", "{b} brand"]).format(b=p["brand"])
        if f["size"]:
            s = f["size"]
            if s in LETTER:
                parts["size"] = rnd.choice(["size {x}", "{x}", "{x} size"]).format(x=rnd.choice(LETTER[s]))
            elif p["category"] == "jeans":
                parts["size"] = rnd.choice(["waist {x}", "{x} waist", "size {x}"]).format(x=s)
            else:
                x = rnd.choice([s, words_for(int(s))])
                parts["size"] = rnd.choice(["size {x}", "UK {x}", "size {x} UK"]).format(x=x)
        if f["max_price"]:
            parts["max_price"] = f"{rnd.choice(PRICE_PRE)} {say_price(f['max_price'], rnd)}"
        order = list(parts)
        rnd.shuffle(order)
        if "category" in order and rnd.random() < 0.6:   # category usually early
            order.remove("category")
            order.insert(rnd.randrange(0, min(3, len(order) + 1)), "category")
        tags = []
        # correction: say a wrong value for one field first
        if rnd.random() < 0.2:
            fld = rnd.choice([k for k in order if k in ("colour", "brand", "size")])
            wrong = None
            if fld == "colour":
                wrong = rnd.choice([c for c in COL if c != p["colour"]])
                wrong_txt = rnd.choice(COL[wrong])
            elif fld == "brand":
                wrong_txt = rnd.choice([b for b in {q["brand"] for q in cat} if b != p["brand"]])
            else:
                same = [q["size"] for q in cat if q["category"] == p["category"] and q["size"] and q["size"] != p["size"]]
                if not same:
                    continue
                wrong_txt = "size " + rnd.choice(same)
            parts[fld] = f"{wrong_txt}, {rnd.choice(CORR)} {parts[fld]}"
            tags.append("correction")
        if rnd.random() < 0.15 and len(order) > 2:
            late = order.pop(rnd.randrange(1, len(order)))
            order.append(late)
            parts[late] = rnd.choice(["oh and also", "one more thing,", "and it should be", "plus"]) + " " + parts[late]
            tags.append("late_constraint")
        text = (rnd.choice(OPEN) + " ".join(parts[k] for k in order) + rnd.choice(TAIL)).strip()
        text = " ".join(text.split())
        out.append({"id": f"stress-{len(out) + 1:04d}", "text": text, "words": text.split(),
                    "filters": f, "target": p["product_id"], "tags": tags})
    with open(a.out, "w", encoding="utf-8") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out)} requests to {a.out}")


if __name__ == "__main__":
    main()
