#!/usr/bin/env python3
"""Refresh the default v2ray configs (run by lab-refresh-configs.yml).

Reads the subscription, starts every node in Xray, keeps the fastest few that really connect
(two probe requests must pass) and writes them as share links to working_configs.txt.
Only "protocol host:port" is printed, never keys or passwords.
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xray_setup as xs  # noqa: E402

DEFAULT_SUB = "https://raw.githubusercontent.com/patterniha/Free-Configs/main/configs.txt"
MAX_TEST = 120
WORKERS = 8
BASE_PORT = 21000


def settings():
    cfg = {}
    for p in ("labcfg/lab/default_sources.json", "lab/default_sources.json"):
        if os.path.isfile(p):
            try:
                cfg = json.load(open(p, encoding="utf-8"))
            except Exception:
                cfg = {}
            break
    sub = (os.environ.get("SUBSCRIPTION") or "").strip() or cfg.get("subscription") or DEFAULT_SUB
    try:
        n = int((os.environ.get("MAX_CONFIGS") or "").strip() or cfg.get("max_configs") or 5)
    except ValueError:
        n = 5
    return sub.split("#")[0], max(1, n)


def check(i, ob):
    port = BASE_PORT + i
    p = xs.start(xs.wrap(ob, port), port, f"c{i}")
    if p is None:
        return None
    try:
        ok1, s1 = xs.probe(port)
        if not ok1:
            return None
        ok2, s2 = xs.probe(port)
        if not ok2:
            return None
        return (s1 + s2) / 2
    finally:
        p.kill()


def main():
    sub, keep = settings()
    print(f"Subscription: {sub.split('?')[0]}  (keep {keep})", flush=True)
    try:
        links, skipped = xs.links_from_text(xs.fetch(sub))
    except Exception as e:
        xs.warn(f"could not read the subscription ({type(e).__name__}) - old list kept")
        return 0
    if skipped:
        print("Not supported, skipped:", ", ".join(sorted(skipped)))
    seen, nodes = set(), []
    for l in links:
        if l in seen:
            continue
        seen.add(l)
        try:
            ob, host, port = xs.to_outbound(l)
        except Exception as e:
            print(f"skip a node: {str(e)[:60]}")
            continue
        nodes.append((l, ob, f"{ob['protocol']} {host}:{port}"))
    nodes = nodes[:MAX_TEST]
    print(f"{len(nodes)} usable nodes to test", flush=True)
    if not nodes:
        xs.warn("no usable node - old list kept")
        return 0
    if not xs.install_xray():
        xs.warn("could not download Xray - old list kept")
        return 0

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        results = list(ex.map(lambda t: check(t[0], t[1][1]), enumerate(nodes)))
    good = []
    for (l, _ob, label), secs in zip(nodes, results):
        if secs is not None:
            good.append((secs, l, label))
    good.sort()
    print(f"{len(good)}/{len(nodes)} nodes connect ({time.time() - t0:.0f}s)", flush=True)
    for secs, _l, label in good[:keep]:
        print(f"  keep: {label}  ({secs:.1f}s)")
    if not good:
        xs.warn("no node connected - old list kept")
        return 0
    with open("working_configs.txt", "w", encoding="utf-8") as f:
        for _s, l, _lab in good[:keep]:
            f.write(l + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
