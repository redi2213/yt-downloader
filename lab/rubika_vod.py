"""Rubika VOD links - runs on THIS phone (Irancell IP).

Gives the direct (signed .m3u8) links of a vod.rubika.ir movie or series.
Same API calls the Rubika web page makes: getAccountInfo, getMedia, getSeasonEpisodes, getPlayInfo.
Every run writes a log to the repo (config branch, diag-results/rubika-latest.txt) so it can be read
without copying anything, and the screen has a Copy log button.
"""
import base64
import json
import platform
import random
import re
import string
import sys
import time
import traceback
from urllib.parse import urljoin

API = "https://rbvod30.iranlms.ir/"
UA = ("Mozilla/5.0 (Linux; Android 13; M2101K6G Build/TKQ1.221013.002) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Version/4.0 Chrome/158.0.8127.46 Mobile Safari/537.36")
QUALITIES = ["master", "all", "1080p", "720p", "468p", "360p"]
MAX_BUTTONS = 60
REPO = "redi2213/yt-downloader"
GH_API = "https://api.github.com/repos/" + REPO
LOG_BRANCH = "config"
LOG_PATH = "diag-results/rubika-latest.txt"


class Blocked(Exception):
    pass


class Fail(Exception):
    pass


def _hide(s):
    return re.sub(r"token=[^&\s\"']+", "token=<hidden>", str(s))


def _http(method, url, headers, payload=None):
    """Return (status code, text). requests inside the APK, urllib as fallback."""
    try:
        import requests
    except Exception:
        requests = None
    if requests is not None:
        r = requests.request(method, url, headers=headers, data=payload, timeout=30)
        return r.status_code, r.content.decode("utf-8", "replace")
    import urllib.error
    import urllib.request
    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


class Rubika:
    def __init__(self, auth, log):
        self.log = log
        self.guest = not auth
        self.auth = auth or "".join(random.choice(string.ascii_lowercase) for _ in range(32))
        self.hdr = {"Content-Type": "application/json", "Accept": "application/json, text/plain, */*",
                    "User-Agent": UA, "Origin": "https://vod.rubika.ir", "Referer": "https://vod.rubika.ir/"}

    def call(self, method, data):
        body = {"auth": self.auth, "api_version": "1",
                "client": {"app_name": "Main", "app_version": "0.1.0", "package": "vod.rubika.ir",
                           "platform": "VODWeb", "lang_code": "fa"},
                "data": data, "method": method}
        payload = json.dumps(body).encode()
        last = ""
        for attempt in range(1, 4):
            t0 = time.time()
            try:
                code, text = _http("POST", API, self.hdr, payload)
            except Exception as e:
                last = "%s: %s %s" % (method, type(e).__name__, e)
                self.log.append("  %s try%d EXC %s" % (method, attempt, _hide(last)))
                time.sleep(2)
                continue
            dt = time.time() - t0
            if code == 403:
                self.log.append("  %s try%d HTTP 403 (%.1fs)" % (method, attempt, dt))
                raise Blocked()
            if code != 200:
                last = "%s: HTTP %s" % (method, code)
                self.log.append("  %s try%d HTTP %s (%.1fs) body=%s" % (method, attempt, code, dt, _hide(text[:200])))
                time.sleep(2)
                continue
            try:
                j = json.loads(text)
            except ValueError:
                last = "%s: the answer is not JSON" % method
                self.log.append("  %s try%d not JSON (%.1fs) body=%s" % (method, attempt, dt, _hide(text[:200])))
                time.sleep(2)
                continue
            d = j.get("data") or {}
            if j.get("status") != "OK":
                self.log.append("  %s try%d %s / %s (%.1fs)" % (method, attempt, j.get("status"), j.get("status_det"), dt))
                raise Fail("%s: %s / %s" % (method, j.get("status"), j.get("status_det")))
            keys = ",".join(sorted(d.keys())) if isinstance(d, dict) else type(d).__name__
            extra = ""
            if method == "getPlayInfo":
                extra = " has_access=%s play_url=%s" % (d.get("has_access"), _hide(((d.get("play_data") or {}).get("play_url") or "")[:110]))
            self.log.append("  %s OK (%.1fs) keys=[%s]%s" % (method, dt, keys, extra))
            return d
        raise Fail(last or method + " failed")


def _pick(n, eps):
    eps = (eps or "all").strip().lower()
    if eps in ("", "all"):
        return set(range(1, n + 1))
    if eps == "last":
        return {n}
    r = re.fullmatch(r"(\d+)\s*-\s*(\d+)", eps)
    if r:
        return set(range(int(r.group(1)), int(r.group(2)) + 1))
    if eps.isdigit():
        return {int(eps)}
    raise Fail("Episodes must be: all, last, a number like 3, or a range like 2-5")


