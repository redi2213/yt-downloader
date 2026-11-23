"""Pornez adapter for Link Lab: reads the page, decodes the player-x.php?q=... parameter (base64 of a query string
that holds the <video><source src=...> tag) and returns the direct mp4 link.

Notes:
- The mp4 is on another host (hls.cdnlivestream.xyz); the download step sends the video page URL as Referer.
- The file has no quality list: the height is taken from the link if it has one (e.g. 720p), else the label is "mp4".
- Fallback: if the q parameter is missing, the player page / the page itself is searched for <source>, .mp4, .m3u8.
"""
import base64
import re
from urllib.parse import parse_qs, urljoin, unquote

SITE_ID = "pornez"
TITLE = "Pornez"
DOMAINS = ["pornez.cam", "pornez.net", "pornez.com"]

UA = "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/124 Mobile Safari/537.36"
_MEDIA = re.compile(r"""https?://[^\s"'<>\\]+?\.(?:mp4|m3u8)(?:\?[^\s"'<>\\]*)?""", re.I)


def _decode_q(q):
    q = unquote(q)
    q = q.replace("-", "+").replace("_", "/")
    raw = base64.b64decode(q + "=" * (-len(q) % 4)).decode("utf-8", "ignore")
    return (parse_qs(raw).get("tag") or [""])[0]


def _media_links(text):
    found = []
    for m in re.finditer(r"""<source[^>]+src=["']([^"']+)["']""", text or "", re.I):
        found.append(m.group(1))
    for m in _MEDIA.finditer(text or ""):
        found.append(m.group(0))
    out = []
    for u in found:
        u = u.replace("&amp;", "&").strip()
        if u and u not in out and not u.lower().endswith((".jpg", ".png", ".webp")):
            out.append(u)
    return out


def extract(url, proxy=None):
    import requests
    proxies = None
    if proxy:
        p = proxy.replace("socks5://", "socks5h://", 1)
        proxies = {"http": p, "https": p}
    headers = {"User-Agent": UA, "Referer": url}
    try:
        r = requests.get(url, headers=headers, proxies=proxies, timeout=20)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        return {"error": "page request failed: %s" % type(e).__name__}
    links = []
    m = re.search(r"player-x\.php\?q=([A-Za-z0-9+/=_%-]+)", html)
    if m:
        try:
            links = _media_links(_decode_q(m.group(1)))
        except Exception:
            links = []
        if not links:
            try:
                pu = urljoin(url, "/wp-content/plugins/clean-tube-player/public/player-x.php?q=" + m.group(1))
                links = _media_links(requests.get(pu, headers=headers, proxies=proxies, timeout=20).text)
            except Exception:
                pass
    if not links:
        links = _media_links(html)
    if not links:
        return {"error": "no video source found in the page (site layout changed?)"}
    t = re.search(r"""<meta[^>]+property=["']og:title["'][^>]+content=["']([^"']+)""", html, re.I) \
        or re.search(r"<title>([^<]+)</title>", html, re.I)
    title = (t.group(1) if t else "pornez").split(" | ")[0].strip() or "pornez"
    qualities = []
    for link in links:
        h = re.search(r"(\d{3,4})p", link)
        qualities.append({"quality": "%sp" % h.group(1) if h else "mp4", "link": link,
                          "ext": "m3u8" if ".m3u8" in link.lower() else "mp4"})
    return {"title": title, "qualities": qualities}


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    import site_runner
    site_runner.run_adapter(sys.modules[__name__])
