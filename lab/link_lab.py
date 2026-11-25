"""Link Lab - any site through yt-dlp (lab copy of the link_downloader repo's tools).

Uses three workflows that are copies of redi2213/link_downloader:
  lab-links.yml         extract the video links (written into the notes of release run-<id>)
  lab-download.yml      extract + download + upload to a release run-<id>
  lab-find-proxies.yml  find free proxies, saved on this repo's lab branch (lab/working_proxies.txt)
The app's own tools and workflows are not touched. Edit this file on the config
branch (lab/link_lab.py) and open the tool again: no build needed.
"""
import re
import time

S = {"urls": "", "quality": "720", "proxy": "", "v2ray": "", "loaded": False}
QUALITIES = [("Best", "best"), ("1080", "1080"), ("720", "720"), ("480", "480"), ("360", "360"), ("240", "240")]
PROXY_FILE = "lab/working_proxies.txt"
CONFIG_FILE = "lab/working_configs.txt"


def _load(host):
    if S["loaded"]:
        return
    S["loaded"] = True
    for key in ("proxy", "v2ray", "quality"):
        value = host.store.get(key)
        if value:
            S[key] = value


# ---------------------------------------------------------------- first screen
def build(host):
    _load(host)
    try:
        raw = host.store.get("browser_quality") or ""
        host.store.delete("browser_quality")        # read once
        q, _, ts = raw.partition("|")
        if q.isdigit() and ts.isdigit() and time.time() - int(ts) < 900:
            S["quality"] = q                        # the quality picked in the in-app browser
            S["auto"] = q
            host.log("quality from the browser:", q)
    except Exception:
        pass
    quick = ""
    if host.prefill:
        keep = []
        for ln in str(host.prefill).splitlines():
            if ln.strip().startswith("#quality=") and ln.strip()[9:].isdigit():
                S["quality"] = ln.strip()[9:]       # the quality picked in the in-app browser
            elif ln.strip().startswith("#quick="):
                quick = ln.strip()[7:]              # a button to run at once (share list favorites)
            else:
                keep.append(ln)
        if "\n".join(keep).strip():
            S["urls"] = "\n".join(keep).strip()
    if quick:
        try:
            host.prefill = ""                       # one-shot: Back must not run it again
        except Exception:
            if S.get("quick_seen") == host.prefill:
                quick = ""
            else:
                S["quick_seen"] = host.prefill
    host.title("Link Lab (any site)")
    host.text("Paste one or more video page links, one per line. yt-dlp reads the page, "
              "so most sites work (xHamster and Beeg use their own API first).")
    urls = host.input("Links, one per line", text=S["urls"], multiline=True)
    host.text("Quality (for the download)")
    quality = host.choice(QUALITIES, default=S["quality"])
    host.status()

    def grab():
        S["urls"] = urls.text.strip()
        S["quality"] = quality.value
        host.store.set("quality", S["quality"])
        return S["urls"]

    def need():
        if not grab():
            host.set_status("Paste a link first")
            return False
        return True

    if S.get("auto"):
        host.button("Browser quality %sp: find on this phone and upload" % S["auto"],
                    lambda: need() and (S.__setitem__("auto_run", True), host.show(phone_screen)))
    host.button("Get links only", lambda: need() and host.show(links_screen))
    host.button("Get links only (this phone)", lambda: need() and host.show(phone_screen))
    host.button("Download to a GitHub release", lambda: need() and start_download(host))
    host.button("Options (proxy / v2ray)", lambda: (grab(), host.show(options_screen)))
    host.button("Free proxies", lambda: (grab(), host.show(proxies_screen)))
    host.row([("Copy log", lambda: _copy_log(host)), ("Clear log", lambda: _clear_log(host))])
    host.back_button("Back")
    runs = {"phone": lambda: need() and host.show(phone_screen),
            "links": lambda: need() and host.show(links_screen),
            "download": lambda: need() and start_download(host)}
    if quick in runs:                               # the quick buttons listed in lab/index.json
        try:
            from kivy.clock import Clock
            Clock.schedule_once(lambda dt: runs[quick](), 0.3)
        except Exception:
            pass


# ---------------------------------------------------------------- options
def options_screen(host):
    host.title("Options")
    host.text("Both are optional. With both empty, Lab uses its automatic sources: the free "
              "proxies (refreshed every 12 hours) and the best configs of the default "
              "subscription (refreshed every 24 hours). They are tried together and the "
              "first that answers wins. Fill these only to use your own.")
    host.text("Proxy (socks5://ip:port or http://ip:port)")
    proxy = host.input("Proxy override", text=S["proxy"])
    host.text("v2ray / Xray config: vless://, vmess://, trojan://, ss:// link, "
              "subscription link or JSON. When set, free proxies are ignored.")
    v2 = host.input("Config", text=S["v2ray"], multiline=True)
    host.status()

    def save():
        S["proxy"] = proxy.text.strip()
        S["v2ray"] = v2.text.strip()
        host.store.set("proxy", S["proxy"])
        host.store.set("v2ray", S["v2ray"])
        host.set_status("Saved")

    def clear():
        proxy.text = ""
        v2.text = ""
        S["proxy"] = S["v2ray"] = ""
        host.store.delete("proxy")
        host.store.delete("v2ray")
        host.set_status("Cleared")

    host.button("Save", save)
    host.button("Clear both", clear)
    host.back_button()


# ---------------------------------------------------------------- get links
def _wait(host, run_id):
    """Waits for a run and shows its jobs (like the Actions tab) in the status line."""
    try:
        from labx import lab_jobs
    except Exception:
        lab_jobs = None
    if lab_jobs is not None:
        return lab_jobs.wait(host, run_id, host.set_status)
    return host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))


