"""Porntasia adapter for Link Lab: uses the site's own JSON API (api.pt1269.com /pwa/video/info).

Notes:
- The site labels its tiers "240" / "480" for guests, but the HLS folders (and the real video) are 720p / 1080p.
  The real height is read from the playlist, so the app shows 720p / 1080p.
- The playlists are media playlists (AES-128). The key and segment links are signed and expire after a few
  hours, so the api.pt1269.com playlist link is returned (it makes fresh signed links on every request).
- No special headers are needed for the playlist, key or segments.
"""
import re

SITE_ID = "porntasia"
TITLE = "Porntasia"
DOMAINS = ["porntasia.app", "pt1269.com"]

API = "https://api.pt1269.com"
UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"
TYPES = {"videos": "short", "jav": "long", "anime": "anime"}


def _video_ref(url):
    m = re.search(r"/(videos|jav|anime)/play/(\d+)", url or "")
    if not m:
        return None, None
    return TYPES[m.group(1)], m.group(2)


def extract(url, proxy=None):
    import requests
    vtype, vid = _video_ref(url)
    if not vid:
        return {"error": "not a Porntasia video link (/videos|jav|anime/play/<id>)"}
    proxies = None
    if proxy:
        p = proxy.replace("socks5://", "socks5h://", 1)
        proxies = {"http": p, "https": p}
    headers = {"User-Agent": UA, "Referer": "https://porntasia.app/", "Origin": "https://porntasia.app"}
    try:
        r = requests.get(API + "/pwa/video/info/" + vid, headers=headers, proxies=proxies, timeout=20,
                         params={"lang": "en", "platform": "web", "token": "", "video_type": vtype})
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": "info request failed: %s" % type(e).__name__}
    status = (data.get("status") or {}).get("code")
    if status != 200:
        return {"error": "site API status %s" % status}
    info = data.get("response") or {}
    urls = info.get("video_urls") or {}
    if not urls:
        return {"error": "no video_urls (login/VIP needed?)"}
    qualities = []
    for label, path in urls.items():
        link = path if str(path).startswith("http") else API + path
        height = None
        try:
            t = requests.get(link, headers=headers, proxies=proxies, timeout=20).text
            m = re.search(r"/(\d{3,4})/(?:segment|key)", t)
            if m:
                height = int(m.group(1))
        except Exception:
            pass
        if not height and str(label).isdigit():
            height = int(label)
        qualities.append({"quality": "%dp" % height if height else str(label), "link": link, "ext": "m3u8"})
    if not qualities:
        return {"error": "no quality found"}
    return {"title": info.get("video_title") or "porntasia-" + vid, "qualities": qualities}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import site_runner
    site_runner.run_adapter(sys.modules[__name__])
