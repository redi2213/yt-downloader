#!/usr/bin/env python3
"""YouTube batch, done entirely on GitHub: for every link it runs list-formats,
picks the quality, then runs download.yml - at most MAX_PARALLEL videos at the
same time. The app (and the phone) can be closed while this runs.

Environment: GH_TOKEN, GITHUB_REPOSITORY, REF, URLS (one link per line),
HEIGHT (99999 = best), HDR, AUDIO_ONLY, MAX_PARALLEL, STORAGE, ARVAN_BUCKET.

For every video it prints one line, which the app reads back from the log:
    RESULT|<link>|<download run id>|ok
    RESULT|<link>|<download run id, may be empty>|failed: <reason>

The format picking below is the same as the app's (api/github/logs.py
parse_formats + services/download_service.py pick_format): keep them in sync.
"""
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

REPO = os.environ["GITHUB_REPOSITORY"]
REF = os.environ.get("REF") or os.environ.get("GITHUB_REF_NAME") or "main"
POLL = 10           # seconds between status checks of a child run
DISPATCH_GAP = 1.5  # seconds between two dispatches (GitHub dislikes bursts)


def _int(name, default, low, high):
    try:
        value = int(str(os.environ.get(name, "")).strip())
    except ValueError:
        value = default
    return max(low, min(high, value))


HEIGHT = _int("HEIGHT", 99999, 1, 99999)
MAX_PARALLEL = _int("MAX_PARALLEL", 6, 1, 20)
HDR = os.environ.get("HDR", "false").strip().lower() == "true"
AUDIO_ONLY = os.environ.get("AUDIO_ONLY", "false").strip().lower() == "true"
STORAGE = os.environ.get("STORAGE", "").strip()
ARVAN_BUCKET = os.environ.get("ARVAN_BUCKET", "").strip()

_inflight = set()
_dispatch_lock = threading.Lock()
_last_dispatch = [0.0]


def log(text):
    print(text, flush=True)


def gh(*args, tries=4):
    """Runs the gh CLI, trying again when GitHub is busy."""
    last = ""
    for n in range(tries):
        p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
        if p.returncode == 0:
            return p.stdout
        last = (p.stderr or p.stdout or "").strip()
        time.sleep(3 * (n + 1))
    raise RuntimeError(last[:200] or "gh failed")


def dispatch(workflow, inputs):
    with _dispatch_lock:
        wait = DISPATCH_GAP - (time.monotonic() - _last_dispatch[0])
        if wait > 0:
            time.sleep(wait)
        args = ["workflow", "run", workflow, "--ref", REF, "-R", REPO]
        for key, value in inputs.items():
            if value != "":
                args += ["-f", f"{key}={value}"]
        gh(*args)
        _last_dispatch[0] = time.monotonic()


def find_run(workflow, token):
    """The run whose title carries ``token`` (the workflows put job_id in run-name)."""
    for _ in range(30):
        out = gh("api", f"repos/{REPO}/actions/workflows/{workflow}/runs?per_page=30")
        for run in json.loads(out).get("workflow_runs", []):
            if token in f"{run.get('display_title') or ''} {run.get('name') or ''}":
                return run["id"]
        time.sleep(2)
    return None


def wait_run(run_id):
    _inflight.add(run_id)
    try:
        while True:
            run = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}"))
            if run.get("status") == "completed":
                return run.get("conclusion") or "unknown"
            time.sleep(POLL)
    finally:
        _inflight.discard(run_id)


def first_job_log(run_id):
    jobs = json.loads(gh("api", f"repos/{REPO}/actions/runs/{run_id}/jobs?per_page=5")).get("jobs", [])
    if not jobs:
        return ""
    return gh("api", f"repos/{REPO}/actions/jobs/{jobs[0]['id']}/logs")


# ---- quality picking (same rules as the app) --------------------------------
_PROTO_RE = re.compile(r"\b(sabr|dash|https)\s*\|")


