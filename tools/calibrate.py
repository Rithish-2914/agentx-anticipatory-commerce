"""Measure how often "one product fits" turns out right, per situation, on a data set.

    python tools/calibrate.py [dev.jsonl]

Runs the agent without ever committing. Each time exactly one product fits and the reading
is stable, it records the situation (flowing, clause_end, ...) and whether that product is
the target. The rates printed here are the CONFIDENCE values in agentx/agent.py.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agentx.agent import Agent       # noqa: E402
from evaluate import Tools           # noqa: E402

path = ROOT / (sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl")
reqs = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
agent = Agent(Tools(), threshold=2.0)          # never commits
stats = defaultdict(lambda: [0, 0])            # situation -> [right, total]
for req in reqs:
    agent.start(req["id"])
    seen = set()
    for w in req["words"]:
        agent.observe(w)
        step = agent.last_step
        if step["pool_size"] == 1 and agent.evidence not in ("pending", "several_fit", "no_candidates"):
            if agent.evidence in seen:
                continue
            seen.add(agent.evidence)       # first time per request, as a commit would be
            stats[agent.evidence][1] += 1
            stats[agent.evidence][0] += step["pool"][0]["product_id"] == req["target"]
    agent.finish()

print(f"{'situation':20} {'right':>6} {'total':>6} {'rate':>6} {'smoothed':>9}   agent.py value")
for name, (ok, n) in sorted(stats.items(), key=lambda kv: -kv[1][1]):
    print(f"{name:20} {ok:6} {n:6} {ok / n:6.2f} {(ok + 1) / (n + 2):9.2f}   {Agent.CONFIDENCE.get(name)}")