def links_screen(host):
    host.title("Getting links")
    host.text("Runs lab-links.yml on GitHub (about a minute). You can leave this screen; "
              "the run keeps going.")
    host.status(height=560)
    host.set_status("Starting...")
    inputs = {"url": S["urls"], "proxy": S["proxy"], "v2ray_config": S["v2ray"]}

    def work():
        run_id = host.gh.dispatch("lab-links.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-links run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = _wait(host, run_id)
        body = ""
        if conclusion == "success":
            for _ in range(6):
                try:
                    body = host.gh.request("GET", "/releases/tags/run-%s" % run_id).json().get("body") or ""
                except Exception as e:
                    host.log("release read:", e)
                    body = ""
                if body:
                    break
                time.sleep(2)
        return run_id, conclusion, body

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(links_result, *res)

    host.background(work, done=done)
    host.back_button()


def links_result(host, run_id, conclusion, body):
    links = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("http")]
    if conclusion != "success":
        host.title("Run finished: %s" % conclusion)
        host.text("Open GitHub > Actions > Lab Links (run %s) to see the log." % run_id)
    elif not body.strip():
        host.title("No links saved")
        host.text("The run succeeded but saved nothing. Open GitHub > Actions > Lab Links "
                  "(run %s) to see the log." % run_id)
    else:
        host.title("Links (%d)" % len(links))
        host.text(body.strip())
    host.status()
    picks = _parse_qualities(body) if conclusion == "success" else []
    if picks:
        host.text("Tap a quality for: copy, download in the app, add to the list, upload to a release, share.")
        many = len({p[1] for p in picks}) > 1
        for title, page, height, link, size in picks[:12]:
            r = {"url": page, "title": title}
            row = {"h": height, "ext": "mp4", "hls": ".m3u8" in link.lower(), "size": size, "url": link, "gh": True}
            label = _phone_label(row)
            if many:
                label += " - " + (title[:22] or page[:22])
            host.button(label, lambda r=r, row=row: host.show(quality_screen, r, row))
        if len(picks) > 12:
            host.text("(%d more not shown)" % (len(picks) - 12))
    if links:
        host.button("Copy all links", lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    if body.strip():
        host.button("Copy everything", lambda: (host.copy(body), host.set_status("Copied")))
    host.back_button()


# ------------------------------------------------------- get links on the phone
# Same button's other runner. lab-links.yml is not started and its logic is not changed.
# yt-dlp runs here, so the request uses this phone's IP (same idea as Any site on the phone).
def phone_screen(host):
    host.title("Getting links on this phone")
    host.text("yt-dlp runs on this phone (this phone's network, not GitHub), so it is usually "
              "faster. Nothing is downloaded and lab-links.yml is not used.")
    host.status()
    host.set_status("Starting...")
    urls = [ln.strip() for ln in S["urls"].splitlines() if ln.strip()]

    def work():
        return _phone_read(host, urls, lambda msg: host.set_status(msg))

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            host.log("phone read failed:", err)
            return
        if S.get("auto_run"):
            S["auto_run"] = False
            pick = _auto_pick(res, S.get("auto"))
            if pick:
                r, row, link = pick
                host.log("auto upload: %sp, link %s" % (row.get("h"), (link or "page")[:120]))
                host.replace(download_screen, r.get("url") or "", str(row.get("h") or S["auto"]), link, r.get("title") or "")
                return
        host.replace(phone_result, res)

    host.background(work, done=done)
    host.back_button()


_IP_BOUND = re.compile(r"[?&]ip=[0-9a-f.:]{7,}|data=[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+", re.I)


def _auto_pick(results, quality):
    """The row of the quality picked in the browser (or the best one below it): (result, row, link for GitHub).
    An HLS row comes first; a link tied to an IP is not sent (GitHub reads the page itself then)."""
    try:
        target = int(quality)
    except (TypeError, ValueError):
        return None
    for r in results or []:
        rows = [x for x in (r.get("rows") or []) if x.get("h")]
        exact = [x for x in rows if x["h"] == target]
        pool = exact or [x for x in rows if x["h"] <= target]
        if not pool:
            continue
        pool.sort(key=lambda x: (-x["h"], 0 if x.get("hls") else 1, 1 if _IP_BOUND.search(x.get("url") or "") else 0))
        row = pool[0]
        link = row.get("url") or ""
        return r, row, ("" if _IP_BOUND.search(link) else link)
    return None


def phone_result(host, results):
    ok = sum(1 for r in results if r.get("rows"))
    host.title("Links on this phone (%d of %d)" % (ok, len(results)))
    blocks = [_phone_block(r) for r in results]
    for r in results:
        host.text(_phone_block(r, links=False))
        for row in (r.get("rows") or [])[:12]:
            host.button(_phone_label(row), lambda r=r, row=row: host.show(quality_screen, r, row))
        extra = len(r.get("rows") or []) - 12
        if extra > 0:
            host.text("(%d more qualities not shown)" % extra)
        if not (r.get("rows") or []) and r.get("url"):
            # Nothing found on this phone: run lab-download.yml right here (GitHub tries its proxies).
            host.button("Download on GitHub (lab-download)",
                        lambda r=r: _run_download(host, r["url"], "best"))
    host.status()
    if any(not (r.get("rows") or []) for r in results):
        host.text("No video link was found for some pages. The site may be blocking this phone's IP: "
                  "turn on a VPN (change the phone's IP) and read again. Or let GitHub try to read it.")
        host.button("Read again on this phone", lambda: host.show(phone_screen))
        host.button("Get links on GitHub (lab-links)", lambda: host.show(links_screen))
    host.text("Tap a quality for: copy, download in the app, upload to a release, share.")
    report = "\n\n".join(blocks)
    host.log("phone read:\n" + report[:3000])
    for r in results:
        if r.get("size_debug"):
            host.log(r["size_debug"])
    host.button("Copy report", lambda: (host.copy(report), host.set_status("Copied")))
    failed = [r for r in results if not (r.get("rows") or [])]
    if failed:
        # One log file per failed link goes to the repo (config branch, folder lab-logs/) so it can be read later.
        host.button("Save log of failed links (%d)" % len(failed), lambda f=failed: _phone_save_logs(host, f))
    host.row([("Copy log", lambda: _copy_log(host)), ("Clear log", lambda: _clear_log(host))])
    host.back_button()


def quality_screen(host, r, row):
    """What to do with one quality that this phone found."""
    link = row["url"]
    page = r.get("url") or ""
    title = r.get("title") or ""
    host.title(_phone_label(row))
    host.text(title)
    if row.get("gh"):
        host.text("This link was read on GitHub. It may be tied to GitHub's IP and fail on this phone; "
                  "Upload to release always works.")
    host.status()
    host.button("Copy direct link", lambda: (host.copy(link), host.set_status("Copied")))
    host.button("Download direct link", lambda: _phone_app_download(host, r, row))
    host.button("Add to download list", lambda: _phone_app_download(host, r, row, start=False))
    host.button("Upload to release",
                lambda: _run_download(host, page, str(row.get("h") or "best"), link, title))
    host.button("Share direct link",
                lambda: None if host.share_text(link) else host.set_status("Share is not available"))
    host.back_button()


def _phone_file_name(title, row):
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', " ", title or "").strip()
    name = re.sub(r"\s+", "_", name).strip("._ ")[:100] or "video"
    h = row.get("h")
    if h:
        name += "_%dp" % h
    return name + (".mp4" if row.get("hls") else "." + (row.get("ext") or "mp4").lstrip("."))


def _phone_app_download(host, r, row, start=True):
    """Starts the download now with the app's own download manager (it shows in Downloads), or only
    puts it in the list (tab Adding) when ``start`` is False."""
    try:
        from core import download_manager as dm
        name = _phone_file_name(r.get("title"), row)
        task = dm.add_pending(row["url"], name=name, category="Any-site", hls=True if row.get("hls") else None)
        if not start:
            host.log("app download added to the list:", name)
            host.set_status("Added to the download list (%s)" % name)
            return
        if not dm.start_task(task.id):
            raise RuntimeError("could not start")
        host.log("app download started:", name)
        host.set_status("Started: see Downloads (%s)" % name)
    except Exception as e:
        host.log("app download failed:", e)
        host.set_status("Failed: %s" % str(e)[:100])


def _phone_block(r, links=True):
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
        lines.append("Picture and sound together:" if links else "Qualities (with size):")
        if links:
            for row in rows:
                lines.append("  " + _phone_label(row))
                lines.append("  " + row["url"])
    elif r.get("video_heights"):
        heights = ", ".join("%dp" % h for h in r["video_heights"])
        lines.append("Supported, but picture and sound are separate (" + heights + "). "
                     "There is no single file to copy. Use Get links only on GitHub, or Download.")
    else:
        lines.append("No video quality was found.")
    return "\n".join(ln for ln in lines if ln)


def _phone_label(row):
    h = row.get("h")
    bits = [("%dp" % h) if h else "unknown height"]
    if row.get("ext"):
        bits.append(row["ext"])
    if row.get("hls"):
        bits.append("HLS")
    if row.get("size"):
        bits.append(row["size"])
    return " · ".join(bits)


_PHONE_SKIP = ("dash", "ism", "f4m", "rtmp", "mhtml")


class _PhoneLog:
    """yt-dlp logger kept in memory. On Android sys.stderr can be a plain string, so yt-dlp's own
    error print crashed with "'str' object has no attribute 'write'" and hid the real error."""

    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(str(msg))


def _phone_read(host, urls, on_status):
    """Reads each link on this phone. A site added to Link Lab (Add workflow > Add a tested site) is read
    by its adapter first (this phone's network); everything else, and an adapter that finds nothing, goes
    through yt-dlp as before."""
    try:
        from labx import site_phone
    except Exception:
        site_phone = None
    entries = []
    if site_phone is not None:
        try:
            entries = site_phone.load_index(host)
        except Exception:
            entries = []
    try:
        import yt_dlp
    except Exception:
        yt_dlp = None
    if yt_dlp is None and not entries:
        raise RuntimeError("yt-dlp is not inside this build")
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "socket_timeout": 30, "retries": 2, "logger": _PhoneLog()}
    out = []
    for n, url in enumerate(urls, 1):
        if on_status:
            on_status("Reading link %d of %d on this phone..." % (n, len(urls)))
        found = None
        if entries:
            try:
                found = site_phone.try_registered(host, url, entries)
            except Exception:
                found = None
        if found is not None:
            found.setdefault("video_heights", [])
            if found.get("rows") or yt_dlp is None:
                out.append(found)
                continue
        if yt_dlp is None:
            out.append({"url": url, "title": url, "error": "yt-dlp is not inside this build"})
            continue
        res = _phone_one(yt_dlp, opts, url)
        if not res.get("rows") or (res.get("extractor") or "").lower() in ("generic", "html5"):
            try:
                alt = _phone_kvs(url)
                if alt and res.get("rows"):
                    # yt-dlp found only some qualities: add the ones from the page's player settings
                    have = set(r.get("h") for r in res["rows"])
                    extra = [r for r in alt["rows"] if r.get("h") not in have]
                    if extra:
                        res["rows"] = sorted(res["rows"] + extra, key=lambda r: -(r.get("h") or 0))
                        res["note"] = ((res.get("note") or "") + " More qualities come from the page's player settings (time-limited links).").strip()
                elif alt:
                    res = alt
            except Exception as e:
                key = "error" if res.get("error") else "note"
                res[key] = ((res.get(key) or "") + " | player-settings fallback: %s" % str(e)[:100]).strip()
        if found is not None and not res.get("rows"):
            res["note"] = ("Site adapter: %s. " % (found.get("error") or "no quality")) + (res.get("note") or "")
        out.append(res)
    if on_status:
        on_status("Reading file sizes...")
    for res in out:
        try:
            _phone_add_sizes(res)
        except Exception:
            pass
    for res in out:
        _phone_drop_same_file(res)
    if on_status:
        on_status("Done")
    return out