def parse_formats(log_text):
    """[(format_id, label)] - one per video quality + codec, first sabr row kept."""
    order, best = [], {}
    for line in log_text.splitlines():
        if "video only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts:
            continue
        m = re.search(r"(\d+p\d*)( HDR)?", clean)
        if not m:
            continue
        label = m.group(0)
        codec = re.search(r"\b(avc1|vp9|vp09|av01|hev1|hvc1)\b", clean)
        proto = _PROTO_RE.search(clean)
        is_sabr = bool(proto and proto.group(1) == "sabr")
        key = (label, codec.group(1) if codec else None)
        if key not in best:
            order.append(key)
            best[key] = (is_sabr, parts[0], label)
        elif is_sabr and not best[key][0]:
            best[key] = (is_sabr, parts[0], label)
    return [(best[k][1], best[k][2]) for k in order]


def pick_format(formats, target_height, want_hdr):
    candidates = []
    for fmt_id, label in formats:
        digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
        if digits:
            candidates.append((fmt_id, int(digits), "HDR" in label))
    if not candidates:
        return None
    if want_hdr:
        pool = [c for c in candidates if c[2]] or candidates
    else:
        pool = [c for c in candidates if not c[2]] or candidates
    if target_height >= 99999:
        return max(pool, key=lambda c: c[1])[0]
    return sorted(pool, key=lambda c: abs(c[1] - target_height))[0][0]


# ---- one video --------------------------------------------------------------
def choose_format(url):
    """(format id, None) or (None, why not). Tries list-formats twice."""
    reason = "list-formats failed"
    for _attempt in range(2):
        token = uuid.uuid4().hex[:12]
        dispatch("list-formats.yml", {"video_url": url, "job_id": token})
        run_id = find_run("list-formats.yml", token)
        if run_id is None:
            reason = "could not find the list-formats run"
            continue
        conclusion = wait_run(run_id)
        if conclusion != "success":
            reason = f"list-formats {conclusion}"
            continue
        picked = pick_format(parse_formats(first_job_log(run_id)), HEIGHT, HDR)
        if picked:
            return picked, None
        reason = "no matching format"
    return None, reason


def one_video(url):
    run_id = ""
    try:
        if AUDIO_ONLY:
            fmt = "bestaudio"
        else:
            fmt, why = choose_format(url)
            if not fmt:
                return url, run_id, f"failed: {why}"
        token = uuid.uuid4().hex[:12]
        dispatch("download.yml", {
            "video_url": url, "format_id": fmt,
            "audio_only": "true" if AUDIO_ONLY else "false",
            "job_id": token, "storage": STORAGE, "arvan_bucket": ARVAN_BUCKET,
        })
        found = find_run("download.yml", token)
        if found is None:
            return url, run_id, "failed: could not find the download run"
        run_id = found
        conclusion = wait_run(found)
        if conclusion != "success":
            return url, run_id, f"failed: download {conclusion}"
        return url, run_id, "ok"
    except Exception as e:  # one video must never stop the others
        return url, run_id, f"failed: {str(e)[:80]}"


def cancel_everything(_signum=None, _frame=None):
    log("Cancelled: stopping the videos that are still running...")
    for run_id in list(_inflight):
        subprocess.run(["gh", "run", "cancel", str(run_id), "-R", REPO], capture_output=True)
    os._exit(1)


def main():
    urls = []
    for item in re.split(r"[\s,]+", os.environ.get("URLS", "")):
        if item.startswith("http") and item not in urls:
            urls.append(item)
    if not urls:
        log("::error::No links were given.")
        return 1
    signal.signal(signal.SIGINT, cancel_everything)
    signal.signal(signal.SIGTERM, cancel_everything)
    log(f"{len(urls)} video(s), {MAX_PARALLEL} at a time, "
        f"{'audio only' if AUDIO_ONLY else ('best' if HEIGHT >= 99999 else str(HEIGHT) + 'p')}"
        f"{', HDR' if HDR else ''}")

    results = []
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        for url, run_id, status in pool.map(one_video, urls):
            log(f"RESULT|{url}|{run_id}|{status}")
            results.append((url, run_id, status))

    ok = sum(1 for r in results if r[2] == "ok")
    log(f"Done: {ok}/{len(results)} downloaded.")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### {ok}/{len(results)} downloaded\n\n| Video | Run | Result |\n|---|---|---|\n")
            for url, run_id, status in results:
                link = f"[{run_id}](https://github.com/{REPO}/actions/runs/{run_id})" if run_id else "-"
                f.write(f"| {url} | {link} | {status} |\n")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
