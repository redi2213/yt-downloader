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


_SIZE_RE = re.compile(r"(?:~\s*)?(\d+(?:\.\d+)?)\s*(KiB|MiB|GiB)")
_PROTO_RE = re.compile(r"\b(sabr|dash|https)\s*\|")
_AUDIO_RE = re.compile(r"\|\s*audio only\s+(\S+)\s+(\d+(?:\.\d+)?)k")
_PLAIN_ID_RE = re.compile(r"\d+-\d+")

_UNIT_TO_MIB = {"KiB": 1 / 1024, "MiB": 1.0, "GiB": 1024.0}

# yt-dlp acodec name -> short label shown next to the video codec
_AUDIO_SHORT = {"opus": "opus", "ac-3": "ac3", "ec-3": "eac3"}


def _size_mib(clean: str):
    """Size of the row in MiB (the FILESIZE column), or None."""
    m = _SIZE_RE.search(clean)
    if not m:
        return None
    return float(m.group(1)) * _UNIT_TO_MIB[m.group(2)]


def _format_mib(mib: float) -> str:
    if mib >= 1024:
        return f"{mib / 1024:.2f}GiB"
    return f"{mib:.2f}MiB"


def _short_audio(acodec: str) -> str:
    if acodec.startswith("mp4a"):
        return "aac"
    return _AUDIO_SHORT.get(acodec, acodec)


def _parse_audio_rows(log_text: str):
    """Audio-only rows that the Download workflow may pick: plain
    ``<itag>-<n>`` ids (no -drc / -vb / -dashy variants) on the sabr protocol."""
    rows = []
    for line in log_text.splitlines():
        if "audio only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts or not _PLAIN_ID_RE.fullmatch(parts[0]):
            continue
        proto = _PROTO_RE.search(clean)
        if not proto or proto.group(1) != "sabr":
            continue
        am = _AUDIO_RE.search(clean)
        if not am:
            continue
        rows.append({
            "id": parts[0],
            "acodec": am.group(1),
            "abr": float(am.group(2)),
            "mib": _size_mib(clean),
        })
    return rows


def _pick_audio(height: int, rows):
    """Same rule as download.yml (keep the two in sync):
      >= 1080p -> highest-bitrate AC-3 / E-AC-3 (AC-3 wins a tie); else highest
                  Opus; else highest AAC
      720p     -> highest AAC
      < 720p   -> lowest AAC
    """
    if not rows:
        return None
    aac = [r for r in rows if r["acodec"].startswith("mp4a")]
    opus = [r for r in rows if r["acodec"] == "opus"]
    surround = [r for r in rows if r["acodec"] in ("ac-3", "ec-3")]
    choice = None
    if height >= 1080:
        if surround:
            choice = max(surround, key=lambda r: (r["abr"], r["acodec"] == "ac-3"))
        elif opus:
            choice = max(opus, key=lambda r: r["abr"])
        elif aac:
            choice = max(aac, key=lambda r: r["abr"])
    elif height >= 720:
        if aac:
            choice = max(aac, key=lambda r: r["abr"])
    else:
        if aac:
            choice = min(aac, key=lambda r: r["abr"])
    if choice is None:
        choice = (max if height >= 720 else min)(rows, key=lambda r: r["abr"])
    return choice


def parse_formats(log_text: str):
    """Returns (format_id, label, size_label, codec_label) tuples, one per
    video quality + codec, skipping storyboards.

    - Duplicates are removed: yt-dlp lists every quality several times
      (-0 / -1 clients, dash, https); the first sabr row is kept.
    - ``size_label`` is video size + the size of the audio the Download
      workflow will pick for that quality (see ``_pick_audio``).
    - ``codec_label`` is the video codec family plus the short audio codec,
      e.g. ``avc1+aac`` (or just the video codec if no audio row is found).
    """
    audio_rows = _parse_audio_rows(log_text)

    order = []          # keys in first-seen order
    best = {}           # key -> (is_sabr, fmt_id, label, video_mib, codec_label)
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
        label = m.group(0)
        # The video codec column looks like "avc1.4d4015", "vp9", or
        # "av01.0.00M.08" - grab just the codec family name for a short label.
        codec_match = re.search(r"\b(avc1|vp9|vp09|av01|hev1|hvc1)\b", clean)
        codec_label = codec_match.group(1) if codec_match else None
        proto = _PROTO_RE.search(clean)
        is_sabr = bool(proto and proto.group(1) == "sabr")
        key = (label, codec_label)
        if key not in best:
            order.append(key)
            best[key] = (is_sabr, fmt_id, label, _size_mib(clean), codec_label)
        elif is_sabr and not best[key][0]:
            # a sabr row beats a dash/https duplicate seen earlier
            best[key] = (is_sabr, fmt_id, label, _size_mib(clean), codec_label)

    results = []
    for key in order:
        _is_sabr, fmt_id, label, video_mib, codec_label = best[key]
        digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
        height = int(digits) if digits else 0
        audio = _pick_audio(height, audio_rows)

        total = video_mib
        if audio is not None and audio["mib"] is not None and video_mib is not None:
            total = video_mib + audio["mib"]
        size_label = _format_mib(total) if total is not None else None

        if audio is not None:
            audio_tag = _short_audio(audio["acodec"])
            codec_label = f"{codec_label}+{audio_tag}" if codec_label else audio_tag
        results.append((fmt_id, label, size_label, codec_label))
    return results
