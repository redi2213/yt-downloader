"""Lab: Diagnostics. Test buttons whose result is saved in the repo (no build needed).

Every button runs a check on this phone, shows the result here (with Copy) and
saves it to the config branch: diag-results/latest.txt (plus a timestamped copy,
last 20 kept). Claude reads that file, so nothing has to be pasted.

To add a check: write step_xxx(host) -> str and add it to STEPS (end of file).
Tokens, cookies and Authorization headers are hidden before saving.
"""
import base64
import html as _html
import inspect
import json
import os
import platform
import re
import sys
import time
import urllib.parse as _up

REPO = "redi2213/yt-downloader"
API = "https://api.github.com/repos/" + REPO
RESULT_BRANCH = "config"
RESULT_DIR = "diag-results"
KEEP = 20
MAX_STEP = 6000
MAX_TOTAL = 24000

_LAST = {"report": "", "saved": ""}
_PROBE = {"page": "", "media": [], "cookies": ""}
JOB_PATH = "diag-jobs/next.json"
VERSION = "2026-11-25e"

_HIDE = [
    (re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "<token>"),
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key)\b\s*[:=]\s*[^\n]+"), r"\1: <hidden>"),
    (re.compile(r"(?i)([?&;][\w-]*(?:token|key|secret|passw|sig|session|auth)[\w-]*)=[^&\s\"']+"), r"\1=<hidden>"),
]


def _hide(text):
    text = str(text)
    for rx, rep in _HIDE:
        text = rx.sub(rep, text)
    return text


