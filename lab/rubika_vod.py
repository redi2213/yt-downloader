"""Rubika VOD links - runs on THIS phone (Irancell IP).

Gives the direct (signed .m3u8) links of a vod.rubika.ir movie or series.
Same API calls the Rubika web page makes: getMedia -> getSeasonEpisodes -> getPlayInfo.
Nothing runs on GitHub: Rubika plays video only on Irancell and the signed links
work only from the network that asked for them.
"""
import json
import random
import re
import string
import time
from urllib.parse import urljoin

API = "https://rbvod30.iranlms.ir/"
UA = ("Mozilla/5.0 (Linux; Android 13; M2101K6G Build/TKQ1.221013.002) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Version/4.0 Chrome/158.0.8127.46 Mobile Safari/537.36")
QUALITIES = ["master", "all", "1080p", "720p", "468p", "360p"]
MAX_BUTTONS = 60


class Blocked(Exception):
    pass


class Fail(Exception):
    pass


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
    def __init__(self, auth):
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
        for _ in range(3):
            try:
                code, text = _http("POST", API, self.hdr, payload)
            except Exception as e:
                last = "%s: %s %s" % (method, type(e).__name__, e)
                time.sleep(2)
                continue
            if code == 403:
                raise Blocked()
            if code != 200:
                last = "%s: HTTP %s" % (method, code)
                time.sleep(2)
                continue
            try:
                j = json.loads(text)
            except ValueError:
                last = "%s: the answer is not JSON" % method
                time.sleep(2)
                continue
            if j.get("status") != "OK":
                raise Fail("%s: %s / %s" % (method, j.get("status"), j.get("status_det")))
            return j.get("data") or {}
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


def _variants(master, notes):
    hdr = {"User-Agent": UA, "Referer": "https://vod.rubika.ir/", "Origin": "https://vod.rubika.ir"}
    try:
        code, text = _http("GET", master, hdr)
    except Exception as e:
        notes.append("could not read the master playlist (%s %s)" % (type(e).__name__, e))
        return []
    if code != 200:
        notes.append("master playlist answered HTTP %s" % code)
        return []
    lines = text.splitlines()
    res = []
    for i, ln in enumerate(lines):
        if ln.startswith("#EXT-X-STREAM-INF") and i + 1 < len(lines):
            u = urljoin(master, lines[i + 1].strip())
            q = re.search(r"out_([0-9a-z]+)\.m3u8", u)
            res.append((q.group(1).lower() if q else "variant", u))
    return res


def collect(page, season, eps, quality, auth, notes):
    """Blocking work (run in a background thread). Returns a result dict."""
    page = (page or "").strip()
    m = re.search(r"/media/(\d+)", page)
    mid = m.group(1) if m else (page if page.isdigit() else "")
    if not mid:
        raise Fail("Give the Rubika link, like https://vod.rubika.ir/media/291423 (or only the number)")
    season = (season or "all").strip().lower()
    quality = (quality or "master").strip().lower()
    cl = Rubika((auth or "").strip())
    if cl.guest:
        notes.append("No auth given: using a random guest auth")
    try:
        acc = cl.call("getAccountInfo", {}).get("subscription_info") or {}
        if acc.get("has_network_subscription"):
            notes.append("Rubika sees your network: %s" % (acc.get("network_subscription_type") or "operator"))
        elif not acc.get("has_paid_subscription"):
            notes.append("Rubika does not see an Irancell network (Wi-Fi or VPN on?) and the account has no subscription: links may be refused")
    except Fail as e:
        notes.append("account check: %s" % e)
    try:
        media = cl.call("getMedia", {"media_id": mid}).get("media") or {}
        mtype = media.get("media_type") or ""
        title = (media.get("title") or mid).replace("|", "-")
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
                notes.append("Season %s: %d episodes" % (snum, len(el)))
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
            try:
                d = cl.call("getPlayInfo", {"media_id": eid, "type": "Main", "version": 1})
            except Fail as e:
                notes.append("skip %s: %s" % (label, e))
                continue
            if d.get("has_access") is False:
                notes.append("skip %s: no access (needs Irancell data, a subscription or a real login auth)" % label)
                continue
            master = ((d.get("play_data") or {}).get("play_url") or "").strip()
            if not master:
                notes.append("skip %s: no play_url in the answer" % label)
                continue
            got = []
            if quality in ("master", "all"):
                got.append(("master", master))
            if quality != "master":
                vs = _variants(master, notes)
                if quality == "all":
                    got += vs
                else:
                    sel = [v for v in vs if v[0] == quality]
                    if sel:
                        got += sel
                    else:
                        notes.append("quality %s not found for %s: giving the master link" % (quality, label))
                        got.append(("master", master))
            for q, u in got:
                rows.append((label, q, u))
            time.sleep(0.3)
    except Blocked:
        raise Fail("Rubika answered HTTP 403: this network is blocked. Turn Wi-Fi/VPN off and use Irancell mobile data.")
    if not rows:
        raise Fail("No link was produced. " + "; ".join(notes[-3:]))
    return {"title": title, "mtype": mtype, "mid": mid, "rows": rows, "notes": notes}


