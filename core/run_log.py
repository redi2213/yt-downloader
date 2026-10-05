"""Reading a GitHub Actions job log: cutting out the part that belongs to one
step and showing its last lines. Pure text processing - no Kivy, no network.

Every log line starts with a UTC timestamp ('2026-10-04T17:41:05.1234567Z '),
and every step has started_at / completed_at, so a step's lines are simply
the lines whose timestamp falls inside its time range (to the second).
"""
import re

_TS_RE = re.compile(r"^\ufeff?(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d+)?Z ?")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _display(body):
    """Cleans one log line for display, or None to hide it."""
    body = _ANSI_RE.sub("", body).rstrip()
    if not body.strip():
        return None
    if body.startswith("##[endgroup]") or body.startswith("##[debug]"):
        return None
    if body.startswith("##[group]"):
        return "> " + body[len("##[group]"):]
    if body.startswith("##[error]"):
        return "ERROR: " + body[len("##[error]"):]
    if body.startswith("##[warning]"):
        return "WARNING: " + body[len("##[warning]"):]
    return body


def parse_log(text):
    """Log text -> list of (timestamp 'YYYY-MM-DDTHH:MM:SS' or None, text),
    hidden/empty lines removed. A line without its own timestamp (rare) takes
    the previous line's."""
    if not text:
        return []
    entries = []
    last_ts = None
    for raw in re.split(r"\r\n|\n|\r", text):
        m = _TS_RE.match(raw)
        if m:
            last_ts = m.group(1)
            body = raw[m.end():]
        else:
            body = raw.lstrip("\ufeff")
        shown = _display(body)
        if shown is not None:
            entries.append((last_ts, shown))
    return entries


def lines_for_step(entries, started_at, completed_at):
    """Lines logged while the step was running. A step that hasn't started
    has none; one that hasn't finished runs up to 'now' (no upper bound)."""
    if not started_at:
        return []
    lo = started_at[:19]
    hi = completed_at[:19] if completed_at else "9999-12-31T23:59:59"
    return [text for ts, text in entries if ts is not None and lo <= ts <= hi]


def _is_step_start(text):
    """First line of a step's own log: 'Run <command or action>' group,
    'Post job cleanup.' (post steps) or 'Cleaning up orphan processes'
    (the final 'Complete job' step). 'Set up job' has no marker - it is
    simply the beginning of the log."""
    return (text.startswith("> Run ") or text == "Post job cleanup."
            or text == "Cleaning up orphan processes")


def step_segments(entries):
    """The log cut into one list of lines per step that produced output, in
    order: segment 0 is 'Set up job'."""
    starts = [i for i, (_ts, text) in enumerate(entries) if _is_step_start(text)]
    bounds = [0] + starts + [len(entries)]
    return [[text for _ts, text in entries[a:b]] for a, b in zip(bounds, bounds[1:])]


def step_lines(entries, steps, number):
    """Lines of step ``number`` (GitHub's step number) of a job.

    Steps that were skipped (an ``if:`` that was false) have no log, so the
    segments line up with the started, non-skipped steps in order. When that
    doesn't add up (counts differ for a finished job, or the log has more
    sections than steps) the timestamp range is used instead - that can
    include a second of the neighbouring step but is never badly wrong."""
    active = [s for s in steps if s.get("started_at") and s.get("conclusion") != "skipped"]
    target = next((s for s in steps if s.get("number") == number), None)
    if target is None or target not in active:
        return []
    segments = step_segments(entries)
    job_done = all(s.get("status") == "completed" for s in steps)
    consistent = (len(segments) == len(active)) if job_done else (len(segments) <= len(active))
    if consistent:
        idx = active.index(target)
        return segments[idx] if idx < len(segments) else []
    return lines_for_step(entries, target.get("started_at"), target.get("completed_at"))


def tail(lines, count=15):
    return lines[-count:] if count > 0 else []


def last_line(entries):
    """The most recent displayable line of the whole job log, or None."""
    for _ts, text in reversed(entries):
        if not text.startswith("> "):
            return text
    return entries[-1][1] if entries else None


def clip(text, max_len=140):
    return text if len(text) <= max_len else text[: max_len - 3] + "..."