# ---------------------------------------------------------------- KVS / KT-player fallback
# Many sites (KVS engine) put the video links in the player settings of the page, e.g.
#   video_url: 'https://site/get_stream/123-480.mp4?md5=..&timestamp=..', video_url_text: '480',
#   video_alt_url: '...-720.mp4...', video_alt_url_text: '720', video_alt_url2: '...-1080.mp4...'
# yt-dlp's generic extractor does not read them ("no media urls"). Used only when yt-dlp found nothing.
_KVS_URL = re.compile(r"""(video(?:_alt)?_url\d*)\s*:\s*['"]([^'"]+)['"]""")
_KVS_TXT = re.compile(r"""(video(?:_alt)?_url\d*)_text\s*:\s*['"]([^'"]*)['"]""")


def _phone_final_url(link, referer):
    """Follows the redirects of a page-player link (a 1-byte Range request, nothing is downloaded) and returns
    where it ends. KVS sites answer get_stream/... with a redirect to the real file on a CDN; that address
    lasts hours and also works from GitHub, while the get_stream address itself expires in minutes and is
    refused to GitHub's IP."""
    try:
        with _phone_http(link, {"Range": "bytes=0-0", "Referer": referer}) as r:
            final = getattr(r, "url", None)
            if not final and hasattr(r, "geturl"):
                final = r.geturl()
            return str(final or "")
    except Exception as e:
        _phone_err(e)
        return ""