def _variants(master, log):
    hdr = {"User-Agent": UA, "Referer": "https://vod.rubika.ir/", "Origin": "https://vod.rubika.ir"}
    try:
        code, text = _http("GET", master, hdr)
    except Exception as e:
        log.append("  master playlist: %s %s" % (type(e).__name__, e))
        return []
    log.append("  master playlist HTTP %s, %d chars" % (code, len(text)))
    if code != 200:
        return []
    lines = text.splitlines()
    res = []
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            u = urljoin(master, lines[i + 1].strip())
            q = re.search(r"out_([0-9a-z]+)\.m3u8", u)
            res.append((q.group(1).lower() if q else "variant", u))
    return res


def collect(page, season, eps, quality, auth, log):
    """Blocking work (run in a background thread). Returns a result dict."""
    page = (page or "").strip()
    m = re.search(r"/media/(\d+)", page)
    mid = m.group(1) if m else (page if page.isdigit() else "")
    if not mid:
        raise Fail("Give the Rubika link, like https://vod.rubika.ir/media/291423 (or only the number)")
    season = (season or "all").strip().lower()
    quality = (quality or "master").strip().lower()
    cl = Rubika((auth or "").strip(), log)
    log.append("media id %s | season=%s episodes=%s quality=%s | %s" % (
        mid, season, eps, quality, "guest auth (random)" if cl.guest else "your auth"))
    try:
        acc = cl.call("getAccountInfo", {}).get("subscription_info") or {}
        log.append("  subscription_info: %s" % json.dumps({k: acc.get(k) for k in (
            "has_paid_subscription", "has_network_subscription", "network_subscription_type")}))
        if not acc.get("has_network_subscription") and not acc.get("has_paid_subscription"):
            log.append("  WARNING: Rubika does not see an Irancell network (Wi-Fi or VPN on?) and the account has no subscription")
    except (Fail, Blocked) as e:
        log.append("  account check failed: %s" % (e or "HTTP 403"))
    try:
        media = cl.call("getMedia", {"media_id": mid}).get("media") or {}
        mtype = media.get("media_type") or ""
        title = (media.get("title") or mid).replace("|", "-")
        log.append("title=%s type=%s" % (title, mtype))
        items = []
        if mtype == "Series":
            seasons = media.get("seasons") or []
            if not seasons:
                raise Fail("This series has no seasons in the answer")
            if eps.strip().lower() == "last" and season == "all":
                seasons = seasons[-1:]
            for si, s in enumerate(seasons, 1):
                snum = s.get("season_number") or si
                if season != "all" and str(snum) != season:
                    continue
                el = cl.call("getSeasonEpisodes", {"series_id": mid, "season_id": s.get("season_id"),
                                                   "section_type": "MediaInfo"}).get("episodes") or []
                keep = _pick(len(el), eps)
                log.append("season %s: %d episodes" % (snum, len(el)))
                for ei, ep in enumerate(el, 1):
                    if ei in keep:
                        name = (ep.get("title") or "").replace("|", "-")
                        items.append(("S%02dE%02d %s" % (int(snum), ei, name), ep.get("media_id")))
                time.sleep(0.3)
        else:
            items.append((title, mid))
        if not items:
            raise Fail("No episode matched (check the season and episodes boxes)")
        rows = []
        for label, eid in items[:200]:
            log.append("episode %s (id %s)" % (label, eid))
            try:
                d = cl.call("getPlayInfo", {"media_id": eid, "type": "Main", "version": 1})
            except Fail as e:
                log.append("  skip: %s" % e)
                continue
            if d.get("has_access") is False:
                log.append("  skip: no access (needs Irancell data, a subscription or a real login auth)")
                continue
            master = ((d.get("play_data") or {}).get("play_url") or "").strip()
            if not master:
                log.append("  skip: no play_url in the answer")
                continue
            got = []
            if quality in ("master", "all"):
                got.append(("master", master))
            if quality != "master":
                vs = _variants(master, log)
                if quality == "all":
                    got += vs
                else:
                    sel = [v for v in vs if v[0] == quality]
                    if sel:
                        got += sel
                    else:
                        log.append("  quality %s not found: giving the master link" % quality)
                        got.append(("master", master))
            for q, u in got:
                rows.append((label, q, u))
            time.sleep(0.3)
    except Blocked:
        raise Fail("Rubika answered HTTP 403: this network is blocked. Turn Wi-Fi/VPN off and use Irancell mobile data.")
    if not rows:
        raise Fail("No link was produced. See the log (last lines): " + " / ".join(x.strip() for x in log[-3:]))
    return {"title": title, "mtype": mtype, "mid": mid, "rows": rows}


# ---- log ----

