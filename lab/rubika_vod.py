"""Rubika VOD links - runs on THIS phone (Irancell IP).

Gives the direct (signed .m3u8) links of a vod.rubika.ir movie or series.
Same API calls the Rubika web page makes: getAccountInfo, getMedia, getSeasonEpisodes, getPlayInfo.
Every run writes a log to the repo (config branch, diag-results/rubika-latest.txt) so it can be read
without copying anything, and the screen has a Copy log button.
"""
import base64
import json
import json as J
import os
import platform
import random
import re
import string
import sys
import time
import threading
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


def _find_auth(data):
    reqs = data.get("requests") if isinstance(data, dict) else data
    for r in reqs or []:
        if "rbvod" in str(r.get("url", "")) and r.get("body"):
            try:
                a = J.loads(r["body"]).get("auth")
            except Exception:
                a = None
            if a:
                return str(a)
    return ""


def _export_auth(log):
    """Read the Rubika auth the web page used from your newest Browser export (private repo yt-exports)."""
    try:
        from api import export_prefs
    except Exception as e:
        raise Fail("Cannot read the exports settings (%s)" % e)
    tok = export_prefs.get_token()
    if not tok:
        raise Fail("No exports token: add it in Settings > Account and sign-in")
    base = "https://api.github.com/repos/%s/contents/" % export_prefs.REPO
    hdr = {"Authorization": "token " + tok, "Accept": "application/vnd.github+json", "User-Agent": "ytbridge"}
    raw = dict(hdr, Accept="application/vnd.github.raw+json")
    code, text = _http("GET", base + "vod.rubika.ir?ref=" + export_prefs.BRANCH, hdr)
    if code != 200:
        raise Fail("Exports repo folder vod.rubika.ir: HTTP %s (make a Browser > Export cookies > Full page export on vod.rubika.ir while logged in)" % code)
    names = sorted((i["name"] for i in J.loads(text) if i.get("type") == "dir"), reverse=True)
    for name in names[:3]:
        code, text = _http("GET", base + "vod.rubika.ir/%s/requests.json?ref=%s" % (name, export_prefs.BRANCH), raw)
        if code != 200:
            log.append("  export %s requests.json: HTTP %s" % (name, code))
            continue
        try:
            a = _find_auth(J.loads(text))
        except ValueError:
            a = ""
        if a:
            log.append("  auth taken from export %s (%d chars)" % (name, len(a)))
            return a
        log.append("  export %s has no Rubika API request with an auth" % name)
    raise Fail("No auth found in the newest vod.rubika.ir exports: log in on the site in the Browser, play a video, then Full page export")


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
        counts = {}
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
                counts[str(snum)] = len(el)
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
    return {"title": title, "mtype": mtype, "mid": mid, "rows": rows, "counts": counts}


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


def _save(host, text, path=None):
    """Blocking: write the log to the config branch. Returns a short status."""
    try:
        url = GH_API + "/contents/" + (path or LOG_PATH)
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
    host.text("5) Rubika auth: leave EMPTY. It is taken by itself from your newest Browser export of vod.rubika.ir (you must be logged in there).")
    auth = host.input("auth (optional)")
    host.button("Get links (this phone)", lambda: host.show(
        run, url.text.strip(), (season.text or "").strip() or "all", (episodes.text or "").strip() or "all",
        quality.value, (auth.text or "").strip()))
    host.button("Followed series (%d)" % len(_load(host)), lambda: host.show(series_list))
    host.status()
    host.back_button("Back")
    try:
        if not host.store.get("follow_off", False):
            _follow_start(host)
    except Exception:
        pass