def _phone_kvs(url):
    """Rows (like _phone_formats) read from the page's player settings, or None when the page has none."""
    from urllib.parse import urljoin
    text = _phone_text(url, {"User-Agent": _PEEK_UA})
    if not text:
        raise RuntimeError("page not read (%s)" % (_NET["err"] or "empty"))
    text = text.replace("\\/", "/")
    labels = dict(_KVS_TXT.findall(text))
    rows, seen, hidden = [], set(), 0
    for key, link in _KVS_URL.findall(text):
        link = link.replace("&amp;", "&").strip()
        if link.startswith("function/"):
            hidden += 1          # encrypted with the site's license code: not supported
            continue
        link = urljoin(url, link)
        if not link.startswith("http") or link in seen:
            continue
        seen.add(link)
        m = re.search(r"(\d{3,4})", labels.get(key, "")) or re.search(r"[-_/](\d{3,4})p?\.mp4", link)
        rows.append({"h": int(m.group(1)) if m else None, "ext": "mp4", "hls": False, "size": "",
                     "url": link, "_tbr": None, "_kvs": True, "_hdr": {"Referer": url, "User-Agent": _PEEK_UA}})
    if not rows:
        if hidden:
            raise RuntimeError("the page's player links are encrypted (function/0/), decoding is not supported yet")
        return None
    resolved = 0
    for row in rows:
        final = _phone_final_url(row["url"], url)
        if final.startswith("http") and final != row["url"]:
            row["url"] = final
            row["_hdr"] = {"User-Agent": _PEEK_UA}
            resolved += 1
    note = "yt-dlp found nothing; these links come from the page's player settings."
    note += (" Followed the site's redirect to the real file address (valid for hours)." if resolved
             else " Not resolved: these links are time-limited, download right away.")
    rows.sort(key=lambda r: -(r["h"] or 0))
    m = re.search(r"video_title\s*:\s*['\"]([^'\"]+)", text) or re.search(r"(?is)<title[^>]*>(.*?)</title>", text)
    title = re.sub(r"\s+", " ", m.group(1)).strip() if m else url
    return {"url": url, "title": title, "extractor": "page player settings (fallback)",
            "note": note,
            "rows": rows, "video_heights": [], "duration": None}


def _phone_drop_same_file(res):
    """Some sites list a quality (e.g. 1080p) in the player settings but serve the lower one's file. A quality
    read from the page that has exactly the size of a lower quality is the same file: hide it."""
    rows = res.get("rows") or []
    by_size = {}
    for row in rows:
        if row.get("size"):
            by_size.setdefault(row["size"], []).append(row)
    drop = []
    for grp in by_size.values():
        if len(grp) > 1:
            grp.sort(key=lambda r: r.get("h") or 0)
            drop.extend(r for r in grp[1:] if r.get("_kvs"))
    if drop:
        res["rows"] = [r for r in rows if not any(r is d for d in drop)]
        res["note"] = ((res.get("note") or "") + " Hidden: %s (same file as a lower quality; the site lists it but serves the lower one)."
                       % ", ".join("%sp" % d.get("h") for d in drop)).strip()


_PEEK_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def _phone_one(yt_dlp, opts, url):
    if "peekvids.com" in (url or "").lower():
        # yt-dlp's own PeekVids extractor fails on this site ("Unable to extract short video ID").
        # The GitHub lab_scripts/links.py reads it with Generic + HTML5, a browser UA and the page
        # as referer - same here.
        url = url.split("?", 1)[0].split("#", 1)[0]
        opts = dict(opts)
        opts["allowed_extractors"] = ["Generic", "HTML5"]
        opts["http_headers"] = {"User-Agent": _PEEK_UA, "Referer": url}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
    except Exception as e:
        import traceback
        # The short error is shown; the last frames go to the log (Copy log) to find where it comes from.
        frames = "\n".join(traceback.format_exc().strip().splitlines()[-8:])
        return {"url": url, "title": url, "error": str(e).strip().splitlines()[-1][:180] or type(e).__name__,
                "size_debug": "read error trace:\n" + frames}
    note = ""
    entries = [e for e in (info.get("entries") or []) if e]
    if entries:
        note = "Playlist: showing the first video only (%d found)." % len(entries)
        info = entries[0] or {}
    rows, video_heights = _phone_formats(info)
    if not rows and video_heights:
        note = (note + " " if note else "") + "Picture and sound come as separate streams."
    if not rows and not video_heights:
        note = (note + " " if note else "") + _phone_debug(info)
    return {"url": url, "title": info.get("title") or url,
            "extractor": info.get("extractor") or info.get("extractor_key") or "",
            "note": note.strip(), "rows": rows, "video_heights": video_heights,
            "duration": info.get("duration")}


