"""YouTube steps done by the phone itself with yt-dlp (no GitHub run).

* ``list_playlist(url)``  - the videos of a playlist (titles + links). A flat
  listing: no player requests, so it works without any YouTube tricks.
* ``list_qualities(url)`` - the qualities of one video as (format_id, label,
  size_label, codec_label), the same tuples the GitHub list gives.

Honest limit: the GitHub workflow uses extra tools the phone does not have
(a JavaScript runtime and a PO-token server), so the phone may see fewer
qualities or fail for some videos - the caller then falls back to GitHub.
Because the phone's format ids do not exist in the GitHub downloader, every
quality here uses the height rule ``bestvideo[height<=N]``, which the Download
workflow understands (the same one the Quick Download buttons send).

Blocking functions (call them from a background thread). Pure helpers, no Kivy.
"""

_PLAYER_CLIENT_TRIES = (["android_vr"], None)  # None = yt-dlp's own default clients


def _yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except Exception as e:
        raise RuntimeError("yt-dlp is not inside this build") from e


def _options(extra=None, clients=None):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 15,
        "retries": 2,
    }
    if clients:
        opts["extractor_args"] = {"youtube": {"player_client": clients}}
    opts.update(extra or {})
    return opts


def list_playlist(url):
    """[{"url", "title"}] in playlist order (empty list when nothing was found)."""
    yt_dlp = _yt_dlp()
    opts = _options({"extract_flat": "in_playlist", "noplaylist": False})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries, seen = [], set()
    for entry in (info or {}).get("entries") or []:
        video_id = (entry or {}).get("id")
        if not video_id or video_id in seen:
            continue
        seen.add(video_id)
        entries.append({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": (entry.get("title") or "").strip() or video_id,
        })
    return entries


def _size_label(size_bytes):
    if not size_bytes:
        return None
    mib = size_bytes / (1024 * 1024)
    return f"{mib / 1024:.2f} GB" if mib >= 1024 else f"{mib:.0f} MB"


_FAMILIES = ("avc1", "vp9", "vp09", "av01", "hev1", "hvc1")


def _family(vcodec):
    vcodec = (vcodec or "").lower()
    for name in _FAMILIES:
        if vcodec.startswith(name):
            return "vp9" if name == "vp09" else name
    return None


def qualities_from_info(info):
    """The (format_id, label, size_label, codec_label) list for one video's
    yt-dlp info dict: one row per height, ascending."""
    formats = (info or {}).get("formats") or []
    audio = [f for f in formats if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")]
    audio_size = max(((f.get("filesize") or f.get("filesize_approx") or 0) for f in audio), default=0)
    by_height = {}
    for f in formats:
        height = f.get("height")
        if not height or f.get("vcodec") in (None, "none"):
            continue
        row = by_height.setdefault(height, {"fps": 0, "families": [], "size": 0})
        row["fps"] = max(row["fps"], f.get("fps") or 0)
        family = _family(f.get("vcodec"))
        if family and family not in row["families"]:
            row["families"].append(family)
        row["size"] = max(row["size"], f.get("filesize") or f.get("filesize_approx") or 0)
    results = []
    for height in sorted(by_height):
        row = by_height[height]
        label = f"{height}p" + (str(int(row["fps"])) if row["fps"] and row["fps"] > 30 else "")
        total = row["size"] + audio_size if row["size"] else 0
        results.append((f"bestvideo[height<={height}]", label, _size_label(total),
                        "/".join(row["families"]) or None))
    return results


def list_qualities(url):
    """The qualities of one video, or raises when the phone could not read it."""
    yt_dlp = _yt_dlp()
    last_error = None
    for clients in _PLAYER_CLIENT_TRIES:
        try:
            with yt_dlp.YoutubeDL(_options(clients=clients)) as ydl:
                info = ydl.extract_info(url, download=False)
            results = qualities_from_info(info)
            if results:
                return results
            last_error = RuntimeError("no qualities came back")
        except Exception as e:
            last_error = e
    raise RuntimeError(str(last_error)[:80] if last_error else "no qualities came back")