def run(host, page, season, eps, quality, auth):
    host.title("Getting the links")
    host.status()
    host.set_status("Asking Rubika from this phone... (about 10-30 seconds)")
    log = []
    params = {"page": page, "season": season, "episodes": eps, "quality": quality, "own_auth": bool(auth)}

    def work():
        result, error, used = None, "", auth
        try:
            if not used:
                try:
                    used = host.store.get("auth", "") or ""
                except Exception:
                    used = ""
                if used:
                    log.append("auth: saved from an earlier run")
            if not used:
                try:
                    used = _export_auth(log)
                except Fail as e:
                    log.append("auth from export failed: %s" % e)
            try:
                result = collect(page, season, eps, quality, used, log)
            except Fail as e:
                if "NOT_REGISTERED" in str(e) and used and not auth:
                    log.append("saved auth refused: reading a fresh one from the export")
                    used = _export_auth(log)
                    result = collect(page, season, eps, quality, used, log)
                else:
                    raise
        except Exception as e:
            error = "%s: %s" % (type(e).__name__, e) if not isinstance(e, Fail) else str(e)
            if not isinstance(e, Fail):
                log.append(traceback.format_exc())
        report = _report(host, params, log, result, error)
        saved = _save(host, report)
        return {"result": result, "error": error, "report": report, "saved": saved, "auth": used if result else ""}

    def done(data, err):
        if err or not data:
            host.replace(show_error, "Plugin crashed: %s" % err, "\n".join(log), "not saved")
        elif data["error"]:
            host.replace(show_error, data["error"], data["report"], data["saved"])
        else:
            try:
                if data.get("auth"):
                    host.store.set("auth", data["auth"])
            except Exception:
                pass
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
    if res.get("mtype") == "Series":
        host.button("Follow this series (save by name)", lambda: host.show(
            follow_form, res["mid"], res["title"], res.get("counts") or {}))
    for label, q, u in rows[:MAX_BUTTONS]:
        _row_button(host, label, q, u)
    if len(rows) > MAX_BUTTONS:
        host.text("Only the first %d are listed as buttons; Copy all has every link." % MAX_BUTTONS)
    host.back_button("Back")


# ---- follow: save a series by name and auto-check for new episodes ----
# Saved in host.store ("follow_json"). While the app is open a background loop checks a series ONLY at its
# release day and time (Tehran): up to `tries` checks, `every` minutes apart, until the new episode shows up;
# then it gives up. No other checks. New links: notification + the series page (Copy / Share / Update).
FOLLOW_ENV = "RUBIKA_FOLLOW_TOKEN"
FOLLOW_LOG_PATH = "diag-results/rubika-follow.txt"
TEHRAN_OFF = 12600  # Tehran = UTC+3:30, no daylight saving
DEF_TRIES = 6
DEF_EVERY = 10  # minutes
TICK_S = 30
DAY_NAMES = {5: "Saturday (شنبه)", 6: "Sunday (یکشنبه)", 0: "Monday (دوشنبه)", 1: "Tuesday (سه‌شنبه)",
             2: "Wednesday (چهارشنبه)", 3: "Thursday (پنجشنبه)", 4: "Friday (جمعه)"}
DAY_ORDER = [5, 6, 0, 1, 2, 3, 4]
_LOCK = threading.Lock()
_CHECK_LOCK = threading.Lock()
_FLOG = []
_SAVED = {"err": 0}


def _load(host):
    try:
        v = json.loads(host.store.get("follow_json", "") or "[]")
        return v if isinstance(v, list) else []
    except Exception:
        return []


def _put(host, items):
    host.store.set("follow_json", json.dumps(items, ensure_ascii=False))


def _update(host, mid, **kw):
    with _LOCK:
        items = _load(host)
        for s in items:
            if s.get("mid") == mid:
                s.update(kw)
        _put(host, items)


def _tstr(ts):
    return time.strftime("%a %H:%M", time.gmtime(ts + TEHRAN_OFF))