def _phone_formats(info):
    both, video = [], []
    candidates = list((info or {}).get("formats") or [])
    if not candidates and (info or {}).get("url"):
        candidates = [info]
    for f in candidates:
        link = f.get("url")
        if not link:
            continue
        proto = (f.get("protocol") or "").lower()
        if any(b in proto for b in _PHONE_SKIP):
            continue
        # A direct file often has no codec info (None = unknown): that is one file with picture and
        # sound (the GitHub links.py accepts it too). Only an explicit "none" means a part is missing.
        v = f.get("vcodec") != "none"
        a = f.get("acodec") != "none"
        h = _phone_height(f)
        if v and a:
            both.append({"h": h, "ext": "mp4" if "m3u8" in proto else (f.get("ext") or "mp4"),
                         "hls": "m3u8" in proto,
                         "size": _phone_size(f.get("filesize") or f.get("filesize_approx")),
                         "url": link.split("#")[0], "_bytes": _phone_bytes(f), "_tbr": f.get("tbr"),
                         "_hdr": dict(f.get("http_headers") or {})})
        elif v and h:
            video.append(h)
    groups = {}
    for row in both:
        groups.setdefault(row.get("h") or 0, []).append(row)
    chosen = []
    for h in sorted(groups, reverse=True):
        pool = groups[h]
        pool.sort(key=lambda r: (r["hls"], -(r.get("_bytes") or 0)))
        row = pool[0]
        row.pop("_bytes", None)
        chosen.append(row)
    return chosen, sorted(set(video), reverse=True)


def _phone_debug(info):
    """Why nothing was listed: what yt-dlp returned (ext/vcodec/acodec/height of the first formats)."""
    fs = list((info or {}).get("formats") or [])
    if not fs:
        return "yt-dlp returned no formats."
    bits = ["%s/%s/%s/%sp" % (f.get("ext"), f.get("vcodec"), f.get("acodec"), f.get("height")) for f in fs[:6]]
    return "yt-dlp saw %d format(s): %s" % (len(fs), ", ".join(bits))


def _phone_height(f):
    if f.get("height"):
        try:
            return int(f["height"])
        except (TypeError, ValueError):
            pass
    text = "%s %s %s" % (f.get("format_note") or "", f.get("format_id") or "", f.get("format") or "")
    m = re.search(r"(\d{3,4})p", text)
    return int(m.group(1)) if m else 0


def _phone_bytes(f):
    try:
        return int(f.get("filesize") or f.get("filesize_approx") or 0)
    except (TypeError, ValueError):
        return 0


def _phone_size(n):
    n = _phone_bytes({"filesize": n})
    if n <= 0:
        return ""
    v, i = float(n), 0
    units = ("B", "KB", "MB", "GB")
    while v >= 1024 and i < 3:
        v /= 1024.0
        i += 1
    return "%d B" % n if i == 0 else "%.1f %s" % (v, units[i])


# ---------------------------------------------------------------- file sizes on the phone
# yt-dlp gives no size for HLS. Like lab_scripts/links.py: read the playlist, ask 3 segments for
# byte 0 only (Range) and multiply by the segment count (a few KB of phone data per quality).
# The requests go through yt-dlp's own network code (same certificates and headers as the read).
# If that fails, the bitrate yt-dlp reported x duration is used. A note says why when no size is found.
_NET = {"ydl": None, "err": "", "referer": ""}


def _phone_http(url, headers=None, timeout=15, method=None):
    h = {"User-Agent": "Mozilla/5.0"}
    if _NET["referer"]:
        h["Referer"] = _NET["referer"]
    if headers:
        h.update(headers)
    try:
        from yt_dlp.networking import Request
        if _NET["ydl"] is None:
            import yt_dlp
            _NET["ydl"] = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "socket_timeout": timeout})
        return _NET["ydl"].urlopen(Request(url, headers=h, method=method))
    except ImportError:
        import urllib.request
        return urllib.request.urlopen(urllib.request.Request(url, headers=h, method=method), timeout=timeout)


def _phone_err(e):
    _NET["err"] = ("%s: %s" % (type(e).__name__, e)).strip()[:110]


def _phone_text(url, hdr=None):
    try:
        with _phone_http(url, hdr) as r:
            return r.read(2000000).decode("utf-8", "replace")
    except Exception as e:
        _phone_err(e)
        return ""


def _phone_range_size(url, hdr=None):
    """Size of a file: a 1-byte Range request, then HEAD. ``hdr`` = the headers yt-dlp gave for this format."""
    try:
        with _phone_http(url, dict(hdr or {}, Range="bytes=0-0")) as r:
            m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range") or "")
            if m:
                return int(m.group(1))
            n = r.headers.get("Content-Length") or ""
            if getattr(r, "status", 0) == 200 and n.isdigit():
                return int(n)
    except Exception as e:
        _phone_err(e)
    try:
        with _phone_http(url, hdr, method="HEAD") as r:
            n = r.headers.get("Content-Length") or ""
            if n.isdigit() and int(n) > 1:
                return int(n)
    except Exception as e:
        _phone_err(e)
    try:
        # Some CDNs refuse Range and HEAD but answer a plain GET: only the headers are used, the body is not read.
        with _phone_http(url, hdr) as r:
            n = r.headers.get("Content-Length") or ""
            if n.isdigit() and int(n) > 1:
                return int(n)
    except Exception as e:
        _phone_err(e)
    return None


