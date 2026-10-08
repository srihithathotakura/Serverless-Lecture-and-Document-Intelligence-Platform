#!/usr/bin/env python3
"""API latency test (stdlib only).
usage: API_URL=https://xxx.execute-api.us-east-1.amazonaws.com ID_TOKEN=<cognito id token> python3 infra/perf/latency_test.py
Runs 50 sequential GET /documents, 5 parallel batches of 10, and 5 POST /ask calls."""
import json
import os
import statistics
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

URL = os.environ["API_URL"].rstrip("/")
TOKEN = os.environ["ID_TOKEN"]
HDR = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def call(method, path, body=None):
    req = urllib.request.Request(URL + path, method=method, headers=HDR,
                                 data=json.dumps(body).encode() if body else None)
    t = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    return (time.perf_counter() - t) * 1000, code


def report(name, rows):
    ms = sorted(r[0] for r in rows)
    errs = sum(1 for r in rows if r[1] >= 400)
    p95 = ms[min(len(ms) - 1, round(0.95 * len(ms)) - 1)]
    print(f"| {name} | {len(ms)} | {statistics.median(ms):.0f} | {p95:.0f} | {max(ms):.0f} | {errs} |")


print("| test | calls | p50 ms | p95 ms | max ms | errors |\n|---|---|---|---|---|---|")
call("GET", "/documents")  # warm up (Lambda cold start)
report("GET /documents sequential", [call("GET", "/documents") for _ in range(50)])
par = []
with ThreadPoolExecutor(10) as ex:
    for _ in range(5):
        par += list(ex.map(lambda _: call("GET", "/documents"), range(10)))
report("GET /documents 5 x 10 parallel", par)
report("POST /ask (includes model call)", [call("POST", "/ask", {"question": "what is this lecture about"}) for _ in range(5)])