# ---- screens ----

def build(host):
    host.title("Rubika VOD links (this phone)")
    host.text("Run it on Irancell mobile data (Wi-Fi and VPN off). Rubika plays video only there, "
              "and the signed links work only from this phone's network.")
    url = host.input("Rubika link, like https://vod.rubika.ir/media/291423")
    try:
        if host.prefill:
            url.text = str(host.prefill).strip()
    except Exception:
        pass
    season = host.input("Season: a number or all")
    episodes = host.input("Episodes: all, last, 3 or 2-5")
    try:
        season.text = "all"
        episodes.text = "all"
    except Exception:
        pass
    quality = host.choice(QUALITIES)
    host.text("master = one link with all 4 qualities inside; all = every quality as its own link.")
    auth = host.input("Rubika auth (empty = guest)")
    host.button("Get links (this phone)", lambda: host.show(
        run, url.text.strip(), season.text.strip() or "all", episodes.text.strip() or "all",
        quality.value, auth.text.strip()))
    host.status()
    host.back_button("Back")


def run(host, page, season, eps, quality, auth):
    host.title("Getting the links")
    host.status()
    host.set_status("Asking Rubika from this phone...")
    notes = []

    def work():
        return collect(page, season, eps, quality, auth, notes)

    def done(res, err):
        if err:
            host.set_status("Failed: %s\n%s" % (err, "\n".join(notes[-6:])))
            return
        host.replace(show_results, res)

    host.background(work, done=done)
    host.back_button("Back")


def show_results(host, res):
    rows = res["rows"]
    host.title("%s (%d link)" % (res["title"], len(rows)))
    host.text("The links are signed and expire: use them soon, from this phone's network.")
    full = "\n".join("%s | %s | %s" % r for r in rows)
    urls = "\n".join(r[2] for r in rows)
    host.status()
    host.button("Copy all (name | quality | link)", lambda: (host.copy(full), host.set_status("Copied %d lines" % len(rows))))
    host.button("Copy links only", lambda: (host.copy(urls), host.set_status("Copied %d links" % len(rows))))
    host.button("Share links", lambda: host.share_text(full))
    for label, q, u in rows[:MAX_BUTTONS]:
        host.button("%s [%s] - copy link" % (label[:40], q), lambda u=u, l=label, q=q: (host.copy(u), host.set_status("Copied: %s [%s]" % (l, q))))
    if len(rows) > MAX_BUTTONS:
        host.text("Only the first %d are listed as buttons; Copy all has every link." % MAX_BUTTONS)
    if res["notes"]:
        host.text("Notes:\n" + "\n".join(res["notes"][-8:]))
    host.back_button("Back")
