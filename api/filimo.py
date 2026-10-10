"""Filimo API calls made directly from the phone (not from GitHub Actions).

Filimo is free to watch only on Irancell mobile data, and it decides that
from the network the request comes from - so the link has to be requested
from the phone. This mirrors what filimo-plus-cli does for `-l`:
  1. GET config/uxEvent       -> checks the token and gives the profile name
  2. GET movie/watch/uid/<id>  -> title + master HLS (m3u8) link
  3. GET master playlist       -> the quality variants, each with its own link
The Filimo token is kept in the same on-device store as the GitHub token.
"""
import re
from urllib.parse import urljoin, urlparse

import requests

from api.github.auth import _settings_store  # same JsonStore file: see note below

# NOTE: a second JsonStore on the same file would overwrite the first one's
# keys on every write, so the Filimo token reuses the existing store object.

BASE = "https://api.filimo.com/api/fa/v1"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36")
TIMEOUT = 25

# '#360p' line, then the STREAM-INF line with RESOLUTION=..., then the link
_VARIANT_RE = re.compile(r"#(\d+(.*?))\n(.*)RESOLUTION=([^,]*)(.*?)\n(.*)")


class FilimoError(Exception):
    pass


def get_token() -> str:
    if _settings_store.exists("filimo"):
        return _settings_store.get("filimo")["token"]
    return ""


def save_token(token: str) -> None:
    _settings_store.put("filimo", token=token)


def _get(url: str, token: str) -> str:
    headers = {"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT}
    try:
        r = requests.get(url, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise FilimoError(f"Network error: {str(e)[:80]}") from e
    if r.status_code in (401, 403):
        raise FilimoError("Filimo token invalid or expired. Update it in Settings.")
    if r.status_code != 200:
        raise FilimoError(f"Filimo returned HTTP {r.status_code}")
    return r.text


def item_id(text: str) -> str:
    """A Filimo link or a bare item id -> the id."""
    text = text.strip()
    if text.startswith("https://") or text.startswith("http://"):
        path = urlparse(text).path.rstrip("/")
        text = path.rsplit("/", 1)[-1]
    return text


def get_profile_name(token: str) -> str:
    data = _get(f"{BASE}/web/config/uxEvent", token)
    try:
        import json
        return json.loads(data)["data"]["user"]["selectedProfile"]["name"] or ""
    except (ValueError, KeyError, TypeError):
        return ""


def get_watch(token: str, uid: str) -> dict:
    import json
    try:
        return json.loads(_get(f"{BASE}/movie/watch/watch/uid/{uid}", token))
    except ValueError as e:
        raise FilimoError("Unexpected reply from Filimo") from e


def master_link(watch: dict) -> str:
    # Like the CLI: the last 'application/vnd.apple.mpegurl' source wins.
    link = ""
    sources = (watch.get("data", {}).get("attributes", {}).get("multiSRC") or [])
    for group in sources:
        for source in group:
            if source.get("type") == "application/vnd.apple.mpegurl":
                link = source.get("src", "")
                break
    return link


def get_variants(token: str, master: str) -> list:
    text = _get(master, token).replace("\r\n", "\n")
    out = []
    for m in _VARIANT_RE.finditer(text):
        link = m.group(6).strip()
        if not link:
            continue
        out.append({"quality": m.group(1), "resolution": m.group(4),
                    "link": urljoin(master, link)})
    return out


def _height(quality: str) -> int:
    m = re.search(r"(\d+)p\b", quality)
    return int(m.group(1)) if m else 0


def pick_variant(variants: list, wanted: str) -> dict:
    """'Best available' -> highest; '720p' -> exact, else the nearest lower."""
    if not variants:
        raise FilimoError("No video qualities found")
    ranked = sorted(variants, key=lambda v: _height(v["quality"]), reverse=True)
    if wanted == "Best available":
        return ranked[0]
    target = int(re.match(r"\d+", wanted).group(0))
    for v in ranked:
        if _height(v["quality"]) == target:
            return v
    lower = [v for v in ranked if 0 < _height(v["quality"]) < target]
    if lower:
        return lower[0]
    raise FilimoError(f"Quality {wanted} not available")


def fetch_link(url_or_id: str, quality: str) -> dict:
    """Returns {'title', 'quality', 'link'} - runs on the phone's network."""
    token = get_token()
    if not token:
        raise FilimoError("No Filimo token. Add it in Settings first.")
    if not get_profile_name(token):
        raise FilimoError("Filimo token invalid or expired. Update it in Settings.")

    watch = get_watch(token, item_id(url_or_id))
    master = master_link(watch)
    if not master:
        raise FilimoError("HLS link not found for this item")

    variant = pick_variant(get_variants(token, master), quality)
    title = watch.get("data", {}).get("attributes", {}).get("movie_title", "")
    return {"title": title, "quality": variant["quality"], "link": variant["link"]}
