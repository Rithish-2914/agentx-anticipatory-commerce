"""One-time Rezolve Labs setup: create a knowledge base, upload catalogue.csv, wait until ready.

    set REZOLVE_API_KEY=...            (PowerShell: $env:REZOLVE_API_KEY="...")
    python tools/rezolve_setup.py
    -> prints REZOLVE_KB_ID to set; then `python evaluate.py --agent my_agent.py` uses Rezolve
       semantic product search for every search (each call counted with tools.record_search()).
"""
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path

API = os.environ.get("REZOLVE_API", "https://api.rezolvelabs.com/api/v1")
ROOT = Path(__file__).resolve().parent.parent


def call(method, path, key, body=None, files=None):
    headers = {"X-API-KEY": key}
    data = None
    if files:
        boundary = uuid.uuid4().hex
        name, content = files
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
                f"Content-Type: text/csv\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    key = os.environ.get("REZOLVE_API_KEY")
    if not key:
        sys.exit("set REZOLVE_API_KEY first")
    kb = call("POST", "/developer-platform/knowledge-bases", key, {"name": "AgentX PS1 catalogue"})["data"]["id"]
    print("knowledge base", kb)
    doc = call("POST", f"/developer-platform/knowledge-bases/{kb}/documents", key,
               files=("catalogue.csv", (ROOT / "catalogue.csv").read_bytes()))["data"]["id"]
    print("document", doc)
    for _ in range(60):
        d = call("GET", f"/developer-platform/knowledge-bases/{kb}/documents/{doc}", key)["data"]
        print("status", d.get("status"))
        if d.get("status") == "ready":
            print("filters:", d.get("availableFilters"))
            break
        time.sleep(2)
    print(f"\nnow set REZOLVE_KB_ID={kb}")


if __name__ == "__main__":
    main()
