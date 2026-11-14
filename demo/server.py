"""Live demo: type (or pick) a shopping request and watch AgentX read it word by word.

    python demo/server.py            # then open http://localhost:8765
    python demo/server.py --port 9000

Standard library only. The page sends the request text; the server runs the real agent
(same code evaluate.py scores) one word at a time and returns what it saw and decided.
"""
import argparse
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentx.agent import Agent          # noqa: E402
from agentx.parser import Parser        # noqa: E402
from evaluate import Tools              # noqa: E402
from search import load_catalogue       # noqa: E402

PAGE = Path(__file__).with_name("index.html")
PARSER = Parser()
CATALOGUE = {p["product_id"]: p for p in load_catalogue()}

# showcase requests from dev.jsonl (the demo shows them; the agent never reads this file)
SHOWCASE = ["dev-0001", "dev-0003", "dev-0017", "dev-0134", "dev-0006", "dev-0022",
            "dev-0068", "dev-0130", "dev-0199", "dev-0040", "dev-0256", "dev-0113"]


def examples():
    rows = {}
    with open(ROOT / "dev.jsonl", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["id"] in SHOWCASE:
                tag = (r["tags"] or ["plain"])[0].replace("_", " ")
                rows[r["id"]] = {"id": r["id"], "text": r["text"], "tag": tag, "target": r["target"]}
    return [rows[i] for i in SHOWCASE if i in rows]


def run(text, target=None):
    tools = Tools()
    agent = Agent(tools, parser=PARSER)
    agent.start("demo")
    words = text.split()
    steps, commit_at = [], None
    t0 = time.perf_counter()
    for i, w in enumerate(words, 1):
        out = agent.observe(w) or {}
        step = dict(agent.last_step)
        step.update(word=w, index=i, filters=out.get("filters"), confidence=out.get("confidence"),
                    commit=out.get("commit"))
        if out.get("commit") and commit_at is None:
            commit_at = i
        steps.append(step)
    final = agent.finish()
    ms = (time.perf_counter() - t0) * 1000
    final_filters = PARSER.parse(words).filters
    product = CATALOGUE.get(final) if final else None
    n = len(words)
    unmet = []
    if product:
        for k in ("category", "colour", "size", "brand"):
            v = final_filters.get(k)
            if v is not None and str(product.get(k, "")).lower() != str(v).lower():
                unmet.append(k)
        if final_filters.get("max_price") is not None and product["price"] > final_filters["max_price"]:
            unmet.append("budget")
    return {
        "unmet": unmet,
        "words": words, "steps": steps, "final": final, "product": product,
        "final_filters": final_filters, "committed": agent.committed, "commit_at": commit_at,
        "words_early": (n - commit_at) if commit_at else 0, "n": n,
        "searches": tools.searches, "ms": round(ms, 2), "catalogue_size": len(CATALOGUE),
        "target": target, "correct": (final == target) if target else None,
        "commit_correct": (agent.committed == final) if agent.committed else None,
        "backend": agent.backend.name,
    }


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html")
        elif self.path == "/api/examples":
            self._send(200, examples())
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/run":
            return self._send(404, {"error": "not found"})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            text = str(body.get("text", "")).strip()[:500]
            if not text:
                return self._send(400, {"error": "empty request"})
            self._send(200, run(text, body.get("target")))
        except Exception as e:  # keep the demo alive on odd input
            self._send(500, {"error": str(e)})

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    print(f"AgentX demo on http://localhost:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
