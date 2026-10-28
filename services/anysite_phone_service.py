"""Any site (phone): the phone itself reads the page with yt-dlp (the phone's IP, not GitHub's), then the
chosen direct link goes to the Upload File workflow, which downloads it on GitHub into a release.

Only formats that are one file with picture AND sound are offered (a plain file or an HLS playlist
with sound): the Upload File workflow downloads one link. A site that gives video and audio separately
(like YouTube) has to use the Any site button (GitHub) instead.

Honest limit: a link tied to the phone's IP can be refused (403) when GitHub downloads it.
Blocking functions (call from a background thread). Pure helpers, no Kivy.
"""
import re
import urllib.parse

from core.async_utils import run_in_background

_SKIP_PROTOCOLS = ("dash", "ism", "f4m", "rtmp", "mhtml")


def _yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except Exception as e:
        raise RuntimeError("yt-dlp is not inside this build") from e


def _options():
    return {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "socket_timeout": 30, "retries": 2}


def _height(f):
    if f.get("height"):
        return int(f["height"])
    text = f"{f.get('format_note') or ''} {f.get('format_id') or ''} {f.get('format') or ''}"
    m = re.search(r"(\d{3,4})p", text)
    return int(m.group(1)) if m else 0


def _short_codec(vcodec):
    return (vcodec or "").split(".")[0] if vcodec not in (None, "none") else ""


def formats_of(info):
    """[{id, h, ext, vcodec, size, url, hls}] - one-file formats with picture and sound."""
    rows, seen = [], set()
    candidates = list((info or {}).get("formats") or [])
    if not candidates and (info or {}).get("url"):
        candidates = [info]
    for f in candidates:
        url = f.get("url")
        if not url:
            continue
        proto = (f.get("protocol") or "").lower()
        if any(b in proto for b in _SKIP_PROTOCOLS):
            continue
        if f.get("vcodec") == "none" or f.get("acodec") == "none":
            continue
        fid = str(f.get("format_id") or len(rows))
        while fid in seen:
            fid += "_"
        seen.add(fid)
        hls = "m3u8" in proto
        rows.append({"id": fid, "h": _height(f) or None, "ext": "mp4" if hls else (f.get("ext") or "mp4"),
                     "vcodec": _short_codec(f.get("vcodec")),
                     "size": f.get("filesize") or f.get("filesize_approx"), "url": url, "hls": hls})
    return rows


def pick(rows, quality):
    """The row for ``quality`` (a height like "720", or "highest"): the closest height, a tie goes to
    the higher one; a plain file is preferred over an HLS playlist."""
    heights = [r for r in rows if r.get("h")]
    pool = heights or list(rows)
    if not pool:
        return None
    if heights:
        if str(quality).isdigit():
            target = int(quality)
            best = min({r["h"] for r in heights}, key=lambda h: (abs(h - target), -h))
        else:
            best = max(r["h"] for r in heights)
        pool = [r for r in heights if r["h"] == best]
    return sorted(reversed(pool), key=lambda r: r["hls"])[0]


def pick_all(results, quality):
    """([(link, row)], [problem text]) for a whole read."""
    picked, problems = [], []
    for link in results:
        row = pick(link.get("formats") or [], quality)
        if row:
            picked.append((link, row))
        else:
            problems.append(link.get("title") or link.get("url") or "?")
    return picked, problems


def pick_by_id(results, url, format_id):
    for link in results:
        if link.get("url") == url:
            for row in link.get("formats") or []:
                if row["id"] == format_id:
                    return link, row
    return None


def file_name(title, row):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "").strip()
    name = re.sub(r"\s+", "_", name).strip("._ ")[:120] or "video"
    ext = (row.get("ext") or "mp4").lstrip(".")
    return name if name.lower().endswith("." + ext.lower()) else f"{name}.{ext}"


def upload_line(link, row):
    """The line for the Upload File workflow: the direct link + a file name hint (#ytb-name=...)."""
    title = link.get("title") if not link.get("error") else ""
    return f"{row['url'].split('#')[0]}#ytb-name={urllib.parse.quote(file_name(title, row))}"


def read_links(urls, on_status=None):
    """[{url, title, formats, error?}] - one entry per page link."""
    yt_dlp = _yt_dlp()
    results = []
    for n, url in enumerate(urls, 1):
        if on_status:
            on_status(f"Reading link {n} of {len(urls)} on this phone...")
        try:
            with yt_dlp.YoutubeDL(_options()) as ydl:
                info = ydl.extract_info(url, download=False)
            entries = [e for e in ((info or {}).get("entries") or []) if e]
            if entries:
                info = entries[0]
            results.append({"url": url, "title": (info or {}).get("title") or url, "formats": formats_of(info)})
        except Exception as e:
            results.append({"url": url, "title": f"{url}\n{str(e)[:140]}", "formats": [], "error": str(e)[:140]})
    return results


def start_read(urls, on_status, on_done):
    """on_done(results) from a background thread."""
    run_in_background(_read_thread, urls, on_status, on_done)


def _read_thread(urls, on_status, on_done):
    try:
        on_done(read_links(urls, on_status))
    except Exception as e:
        on_done([{"url": (urls or [""])[0], "title": f"Error: {str(e)[:100]}", "formats": [], "error": str(e)[:100]}])
