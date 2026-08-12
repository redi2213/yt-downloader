"""Fetching a run's job log and parsing yt-dlp's ``-F`` output out of it."""
import re

from api.github import client
from core.config import API_BASE


def get_run_log_text(run_id) -> str:
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = client.get(url)
    jobs = r.json().get("jobs", [])
    if not jobs:
        return ""
    job_id = jobs[0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = client.get(log_url)
    return r.text


def parse_formats(log_text: str):
    """Extracts (format_id, label, size_label, codec_label) tuples for every
    video-only format line in a yt-dlp ``-F`` log, skipping storyboards."""
    results = []
    for line in log_text.splitlines():
        if "video only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts:
            continue
        fmt_id = parts[0]
        m = re.search(r"(\d+p\d*)( HDR)?", clean)
        if not m:
            continue
        # yt-dlp's -F output includes an approximate size like "~ 15.50MiB" or
        # "77.16MiB" in one of the columns - grab it if present so it can be
        # shown next to the quality option.
        size_match = re.search(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)", clean)
        size_label = f"{size_match.group(1)}{size_match.group(2)}" if size_match else None
        # The video codec column looks like "avc1.4d4015", "vp9", or
        # "av01.0.00M.08" - grab just the codec family name for a short label.
        codec_match = re.search(r"\b(avc1|vp9|vp09|av01|hev1|hvc1)\b", clean)
        codec_label = codec_match.group(1) if codec_match else None
        results.append((fmt_id, m.group(0), size_label, codec_label))
    return results
