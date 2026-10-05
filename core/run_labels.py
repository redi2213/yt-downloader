"""Human-friendly names for GitHub Actions runs: which tool a workflow file
belongs to, a short title taken from the run's name, and a one-word status.
Pure text helpers - no Kivy, no network.
"""
import re
from urllib.parse import urlparse

# workflow file -> tool name shown in lists
TOOL_LABELS = {
    "download.yml": "YouTube download",
    "list-formats.yml": "YouTube qualities",
    "list-playlist.yml": "YouTube playlist",
    "upload-file.yml": "Upload",
    "zip-release.yml": "Zip",
    "download-anything.yml": "Download anything",
    "aparat-download.yml": "Aparat",
    "telegram-download.yml": "Telegram",
    "cleanup-releases.yml": "Cleanup",
    "build-apk.yml": "Build APK",
}

_URL_RE = re.compile(r"https?://[^\s\]]+", re.IGNORECASE)


def tool_label(workflow_file):
    if not workflow_file:
        return "?"
    if workflow_file in TOOL_LABELS:
        return TOOL_LABELS[workflow_file]
    return re.sub(r"\.ya?ml$", "", workflow_file)


def short_title(name, max_len=34):
    """The link inside a run's name ('Download https://youtu.be/abc?x=1 [..]')
    as 'youtu.be/abc?x=1', shortened. '' when the name has no link (plain
    workflow names add nothing the tool label doesn't already say)."""
    m = _URL_RE.search(name or "")
    if not m:
        return ""
    parsed = urlparse(m.group(0))
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    rest = parsed.path.strip("/")
    if parsed.query:
        rest = f"{rest}?{parsed.query}" if rest else f"?{parsed.query}"
    text = host + (f"/{rest}" if rest else "")
    if len(text) > max_len:
        text = text[: max_len - 3] + "..."
    return text


def status_word(status, conclusion=None):
    """One short word for a run or step. Returns (word, kind) where kind is
    one of ok / fail / running / waiting / other, used for colouring."""
    if status == "completed" or conclusion:
        if conclusion == "success":
            return "OK", "ok"
        if conclusion in ("failure", "timed_out", "startup_failure"):
            return "FAILED", "fail"
        if conclusion == "cancelled":
            return "cancelled", "other"
        if conclusion == "skipped":
            return "skipped", "other"
        return (conclusion or "done"), "other"
    if status == "in_progress":
        return "RUNNING", "running"
    if status in ("queued", "waiting", "pending", "requested"):
        return "waiting", "waiting"
    return (status or "unknown"), "other"


_MARKUP_COLORS = {
    "ok": "66dd77", "fail": "ff6666", "running": "ffcc44",
    "waiting": "aaaaaa", "other": "aaaaaa",
}


def escape_markup(text):
    """Escapes text for a Kivy Label with markup=True."""
    return (text or "").replace("&", "&amp;").replace("[", "&bl;").replace("]", "&br;")


def progress_markup(job, now=None):
    """The steps of a job as coloured Kivy-markup lines:
    'Download - RUNNING 12s'. Skipped steps are left out. Returns
    (text, number_of_lines)."""
    from core import timeutil
    lines = []
    for step in job.get("steps", []):
        if step.get("conclusion") == "skipped":
            continue
        word, kind = status_word(step.get("status"), step.get("conclusion"))
        duration = ""
        if step.get("started_at"):
            duration = timeutil.duration_text(step.get("started_at"), step.get("completed_at"), now=now)
        name = step.get("name") or "?"
        if len(name) > 34:
            name = name[:31] + "..."
        extra = f" {duration}" if duration else ""
        lines.append(f"{escape_markup(name)} - [color={_MARKUP_COLORS[kind]}]{word}[/color]{extra}")
    return "\n".join(lines), len(lines)
