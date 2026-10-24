#!/usr/bin/env python3
"""Site log for the Any-Site-Upload workflow.

check   - before anything starts: warn (and stop) if a link's site failed before and never worked
append  - add record files (given as arguments, default logs/*.json) to site-log.jsonl on the config branch
summary - print a per-site table from a log file (or stdin)

The log is a plain JSON-lines file on the `config` branch, so no APK rebuild is needed to read it.
Writing it never fails the run: every problem here is only a warning.
"""
import base64
import glob
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GH_TOKEN", "")
BRANCH = "config"
PATH = "site-log.jsonl"
MAX_LINES = 3000          # oldest lines are dropped beyond this (file stays well under 1 MB)


def host_of(url):
    h = (urllib.parse.urlsplit(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def api(method, path, body=None, accept="application/vnd.github+json"):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/{path}", data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": accept,
                 "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def read_log():
    """Return (text, sha). ('', None) when the file does not exist yet."""
    q = f"contents/{PATH}?ref={BRANCH}"
    try:
        meta = json.loads(api("GET", q))
        raw = api("GET", q, accept="application/vnd.github.raw+json").decode("utf-8", "replace")
        return raw, meta.get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return "", None
        raise


def parse(text):
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def cmd_check():
    matrix = json.loads(os.environ.get("MATRIX") or "[]")
    force = (os.environ.get("FORCE") or "no").strip().lower() == "yes"
    try:
        text, _ = read_log()
    except Exception as e:
        print(f"Site log could not be read ({e}); skipping the check.")
        return 0

    stats = {}
    for r in parse(text):
        d = r.get("domain")
        if not d:
            continue
        s = stats.setdefault(d, {"success": 0, "bad": 0, "reason": ""})
        st = r.get("status")
        if st == "success":
            s["success"] += 1
        elif st in ("fail", "small"):
            s["bad"] += 1
            s["reason"] = r.get("reason") or st

    warn = {}
    for m in matrix:
        d = host_of(m["url"])
        s = stats.get(d)
        if s and s["bad"] and not s["success"]:
            warn[d] = s
    if not warn:
        print("Site history: no known problem for these links.")
        return 0

    lines = []
    for d, s in warn.items():
        print("SITE_WARNING " + json.dumps(
            {"domain": d, "fail": s["bad"], "success": s["success"], "last_reason": s["reason"]},
            ensure_ascii=False))
        lines.append(f"- **{d}**: {s['bad']} بار ناموفق، ۰ بار موفق. آخرین علت: {s['reason']}")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as fh:
            fh.write("### ⚠️ این سایت‌ها قبلاً فقط خطا داده‌اند\n\n" + "\n".join(lines) + "\n\n")
            fh.write("برای ادامه، دوباره اجرا کن و force=yes بگذار.\n")
    if force:
        print("force=yes: continuing although these sites failed before.")
        return 0
    names = ", ".join(warn)
    print(f"::error title=Site failed before::{names} - run again with force=yes to continue anyway")
    return 1


def cmd_append(paths=None):
    recs = []
    for p in (paths or sorted(glob.glob("logs/*.json"))):
        try:
            with open(p, encoding="utf-8") as fh:
                recs.append(json.load(fh))
        except Exception:
            pass
    if not recs:
        print("Nothing to log.")
        return 0
    new = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in recs]
    for attempt in range(1, 9):
        try:
            text, sha = read_log()
            lines = [l for l in text.splitlines() if l.strip()] + new
            lines = lines[-MAX_LINES:]
            body = {
                "message": f"site-log: +{len(new)} (run {os.environ.get('GITHUB_RUN_ID', '')})",
                "content": base64.b64encode(("\n".join(lines) + "\n").encode("utf-8")).decode(),
                "branch": BRANCH,
            }
            if sha:
                body["sha"] = sha
            api("PUT", f"contents/{PATH}", body)
            print(f"Logged {len(new)} record(s) to {PATH} on the {BRANCH} branch.")
            return 0
        except urllib.error.HTTPError as e:
            if e.code in (409, 422) and attempt < 8:
                time.sleep(random.uniform(1, 4))      # another run wrote at the same time
                continue
            print(f"::warning::site log could not be written: HTTP {e.code}")
            return 0
        except Exception as e:
            print(f"::warning::site log could not be written: {e}")
            return 0
    return 0


def cmd_summary(path=None):
    if path:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = sys.stdin.read()
    rows = {}
    for r in parse(text):
        d = r.get("domain") or "?"
        s = rows.setdefault(d, {"n": {"success": 0, "small": 0, "fail": 0, "unknown": 0},
                                "last": "", "reason": ""})
        st = r.get("status") or "unknown"
        s["n"][st if st in s["n"] else "unknown"] += 1
        s["last"] = (r.get("ts") or "")[:10]
        if st in ("fail", "small"):
            s["reason"] = (r.get("reason") or "")[:50]
    print(f"{'site':<30}{'ok':>4}{'small':>6}{'fail':>5}{'?':>3}  {'last':<11}reason")
    for d, s in sorted(rows.items(), key=lambda kv: (-kv[1]["n"]["success"], kv[0])):
        n = s["n"]
        print(f"{d[:29]:<30}{n['success']:>4}{n['small']:>6}{n['fail']:>5}{n['unknown']:>3}  "
              f"{s['last']:<11}{s['reason']}")
    if not rows:
        print("(the log is empty)")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "check":
        sys.exit(cmd_check())
    if cmd == "append":
        sys.exit(cmd_append(sys.argv[2:]))
    if cmd == "summary":
        sys.exit(cmd_summary(sys.argv[2] if len(sys.argv) > 2 else None))
    print("usage: site_log.py check | append | summary [file]")
    sys.exit(2)
