"""Live job list for a running workflow (Lab). No Kivy, no widgets.

wait(host, run_id, on_status) polls the run and its jobs through host.gh.request and sends
on_status a short text like the Actions tab: one line per job, plus the steps of the job that is
running (or the failed steps of a failed job). It returns the run's conclusion, like host.gh.wait.
When the run cannot be read it falls back to host.gh.wait, so a Lab tool is never worse than before.

The status line that shows the text must be tall: host.status(height=560).
"""
import time
from datetime import datetime, timezone

MAX_LINES = 12
_DONE = {"success": "[OK]", "failure": "[FAIL]", "cancelled": "[STOP]", "skipped": "[SKIP]",
         "timed_out": "[TIME]", "neutral": "[OK]"}


def _tag(status, conclusion):
    if status == "completed":
        return _DONE.get(conclusion or "", "[--]")
    if status == "in_progress":
        return "[RUN]"
    return "[WAIT]"


def _secs(start, end):
    try:
        t0 = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        t1 = (datetime.strptime(end, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
              if end else datetime.now(timezone.utc))
        return max(0, int((t1 - t0).total_seconds()))
    except Exception:
        return None


def _dur(item):
    n = _secs(item.get("started_at"), item.get("completed_at")) if item.get("started_at") else None
    if n is None:
        return ""
    return " (%ds)" % n if n < 60 else " (%dm%02ds)" % (n // 60, n % 60)


def _steps(job):
    steps = list(job.get("steps") or [])
    if job.get("status") == "in_progress":
        if len(steps) <= 6:
            return steps
        at = next((i for i, s in enumerate(steps) if s.get("status") == "in_progress"), len(steps) - 1)
        return steps[max(0, at - 2): at + 3]
    if job.get("conclusion") == "failure":
        return [s for s in steps if s.get("conclusion") == "failure"][:3]
    return []


def format_text(run_id, run, jobs, max_lines=MAX_LINES):
    """The text for one poll: header, then a line per job (and the steps worth seeing)."""
    state = str((run or {}).get("status") or "queued").replace("_", " ")
    if (run or {}).get("status") == "completed":
        state = "finished: %s" % ((run or {}).get("conclusion") or "?")
    lines = ["Run %s - %s" % (run_id, state)]
    if not jobs:
        lines.append("Waiting for a runner...")
    for job in jobs or []:
        lines.append("%s %s%s" % (_tag(job.get("status"), job.get("conclusion")),
                                  str(job.get("name") or "job")[:34], _dur(job)))
        for step in _steps(job):
            lines.append("    %s %s" % (_tag(step.get("status"), step.get("conclusion")),
                                        str(step.get("name") or "step")[:30]))
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + ["..."]
    return "\n".join(lines)


def _fallback(host, run_id, say, stop_event):
    kw = {"stop_event": stop_event} if stop_event is not None else {}
    return host.gh.wait(run_id, on_status=lambda s: say("%s..." % s), **kw)


def wait(host, run_id, on_status=None, stop_event=None, limit=7200):
    """Returns the conclusion of the run (success, failure, cancelled, ...). Blocking: call it inside
    host.background()."""
    say = on_status or (lambda text: None)
    start = time.time()
    failures = 0
    seen = False
    last = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return "cancelled_locally"
        try:
            run = host.gh.request("GET", "/actions/runs/%s" % run_id).json()
            jobs = []
            try:
                jobs = host.gh.request("GET", "/actions/runs/%s/jobs?per_page=30" % run_id).json().get("jobs") or []
            except Exception as e:
                host.log("jobs read:", e)
            failures = 0
            seen = True
        except Exception as e:
            failures += 1
            if not seen or failures >= 5:
                host.log("run read failed, using the plain wait:", e)
                return _fallback(host, run_id, say, stop_event)
            time.sleep(6)
            continue
        text = format_text(run_id, run, jobs)
        if text != last:
            say(text)
            last = text
        if run.get("status") == "completed":
            return run.get("conclusion") or "unknown"
        if time.time() - start > limit:
            return "timed_out"
        time.sleep(5 if time.time() - start < 120 else 10)


def selftest():
    jobs = [{"name": "extract", "status": "in_progress", "started_at": "2026-11-18T08:00:00Z",
             "steps": [{"name": "Set up job", "status": "completed", "conclusion": "success"},
                       {"name": "Run yt-dlp", "status": "in_progress"}, {"name": "Upload", "status": "queued"}]},
            {"name": "notify", "status": "queued", "steps": []}]
    t = format_text(5, {"status": "in_progress"}, jobs)
    assert t.splitlines()[0] == "Run 5 - in progress" and "[RUN] extract" in t and "[RUN] Run yt-dlp" in t, t
    assert "[WAIT] notify" in t
    assert "Waiting for a runner" in format_text(5, {"status": "queued"}, [])
    bad = [{"name": "j", "status": "completed", "conclusion": "failure",
            "steps": [{"name": "fine", "status": "completed", "conclusion": "success"},
                      {"name": "boom", "status": "completed", "conclusion": "failure"}]}]
    t = format_text(6, {"status": "completed", "conclusion": "failure"}, bad)
    assert "finished: failure" in t and "[FAIL] boom" in t and "fine" not in t, t
    assert len(format_text(1, {}, [{"name": "x%d" % i} for i in range(40)]).splitlines()) == MAX_LINES

    class _R:
        def __init__(self, d):
            self.d = d

        def json(self):
            return self.d

    class _Gh:
        n = 0

        def request(self, m, path):
            if path.endswith("/jobs?per_page=30"):
                return _R({"jobs": jobs})
            self.n += 1
            return _R({"status": "completed" if self.n > 1 else "in_progress", "conclusion": "success"})

    class _H:
        gh = _Gh()

        def log(self, *a):
            pass
    got = []
    real = time.sleep
    time.sleep = lambda s: None
    try:
        assert wait(_H(), 7, got.append) == "success" and len(got) == 2, got
    finally:
        time.sleep = real

    class _Bad:
        def request(self, *a):
            raise RuntimeError("no")

        def wait(self, run_id, on_status=None, stop_event=None):
            on_status("queued")
            return "failure"

    class _H2:
        gh = _Bad()

        def log(self, *a):
            pass
    got = []
    assert wait(_H2(), 1, got.append) == "failure" and got == ["queued..."], got
    return "ok"


if __name__ == "__main__":
    print(selftest())
