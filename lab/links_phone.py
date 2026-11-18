"""Get links only (phone) — the phone reads qualities with yt-dlp.

Same idea as Any site (phone): this phone's IP opens the page, so it is fast and
shows which sites work from here. Nothing is downloaded and GitHub is not used.
Link Lab's "Get links only" (lab-links.yml) is a different button and is not changed.
"""
import re

S = {"urls": "", "loaded": False}
_SKIP = ("dash", "ism", "f4m", "rtmp", "mhtml")


def _load(host):
    if S["loaded"]:
        return
    S["loaded"] = True
    saved = host.store.get("urls")
    if saved:
        S["urls"] = saved


def build(host):
    _load(host)
    if host.prefill and not S["urls"]:
        S["urls"] = host.prefill
    host.title("Get links only (\u0628\u0627 \u06af\u0648\u0634\u06cc)")
    host.text(
        "Paste page links, one per line. This phone reads each page with yt-dlp "
        "(this phone's network, not GitHub) and lists the qualities. Nothing is "
        "downloaded. Link Lab is unchanged."
    )
    urls = host.input("Links, one per line", text=S["urls"], multiline=True)
    host.status()

    def go():
        text = (urls.text or "").strip()
        S["urls"] = text
        host.store.set("urls", text)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            host.set_status("Paste a link first")
            return
        host.show(reading_screen, lines)

    host.button("Read qualities on this phone", go)
    host.button("Show log", host.show_log)
    host.back_button("Back")


def reading_screen(host, lines):
    host.title("Reading on this phone")
    host.text("yt-dlp is running on this phone. You can leave this screen; the read keeps going.")
    host.status()
    host.set_status("Starting...")

    def work():
        return _read_all(lines, lambda msg: host.set_status(msg))

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            host.log("read failed:", err)
            return
        host.replace(result_screen, res)

    host.background(work, done=done)
    host.back_button("Back")


def result_screen(host, results):
    ok = sum(1 for r in results if r.get("rows") or r.get("video_heights"))
    host.title("Qualities (%d of %d)" % (ok, len(results)))
    blocks = []
    for r in results:
        blocks.append(_block(r))
        host.text(_block(r))
        for row in (r.get("rows") or [])[:8]:
            label = _row_label(row)
            host.button(
                "Copy " + label,
                lambda u=row["url"], lab=label: (host.copy(u), host.set_status("Copied " + lab)),
            )
        extra = len(r.get("rows") or []) - 8
        if extra > 0:
            host.text("(%d more qualities not shown)" % extra)
    host.status()
    report = "\n\n".join(blocks)
    host.button("Copy report", lambda: (host.copy(report), host.set_status("Copied")))
    host.back_button("Back")


def _block(r):
    lines = [r.get("title") or r.get("url") or "?"]
    if r.get("extractor"):
        lines.append("extractor: " + r["extractor"])
    lines.append(r.get("url") or "")
    if r.get("error"):
        lines.append("NOT READ: " + r["error"])
        return "\n".join(lines)
    if r.get("note"):
        lines.append(r["note"])
    rows = r.get("rows") or []
    if rows:
        lines.append("Picture and sound together:")
        for row in rows:
            lines.append("  " + _row_label(row))
    elif r.get("video_heights"):
        heights = ", ".join("%dp" % h for h in r["video_heights"])
        lines.append(
            "Supported, but picture and sound are separate (" + heights + "). "
            "There is no single file to copy. Use Any site (GitHub) or Link Lab download."
        )
    else:
        lines.append("No video quality was found.")
    return "\n".join(ln for ln in lines if ln)


def _row_label(row):
    h = row.get("h")
    bits = [("%dp" % h) if h else "unknown height"]
    if row.get("ext"):
        bits.append(row["ext"])
    if row.get("hls"):
        bits.append("HLS")
    if row.get("size"):
        bits.append(row["size"])
    return " · ".join(bits)


def _read_all(urls, on_status):
    yt_dlp = _yt_dlp()
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 2,
    }
    out = []
    for n, url in enumerate(urls, 1):
        if on_status:
            on_status("Reading link %d of %d on this phone..." % (n, len(urls)))
        out.append(_one(yt_dlp, opts, url))
    if on_status:
        on_status("Done")
    return out


def _yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except Exception as e:
        raise RuntimeError("yt-dlp is not inside this build") from e


def _one(yt_dlp, opts, url):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as e:
        return {"url": url, "title": url, "error": str(e).strip().splitlines()[-1][:180]}
    note = ""
    entries = [e for e in (info.get("entries") or []) if e]
    if entries:
        note = "Playlist: showing the first video only (%d found)." % len(entries)
        info = entries[0] or {}
    rows, video_heights = _formats(info)
    if not rows and video_heights:
        note = (note + " " if note else "") + "Picture and sound come as separate streams."
    return {
        "url": url,
        "title": info.get("title") or url,
        "extractor": info.get("extractor") or info.get("extractor_key") or "",
        "note": note.strip(),
        "rows": rows,
        "video_heights": video_heights,
    }


def _formats(info):
    """One direct file per height when picture and sound are together, else video-only heights."""
    both, video = [], []
    candidates = list((info or {}).get("formats") or [])
    if not candidates and (info or {}).get("url"):
        candidates = [info]
    for f in candidates:
        url = f.get("url")
        if not url:
            continue
        proto = (f.get("protocol") or "").lower()
        if any(b in proto for b in _SKIP):
            continue
        # A direct file often has no codec info (None = unknown): that is one file with picture and
        # sound (the GitHub links.py accepts it too). Only an explicit "none" means a part is missing.
        v = f.get("vcodec") != "none"
        a = f.get("acodec") != "none"
        h = _height(f)
        if v and a:
            both.append({
                "h": h,
                "ext": "mp4" if "m3u8" in proto else (f.get("ext") or "mp4"),
                "hls": "m3u8" in proto,
                "size": _size(f.get("filesize") or f.get("filesize_approx")),
                "url": url.split("#")[0],
                "_bytes": _bytes(f),
            })
        elif v and h:
            video.append(h)
    rows = _best_per_height(both)
    for row in rows:
        row.pop("_bytes", None)
    return rows, sorted(set(video), reverse=True)


def _best_per_height(rows):
    groups = {}
    for row in rows:
        groups.setdefault(row.get("h") or 0, []).append(row)
    chosen = []
    for h in sorted(groups, reverse=True):
        pool = groups[h]
        pool.sort(key=lambda r: (r["hls"], -(r.get("_bytes") or 0)))
        chosen.append(pool[0])
    return chosen


def _height(f):
    if f.get("height"):
        try:
            return int(f["height"])
        except (TypeError, ValueError):
            pass
    text = "%s %s %s" % (f.get("format_note") or "", f.get("format_id") or "", f.get("format") or "")
    m = re.search(r"(\d{3,4})p", text)
    return int(m.group(1)) if m else 0


def _bytes(f):
    try:
        return int(f.get("filesize") or f.get("filesize_approx") or 0)
    except (TypeError, ValueError):
        return 0


def _size(n):
    n = _bytes({"filesize": n})
    if n <= 0:
        return ""
    v, i = float(n), 0
    units = ("B", "KB", "MB", "GB")
    while v >= 1024 and i < 3:
        v /= 1024.0
        i += 1
    return "%d B" % n if i == 0 else "%.1f %s" % (v, units[i])
