"""FilmNet VOD links - runs on THIS phone (MCI / Hamrah-e-Aval IP).

Gives the direct (signed .m3u8) links of a filmnet.ir movie or series.
Same API calls the FilmNet web page makes (https://filmnet.ir/api-v2/):
  video-contents/<series id>  -> seasons[].episodes[]
  video-contents/<episode id> -> video_files.primary[0].video_file_id
  video-contents/<episode id>/files/<file id>/url (login headers) -> data.url = master m3u8
FilmNet is free only for MCI (Hamrah-e-Aval) mobile data, so the links are asked from the phone.
Auth (Bearer + profile token, user-id, device-id) is taken from your newest Browser export of filmnet.ir (private repo yt-exports).
Every run writes a log to the repo (config branch, diag-results/filmnet-latest.txt) and the screen has a Copy log button.
"""
import base64
import json
import json as J
import os
import platform
import re
import sys
import time
import threading
import traceback
from urllib.parse import urljoin

BASE = "https://filmnet.ir/api-v2/"
SITE = "https://filmnet.ir/"
VERSION = "v1.47.41"
UA = ("Mozilla/5.0 (Linux; Android 13; M2101K6G Build/TKQ1.221013.002) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Version/4.0 Chrome/158.0.8127.46 Mobile Safari/537.36")
QUALITIES = ["master", "all", "1080p-HQ", "1080p", "720p", "480p"]
MAX_BUTTONS = 60
REPO = "redi2213/yt-downloader"
GH_API = "https://api.github.com/repos/" + REPO
LOG_BRANCH = "config"
LOG_PATH = "diag-results/filmnet-latest.txt"
EXPORT_DIR = "filmnet.ir"


class Blocked(Exception):
    pass


class Fail(Exception):
    pass


def _hide(s):
    s = re.sub(r"(token|sig|usid|afcn|cip)=[^&\s\"']+", r"\1=<hidden>", str(s))
    s = re.sub(r"/v5/[^/\s\"']+/[^/\s\"']+/", "/v5/<hidden>/<hidden>/", s)
    s = re.sub(r"eyJ[A-Za-z0-9._\-]{20,}", "<hidden>", s)
    return re.sub(r"Bearer\s+\S+", "Bearer <hidden>", s)


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


def _parse_auth(auth):
    """Stored/typed auth -> dict(token, profile, user_id, device_id, version, cookie). Accepts JSON or a bare token."""
    a = (auth or "").strip()
    keys = ("token", "profile", "user_id", "device_id", "version", "cookie")
    if a.startswith("{"):
        try:
            d = J.loads(a)
            if d.get("token"):
                return {k: str(d.get(k) or "") for k in keys}
        except ValueError:
            pass
    if a.lower().startswith("bearer "):
        a = a[7:].strip()
    return dict({k: "" for k in keys}, token=a)


