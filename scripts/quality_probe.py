"""What quality is a downloaded media file? (resolution, codec, fps ...)

Used by storage_publish.py for EVERY workflow that publishes video or audio, so the app can
show the quality next to the size - not only for the YouTube download. ffprobe is used when it is
on the runner; otherwise the quality that is written in the file name (``..._720p_30fps.mp4``) is
used, so a missing ffprobe never breaks a run. Never raises.

``probe_file(path)``   -> {"resolution", "codec", "fps", "bitrate_mbps", "duration_s", "size_bytes", "audio_only"}
                          (empty values left out; {} for a file that is not video / audio)
``probe_files(paths)`` -> {"by_file": {file name: short dict}, + the details of the first file at the top
                          level} - the block the release description keeps (``<!--ytb-quality:...-->``).
"""
import json
import os
import re
import shutil
import subprocess

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".ts", ".m4v", ".3gp", ".flv", ".wmv", ".mpg", ".mpeg"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".wma", ".mka"}
MAX_FILES = 100                       # entries kept in by_file (the release description is limited)
_SHORT_KEYS = ("resolution", "codec", "fps", "audio_only")


def _fps(rate):
    try:
        a, b = str(rate).split("/")
        return round(int(a) / int(b), 2) if int(b) else 0
    except Exception:
        return 0


def _from_name(name):
    """Quality written in the file name: '..._720p_30fps.mp4' -> ('720p', 30.0)."""
    m = re.search(r"(?<![0-9])(\d{3,4})p(?![a-z0-9])", name, re.I)
    f = re.search(r"(?<![0-9])(\d{2,3})fps", name, re.I)
    return (f"{int(m.group(1))}p" if m else ""), (float(f.group(1)) if f else 0)


_install_tried = False


def _ensure_ffprobe():
    """On a GitHub runner without ffprobe: install ffmpeg once (about 20 s). Anywhere else: nothing."""
    global _install_tried
    if shutil.which("ffprobe") or _install_tried or os.environ.get("GITHUB_ACTIONS") != "true":
        return bool(shutil.which("ffprobe"))
    _install_tried = True
    try:
        subprocess.run("sudo -n apt-get update -qq && sudo -n apt-get install -y -qq ffmpeg",
                       shell=True, capture_output=True, timeout=240)
    except Exception:
        pass
    return bool(shutil.which("ffprobe"))


def _ffprobe(path):
    if not _ensure_ffprobe():
        return {}
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,codec_name,width,height,r_frame_rate,bit_rate:format=duration,size,bit_rate",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60).stdout
        return json.loads(out or "{}")
    except Exception:
        return {}


def probe_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext not in VIDEO_EXT and ext not in AUDIO_EXT:
        return {}
    data = _ffprobe(path)
    streams = data.get("streams", []) or []
    fmt = data.get("format", {}) or {}
    video = next((s for s in streams if s.get("codec_type") == "video" and s.get("width")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    audio_only = ext in AUDIO_EXT or (video is None and audio is not None)

    q = {"audio_only": audio_only}
    if audio_only:
        q["codec"] = str((audio or {}).get("codec_name") or ext.lstrip(".")).upper()
    else:
        resolution, fps = _from_name(os.path.basename(path))
        if video:
            w, h = int(video.get("width") or 0), int(video.get("height") or 0)
            if w and h:
                resolution = f"{min(w, h)}p"           # a portrait 1080x1920 clip is 1080p
            fps = _fps(video.get("r_frame_rate")) or fps
            q["codec"] = str(video.get("codec_name") or "").upper()
        q["resolution"], q["fps"] = resolution, fps
    try:
        q["duration_s"] = round(float(fmt.get("duration") or 0), 1)
    except (TypeError, ValueError):
        pass
    try:
        q["size_bytes"] = int(fmt.get("size") or os.path.getsize(path))
    except (TypeError, ValueError, OSError):
        pass
    br = (video or audio or {}).get("bit_rate") or fmt.get("bit_rate")
    if str(br).isdigit():
        q["bitrate_mbps"] = round(int(br) / 1_000_000, 2)
    return {k: v for k, v in q.items() if v not in (0, 0.0, "", False, None) or k == "audio_only" and v}


def probe_files(paths):
    """The quality block for a list of files (see the module text). {} when none is media."""
    by_file, first = {}, {}
    for p in paths:
        q = probe_file(p)
        if not q:
            continue
        if not first:
            first = q
        if len(by_file) < MAX_FILES:
            by_file[os.path.basename(p)] = {k: q[k] for k in _SHORT_KEYS if k in q}
    if not by_file:
        return {}
    out = dict(first)
    out["by_file"] = by_file
    return out


def merge(base, probed):
    """``base`` (the YouTube workflow's own numbers) wins at the top level; ``probed`` adds by_file."""
    if not probed:
        return dict(base or {})
    out = dict(probed)
    out.update(base or {})
    out["by_file"] = probed.get("by_file", {})
    return out