def _phone_master_bw(url, hdr=None):
    """{height: bits per second} from the variants of an HLS master playlist (empty when it is not one)."""
    text = _phone_text(url, hdr)
    out = {}
    for ln in text.splitlines():
        if not ln.startswith("#EXT-X-STREAM-INF"):
            continue
        h = re.search(r"RESOLUTION=\d+x(\d+)", ln) or re.search(r'NAME="?(\d{3,4})p', ln)
        bw = re.search(r"AVERAGE-BANDWIDTH=(\d+)", ln) or re.search(r"(?<![A-Z-])BANDWIDTH=(\d+)", ln)
        if h and bw:
            out[int(h.group(1))] = int(bw.group(1))
    return out


def _phone_hls_estimate(url, height=0, hdr=None):
    from urllib.parse import urljoin
    text = _phone_text(url, hdr)
    if "#EXTM3U" not in text:
        return None
    if "#EXT-X-STREAM-INF" in text:
        lines = text.splitlines()
        pick = None
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"RESOLUTION=\d+x(\d+)", ln)
                if pick is None:
                    pick = i
                if height and m and int(m.group(1)) == height:
                    pick = i             # the variant of this quality, not just the first one
                    break
                if not height:
                    break
        for nxt in lines[(pick or 0) + 1:]:
            if nxt.strip() and not nxt.startswith("#"):
                url = urljoin(url, nxt.strip())
                break
        text = _phone_text(url, hdr)
        if "#EXTM3U" not in text:
            return None
    segs = [urljoin(url, ln.strip()) for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not segs:
        return None
    n = len(segs)
    sizes = [s for s in (_phone_range_size(segs[i], hdr) for i in sorted({0, n // 3, (2 * n) // 3})) if s]
    return int(sum(sizes) / len(sizes) * n) if sizes else None


def _phone_add_sizes(res):
    from concurrent.futures import ThreadPoolExecutor
    rows = res.get("rows") or []
    if not rows:
        return
    _NET["err"] = ""
    _NET["referer"] = res.get("url") or ""

    def one(row):
        if row.get("size"):
            return
        try:
            link = row.get("url") or ""
            if row.get("hls") or ".m3u8" in link:
                n = _phone_hls_estimate(link, row.get("h") or 0, row.get("_hdr"))
                if n:
                    row["size"] = "~" + _phone_size(n)
            else:
                n = _phone_range_size(link, row.get("_hdr"))
                if n:
                    row["size"] = _phone_size(n)
        except Exception as e:
            _phone_err(e)

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, rows))
    dur = res.get("duration") or 0
    _TWIN = []
    # The mp4 links are tied to the IP and answer 403 to a size request. Their HLS twin is not: same path with
    # "<h>p.h264.mp4.m3u8" (xHamster-style). Read that playlist the way the 1080p one is read.
    try:
        hls = next((r for r in rows if r.get("hls") or ".m3u8" in (r.get("url") or "")), None)
        pat = re.compile(r"/\d{3,4}p\.[a-z0-9]+\.mp4\.m3u8")
        if hls and pat.search(hls["url"]):
            def twin(row):
                if row.get("size") or not row.get("h"):
                    return
                for codec in ("h264", "av1"):
                    cand = pat.sub("/%dp.%s.mp4.m3u8" % (row["h"], codec), hls["url"], count=1)
                    _NET["err"] = ""
                    n = _phone_hls_estimate(cand, row["h"], hls.get("_hdr"))
                    _TWIN.append("%dp.%s -> %s%s" % (row["h"], codec, n if n else "none",
                                                      "" if n else " (%s)" % (_NET["err"] or "no segments")))
                    if n:
                        row["size"] = "~" + _phone_size(n) + " (HLS)"
                        return
            from concurrent.futures import ThreadPoolExecutor as _TP
            with _TP(max_workers=4) as ex2:
                list(ex2.map(twin, rows))
    except Exception as e:
        _phone_err(e)
    if dur and any(not r.get("size") for r in rows):
        # The file itself refused the size request (often HTTP 403): use the HLS master playlist's
        # bandwidth per height x duration, shown with ~ and (est.).
        try:
            hls = next((r for r in rows if r.get("hls") or ".m3u8" in (r.get("url") or "")), None)
            bw = _phone_master_bw(hls["url"], hls.get("_hdr")) if hls else {}
            if hls and not bw and re.search(r"/\d{3,4}p\.[a-z0-9]+\.mp4\.m3u8", hls["url"]):
                bw = _phone_master_bw(re.sub(r"/\d{3,4}p\.", "/_TPL_.", hls["url"], count=1), hls.get("_hdr"))
            for row in rows:
                if not row.get("size") and bw.get(row.get("h")):
                    row["size"] = "~" + _phone_size(int(bw[row["h"]] / 8.0 * float(dur))) + " (est.)"
        except Exception as e:
            _phone_err(e)
    for row in rows:
        tbr = row.pop("_tbr", None)
        row.pop("_hdr", None)
        if not row.get("size") and tbr and dur:
            try:
                row["size"] = "~" + _phone_size(int(float(tbr) * 1000 / 8 * float(dur))) + " (bitrate)"
            except Exception:
                pass
    why = _NET["err"] or "no size in the playlist"
    res["size_debug"] = "size errors: %s; duration=%s; master=%s; code=v3\ntwin: %s" % (
        why, dur, bool(locals().get("bw")), "; ".join(_TWIN) or "not tried")
    if any(not r.get("size") for r in rows):
        res["note"] = ((res.get("note") or "") + " Size not found for some qualities (%s)." % why).strip()
    elif any("(est.)" in r["size"] or "(bitrate)" in r["size"] or "(HLS)" in r["size"] for r in rows if r.get("size")):
        res["note"] = ((res.get("note") or "") + " Exact size is not available for the mp4 file (%s); ~ = size of the HLS stream or an estimate." % why).strip()


# ---------------------------------------------------------------- download
def _run_download(host, url, quality, link="", title=""):
    host.log("download:", quality, url[:200], "(phone link)" if link else "")
    host.show(download_screen, url, quality, link, title)


def download_screen(host, url, quality, link="", title=""):
    # NOT host.run_action: that always starts the workflow on main, where lab-download.yml
    # is only an empty stub. host.gh.dispatch starts it from the lab branch (the real one).
    label = quality if str(quality) == "best" else "%sp" % quality
    host.title("Downloading (%s)" % label)
    host.text("Runs lab-download.yml from the lab branch and saves the video in a GitHub "
              "release. You can leave this screen; the run keeps going.")
    host.status(height=560)
    host.set_status("Starting...")
    inputs = {"url": url, "quality": str(quality), "proxy": S["proxy"], "v2ray_config": S["v2ray"]}
    # The link this phone already found goes to GitHub, so the run skips its own (slow) extract step.
    # Links tied to an IP (data=1.2.3.4) would not work from GitHub, so those are not sent.
    if link and link.startswith("http") and len(link) < 60000 and not _IP_BOUND.search(link):
        inputs["direct_link"] = link
        inputs["direct_title"] = (title or "")[:200]
        host.text("Using the link found on this phone: GitHub skips the extract step.")

    state = {"run": None}

    def refresh():
        # Re-reads the run and its jobs right now (the screen also updates by itself every few seconds).
        rid = state["run"]
        if not rid:
            host.set_status("The run has not started yet...")
            return

        def read():
            run = host.gh.request("GET", "/actions/runs/%s" % rid).json()
            jobs = []
            try:
                jobs = host.gh.request("GET", "/actions/runs/%s/jobs?per_page=30" % rid).json().get("jobs") or []
            except Exception as e:
                host.log("jobs read:", e)
            return run, jobs

        def shown(res, err):
            if err is not None:
                host.set_status("Refresh failed: %s" % err)
                return
            run, jobs = res
            try:
                from labx import lab_jobs
                host.set_status(lab_jobs.format_text(rid, run, jobs))
            except Exception:
                host.set_status("Run %s - %s" % (rid, run.get("conclusion") or run.get("status")))

        host.background(read, done=shown)

    def work():
        run_id = host.gh.dispatch("lab-download.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        state["run"] = run_id
        host.log("lab-download run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = _wait(host, run_id)
        links = []
        if conclusion == "success":
            try:
                links = host.gh.release_links(run_id, attempts=6, delay=2)
            except Exception as e:
                host.log("release links:", e)
        return run_id, conclusion, links

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(download_result, *res)

    host.background(work, done=done)
    host.button("Refresh", refresh)
    host.back_button()


def download_result(host, run_id, conclusion, links):
    if conclusion != "success":
        host.title("Run finished: %s" % conclusion)
        host.text("Open GitHub > Actions > Lab Download Release (run %s) to see the log." % run_id)
    elif not links:
        host.title("No file saved")
        host.text("The run succeeded but no release file was found. Open GitHub > Actions > "
                  "Lab Download Release (run %s) to see the log." % run_id)
    else:
        host.title("Downloaded (%d file%s)" % (len(links), "" if len(links) == 1 else "s"))
        host.text("Saved in release run-%s. Open it from Release History in the app "
                  "(the app downloads with your GitHub token).\n\n%s" % (run_id, "\n".join(links)))
    host.status()
    if links:
        host.button("Copy link%s" % ("" if len(links) == 1 else "s"),
                    lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    host.back_button()


def start_download(host):
    _run_download(host, S["urls"], S["quality"])


def _parse_qualities(body):
    """Read the release notes written by lab_scripts/links.py: (title, page link, height, direct link)."""
    out, seen = [], set()
    title = page = ""
    pending = None
    pending_size = ""
    for raw in (body or "").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        if ln.startswith("# page:"):
            page = ln[7:].strip()
            continue
        if ln.startswith("# method:") or ln.startswith("# ERROR"):
            continue
        if ln.startswith("# quality:"):
            m = re.match(r"#\s*quality:\s*(\d{3,4})p", ln)
            pending = int(m.group(1)) if m else None
            ms = re.search(r"\|\s*size:\s*(.+)$", ln)
            pending_size = ms.group(1).strip() if ms else ""
            continue
        if ln.startswith("# "):
            title = ln[2:].strip()
            pending = None
            continue
        if ln.startswith("http"):
            if pending and page and (page, pending) not in seen:
                seen.add((page, pending))
                out.append((title, page, pending, ln, pending_size))
            pending = None
            pending_size = ""
    return out


# ---------------------------------------------------------------- free proxies
def proxies_screen(host):
    host.title("Free proxies (lab list)")
    host.text("Both lists refresh by themselves: proxies every 12 hours, configs every 24 hours "
              "(GitHub schedule). They are saved on the lab branch (%s, %s) and used by Get "
              "links and Download when no proxy / v2ray config is set. The buttons below "
              "refresh them right now." % (PROXY_FILE, CONFIG_FILE))
    host.button("Find new working proxies", lambda: host.show(find_screen))
    host.button("Show the saved list", lambda: host.show(list_screen))
    host.button("Refresh default configs", lambda: host.show(configs_find_screen))
    host.button("Show default configs", lambda: host.show(configs_list_screen))
    host.back_button()


def find_screen(host):
    host.title("Finding proxies")
    host.text("Runs lab-find-proxies.yml. This can take several minutes; the result is saved on "
              "GitHub even if you leave this screen.")
    host.status(height=560)
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-find-proxies.yml",
                                  {"needed": "8", "max_candidates": "100", "xh_check": "0"})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-find-proxies run", run_id)
        conclusion = _wait(host, run_id)
        return conclusion, _read_list(host)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        conclusion, lines = res
        host.replace(list_view, "Run finished: %s" % conclusion, lines)

    host.background(work, done=done)
    host.back_button()


def list_screen(host):
    host.title("Saved proxy list")
    host.status()
    host.set_status("Reading...")

    def done(lines, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(list_view, "Saved proxy list", lines)

    host.background(lambda: _read_list(host), done=done)
    host.back_button()


def _read_list(host):
    try:
        text = host.gh.read_file(PROXY_FILE, ref="lab")
    except Exception as e:
        host.log("proxy list read:", e)
        return None
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def list_view(host, heading, lines):
    host.title(heading)
    if lines is None:
        host.text("No saved list yet. Use \"Find new working proxies\".")
    elif not lines:
        host.text("The list is empty.")
    else:
        host.text("%d proxies:\n%s" % (len(lines), "\n".join(lines)))
    host.status()
    if lines:
        host.button("Copy the list", lambda: (host.copy("\n".join(lines)), host.set_status("Copied")))
    host.back_button()


# ---------------------------------------------------------------- default configs
def _read_configs(host):
    """(updated text, ['vless host:port', ...]) from the saved list. Keys are never shown."""
    from urllib.parse import urlsplit
    try:
        text = host.gh.read_file(CONFIG_FILE, ref="lab")
    except Exception as e:
        host.log("config list read:", e)
        return None
    updated, items = "", []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("# Updated:"):
            updated = ln[10:].strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            u = urlsplit(ln)
            items.append("%s %s:%s" % (u.scheme, u.hostname, u.port))
        except Exception:
            items.append(ln.split("://")[0] + " (config)")
    return updated, items


def configs_find_screen(host):
    host.title("Refreshing configs")
    host.text("Runs lab-refresh-configs.yml: tests the nodes of the default subscription and "
              "keeps the best few. It takes a few minutes; the result is saved on GitHub even "
              "if you leave this screen.")
    host.status(height=560)
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-refresh-configs.yml", {})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-refresh-configs run", run_id)
        conclusion = _wait(host, run_id)
        return conclusion, _read_configs(host)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        conclusion, info = res
        host.replace(configs_view, "Run finished: %s" % conclusion, info)

    host.background(work, done=done)
    host.back_button()


def configs_list_screen(host):
    host.title("Default configs")
    host.status()
    host.set_status("Reading...")

    def done(info, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(configs_view, "Default configs", info)

    host.background(lambda: _read_configs(host), done=done)
    host.back_button()


def configs_view(host, heading, info):
    host.title(heading)
    if info is None:
        host.text("No saved configs yet. Use \"Refresh default configs\".")
    else:
        updated, items = info
        if not items:
            host.text("The list is empty.")
        else:
            host.text("%d configs (updated %s):\n%s" % (len(items), updated or "?", "\n".join(items)))
    host.status()
    host.back_button()


# ------------------------------------------------ failure logs (config branch, lab-logs/)
def _lab_log_name(mode, url):
    import hashlib
    from urllib.parse import urlsplit
    try:
        site = (urlsplit(url or "").netloc or "site").lower().replace("www.", "")
    except Exception:
        site = "site"
    site = re.sub(r"[^a-z0-9.-]", "", site)[:40] or "site"
    short = hashlib.sha1((url or "").encode("utf-8", "ignore")).hexdigest()[:6]
    return "%s-%s-%s-%s.txt" % (time.strftime("%Y%m%d-%H%M%S", time.gmtime()), mode, site, short)


def _lab_log_text(mode, r):
    """The log of ONE link that this phone could not read. The link is saved without ?query / #fragment."""
    from urllib.parse import urlsplit, urlunsplit
    url = r.get("url") or ""
    try:
        p = urlsplit(url)
        shown = urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except Exception:
        shown = url.split("?", 1)[0].split("#", 1)[0]
    lines = [
        "Lab link failure log",
        "mode: %s" % mode,
        "time (UTC): %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "url: %s" % shown,
        "title: %s" % (r.get("title") if r.get("title") != url else ""),
        "extractor: %s" % (r.get("extractor") or ""),
        "error: %s" % (r.get("error") or "no video link found"),
        "note: %s" % (r.get("note") or ""),
        "video-only heights: %s" % (r.get("video_heights") or ""),
        "",
        "---- details ----",
        (r.get("size_debug") or "")[:6000],
    ]
    return "\n".join(lines) + "\n"


def _phone_save_logs(host, failed):
    host.set_status("Saving %d log file(s)..." % len(failed))

    def work():
        from api.github import repo_files
        saved = []
        for r in failed:
            name = _lab_log_name("phone", r.get("url") or "")
            repo_files.replace_file("config", "lab-logs/" + name,
                                    _lab_log_text("phone", r).encode("utf-8"), "lab log (phone): " + name)
            saved.append(name)
        return saved

    def done(res, err):
        if err is not None:
            host.set_status("Could not save the log: %s" % str(err)[:80])
            host.log("save log failed:", err)
            return
        host.set_status("Saved %d log file(s) to config/lab-logs" % len(res))

    host.background(work, done=done)


def _copy_log(host):
    """Copies only the END of the log (the newest lines, at most 60 lines / 7000 characters): the whole
    log is kept on the phone (400 lines) and is too long to paste."""
    try:
        text = host._log.text()
    except Exception:
        host.show_log()
        return
    lines = (text or "").splitlines()[-60:]
    out = "\n".join(lines)[-7000:]
    host.copy(out or "(empty)")
    host.set_status("Copied the last %d lines" % len(lines) if lines else "The log is empty")


def _clear_log(host):
    try:
        host._log.clear()
        host.set_status("Log cleared")
    except Exception as e:
        host.set_status("Could not clear: %s" % str(e)[:60])