def _num(x):
    t = str(x or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    m = re.search(r"\d+", t)
    return int(m.group(0)) if m else 0


class FilmNet:
    def __init__(self, auth, log):
        self.log = log
        self.a = _parse_auth(auth)
        if not (self.a["token"] and self.a["user_id"] and self.a["device_id"]):
            raise Fail("No FilmNet auth: open filmnet.ir in the Browser, play a video, then Export cookies > Full page export")

    def hdr(self, api=True, authed=False):
        h = {"Accept": "application/json, text/plain, */*", "User-Agent": UA, "Referer": SITE}
        if api:
            h.update({"X-platform": "Web", "version-number": self.a["version"] or VERSION,
                      "user-id": self.a["user_id"], "device-id": self.a["device_id"]})
            if authed:
                h["Authorization"] = "Bearer " + self.a["token"]
                if self.a["profile"]:
                    h["X-Profile-Token"] = self.a["profile"]
        if self.a["cookie"]:
            h["Cookie"] = self.a["cookie"]
        return h

    def get(self, path, authed=False):
        tag = path.split("?")[0][:56]
        last = ""
        for attempt in range(1, 4):
            t0 = time.time()
            try:
                code, text = _http("GET", BASE + path, self.hdr(authed=authed))
            except Exception as e:
                last = "%s: %s %s" % (tag, type(e).__name__, e)
                self.log.append("  %s try%d EXC %s" % (tag, attempt, _hide(last)))
                time.sleep(2)
                continue
            dt = time.time() - t0
            if code == 401 and authed:
                self.log.append("  %s try%d HTTP 401 (%.1fs)" % (tag, attempt, dt))
                raise Fail("NOT_REGISTERED: FilmNet rejected the token (HTTP 401)")
            if code == 403:
                self.log.append("  %s try%d HTTP 403 (%.1fs) body=%s" % (tag, attempt, dt, _hide(text[:200])))
                raise Blocked()
            if code == 404:
                raise Fail("%s: not found (HTTP 404)" % tag)
            if code != 200:
                last = "%s: HTTP %s" % (tag, code)
                self.log.append("  %s try%d HTTP %s (%.1fs) body=%s" % (tag, attempt, code, dt, _hide(text[:200])))
                time.sleep(2)
                continue
            try:
                j = json.loads(text)
            except ValueError:
                last = "%s: the answer is not JSON" % tag
                self.log.append("  %s try%d not JSON (%.1fs) body=%s" % (tag, attempt, dt, _hide(text[:200])))
                time.sleep(2)
                continue
            self.log.append("  %s OK (%.1fs)" % (tag, dt))
            return j
        raise Fail(last or tag + " failed")

    def content(self, cid):
        """video-contents/<id>: series (seasons), episode or movie. Public, no login needed."""
        return (self.get("video-contents/" + cid).get("data") or {})

    def carrier(self, cid):
        """conditional-prop (login): says which carrier FilmNet sees. Also catches an old token early."""
        try:
            d = (self.get("video-contents/%s/conditional-prop" % cid, True).get("data") or {})
        except Fail as e:
            if "NOT_REGISTERED" in str(e):
                raise
            self.log.append("  conditional-prop: %s" % e)
            return ""
        key = str(d.get("carrier_key") or "")
        self.log.append("  conditional-prop: carrier=%s flag=%s" % (key or "-", d.get("conditional_flag") or "-"))
        return key

    def play(self, cid):
        """Master m3u8 of one episode/movie: video file id, then files/<id>/url (login)."""
        d = self.content(cid)
        prim = (d.get("video_files") or {}).get("primary") or []
        fid = next((str(p.get("video_file_id")) for p in prim if p.get("video_file_id")), "")
        title = d.get("title") or ""
        if not fid:
            self.log.append("  play %s: no primary video file (access=%s flag=%s)" % (
                cid, d.get("video_content_access_approach"), d.get("conditional_flag")))
            return {"master": "", "title": title, "expires": ""}
        j = self.get("video-contents/%s/files/%s/url" % (d.get("id") or cid, fid), True)
        dd = j.get("data") or {}
        master = str(dd.get("url") or "")
        self.log.append("  play %s: master=%s expires=%s%s" % (
            cid, "yes" if master else "NO", dd.get("expiration_time") or "-",
            "" if master else " msg=%s" % _hide((j.get("meta") or {}).get("display_message"))))
        return {"master": master, "title": title, "expires": str(dd.get("expiration_time") or "")}


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


def _variants(master, log, cl):
    """Video qualities of a master playlist, best first. The links are muxed (audio inside).
    Same height twice (FilmNet 1080HQ and 1080): the higher bitrate is named 1080p-HQ."""
    try:
        code, text = _http("GET", master, cl.hdr(api=False))
    except Exception as e:
        log.append("  master playlist: %s %s" % (type(e).__name__, e))
        return []
    log.append("  master playlist HTTP %s, %d chars" % (code, len(text)))
    if code != 200:
        return []
    lines = text.replace("\r\n", "\n").splitlines()
    raw = []
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            u = urljoin(master, lines[i + 1].strip())
            m = re.search(r"RESOLUTION=\d+x(\d+)", ln)
            b = re.search(r"[^-]BANDWIDTH=(\d+)", ln)
            raw.append((int(m.group(1)) if m else 0, int(b.group(1)) if b else 0, u))
    raw.sort(key=lambda v: (v[0], v[1]), reverse=True)
    out, seen = [], {}
    for h, b, u in raw:
        same = sum(1 for x in raw if x[0] == h)
        seen[h] = seen.get(h, 0) + 1
        q = ("%dp" % h) if h else "variant"
        if same > 1 and seen[h] == 1:
            q += "-HQ"
        out.append((q, u))
    return out


def _find_auth(data):
    reqs = data.get("requests") if isinstance(data, dict) else data
    for r in reqs or []:
        if "filmnet.ir/api-v2/" not in str(r.get("url", "")):
            continue
        h = {str(k).lower(): v for k, v in (r.get("headers") or {}).items()}
        a = str(h.get("authorization") or "")
        if a.lower().startswith("bearer ") and len(a) > 40 and h.get("user-id") and h.get("device-id"):
            return {"token": a[7:].strip(), "profile": str(h.get("x-profile-token") or ""),
                    "user_id": str(h.get("user-id")), "device_id": str(h.get("device-id")),
                    "version": str(h.get("version-number") or ""), "cookie": str(r.get("cookie") or "")}
    return None


def _export_auth(log):
    """Read the FilmNet auth the web page used from your newest Browser export (private repo yt-exports)."""
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
    code, text = _http("GET", base + EXPORT_DIR + "?ref=" + export_prefs.BRANCH, hdr)
    if code != 200:
        raise Fail("Exports repo folder %s: HTTP %s (make a Browser > Export cookies > Full page export on filmnet.ir)" % (EXPORT_DIR, code))
    names = sorted((i["name"] for i in J.loads(text) if i.get("type") == "dir"), reverse=True)
    for name in names[:3]:
        code, text = _http("GET", base + "%s/%s/requests.json?ref=%s" % (EXPORT_DIR, name, export_prefs.BRANCH), raw)
        if code != 200:
            log.append("  export %s requests.json: HTTP %s" % (name, code))
            continue
        try:
            a = _find_auth(J.loads(text))
        except ValueError:
            a = None
        if a:
            log.append("  auth taken from export %s (%d chars, cookie %s)" % (name, len(a["token"]), "yes" if a["cookie"] else "no"))
            return J.dumps(a)
        log.append("  export %s has no FilmNet API request with an auth" % name)
    raise Fail("No auth found in the newest filmnet.ir exports: open the site in the Browser, play a video, then Full page export")


def _id_of(page):
    """FilmNet link (/contents/<id>/<slug> or /play/<id>/p) or a bare id -> (id, play link = single episode?)."""
    page = (page or "").strip()
    m = re.search(r"filmnet\.ir/(contents|play)/([A-Za-z0-9]{4,14})(?:[/?#]|$)", page)
    if m:
        return m.group(2), m.group(1) == "play"
    if re.fullmatch(r"sc[A-Za-z0-9]{3,12}", page):
        return page, False
    raise Fail("Give the FilmNet link, like https://filmnet.ir/contents/sc9nEOr/Yal-1404 (or only the code sc9nEOr)")


def _seasons(d):
    """series content -> [(season number, [episode dicts sorted by number])] sorted by season."""
    out = []
    for s in d.get("seasons") or []:
        if not isinstance(s, dict):
            continue
        el = [e for e in (s.get("episodes") or []) if isinstance(e, dict) and e.get("id") and e.get("status", "active") == "active"]
        el.sort(key=lambda e: _num(e.get("episode")))
        sn = _num(s.get("season")) or (_num(el[0].get("season")) if el else 0) or len(out) + 1
        out.append((sn, el))
    return sorted(out, key=lambda x: x[0])


def _label(sn, no, name=""):
    return ("S%02dE%02d %s" % (sn, no, (name or "").replace("|", "-"))).strip()


def collect(page, season, eps, quality, auth, log):
    """Blocking work (run in a background thread). Returns a result dict."""
    cid, single = _id_of(page)
    season = (season or "all").strip().lower()
    quality = (quality or "master").strip()
    ql = quality.lower()
    if ql not in [q.lower() for q in QUALITIES]:
        raise Fail("Quality must be one of: " + ", ".join(QUALITIES))
    cl = FilmNet(auth, log)
    log.append("id %s%s | season=%s episodes=%s quality=%s" % (cid, " (play link = single episode)" if single else "", season, eps, quality))
    try:
        d = cl.content(cid)
        typ = str(d.get("type") or "")
        title = str(d.get("title") or cid).replace("|", "-")
        ser = d.get("series") or {}
        is_series = typ == "series" or bool(d.get("seasons"))
        sid, sname, counts, pub = "", title, {}, ""
        items = []
        log.append("title=%s type=%s access=%s flag=%s" % (title, typ, d.get("video_content_access_approach"), d.get("conditional_flag")))
        car = cl.carrier(str(d.get("short_id") or cid))
        if car and car.upper() != "MCI":
            log.append("  WARNING: FilmNet sees carrier %s, not MCI: use MCI (Hamrah-e-Aval) mobile data, Wi-Fi/VPN off" % car)
        elif not car:
            log.append("  note: no carrier answer: FilmNet may not see an MCI account (Wi-Fi or VPN on?)")
        if is_series and not single:
            sid, sname = str(d.get("short_id") or cid), title
            seasons = _seasons(d)
            if not seasons:
                raise Fail("This series has no seasons in the answer")
            for sn, el in seasons:
                counts[str(sn)] = len(el)
            use = seasons[-1:] if (eps.strip().lower() == "last" and season == "all") else seasons
            for sn, el in use:
                if season != "all" and str(sn) != season:
                    continue
                keep = _pick(len(el), eps)
                log.append("season %s: %d episodes" % (sn, len(el)))
                for ei, e in enumerate(el, 1):
                    if ei in keep:
                        items.append((_label(sn, _num(e.get("episode")) or ei, e.get("sub_title") or ""), str(e.get("id"))))
        elif typ == "episode":
            sid, sname = str(ser.get("short_id") or ""), str(ser.get("series_title") or title)
            sn, no = _num(d.get("season") or ser.get("season")), _num(d.get("episode") or ser.get("episode"))
            items.append((_label(sn, no, d.get("sub_title") or "") if (sn or no) else title, str(d.get("id") or cid)))
            if sid:
                try:
                    for s2, el2 in _seasons(cl.content(sid)):
                        counts[str(s2)] = len(el2)
                except Fail as e:
                    log.append("  series counts: %s" % e)
        else:
            items.append((title, str(d.get("id") or cid)))
        mtype = "Series" if sid else "Movie"
        if not items:
            raise Fail("No episode matched (check the season and episodes boxes)")
        rows = []
        for label, eid in items[:200]:
            log.append("episode %s (id %s)" % (label, eid))
            try:
                p = cl.play(eid)
            except Fail as e:
                if "NOT_REGISTERED" in str(e):
                    raise
                log.append("  skip: %s" % e)
                continue
            master = p["master"].strip()
            if not master:
                log.append("  skip: no m3u8 in the answer (needs MCI mobile data, or the episode is not out yet)")
                continue
            got = []
            if ql in ("master", "all"):
                got.append(("master", master))
            if ql != "master":
                vs = _variants(master, log, cl)
                if ql == "all":
                    got += vs
                else:
                    sel = [v for v in vs if v[0].lower() == ql]
                    if sel:
                        got += sel[:1]
                    else:
                        log.append("  quality %s not found: giving the master link" % quality)
                        got.append(("master", master))
            for q, u in got:
                rows.append((label, q, u))
            time.sleep(0.3)
    except Blocked:
        raise Fail("FilmNet answered HTTP 403: this network is blocked. Turn Wi-Fi/VPN off and use MCI (Hamrah-e-Aval) mobile data.")
    if not rows:
        raise Fail("No link was produced. See the log (last lines): " + " / ".join(x.strip() for x in log[-3:]))
    return {"title": title, "mtype": mtype, "mid": sid or cid, "uid": sid or cid, "rows": rows, "counts": counts,
            "series_id": sid, "series_name": sname, "pub": pub}


# ---- log ----

def _report(host, params, log, result, error):
    head = ["FilmNet VOD log", time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
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
        body = {"message": "filmnet log", "branch": LOG_BRANCH,
                "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
        if sha:
            body["sha"] = sha
        host.gh.request("PUT", url, json=body)
        return "Log saved to the repo (config branch, %s)" % LOG_PATH
    except Exception as e:
        return "Log NOT saved to the repo: %s" % str(e)[:120]


# ---- screens ----

def build(host):
    host.title("FilmNet VOD links (this phone)")
    host.text("Use MCI (Hamrah-e-Aval) mobile data (Wi-Fi and VPN off). FilmNet is free only for MCI there, "
              "and the signed links work only from this phone's network.")
    host.text("1) FilmNet page link (movie or series). A /contents/ link = the whole series; a /play/ link = only that episode:")
    url = host.input("https://filmnet.ir/contents/sc9nEOr/Yal-1404")
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
    host.text("4) Quality (master = one link that has all qualities inside; all = every quality as its own link; "
              "1080p-HQ is the higher-bitrate 1080. Every quality link already has the audio inside):")
    quality = host.choice(QUALITIES)
    host.text("5) FilmNet auth: leave EMPTY. It is taken by itself from your newest Browser export of filmnet.ir.")
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
    host.set_status("Asking FilmNet from this phone... (about 10-30 seconds)")
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
    if res.get("series_id"):
        host.button("Follow this series (save by name)", lambda: host.show(
            follow_form, res["series_id"], res.get("series_name") or res["title"], res.get("counts") or {}, None,
            res.get("pub") or "", res.get("uid") or ""))
    for label, q, u in rows[:MAX_BUTTONS]:
        _row_button(host, label, q, u)
    if len(rows) > MAX_BUTTONS:
        host.text("Only the first %d are listed as buttons; Copy all has every link." % MAX_BUTTONS)
    host.back_button("Back")


# ---- follow: save a series by name and auto-check for new episodes ----
# Saved in host.store ("follow_json"). While the app is open a background loop checks a series ONLY at its
# release day and time (Tehran): up to `tries` checks, `every` minutes apart, until the new episode shows up;
# then it gives up. No other checks. New links: notification + the series page (Copy / Share / Update).
FOLLOW_ENV = "FILMNET_FOLLOW_TOKEN"
FOLLOW_LOG_PATH = "diag-results/filmnet-follow.txt"
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


_PDAYS = [("چهارشنبه", 2), ("پنجشنبه", 3), ("سهشنبه", 1), ("دوشنبه", 0), ("یکشنبه", 6), ("جمعه", 4), ("شنبه", 5)]


def _parse_pub(txt):
    """FilmNet's publish_date_info like 'چهارشنبه‌ها، 20:00' -> (weekday 0=Mon.., minutes) or (None, None)."""
    t = str(txt or "").replace("\u200c", "").replace(" ", "").replace("ي", "ی").replace("ك", "ک")
    t = t.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    day = next((d for w, d in _PDAYS if w in t), None)
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    hm = int(m.group(1)) * 60 + int(m.group(2)) if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 else None
    return day, hm


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
    cl = FilmNet(auth, log)
    sid = s.get("uid") or s["mid"]
    try:
        seasons = _seasons(cl.content(sid))
        if not seasons:
            raise Fail("The series has no seasons in the answer")
        want = str(s.get("season") or "last").strip().lower()
        snum = None
        for sn, _el in seasons:
            if want != "last" and str(sn) == want:
                snum = sn
        if snum is None:
            if want != "last":
                raise Fail("Season %s not found" % want)
            snum = seasons[-1][0]
        el = next(e for sn, e in seasons if sn == snum)
    except Blocked:
        raise Fail("FilmNet answered HTTP 403: this network is blocked (use MCI mobile data, Wi-Fi/VPN off)")
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
        res = collect(sid, str(snum), "%d-%d" % (known + 1, n), s.get("quality") or "master", auth, log)
    except Fail as e:
        if "NOT_REGISTERED" in str(e):
            raise
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
                _notify(host, "FilmNet: " + out["name"], r["msg"])
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
            _notify(host, "FilmNet: " + out["name"], "No new episode after %d tries" % att)
        if done and rel:
            upd["done_rel"] = rel
        _update(host, s["mid"], **upd)
        _FLOG.append("[%s] %s (%s%s): %s" % (_tstr(now), out["name"], why, " try %d/%d" % (att, tries) if sched else "", out["msg"]))
        _FLOG.extend(_hide(x) for x in log[-12:])
        del _FLOG[:-80]
        if out["rows"] or (not out["ok"] and now - _SAVED["err"] > 3600) or "gave up" in out["msg"]:
            if not out["rows"]:
                _SAVED["err"] = now
            _save(host, "FilmNet follow log\n" + "\n".join(_FLOG), FOLLOW_LOG_PATH)
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


def follow_form(host, mid, title, counts=None, old=None, pub="", uid=""):
    old = old or {}
    counts = counts or {}
    sug_day, sug_hm = _parse_pub(pub)
    first_day = old.get("day") if old.get("day") is not None else sug_day
    order = ([first_day] if first_day is not None else []) + [k for k in DAY_ORDER if k != first_day]
    host.title("Follow a series")
    host.text("Name to save it with:")
    name = host.input("name")
    host.text("Release day (Tehran time)%s:" % (
        (" - FilmNet says: %s, so %s is first in the list" % (pub, DAY_NAMES[first_day].split(" ")[0])) if first_day is not None
        else ". You must pick it"))
    day = host.choice([DAY_NAMES[k] for k in order])
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
        hm = int(old.get("hm", sug_hm if sug_hm is not None else 720))
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
            wd = first_day
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
        item = {"mid": mid, "uid": uid or old.get("uid") or mid, "name": (name.text or "").strip() or mid, "day": wd,
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
              "then gives up. It works only while the app is open, on MCI (Hamrah-e-Aval) mobile data."
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
        run, s.get("uid") or mid, str(s.get("snum") or s.get("season") or "all").replace("last", "all"), "last",
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
    host.set_status("Asking FilmNet from this phone... (10-60 seconds)")

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
    """Signed links expire: ask FilmNet again for the episodes of the last found links (or the newest one)."""
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
        return _variants(master, log, FilmNet(_get_auth(host, log), log))

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
