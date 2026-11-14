"""Product search backends. Every call is counted through tools (local) or
tools.record_search() (Rezolve Labs), as the rules require.

LocalBackend    - the starter kit's search.py, through tools.search
RezolveBackend  - Rezolve Labs semantic product search over a knowledge base holding
                  catalogue.csv (set REZOLVE_API_KEY and REZOLVE_KB_ID)
"""
import json
import os
import urllib.request

REZOLVE_API = os.environ.get("REZOLVE_API", "https://api.rezolvelabs.com/api/v1")


class LocalBackend:
    name = "local"
    max_k = 200

    def __init__(self, tools):
        self.tools = tools

    def search(self, query, filters, k):
        f = {key: v for key, v in filters.items() if v is not None}
        return self.tools.search(query, f, k=k)


class RezolveBackend:
    """Semantic product search (Rezolve Labs). Filters map to KB columns; price uses price_lte."""
    name = "rezolve"
    max_k = int(os.environ.get("REZOLVE_MAX_K", 50))   # page size the API returns at most

    def __init__(self, tools, api_key, kb_id, timeout=10):
        self.tools, self.key, self.kb, self.timeout = tools, api_key, kb_id, timeout

    def _post(self, path, body):
        req = urllib.request.Request(
            f"{REZOLVE_API}{path}", data=json.dumps(body).encode(), method="POST",
            headers={"X-API-KEY": self.key, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            return json.loads(r.read().decode())

    def search(self, query, filters, k):
        f = {}
        for key, v in filters.items():
            if v is None:
                continue
            if key == "max_price":
                f["price_lte"] = v
            elif key == "min_price":
                f["price_gte"] = v
            else:
                f[key] = v
        self.tools.record_search()
        out = self._post("/product-discovery/search", {
            "knowledgeBaseId": self.kb, "query": query or filters.get("category") or "",
            "filters": f, "limit": k})
        data = out.get("data", out)
        items = data.get("results") or data.get("items") or data.get("products") or []
        hits = []
        for it in items:
            p = dict(it.get("metadata") or it.get("attributes") or {})
            p.update({kk: vv for kk, vv in it.items() if not isinstance(vv, (dict, list))})
            p["product_id"] = it.get("id") or p.get("product_id")
            if "price" in p:
                try:
                    p["price"] = int(float(p["price"]))
                except (TypeError, ValueError):
                    pass
            hits.append(p)
        return hits


def make_backend(tools):
    key, kb = os.environ.get("REZOLVE_API_KEY"), os.environ.get("REZOLVE_KB_ID")
    if key and kb:
        return RezolveBackend(tools, key, kb)
    return LocalBackend(tools)