def _when(s):
    hm = int(s.get("hm", 720))
    return "%s %02d:%02d" % (DAY_NAMES.get(s.get("day"), "?").split(" ")[0][:3], hm // 60, hm % 60)


def _window(s):
    try:
        t = max(1, int(s.get("tries") or DEF_TRIES))
        e = max(1, int(s.get("every") or DEF_EVERY))
    except Exception:
        t, e = DEF_TRIES, DEF_EVERY
    return t, e


def _release_ts(s, now):
    """UTC seconds of the release time whose try-window (tries x every) is open now, else None."""
    try:
        hm = int(s.get("hm", 720))
    except Exception:
        hm = 720
    t, e = _window(s)
    span = min(t * e * 60, 23 * 3600)
    day0 = int((now + TEHRAN_OFF) // 86400) * 86400  # Tehran midnight, shifted
    for back in (0, 1):
        d = day0 - back * 86400
        if time.gmtime(d).tm_wday == s.get("day"):
            rel = d + hm * 60 - TEHRAN_OFF
            if rel <= now < rel + span:
                return rel
    return None


def _episode_no(label):
    m = re.match(r"S\d+E(\d+)", label or "")
    return int(m.group(1)) if m else 0


def _get_auth(host, log, fresh=False):
    used = ""
    if not fresh:
        try:
            used = host.store.get("auth", "") or ""
        except Exception:
            used = ""
        if used:
            log.append("auth: saved from an earlier run")
    return used or _export_auth(log)


def _with_auth(host, log, fn):
    auth = _get_auth(host, log)
    try:
        return fn(auth), auth
    except Fail as e:
        if "NOT_REGISTERED" in str(e):
            log.append("saved auth refused: reading a fresh one from the export")
            auth = _get_auth(host, log, True)
            return fn(auth), auth
        raise


def _check(s, auth, log):
    """Blocking. Count the episodes of the followed season and get the links of the new ones."""
    cl = Rubika(auth, log)
    try:
        media = cl.call("getMedia", {"media_id": s["mid"]}).get("media") or {}
        seasons = media.get("seasons") or []
        if not seasons:
            raise Fail("The series has no seasons in the answer")
        want = str(s.get("season") or "last").strip().lower()
        pick, snum = None, None
        for si, se in enumerate(seasons, 1):
            sn = se.get("season_number") or si
            if want != "last" and str(sn) == want:
                pick, snum = se, int(sn)
        if pick is None:
            if want != "last":
                raise Fail("Season %s not found" % want)
            pick = seasons[-1]
            snum = int(pick.get("season_number") or len(seasons))
        el = cl.call("getSeasonEpisodes", {"series_id": s["mid"], "season_id": pick.get("season_id"),
                                           "section_type": "MediaInfo"}).get("episodes") or []
    except Blocked:
        raise Fail("Rubika answered HTTP 403: this network is blocked (use Irancell mobile data, Wi-Fi/VPN off)")
    n = len(el)
    known = s.get("known")
    if s.get("snum") is not None and s.get("snum") != snum:
        known = 0
        log.append("  new season %s: counting from 0" % snum)
    base = {"snum": snum, "n": n, "rows": []}
    if known is None:
        return dict(base, known=n, msg="start point set: %d episodes now" % n)
    if n <= known:
        return dict(base, known=known, msg="no new episode (%d episodes)" % n)
    try:
        res = collect(s["mid"], str(snum), "%d-%d" % (known + 1, n), s.get("quality") or "master", auth, log)
    except Fail as e:
        return dict(base, known=known, msg="%d new episode(s) listed, no link yet: %s" % (n - known, str(e)[:80]))
    rows = res["rows"]
    got = {_episode_no(r[0]) for r in rows}
    k = known
    while k + 1 in got:
        k += 1
    labels = []
    for r in rows:
        if r[0] not in labels:
            labels.append(r[0])
    return dict(base, known=k, rows=rows, msg="NEW: " + ", ".join(labels))


def _notify(host, title, msg):
    try:
        host.nav.schedule(lambda: host.notify(title, msg))
    except Exception:
        pass


def _check_one(host, s, why):
    """why = "scheduled" (counts as one try of the release window) or "manual" (counts nothing)."""
    with _CHECK_LOCK:
        now = time.time()
        log = []
        sched = (why == "scheduled")
        out = {"name": s.get("name") or s["mid"], "mid": s["mid"], "rows": [], "msg": "", "ok": True}
        rel = _release_ts(s, now)
        tries, every = _window(s)
        att = (s.get("att") or 0) if s.get("att_rel") == rel else 0
        upd = {"last_check": now}
        if sched:
            att += 1
            upd.update(att_rel=rel, att=att, next=now + every * 60)
        done = False
        try:
            r, auth = _with_auth(host, log, lambda a: _check(s, a, log))
            try:
                host.store.set("auth", auth)
            except Exception:
                pass
            upd.update(known=r["known"], snum=r["snum"], last_msg=r["msg"])
            if r["rows"]:
                upd["found"] = [list(x) for x in r["rows"]]
                upd["found_at"] = now
                _notify(host, "Rubika: " + out["name"], r["msg"])
                done = r["known"] >= r["n"]
            out.update(rows=r["rows"], msg=r["msg"])
        except Exception as e:
            upd["last_msg"] = "error: %s" % str(e)[:100]
            out.update(ok=False, msg="error: %s" % e)
            if not isinstance(e, Fail):
                log.append(traceback.format_exc())
        if sched and rel and not done and att >= tries:
            done = True
            out["msg"] += " | gave up after %d tries" % att
            upd["last_msg"] = out["msg"][:140]
            _notify(host, "Rubika: " + out["name"], "No new episode after %d tries" % att)
        if done and rel:
            upd["done_rel"] = rel
        _update(host, s["mid"], **upd)
        _FLOG.append("[%s] %s (%s%s): %s" % (_tstr(now), out["name"], why, " try %d/%d" % (att, tries) if sched else "", out["msg"]))
        _FLOG.extend(_hide(x) for x in log[-12:])
        del _FLOG[:-80]
        if out["rows"] or (not out["ok"] and now - _SAVED["err"] > 3600) or "gave up" in out["msg"]:
            if not out["rows"]:
                _SAVED["err"] = now
            _save(host, "Rubika follow log\n" + "\n".join(_FLOG), FOLLOW_LOG_PATH)
        return out


def _follow_loop(host, token):
    while os.environ.get(FOLLOW_ENV) == token:
        try:
            now = time.time()
            for s in _load(host):
                if now < (s.get("next") or 0):
                    continue
                rel = _release_ts(s, now)
                if rel is not None and s.get("done_rel") != rel:
                    _check_one(host, s, "scheduled")
        except Exception:
            pass
        end = time.time() + TICK_S
        while time.time() < end and os.environ.get(FOLLOW_ENV) == token:
            time.sleep(1)


def _follow_on():
    return bool(os.environ.get(FOLLOW_ENV))


def _follow_start(host):
    if _follow_on():
        return
    token = str(int(time.time() * 1000))
    os.environ[FOLLOW_ENV] = token
    threading.Thread(target=_follow_loop, args=(host, token), daemon=True).start()


def _toggle_follow(host):
    if _follow_on():
        os.environ.pop(FOLLOW_ENV, None)
        host.store.set("follow_off", True)
    else:
        host.store.set("follow_off", False)
        _follow_start(host)
    host.replace(series_list)


def follow_form(host, mid, title, counts=None, old=None):
    old = old or {}
    counts = counts or {}
    host.title("Follow a series")
    host.text("Name to save it with:")
    name = host.input("name")
    host.text("Release day (Tehran time). You must pick it:")
    day = host.choice([DAY_NAMES[k] for k in DAY_ORDER])
    host.text("Release time (Tehran, 24h), like 12:00:")
    tm = host.input("12:00")
    host.text("Season: last (newest; follows a new season by itself) or a number:")
    season = host.input("last")
    host.text("Episodes you already have (only the next ones count as new). Lower it by one to get the latest episode now:")
    known = host.input("number")
    host.text("Tries: how many times to check, starting at the release time (then it gives up):")
    tries = host.input("6")
    host.text("Minutes between the tries:")
    every = host.input("10")
    host.text("Quality (master = one link with all qualities inside):")
    quality = host.choice(QUALITIES)
    try:
        name.text = old.get("name") or title or mid
        hm = int(old.get("hm", 720))
        tm.text = "%02d:%02d" % (hm // 60, hm % 60)
        season.text = str(old.get("season") or "last")
        tries.text = str(old.get("tries") or DEF_TRIES)
        every.text = str(old.get("every") or DEF_EVERY)
        if old.get("known") is not None:
            known.text = str(old["known"])
        elif counts:
            known.text = str(counts[str(max(int(k) for k in counts))])
    except Exception:
        pass

    def save():
        m = re.fullmatch(r"(\d{1,2})\s*[:.]\s*(\d{2})", (tm.text or "").strip())
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            host.set_status("Time must look like 12:00")
            return
        wd = None
        for k, v in DAY_NAMES.items():
            if v == day.value:
                wd = k
        if wd is None:
            host.set_status("Pick the release day")
            return
        se = (season.text or "").strip().lower() or "last"
        if se != "last" and not se.isdigit():
            host.set_status("Season must be last or a number")
            return
        tr, ev = (tries.text or "").strip() or str(DEF_TRIES), (every.text or "").strip() or str(DEF_EVERY)
        if not (tr.isdigit() and ev.isdigit() and 1 <= int(tr) <= 30 and 1 <= int(ev) <= 60):
            host.set_status("Tries must be 1-30 and minutes 1-60")
            return
        kn = (known.text or "").strip()
        if kn and not kn.isdigit():
            host.set_status("Episodes you have must be a number")
            return
        item = {"mid": mid, "name": (name.text or "").strip() or mid, "day": wd,
                "hm": int(m.group(1)) * 60 + int(m.group(2)), "season": se, "quality": quality.value or "master",
                "known": int(kn) if kn else None, "snum": int(se) if se.isdigit() else None,
                "tries": int(tr), "every": int(ev), "next": 0, "done_rel": 0}
        with _LOCK:
            items = [x for x in _load(host) if x.get("mid") != mid] + [item]
            _put(host, items)
        try:
            host.store.set("follow_off", False)
        except Exception:
            pass
        _follow_start(host)
        host.replace(series_list)

    host.button("Save", save)
    host.status()
    host.back_button("Back")


def series_list(host):
    items = _load(host)
    host.title("Followed series (%d)" % len(items))
    host.text("Auto-check is %s. It checks only at each series' release day and time (Tehran), a few times, "
              "then gives up. It works only while the app is open, on Irancell mobile data."
              % ("ON" if _follow_on() else "OFF"))
    host.status()
    host.button("Auto-check: turn %s" % ("OFF" if _follow_on() else "ON"), lambda: _toggle_follow(host))
    if items:
        host.button("Check all now", lambda: host.show(check_screen, [s["mid"] for s in items]))
    for s in items:
        host.button("%s | %s | have %s" % ((s.get("name") or s["mid"])[:30], _when(s), s.get("known", "?")),
                    lambda m=s["mid"]: host.show(series_detail, m))
    if not items:
        host.text("Nothing saved yet. Get the links of a series once, then press 'Follow this series'.")
    host.back_button("Back")


def series_detail(host, mid):
    s = next((x for x in _load(host) if x.get("mid") == mid), None)
    if not s:
        host.title("Series not found")
        host.back_button("Back")
        return
    host.title(s.get("name") or mid)
    last = _tstr(s["last_check"]) if s.get("last_check") else "never"
    host.text("Release: %s (Tehran), %s tries every %s min | season: %s | quality: %s | episodes you have: %s\nLast check: %s - %s"
              % (_when(s), _window(s)[0], _window(s)[1], s.get("season"), s.get("quality"), s.get("known"), last, s.get("last_msg") or "-"))
    host.status()
    host.button("Check now", lambda: host.show(check_screen, [mid]))
    host.button("Update links (links expire)", lambda: host.show(update_screen, mid))
    host.button("Get latest episode links", lambda: host.show(
        run, mid, str(s.get("snum") or s.get("season") or "all").replace("last", "all"), "last",
        s.get("quality") or "master", ""))
    host.button("Edit", lambda: host.show(follow_form, mid, s.get("name"), {}, s))
    host.button("Delete from the list", lambda: (_put(host, [x for x in _load(host) if x.get("mid") != mid]),
                                                  host.replace(series_list)))
    rows = s.get("found") or []
    if rows:
        host.text("Last new links (found %s). They expire: use them soon from this phone." % _tstr(s.get("found_at") or 0))
        full = "\n".join("%s | %s | %s" % tuple(r) for r in rows)
        host.button("Copy all (name | quality | link)", lambda: (host.copy(full), host.set_status("Copied")))
        host.button("Share links", lambda: host.share_text(full))
        for label, q, u in rows[:MAX_BUTTONS]:
            _row_button(host, label, q, u)
    host.back_button("Back")


def check_screen(host, mids):
    host.title("Checking")
    host.status()
    host.set_status("Asking Rubika from this phone... (10-60 seconds)")

    def work():
        return [_check_one(host, s, "manual") for s in _load(host) if s.get("mid") in mids]

    def done(data, err):
        host.replace(check_result, data or [], str(err or ""))

    host.background(work, done=done)
    host.back_button("Back")


def check_result(host, outs, err):
    host.title("Check result")
    if err:
        host.text("Crashed: " + err)
    for o in outs:
        host.text("%s: %s" % (o["name"], o["msg"]))
        rows = o["rows"]
        if rows:
            full = "\n".join("%s | %s | %s" % tuple(r) for r in rows)
            host.button("Copy all: %s" % o["name"][:30], lambda f=full: (host.copy(f), host.set_status("Copied")))
            host.button("Share: %s" % o["name"][:30], lambda f=full: host.share_text(f))
            for label, q, u in rows[:MAX_BUTTONS]:
                _row_button(host, label, q, u)
    host.status()
    host.back_button("Back")


def update_screen(host, mid):
    """Signed links expire: ask Rubika again for the episodes of the last found links (or the newest one)."""
    host.title("Updating links")
    host.status()
    host.set_status("Getting fresh links from this phone... (10-60 seconds)")

    def work():
        s = next((x for x in _load(host) if x.get("mid") == mid), None)
        if not s:
            return []
        name = s.get("name") or mid
        log = []
        nums = [x for x in (_episode_no(r[0]) for r in (s.get("found") or [])) if x]
        a = min(nums) if nums else max(int(s.get("known") or 1), 1)
        s2 = dict(s, known=a - 1)
        try:
            r, auth = _with_auth(host, log, lambda au: _check(s2, au, log))
        except Exception as e:
            return [{"name": name, "rows": [], "msg": "error: %s" % e}]
        if not r["rows"]:
            return [{"name": name, "rows": [], "msg": r["msg"]}]
        _update(host, mid, found=[list(x) for x in r["rows"]], found_at=time.time(), snum=r["snum"],
                known=max(int(s.get("known") or 0), r["known"]), last_msg="links updated")
        return [{"name": name, "rows": r["rows"], "msg": "Links updated: " + r["msg"].replace("NEW: ", "")}]

    def done(data, err):
        host.replace(check_result, data or [], str(err or ""))

    host.background(work, done=done)
    host.back_button("Back")


def _row_button(host, label, q, u):
    """A master link opens a screen with the qualities split; any other link is copied on tap."""
    if q == "master":
        host.button("%s [master] - pick quality" % label[:36], lambda l=label, u=u: host.show(quality_screen, l, u))
    else:
        host.button("%s [%s] - copy link" % (label[:40], q),
                    lambda u=u, l=label, q=q: (host.copy(u), host.set_status("Copied: %s [%s]" % (l, q))))


def quality_screen(host, label, master):
    host.title(label[:50])
    host.status()
    host.set_status("Reading the qualities from this phone...")
    log = []

    def work():
        return _variants(master, log)

    def done(vs, err):
        host.replace(quality_result, label, master, vs or [], str(err or ""), log[-1] if log else "")

    host.background(work, done=done)
    host.back_button("Back")


def quality_result(host, label, master, vs, err, last):
    host.title("%s - qualities" % label[:40])
    if err:
        host.text("Failed: " + err)
    elif not vs:
        host.text("No separate qualities found (%s). The link may have expired: use Update links." % (_hide(last) or "no answer"))
    host.status()
    host.button("Copy master link (all qualities inside)", lambda: (host.copy(master), host.set_status("Master link copied")))
    for q, u in vs:
        host.button("%s - copy link" % q, lambda u=u, q=q: (host.copy(u), host.set_status("Copied %s" % q)))
    if vs:
        allq = "\n".join("%s | %s | %s" % (label, q, u) for q, u in vs)
        host.button("Copy all qualities (name | quality | link)", lambda: (host.copy(allq), host.set_status("Copied")))
    host.back_button("Back")