# ---------------------------------------------------------------- steps
def step_env(host):
    out = ["time_utc: " + time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
           "python: " + sys.version.split()[0],
           "platform: %s / %s" % (sys.platform, platform.machine())]
    try:
        import kivy
        out.append("kivy: " + str(kivy.__version__))
    except Exception as e:
        out.append("kivy: n/a (%s)" % str(e)[:60])
    try:
        st = os.statvfs(os.getcwd())
        out.append("free_space_mb: %d" % (st.f_bavail * st.f_frsize // 1048576))
    except Exception as e:
        out.append("free_space_mb: n/a (%s)" % str(e)[:60])
    return "\n".join(out)


def step_ytdlp(host):
    try:
        from yt_dlp.version import __version__
        return "yt_dlp: " + str(__version__)
    except Exception as e:
        return "yt_dlp: not available (%s)" % str(e)[:100]


_NET = [("github_api", "https://api.github.com/zen"),
        ("youtube", "https://www.youtube.com/generate_204"),
        ("google", "https://www.google.com/generate_204")]


def step_net(host):
    out = []
    for name, url in _NET:
        t = time.time()
        try:
            r = host.get(url)
            out.append("%s: HTTP %s in %d ms" % (name, getattr(r, "status_code", "?"), (time.time() - t) * 1000))
        except Exception as e:
            out.append("%s: FAILED %s: %s" % (name, type(e).__name__, str(e)[:100]))
    return "\n".join(out)


def step_github(host):
    out = []
    r = host.gh.request("GET", API).json()
    out.append("repo: %s private=%s default_branch=%s" % (r.get("full_name"), r.get("private"), r.get("default_branch")))
    out.append("permissions: %s" % (r.get("permissions"),))
    try:
        core = host.gh.request("GET", "https://api.github.com/rate_limit").json()["resources"]["core"]
        out.append("rate_limit: %s of %s left" % (core.get("remaining"), core.get("limit")))
    except Exception as e:
        out.append("rate_limit: FAILED %s" % str(e)[:80])
    try:
        names = [b.get("name") for b in host.gh.request("GET", API + "/branches?per_page=30").json()]
        out.append("branches: " + ", ".join(names))
    except Exception as e:
        out.append("branches: FAILED %s" % str(e)[:80])
    return "\n".join(out)


def step_runs(host):
    runs = host.gh.request("GET", API + "/actions/runs?per_page=8").json().get("workflow_runs", [])
    out = []
    for w in runs:
        out.append("%s | %s/%s | %s | %s | %s" % (w.get("name"), w.get("status"), w.get("conclusion"),
                                                  w.get("head_branch"), w.get("created_at"), w.get("html_url")))
    return "\n".join(out) or "no runs"


def step_lablogs(host):
    items = host.gh.request("GET", API + "/contents/lab-logs?ref=" + RESULT_BRANCH).json()
    names = sorted(i.get("name", "") for i in items)
    return "count: %d\nlast 5 by name:\n%s" % (len(names), "\n".join(names[-5:]))


_UA = {"User-Agent": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"}
_MEDIA = re.compile(r"""https?://[^\s"'<>\\]+?\.(?:m3u8|mp4|webm|mpd|mkv)(?:\?[^\s"'<>\\]*)?""", re.I)


def _fetch(host, url):
    try:
        return host.get(url, headers=_UA)
    except TypeError:
        return host.get(url)


def _cookie_header(r):
    try:
        return "; ".join("%s=%s" % (k, v) for k, v in r.cookies.items())
    except Exception:
        return ""


def _uniq(items, n=15):
    seen = []
    for i in items:
        i = i.replace("&amp;", "&").strip()
        if i and i not in seen:
            seen.append(i)
    return seen[:n]


def step_probe(host, url):
    if not url.startswith("http"):
        return "No valid URL (must start with http)"
    r = _fetch(host, url)
    body = getattr(r, "text", "") or ""
    try:
        ctype = r.headers.get("content-type", "?")
    except Exception:
        ctype = "?"
    out = ["url: " + url, "HTTP %s, %d chars, content-type: %s" % (getattr(r, "status_code", "?"), len(body), ctype)]
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
    out.append("title: " + (_html.unescape(m.group(1)).strip()[:120] if m else "-"))
    txt = body.replace("\\/", "/")
    sections = [
        ("meta og:video / twitter:player", re.findall(r"(?i)<meta[^>]+(?:og:video[\w:]*|twitter:player[\w:]*)[^>]*content=[\"']([^\"']+)", txt)),
        ("video/source src", re.findall(r"(?i)<(?:video|source)[^>]+src=[\"']([^\"']+)", txt)),
        ("iframe src", re.findall(r"(?i)<iframe[^>]+src=[\"']([^\"']+)", txt)),
        ("media urls in page", _MEDIA.findall(txt)),
        ("JSON/JS video keys", re.findall(r"(?i)[\"']?(?:contentUrl|embedUrl|video_url|videoUrl|stream_url|hls|file)[\"']?\s*[:=]\s*[\"']([^\"']+)", txt)),
        ("external scripts", re.findall(r"(?i)<script[^>]+src=[\"']([^\"']+)", txt)),
    ]
    _PROBE["page"] = url
    _PROBE["body"] = body
    _PROBE["cookies"] = _cookie_header(r)
    out.append("cookies from page: %s" % (", ".join(c.split("=")[0] for c in _PROBE["cookies"].split("; ")) if _PROBE["cookies"] else "none"))
    try:
        sc = r.headers.get("set-cookie", "")
    except Exception:
        sc = ""
    out.append("set-cookie names: %s" % (", ".join(re.findall(r"(?:^|,\s*)([\w.-]+)=", sc)) or "none"))
    _PROBE["media"] = _uniq(_MEDIA.findall(txt))
    found = False
    for name, items in sections:
        items = _uniq(items)
        if items and not name.startswith("external"):
            found = True
        out.append("%s (%d):" % (name, len(items)))
        out.extend("  " + i[:200] for i in items)
    out.append("inline scripts: %d" % len(re.findall(r"(?i)<script(?![^>]*\bsrc=)", body)))
    if not found:
        out.append("NOTE: no video clue in the static HTML; it is probably loaded by JavaScript (needs Page Sniffer / network log).")
    return "\n".join(out)


def _call(fn, host, args):
    try:
        params = inspect.signature(fn).parameters
    except Exception:
        params = {}
    return fn(host, **dict((k, v) for k, v in args.items() if k in params))


def step_media_test(host, url="", referer="", count=3):
    """Fetches only the first 1 KB of each media link (stream) and shows what the server answers."""
    urls = [url] if url and url != "auto" else list(_PROBE["media"])
    if not urls:
        return "no media URL (run probe first in the same job, or give url)"
    ref = referer or _PROBE["page"]
    cookie = _PROBE.get("cookies", "")
    out = ["referer: %s" % (ref or "-"), "cookie sent: %s" % ("yes" if cookie else "no")]
    for n, u in enumerate(urls[:int(count)]):
        variants = [("rnd+ref+range", ref, cookie, True)]
        if n == 0:
            variants += [("rnd+ref+kt_tcookie", ref, (cookie + "; " if cookie else "") + "kt_tcookie=1", True), ("no rnd, ref+range", ref, cookie, True), ("bare, no ref/cookie", "", "", True)]
        for name, rf, ck, rng in variants:
            h = dict(_UA)
            if rng:
                h["Range"] = "bytes=0-1023"
            if rf:
                h["Referer"] = rf
            if ck:
                h["Cookie"] = ck
            if name.startswith("video"):
                h.update({"Accept": "*/*", "Sec-Fetch-Dest": "video", "Sec-Fetch-Mode": "no-cors", "Sec-Fetch-Site": "same-origin"})
            uu = u
            if name.startswith("rnd"):
                uu = u + ("&" if "?" in u else "?") + "rnd=%d" % int(time.time() * 1000)
            label = "%s [%s]" % (uu[:170], name)
            try:
                r = host.get(uu, headers=h, stream=True)
            except TypeError:
                out.append("%s -> skipped: host.get has no headers/stream support (would download the whole file)" % label)
                break
            except Exception as e:
                out.append("%s -> FAILED %s: %s" % (label, type(e).__name__, str(e)[:100]))
                continue
            head = b""
            try:
                head = next(r.iter_content(1024))
            except Exception:
                pass
            try:
                hd = r.headers
                info = " ".join("%s=%s" % (k, str(hd.get(k))[:80]) for k in
                                ("content-type", "content-length", "content-range", "server", "location", "content-disposition") if hd.get(k))
            except Exception:
                info = "headers n/a"
            try:
                r.close()
            except Exception:
                pass
            is_mp4 = head[4:8] == b"ftyp"
            body = "" if is_mp4 else " body=%r" % head[:120]
            out.append("%s -> HTTP %s %s first_bytes=%d ftyp=%s%s" % (label, getattr(r, "status_code", "?"), info, len(head), is_mp4, body))
    return "\n".join(out)


def step_context(host, pattern="get_stream", url="", width=250, limit=3):
    """Shows the text around matches of a regex, in the probed page or in another file (relative path ok)."""
    if url:
        target = _up.urljoin(_PROBE["page"] or url, url)
        r = _fetch(host, target)
        body = getattr(r, "text", "") or ""
        head = "%s: HTTP %s, %d chars" % (target, getattr(r, "status_code", "?"), len(body))
    else:
        body = _PROBE.get("body", "")
        head = "page (from probe), %d chars" % len(body)
    if not body:
        return head + "\nno content (run probe first)"
    out = [head]
    last_end = -1
    seen = 0
    for m in re.finditer(pattern, body, re.I):
        if m.start() < last_end:
            continue
        a = max(0, m.start() - int(width))
        b = min(len(body), m.end() + int(width))
        out.append("--- match at %d ---\n%s" % (m.start(), body[a:b].replace("\n", " ")))
        last_end = b
        seen += 1
        if seen >= int(limit):
            break
    if not seen:
        out.append("no match for: " + pattern)
    return "\n".join(out)


def _show_hdrs(hd):
    try:
        return " ".join("%s=%s" % (k, str(hd.get(k))[:100]) for k in
                        ("content-type", "content-length", "content-range", "server", "location", "content-disposition") if hd.get(k))
    except Exception:
        return "headers n/a"


def _hops(url, headers, limit):
    """Follows redirects by hand with `requests` (redirects off): every hop = status, Location, key headers."""
    import requests
    out, cur = [], url
    for i in range(int(limit)):
        try:
            r = requests.get(cur, headers=headers, allow_redirects=False, stream=True, timeout=20)
        except Exception as e:
            out.append("   hop %d -> FAILED %s: %s" % (i, type(e).__name__, str(e)[:120]))
            break
        head = b""
        if r.status_code < 300:
            try:
                head = next(r.iter_content(16))
            except Exception:
                pass
        loc = r.headers.get("Location")
        out.append("   hop %d %s -> HTTP %s %s%s" % (i, cur[:80], r.status_code, _show_hdrs(r.headers),
                                                  "" if loc else " first=%r" % head[:8]))
        r.close()
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            cur = _up.urljoin(cur, loc)
            continue
        break
    else:
        out.append("   (stopped after %d hops)" % int(limit))
    return out


def _followed(url, headers):
    """Same request with automatic redirects: where it ends (requests) and what yt-dlp's urlopen reports."""
    out = []
    try:
        import requests
        r = requests.get(url, headers=headers, stream=True, timeout=20)
        out.append("   requests+redirects -> HTTP %s final=%s via=%s %s" % (
            r.status_code, r.url[:150], [h.status_code for h in r.history], _show_hdrs(r.headers)))
        r.close()
    except Exception as e:
        out.append("   requests+redirects -> FAILED %s: %s" % (type(e).__name__, str(e)[:120]))
    try:
        import yt_dlp
        from yt_dlp.networking import Request
        ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "socket_timeout": 20})
        with ydl.urlopen(Request(url, headers=headers)) as r:
            fin = getattr(r, "url", None) or (r.geturl() if hasattr(r, "geturl") else "")
            out.append("   yt-dlp urlopen -> status=%s final=%s same_as_input=%s %s" % (
                getattr(r, "status", "?"), str(fin)[:150], str(fin) == url, _show_hdrs(r.headers)))
    except Exception as e:
        out.append("   yt-dlp urlopen -> FAILED %s: %s" % (type(e).__name__, str(e)[:120]))
    return out


_CHROME = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def step_redirects(host, url="", referer="", count=2, hops=8):
    """Follows the redirects of get_stream links hop by hop (requests, redirects off), then with automatic
    redirects (requests and yt-dlp urlopen = what Link Lab uses), for several header variants. Put it after probe."""
    urls = [url] if url and url != "auto" else list(_PROBE["media"])
    if not urls:
        return "no media URL (run probe first in the same job, or give url)"
    ref = referer or _PROBE["page"]
    ck = _PROBE.get("cookies", "")
    variants = [("short UA + Range + Referer (as _phone_final_url)", {"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0", "Referer": ref}),
                ("Chrome UA + Range + Referer", {"User-Agent": _CHROME, "Range": "bytes=0-0", "Referer": ref}),
                ("Chrome UA + Referer, no Range", {"User-Agent": _CHROME, "Referer": ref})]
    if ck:
        variants.append(("Chrome UA + Range + Referer + page cookie", {"User-Agent": _CHROME, "Range": "bytes=0-0", "Referer": ref, "Cookie": ck}))
    out = ["referer: %s | page cookie: %s" % (ref or "-", "yes" if ck else "no")]
    for u in urls[:int(count)]:
        out.append("== %s" % u[:120])
        for name, h in variants:
            out.append("  [%s]" % name)
            out.extend(_hops(u, h, hops))
            out.extend(_followed(u, h))
    return "\n".join(out)


def _cnames(c):
    return sorted(set(x.split("=")[0].strip() for x in (c or "").split(";") if "=" in x))


def _resp_line(tag, r):
    try:
        hist = [h.status_code for h in r.history]
        return "   %s -> HTTP %s final=%s via=%s cookies_sent=%s %s" % (
            tag, r.status_code, r.url[:110], hist, _cnames(r.request.headers.get("Cookie")), _show_hdrs(r.headers))
    except Exception as e:
        return "   %s -> %s: %s" % (tag, type(e).__name__, str(e)[:100])


def step_session_test(host, url="", count=2):
    """Does get_stream need the cookies the page itself sets? Three ways to read the page and then the fresh
    get_stream links: host.get (the app's long-lived session), a brand-new requests.Session, one yt-dlp
    YoutubeDL (like Link Lab). Each prints status, final address after redirects, cookie names sent."""
    page = url or _PROBE["page"]
    if not page:
        return "no url (give url of the video page)"
    n = int(count)
    out = ["page: " + page]

    def links(text):
        return _uniq(_MEDIA.findall((text or "").replace("\\/", "/")))[:n]

    # A) host.get: the app's session (keeps cookies between calls)
    out.append("[A host.get session]")
    try:
        r = host.get(page, headers=_UA)
        ls = links(getattr(r, "text", ""))
        out.append("   page HTTP %s, links=%d, cookies_sent=%s, set-cookie names=%s" % (
            getattr(r, "status_code", "?"), len(ls), _cnames(r.request.headers.get("Cookie")),
            re.findall(r"(?:^|,\s*)([\w.-]+)=", r.headers.get("set-cookie", "")) or "none"))
        for u in ls:
            h = dict(_UA, Range="bytes=0-0", Referer=page)
            rr = host.get(u, headers=h, stream=True)
            out.append(_resp_line(u.split("/get_stream/")[-1][:14], rr))
            rr.close()
    except Exception as e:
        out.append("   FAILED %s: %s" % (type(e).__name__, str(e)[:120]))

    # B) a brand-new requests session
    out.append("[B new requests.Session: page, then links]")
    try:
        import requests
        s = requests.Session()
        r = s.get(page, headers=_UA, timeout=20)
        ls = links(r.text)
        out.append("   page HTTP %s, links=%d, session cookies=%s" % (r.status_code, len(ls), sorted(s.cookies.keys())))
        for u in ls:
            rr = s.get(u, headers=dict(_UA, Range="bytes=0-0", Referer=page), stream=True, timeout=20)
            out.append(_resp_line(u.split("/get_stream/")[-1][:14], rr))
            rr.close()
    except Exception as e:
        out.append("   FAILED %s: %s" % (type(e).__name__, str(e)[:120]))

    # C) one yt-dlp YoutubeDL object: page, then links (what Link Lab does)
    out.append("[C one yt-dlp YoutubeDL: page, then links]")
    try:
        import yt_dlp
        from yt_dlp.networking import Request
        ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "socket_timeout": 20})
        with ydl.urlopen(Request(page, headers={"User-Agent": _CHROME})) as r:
            text = r.read(2000000).decode("utf-8", "replace")
        ls = links(text)
        out.append("   page links=%d, jar cookies=%s" % (len(ls), sorted(set(c.name for c in ydl.cookiejar))))
        for u in ls:
            with ydl.urlopen(Request(u, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0", "Referer": page})) as r:
                fin = getattr(r, "url", "") or ""
                out.append("   %s -> status=%s final=%s same=%s %s" % (u.split("/get_stream/")[-1][:14], getattr(r, "status", "?"),
                                                                    str(fin)[:110], str(fin) == u, _show_hdrs(r.headers)))
    except Exception as e:
        out.append("   FAILED %s: %s" % (type(e).__name__, str(e)[:120]))
    return "\n".join(out)


def step_net_identity(host, site="www.thepornbang.com"):
    """Which network the phone is on right now: country and provider (no IP address is printed, the repo is
    public), IPv4/IPv6, proxy settings in the environment, and the address family the site resolves to."""
    out = []
    try:
        j = host.get("https://ipinfo.io/json", headers=_UA).json()
        ip = str(j.get("ip", ""))
        out.append("ipinfo: country=%s org=%s family=%s" % (j.get("country"), j.get("org"), "IPv6" if ":" in ip else "IPv4"))
    except Exception as e:
        out.append("ipinfo FAILED %s: %s" % (type(e).__name__, str(e)[:100]))
    try:
        t = host.get("https://www.cloudflare.com/cdn-cgi/trace", headers=_UA).text
        kv = dict(l.split("=", 1) for l in t.splitlines() if "=" in l)
        out.append("cloudflare trace: loc=%s colo=%s warp=%s http=%s" % (kv.get("loc"), kv.get("colo"), kv.get("warp"), kv.get("http")))
    except Exception as e:
        out.append("cloudflare trace FAILED %s: %s" % (type(e).__name__, str(e)[:100]))
    env = [k for k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "no_proxy", "NO_PROXY") if os.environ.get(k)]
    out.append("proxy env vars set: %s" % (", ".join(env) or "none"))
    try:
        import requests
        px = requests.utils.get_environ_proxies("https://" + site)
        out.append("requests proxies for site: %s" % ({k: _up.urlsplit(v).scheme + "://<host>" for k, v in px.items()} or "none"))
    except Exception as e:
        out.append("requests proxies check FAILED: %s" % str(e)[:80])
    try:
        import socket
        fam = {}
        for a in socket.getaddrinfo(site, 443, proto=socket.IPPROTO_TCP):
            fam.setdefault("IPv6" if a[0] == socket.AF_INET6 else "IPv4", []).append(a[4][0])
        out.append("%s resolves to: %s" % (site, {k: v[:2] for k, v in fam.items()}))
    except Exception as e:
        out.append("resolve FAILED: %s" % str(e)[:80])
    return "\n".join(out)


def step_phone_rows(host, url=""):
    """Shows what yt-dlp returns for the page and what Link Lab's _phone_kvs builds (height, size, link), to see
    where an 'unknown height' row with a get_stream link comes from."""
    url = url or _PROBE["page"]
    if not url:
        return "no url (run probe first in the same job, or give url)"
    out = ["page: " + url]
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        out.append("yt-dlp: extractor=%s entries=%s" % (info.get("extractor"), len(info.get("entries") or [])))
        fm = list(info.get("formats") or ([info] if info.get("url") else []))
        for f in fm:
            out.append("  fmt id=%s height=%s ext=%s proto=%s url=%s" % (
                f.get("format_id"), f.get("height"), f.get("ext"), f.get("protocol"), str(f.get("url"))[:150]))
        if not fm:
            out.append("  (no formats)")
    except Exception as e:
        out.append("yt-dlp FAILED: %s: %s" % (type(e).__name__, str(e).strip().splitlines()[-1][:160]))
    mod = None
    try:
        for m in list(sys.modules.values()):
            if getattr(m, "_phone_kvs", None) and getattr(m, "_phone_final_url", None):
                mod = m
                break
    except Exception:
        mod = None
    if mod is None:
        out.append("Link Lab module not found in memory (open Lab > Link Lab once, then run this job again)")
        return "\n".join(out)
    try:
        res = mod._phone_kvs(url)
        out.append("_phone_kvs: %s" % ("None" if not res else "note=" + str(res.get("note"))[:200]))
        for r in (res or {}).get("rows", []):
            out.append("  row h=%s size=%r kvs=%s hdr=%s url=%s" % (
                r.get("h"), r.get("size"), r.get("_kvs"), sorted((r.get("_hdr") or {}).keys()), str(r.get("url"))[:170]))
    except Exception as e:
        out.append("_phone_kvs FAILED: %s: %s" % (type(e).__name__, str(e)[:160]))
    return "\n".join(out)


# Steps that need arguments: used only by Claude's job (diag-jobs/next.json).
ARG_STEPS = [
    ("probe", "Page probe", step_probe),
    ("media_test", "Media link test", step_media_test),
    ("context", "Context grep", step_context),
    ("redirects", "Redirect trace (hop by hop)", step_redirects),
    ("session_test", "Session test (page, then get_stream)", step_session_test),
    ("net_identity", "Network identity (country, provider, proxy)", step_net_identity),
    ("phone_rows", "Link Lab rows (yt-dlp vs player settings)", step_phone_rows),
]


# (id, button title, function). Add new checks here.
STEPS = [
    ("env", "Environment (phone, python, space)", step_env),
    ("ytdlp", "yt-dlp version", step_ytdlp),
    ("net", "Network reach (GitHub, YouTube, Google)", step_net),
    ("github", "GitHub access (token, repo, branches)", step_github),
    ("runs", "Last workflow runs", step_runs),
    ("lablogs", "Lab failed-link logs (list)", step_lablogs),
]


# ---------------------------------------------------------------- saving
def _put(host, path, text, msg):
    url = API + "/contents/" + path
    sha = None
    try:
        sha = host.gh.request("GET", url + "?ref=" + RESULT_BRANCH).json().get("sha")
    except Exception:
        sha = None
    body = {"message": msg, "branch": RESULT_BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    host.gh.request("PUT", url, json=body)


def _prune(host):
    try:
        items = host.gh.request("GET", API + "/contents/" + RESULT_DIR + "?ref=" + RESULT_BRANCH).json()
        old = sorted((i for i in items if i.get("name", "").endswith(".txt") and i.get("name") != "latest.txt"),
                     key=lambda i: i["name"])
        for i in old[:-KEEP]:
            host.gh.request("DELETE", API + "/contents/" + i["path"],
                            json={"message": "diag: prune", "sha": i["sha"], "branch": RESULT_BRANCH})
    except Exception:
        pass


def _save(host, report, tag):
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    try:
        _put(host, RESULT_DIR + "/latest.txt", report, "diag: " + tag)
        _put(host, "%s/%s-%s.txt" % (RESULT_DIR, stamp, tag), report, "diag: " + tag)
    except Exception as e:
        return "NOT saved to repo: %s" % str(e)[:120]
    _prune(host)
    return "Saved: %s branch, %s/latest.txt" % (RESULT_BRANCH, RESULT_DIR)


# ---------------------------------------------------------------- screens
def build(host):
    host.title("Diagnostics")
    host.text("Each button runs a check, saves the result to the repo "
              "(config branch, diag-results/latest.txt) and shows it here with Copy. "
              "Then just tell Claude it is done.")
    host.status()
    host.button("Run Claude's job (ready-made task)", lambda: _run_job(host))
    host.button("Run all", lambda: _run(host, STEPS, "all"))
    for s in STEPS:
        host.button(s[1], lambda s=s: _run(host, [s], s[0]))
    host.button("Page probe (enter a URL)", lambda: host.show(probe_screen))
    host.button("Show last result", lambda: host.show(result_screen))
    host.back_button("Back")


def probe_screen(host):
    host.title("Page probe")
    host.text("Enter a page URL. The phone fetches the page and lists the video clues it finds "
              "(iframes, sources, m3u8/mp4 links). The result is saved to the repo.")
    field = host.input("Page URL")
    try:
        saved = host.store.get("probe_url", "")
        if saved:
            field.text = saved
    except Exception:
        pass
    host.status()

    def go():
        url = (field.text or "").strip()
        try:
            host.store.set("probe_url", url)
        except Exception:
            pass
        _run(host, [("probe", "Page probe", lambda h: step_probe(h, url))], "probe")

    host.button("Probe this page", go)
    host.back_button()


def result_screen(host):
    host.title("Result")
    host.status()
    host.set_status(_LAST["saved"] or "Nothing run yet")
    rep = _LAST["report"]
    if rep:
        shown = rep[:2500]
        if len(rep) > 2500:
            shown += "\n... (cut here; Copy gives everything)"
    else:
        shown = "Nothing run yet."
    host.text(shown)
    host.button("Copy all", lambda: host.copy(_LAST["report"] or "(empty)"))
    host.back_button()


def _report(host, selected, tag, head=""):
    parts = ["# Diagnostics (%s) %s UTC, diag.py v%s" % (tag, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()), VERSION)]
    if head:
        parts.append(_hide(head))
    for sid, title, fn in selected:
        try:
            txt = fn(host)
        except Exception as e:
            txt = "ERROR %s: %s" % (type(e).__name__, str(e)[:200])
        parts.append("## %s (%s)\n%s" % (title, sid, _hide(txt)[:MAX_STEP]))
    return "\n\n".join(parts)[:MAX_TOTAL]


def _finish(host):
    def done(result, error):
        if error:
            host.set_status("Failed: %s" % str(error)[:120])
            return
        _LAST["report"], _LAST["saved"] = result
        host.set_status(result[1])
        host.show(result_screen)
    return done


def _run(host, selected, tag):
    host.set_status("Running %d check(s)..." % len(selected))

    def work():
        report = _report(host, selected, tag)
        return report, _save(host, report, tag)

    host.background(work, done=_finish(host))


def _read_job(host):
    r = host.gh.request("GET", API + "/contents/" + JOB_PATH + "?ref=" + RESULT_BRANCH).json()
    return json.loads(base64.b64decode(r["content"]).decode("utf-8"))


def _run_job(host):
    host.set_status("Reading Claude's job...")

    def inner():
        job = _read_job(host)
        known = dict((s[0], s) for s in STEPS + ARG_STEPS)
        selected = []
        for item in job.get("steps", []):
            sid = str(item.get("step"))
            args = dict((k, v) for k, v in item.items() if k != "step")
            if sid in known:
                _, title, fn = known[sid]
                title = str(item.get("label") or title)
                selected.append((sid, title, lambda h, fn=fn, args=args: _call(fn, h, args)))
            else:
                selected.append((sid, "Unknown step", lambda h, sid=sid: "unknown step: " + sid))
        head = "job: %s\ntitle: %s" % (job.get("id"), job.get("title"))
        report = _report(host, selected, "job", head)
        return report, _save(host, report, "job")

    def work():
        try:
            return inner()
        except Exception:
            import traceback
            report = "# Diagnostics (job) FAILED\n" + _hide(traceback.format_exc())[-3000:]
            return report, _save(host, report, "job-error")

    host.background(work, done=_finish(host))
