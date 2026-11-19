"""Build site/data.js: real agent runs and measured numbers for the website.

    python tools/build_site_data.py

Everything the website shows comes from here: the replay scenarios are traces of the
actual agent (same code evaluate.py scores), and the stats are re-measured on dev.jsonl.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "demo"))

from agentx.agent import Agent                      # noqa: E402
from evaluate import BaselineAgent, run, summarise  # noqa: E402
import server                                       # noqa: E402  (demo/server.py: run())

SCENARIOS = [
    ("Plain", "dev-0001"),
    ("Correction", "dev-0003"),
    ("Correction", "dev-0017"),
    ("Late constraint", "dev-0006"),
    ("Hindi–English", "dev-0103"),
    ("Hindi–English", "dev-0130"),
]


def main():
    reqs = [json.loads(l) for l in open(ROOT / "dev.jsonl", encoding="utf-8") if l.strip()]
    by_id = {r["id"]: r for r in reqs}

    scenarios = []
    for tag, rid in SCENARIOS:
        r = by_id[rid]
        res = server.run(r["text"], r["target"])
        keep = ("word", "index", "state", "text", "pool_size", "pool", "pending", "filters",
                "confidence", "commit", "searches")
        res["steps"] = [{k: s.get(k) for k in keep} for s in res["steps"]]
        scenarios.append({"tag": tag, "id": rid, "text": r["text"], **res})

    ours, _ = run(Agent, reqs)
    base, _ = run(BaselineAgent, reqs)
    s, b = summarise(ours), summarise(base)
    tags = {}
    for t in ("plain", "correction", "late_constraint", "code_mixed"):
        rows = [x for x in ours if (t in x["tags"]) or (t == "plain" and not x["tags"])]
        brows = [x for x in base if (t in x["tags"]) or (t == "plain" and not x["tags"])]
        tags[t] = {"n": len(rows), "score": round(summarise(rows)["score"], 1),
                   "baseline": round(summarise(brows)["score"], 1),
                   "wrong": summarise(rows)["wrong_commits"]}

    # threshold sweep: what lowering/raising the confidence bar would do
    sweep = []
    for thr in (0.5, 0.6, 0.8, 0.9, 0.95, 0.99, 1.01):
        cls = type("A", (Agent,), {"__init__": lambda self, tools, t=thr: Agent.__init__(self, tools, threshold=t)})
        x = summarise(run(cls, reqs)[0])
        sweep.append({"threshold": thr, "score": round(x["score"], 1), "wrong": x["wrong_commits"],
                      "early": round(100 * x["early_share"], 1)})

    # calibration (same as tools/calibrate.py)
    agent = Agent(server.Tools(), threshold=2.0)
    cal = defaultdict(lambda: [0, 0])
    for req in reqs:
        agent.start(req["id"])
        seen = set()
        for w in req["words"]:
            agent.observe(w)
            st = agent.last_step
            if st["pool_size"] == 1 and agent.evidence not in ("pending", "several_fit", "no_candidates") \
                    and agent.evidence not in seen:
                seen.add(agent.evidence)
                cal[agent.evidence][1] += 1
                cal[agent.evidence][0] += st["pool"][0]["product_id"] == req["target"]
        agent.finish()

    data = {
        "scenarios": scenarios,
        "stats": {
            "accuracy": s["accuracy"], "baseline_accuracy": b["accuracy"],
            "wrong": s["wrong_commits"], "early_share": s["early_share"],
            "oracle_share": s["oracle_share"], "searches": s["searches"],
            "baseline_searches": b["searches"], "score": round(s["score"], 1),
            "baseline_score": round(b["score"], 1), "requests": s["requests"],
        },
        "tags": tags, "sweep": sweep,
        "calibration": [{"situation": k, "right": v[0], "total": v[1],
                         "confidence": Agent.CONFIDENCE.get(k)} for k, v in
                        sorted(cal.items(), key=lambda kv: -Agent.CONFIDENCE.get(kv[0], 0))],
        "threshold": Agent(server.Tools()).threshold,
        "catalogue_size": len(server.CATALOGUE),
    }
    out = ROOT / "site" / "data.js"
    out.parent.mkdir(exist_ok=True)
    out.write_text("window.AGENTX = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size // 1024} KB): {len(scenarios)} scenarios, "
          f"score {data['stats']['score']} vs {data['stats']['baseline_score']}")
    for x in sweep:
        print("  threshold", x)


if __name__ == "__main__":
    main()
