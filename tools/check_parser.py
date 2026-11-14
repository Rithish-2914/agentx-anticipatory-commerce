"""Compare the parser's reading of each full dev request with the gold filters."""
import json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agentx.parser import Parser
P = Parser()
bad = 0; fc = Counter(); rows = 0
for l in open(ROOT / (sys.argv[1] if len(sys.argv) > 1 else "dev.jsonl"), encoding="utf-8"):
    r = json.loads(l); g = r["filters"]; rows += 1
    f = P.parse(r["words"]).filters
    diff = {k: (f[k], g[k]) for k in g if str(f[k]).lower() != str(g[k]).lower()}
    if diff:
        bad += 1; fc.update(diff.keys())
        print(r["id"][-3:], r["text"], diff)
print(f"{rows - bad}/{rows} fully correct", dict(fc))
