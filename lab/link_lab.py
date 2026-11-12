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
QUALITIES = [("Best", "best"), ("1080", "1080"), ("720", "720"), ("480", "480")]
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
    if host.prefill and not S["urls"]:
        S["urls"] = host.prefill
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

    host.button("Get links only", lambda: need() and host.show(links_screen))
    host.button("Get links only (this phone)", lambda: need() and host.show(phone_screen))
    host.button("Download to a GitHub release", lambda: need() and start_download(host))
    host.button("Options (proxy / v2ray)", lambda: (grab(), host.show(options_screen)))
    host.button("Free proxies", lambda: (grab(), host.show(proxies_screen)))
    host.button("Show log", host.show_log)
    host.back_button("Back")


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
def links_screen(host):
    host.title("Getting links")
    host.text("Runs lab-links.yml on GitHub (about a minute). You can leave this screen; "
              "the run keeps going.")
    host.status()
    host.set_status("Starting...")
    inputs = {"url": S["urls"], "proxy": S["proxy"], "v2ray_config": S["v2ray"]}

    def work():
        run_id = host.gh.dispatch("lab-links.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-links run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
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
        host.text("Download one quality (runs lab-download.yml and makes a GitHub release):")
        for title, page, height, link, size in picks[:12]:
            sfx = (" \u2022 " + size) if size else ""
            label = "Download %dp%s" % (height, sfx)
            if len({p[1] for p in picks}) > 1:
                label += " - " + (title[:22] or page[:22])
            host.row([
                (label, lambda p=page, h=height: _run_download(host, p, str(h))),
                ("Copy %dp link%s" % (height, sfx),
                 lambda u=link, h=height: (host.copy(u), host.set_status("Copied %dp link" % h))),
            ])
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
        host.replace(phone_result, res)

    host.background(work, done=done)
    host.back_button()


def phone_result(host, results):
    ok = sum(1 for r in results if r.get("rows"))
    host.title("Links on this phone (%d of %d)" % (ok, len(results)))
    blocks = [_phone_block(r) for r in results]
    for r in results:
        host.text(_phone_block(r))
        page = r.get("url") or ""
        for row in (r.get("rows") or [])[:12]:
            label = _phone_label(row)
            host.row([
                ("Copy " + label, lambda u=row["url"], lab=label: (host.copy(u), host.set_status("Copied " + lab))),
                ("Download " + label,
                 lambda p=page, h=row.get("h"), lk=row["url"], t=r.get("title") or "": _run_download(host, p, str(h or "best"), lk, t)),
            ])
        extra = len(r.get("rows") or []) - 12
        if extra > 0:
            host.text("(%d more qualities not shown)" % extra)
    host.status()
    host.text("Copy uses the link this phone just read. Download still runs lab-download.yml on GitHub.")
    report = "\n\n".join(blocks)
    if any(r.get("rows") for r in results):
        host.button("Copy report", lambda: (host.copy(report), host.set_status("Copied")))
    host.back_button()


def _phone_block(r):
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
            "socket_timeout": 30, "retries": 2}
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
    if on_status:
        on_status("Done")
    return out


def _phone_one(yt_dlp, opts, url):
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
    rows, video_heights = _phone_formats(info)
    if not rows and video_heights:
        note = (note + " " if note else "") + "Picture and sound come as separate streams."
    return {"url": url, "title": info.get("title") or url,
            "extractor": info.get("extractor") or info.get("extractor_key") or "",
            "note": note.strip(), "rows": rows, "video_heights": video_heights}


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
        v = f.get("vcodec") not in (None, "none")
        a = f.get("acodec") not in (None, "none")
        h = _phone_height(f)
        if v and a:
            both.append({"h": h, "ext": "mp4" if "m3u8" in proto else (f.get("ext") or "mp4"),
                         "hls": "m3u8" in proto,
                         "size": _phone_size(f.get("filesize") or f.get("filesize_approx")),
                         "url": link.split("#")[0], "_bytes": _phone_bytes(f)})
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
# byte 0 only (Range) and multiply by the segment count. A few KB of phone data per quality.
def _phone_http(url, headers=None, timeout=15):
    import urllib.request
    h = {"User-Agent": "Mozilla/5.0"}
    if headers:
        h.update(headers)
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout)


def _phone_text(url):
    try:
        with _phone_http(url) as r:
            return r.read(2000000).decode("utf-8", "replace")
    except Exception:
        return ""


def _phone_range_size(url):
    try:
        with _phone_http(url, {"Range": "bytes=0-0"}) as r:
            m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range") or "")
            if m:
                return int(m.group(1))
            n = r.headers.get("Content-Length") or ""
            if getattr(r, "status", 0) == 200 and n.isdigit():
                return int(n)
    except Exception:
        pass
    return None


def _phone_hls_estimate(url):
    from urllib.parse import urljoin
    text = _phone_text(url)
    if "#EXTM3U" not in text:
        return None
    if "#EXT-X-STREAM-INF" in text:
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                for nxt in lines[i + 1:]:
                    if nxt.strip() and not nxt.startswith("#"):
                        url = urljoin(url, nxt.strip())
                        break
                break
        text = _phone_text(url)
        if "#EXTM3U" not in text:
            return None
    segs = [urljoin(url, ln.strip()) for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not segs:
        return None
    n = len(segs)
    sizes = [s for s in (_phone_range_size(segs[i]) for i in sorted({0, n // 3, (2 * n) // 3})) if s]
    return int(sum(sizes) / len(sizes) * n) if sizes else None


def _phone_add_sizes(res):
    from concurrent.futures import ThreadPoolExecutor
    rows = [r for r in (res.get("rows") or []) if not r.get("size")]
    if not rows:
        return

    def one(row):
        try:
            link = row.get("url") or ""
            if row.get("hls") or ".m3u8" in link:
                n = _phone_hls_estimate(link)
                if n:
                    row["size"] = "~" + _phone_size(n)
            else:
                n = _phone_range_size(link)
                if n:
                    row["size"] = _phone_size(n)
        except Exception:
            pass

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, rows))


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
    host.status()
    host.set_status("Starting...")
    inputs = {"url": url, "quality": str(quality), "proxy": S["proxy"], "v2ray_config": S["v2ray"]}
    # The link this phone already found goes to GitHub, so the run skips its own (slow) extract step.
    # Links tied to an IP (data=1.2.3.4) would not work from GitHub, so those are not sent.
    if link and link.startswith("http") and len(link) < 60000 and not re.search(r"data=\d+\.\d+\.\d+\.\d+", link):
        inputs["direct_link"] = link
        inputs["direct_title"] = (title or "")[:200]
        host.text("Using the link found on this phone: GitHub skips the extract step.")

    def work():
        run_id = host.gh.dispatch("lab-download.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-download run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
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
    host.status()
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-find-proxies.yml",
                                  {"needed": "8", "max_candidates": "100", "xh_check": "0"})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-find-proxies run", run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
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
    host.status()
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-refresh-configs.yml", {})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-refresh-configs run", run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
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