def _report(host, params, log, result, error):
    head = ["Rubika VOD log", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "python %s | %s" % (sys.version.split()[0], platform.platform())]
    try:
        head.append("app_version=%s id=%s" % (getattr(host, "app_version", "?"), getattr(host, "id", "?")))
    except Exception:
        pass
    head.append("inputs: " + _hide(json.dumps(params, ensure_ascii=False)))
    out = head + ["", "--- steps ---"] + [_hide(x) for x in log] + ["", "--- result ---"]
    if error:
        out.append("FAILED: " + _hide(error))
    elif result:
        out.append("OK: %d link(s) for %s" % (len(result["rows"]), result["title"]))
        for label, q, u in result["rows"][:30]:
            out.append("  %s | %s | %s" % (label, q, _hide(u)[:140]))
    return "\n".join(out)


def _save(host, text):
    """Blocking: write the log to the config branch. Returns a short status."""
    try:
        url = GH_API + "/contents/" + LOG_PATH
        sha = None
        try:
            sha = host.gh.request("GET", url + "?ref=" + LOG_BRANCH).json().get("sha")
        except Exception:
            sha = None
        body = {"message": "rubika log", "branch": LOG_BRANCH,
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
        if sha:
            body["sha"] = sha
        host.gh.request("PUT", url, json=body)
        return "Log saved to the repo (config branch, %s)" % LOG_PATH
    except Exception as e:
        return "Log NOT saved to the repo: %s" % str(e)[:120]


# ---- screens ----

def build(host):
    host.title("Rubika VOD links (this phone)")
    host.text("Use Irancell mobile data (Wi-Fi and VPN off). Rubika plays video only there, "
              "and the signed links work only from this phone's network.")
    host.text("1) Rubika page link (movie or series):")
    url = host.input("https://vod.rubika.ir/media/291423")
    try:
        if host.prefill:
            url.text = str(host.prefill).strip()
    except Exception:
        pass
    host.text("2) Season: a number, or all")
    season = host.input("all")
    host.text("3) Episodes: all, last, a number like 3, or a range like 2-5")
    episodes = host.input("all")
    try:
        season.text = "all"
        episodes.text = "all"
    except Exception:
        pass
    host.text("4) Quality (master = one link that has all 4 qualities inside; all = every quality as its own link):")
    quality = host.choice(QUALITIES)
    host.text("5) Rubika auth: leave EMPTY (a guest auth is used). Fill it only if the log says the guest auth is refused.")
    auth = host.input("auth (optional)")
    host.button("Get links (this phone)", lambda: host.show(
        run, url.text.strip(), (season.text or "").strip() or "all", (episodes.text or "").strip() or "all",
        quality.value, (auth.text or "").strip()))
    host.status()
    host.back_button("Back")


def run(host, page, season, eps, quality, auth):
    host.title("Getting the links")
    host.status()
    host.set_status("Asking Rubika from this phone... (about 10-30 seconds)")
    log = []
    params = {"page": page, "season": season, "episodes": eps, "quality": quality, "own_auth": bool(auth)}

    def work():
        result, error = None, ""
        try:
            result = collect(page, season, eps, quality, auth, log)
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e) if not isinstance(e, Fail) else str(e)
            if not isinstance(e, Fail):
                log.append(traceback.format_exc())
        report = _report(host, params, log, result, error)
        saved = _save(host, report)
        return {"result": result, "error": error, "report": report, "saved": saved}

    def done(data, err):
        if err or not data:
            host.replace(show_error, "Plugin crashed: %s" % err, "\n".join(log), "not saved")
        elif data["error"]:
            host.replace(show_error, data["error"], data["report"], data["saved"])
        else:
            host.replace(show_results, data["result"], data["report"], data["saved"])

    host.background(work, done=done)
    host.back_button("Back")


def show_error(host, msg, report, saved):
    host.title("Failed")
    host.text(msg)
    host.text(saved)
    host.status()
    host.button("Copy log", lambda: (host.copy(report), host.set_status("Log copied")))
    host.text("Last lines of the log:\n" + "\n".join(report.splitlines()[-12:]))
    host.back_button("Back")


def show_results(host, res, report, saved):
    rows = res["rows"]
    host.title("%s (%d link)" % (res["title"], len(rows)))
    host.text("The links are signed and expire: use them soon, from this phone's network. " + saved)
    full = "\n".join("%s | %s | %s" % r for r in rows)
    urls = "\n".join(r[2] for r in rows)
    host.status()
    host.button("Copy all (name | quality | link)", lambda: (host.copy(full), host.set_status("Copied %d lines" % len(rows))))
    host.button("Copy links only", lambda: (host.copy(urls), host.set_status("Copied %d links" % len(rows))))
    host.button("Share links", lambda: host.share_text(full))
    host.button("Copy log", lambda: (host.copy(report), host.set_status("Log copied")))
    for label, q, u in rows[:MAX_BUTTONS]:
        host.button("%s [%s] - copy link" % (label[:40], q), lambda u=u, l=label, q=q: (host.copy(u), host.set_status("Copied: %s [%s]" % (l, q))))
    if len(rows) > MAX_BUTTONS:
        host.text("Only the first %d are listed as buttons; Copy all has every link." % MAX_BUTTONS)
    host.back_button("Back")
