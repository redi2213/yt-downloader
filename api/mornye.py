"""Mornye / Tidal lossless links requested from the phone itself.

api.zarz.moe answers GitHub's runner IPs with a Cloudflare challenge (every
path, not only /bootstrap), so the signed-session calls cannot be made from
GitHub Actions. This module repeats them from the phone's own network (same
idea as api/filimo.py) and returns direct FLAC links from Tidal's CDN. It
only gets the links; downloading them is a separate step.

Flow (mirrors the Mornye tidal-web extension):
  1. Spotify link -> track list        (open.spotify.com embed page, no login)
  2. each track   -> ISRC + Tidal id   (POST api.zarz.moe/v1/resolve)
  3. signed session with api.zarz.moe  (bootstrap -> one browser check -> the
                                        user pastes the code the page shows ->
                                        exchange; kept on the phone, ~2 hours)
  4. each track   -> ticket -> /dl/tid -> manifest -> direct FLAC link

The session record is kept in the same on-device store as the GitHub token.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlparse, urlunparse

import requests

from api.github.auth import _settings_store  # one shared JsonStore: see api/filimo.py

TIDAL_API = "https://tidal.com/v1"
TIDAL_TOKEN = "49YxDN9a2aFV6RTG"        # the public web token the Mornye extension uses
BASE = "https://api.zarz.moe/v2"
RESOLVE_URL = "https://api.zarz.moe/v1/resolve"
# One signed session per provider: the gateway binds a session to the app version of
# the Mornye extension that made it (the values are the manifests' signedSession
# appVersion). A ticket for Qobuz/Deezer asked with the Tidal session is refused (403).
APP_VERSIONS = {"tidal": "tidal-web@1.2.5", "qobuz": "qobuz-web@1.2.21",
                "deezer": "deezer@1.3.5"}
PROVIDER_NAMES = {"tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer"}
PLATFORM = "extension"
SCHEME = "ZARZ-HMAC-V1"
PREFIX = "X-Zarz-"
WINDOW_SECONDS = 300
TIMEOUT = 25
SESSION_KEYS = {"tidal": "mornye_session", "qobuz": "mornye_session_qobuz",
                "deezer": "mornye_session_deezer"}
GATEWAY_UA = "SpotiFLAC-Mobile/%s"
BROWSER_UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

_SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|album|playlist|artist)[/:]([A-Za-z0-9]+)")
_EXT_BY_MIME = {"audio/flac": ".flac", "audio/x-flac": ".flac", "audio/mp4": ".m4a",
                "audio/mpeg": ".mp3"}

_LOG = []


def _log(message) -> None:
    """A short trail of what happened (no secrets) for 'Copy log' in the app."""
    _LOG.append(time.strftime("%H:%M:%S ") + str(message)[:300])
    del _LOG[:-200]


def get_log() -> str:
    return "\n".join(_LOG)


_http = requests.Session()
_http.headers.update({"Accept": "application/json", "Accept-Encoding": "gzip"})


class MornyeError(Exception):
    pass


class NeedsVerify(MornyeError):
    """The gateway wants the browser check again."""


class Cancelled(MornyeError):
    pass


# -- session record (one per provider) --------------------------------------------
def _load(provider: str = "tidal") -> dict:
    key = SESSION_KEYS[provider]
    rec = {}
    if _settings_store.exists(key):
        rec = dict(_settings_store.get(key))
    if not rec.get("install_id"):
        rec["install_id"] = secrets.token_hex(16)
        _save(provider, rec)
    return rec


def _save(provider: str, rec: dict) -> None:
    _settings_store.put(SESSION_KEYS[provider], **rec)


def clear_session(provider: str = None) -> None:
    for name in ([provider] if provider else list(SESSION_KEYS)):
        rec = _load(name)
        for key in ("session_id", "session_secret", "expires_at", "refresh_after"):
            rec.pop(key, None)
        _save(name, rec)


def _parse_time(value):
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    text = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), text)
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def session_valid(rec: dict) -> bool:
    if not rec.get("session_id") or not rec.get("session_secret"):
        return False
    expires = _parse_time(rec.get("expires_at"))
    if expires and datetime.now(timezone.utc) >= expires:
        return False
    return True


def _store_session(provider: str, rec: dict, data: dict) -> None:
    rec["session_id"] = data["session_id"]
    rec["session_secret"] = data["session_secret"]
    rec["expires_at"] = data.get("expires_at", "")
    rec["refresh_after"] = data.get("refresh_after", "") or ""
    _save(provider, rec)


def _ua(provider: str) -> dict:
    return {"User-Agent": GATEWAY_UA % APP_VERSIONS[provider]}


# -- gateway calls --------------------------------------------------------------
def _check_blocked(resp) -> None:
    if resp.status_code == 403 and "just a moment" in resp.text[:600].lower():
        raise MornyeError(
            "api.zarz.moe blocked this network (Cloudflare check). "
            "Turn off any VPN/proxy and try again, or try another connection.")


def _envelope(resp) -> dict:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _gateway_says_verify(resp) -> bool:
    """True when a 401/428 is the gateway's own (not the provider's)."""
    if resp.status_code not in (401, 428):
        return False
    env = _envelope(resp)
    origin = str(env.get("origin") or "").lower()
    code = str(env.get("code") or "").upper()
    if not (origin or code or env.get("action")):  # no envelope: go by status
        return True
    if origin != "gateway":
        return False
    return code in ("SESSION_INVALID", "VERIFY_REQUIRED")


def _error_text(resp) -> str:
    env = _envelope(resp)
    text = str(env.get("error") or env.get("message") or "").strip()
    return text or f"HTTP {resp.status_code}"


def _bootstrap(provider: str, rec: dict) -> dict:
    try:
        resp = _http.get(BASE + "/bootstrap", timeout=30, headers=_ua(provider),
                         params={"install_id": rec["install_id"],
                                 "app_version": APP_VERSIONS[provider]})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
    _log(f"bootstrap {provider} http {resp.status_code}")
    _check_blocked(resp)
    if resp.status_code != 200:
        raise MornyeError(f"Mornye gateway: {_error_text(resp)}")
    try:
        return resp.json()
    except ValueError as e:
        raise MornyeError("Unexpected reply from the Mornye gateway") from e


def _challenge_url(data: dict) -> str:
    """The page where the person passes the check. No callback is passed on
    purpose: the page only accepts the app's own deep link as a callback, and a
    deep link nothing handles would replace the page and hide the code box.
    Without a callback the page stays open and shows the code with a Copy button
    (after it closed itself once, opening it again shows the code at once)."""
    base = data.get("auth_url") or data.get("challenge_url")
    if base:
        parts = list(urlparse(base))
        query = [(k, v) for k, v in parse_qsl(parts[4]) if k != "cb"]
        parts[4] = urlencode(query)
        return urlunparse(parts)
    challenge_id = data.get("challenge_id")
    if not challenge_id:
        raise MornyeError("The gateway gave no verification challenge")
    return BASE + "/challenge?" + urlencode({"id": challenge_id})


def parse_grant(text: str) -> str:
    """The pasted text (full link, 'grant=...' or the bare code) -> the grant."""
    text = (text or "").strip()
    m = re.search(r"grant=([^&\s]+)", text)
    if m:
        return unquote(m.group(1))
    if re.fullmatch(r"[A-Za-z0-9_.~\-]{16,}", text):
        return text
    return ""


def _exchange(provider: str, rec: dict, grant: str) -> None:
    try:
        resp = _http.post(BASE + "/session/exchange", timeout=TIMEOUT, headers=_ua(provider),
                          json={"grant": grant, "install_id": rec["install_id"],
                                "app_version": APP_VERSIONS[provider],
                                "platform": PLATFORM})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
    _log(f"exchange {provider} http {resp.status_code}"
         + ("" if resp.status_code == 200 else " " + resp.text[:160]))
    _check_blocked(resp)
    if resp.status_code != 200:
        raise MornyeError(f"Verification was not accepted: {_error_text(resp)}")
    try:
        _store_session(provider, rec, resp.json())
    except (ValueError, KeyError) as e:
        raise MornyeError("Unexpected reply to the verification") from e


def _verify(provider: str, progress, ask_grant) -> None:
    """Bootstrap; if the gateway wants a human check, ask_grant(url, provider_name)
    opens it for the person and blocks until they paste the code (returns the text)."""
    rec = _load(provider)
    data = _bootstrap(provider, rec)
    if data.get("session_id") and data.get("session_secret"):
        _store_session(provider, rec, data)
        return
    url = _challenge_url(data)
    name = PROVIDER_NAMES[provider]
    progress(f"One-time check for {name}: finish it in the browser, then paste the code...")
    grant = parse_grant(ask_grant(url, name))
    if not grant:
        raise MornyeError("That is not a verification code")
    progress("Check done, starting the session...")
    _exchange(provider, rec, grant)


def _sign_headers(rec: dict, app_version: str, method: str, path: str, body: bytes) -> dict:
    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (now.microsecond // 1000)
    nonce = secrets.token_hex(12)
    body_hash = hashlib.sha256(body).hexdigest()
    window = int(time.time() // WINDOW_SECONDS)
    key = hmac.new(rec["session_secret"].encode(),
                   ("%d:%s" % (window, rec["session_id"])).encode(), hashlib.sha256).digest()
    key_text = base64.urlsafe_b64encode(key).rstrip(b"=").decode()
    signed_path = urlparse(BASE + path).path
    signing_input = "\n".join([SCHEME, method, signed_path, "", body_hash, stamp, nonce,
                               rec["session_id"], app_version, PLATFORM])
    sig = base64.urlsafe_b64encode(
        hmac.new(key_text.encode(), signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {PREFIX + "Session": rec["session_id"], PREFIX + "Timestamp": stamp,
            PREFIX + "Nonce": nonce, PREFIX + "Body-Sha256": body_hash,
            PREFIX + "Signature": sig, PREFIX + "App-Version": app_version,
            PREFIX + "Platform": PLATFORM}


def _maybe_refresh(provider: str, rec: dict) -> None:
    """Extends the session when the gateway's refresh_after has passed. A failed
    refresh is ignored - the session stays valid until it expires."""
    refresh_at = _parse_time(rec.get("refresh_after"))
    if not refresh_at or datetime.now(timezone.utc) < refresh_at:
        return
    body = json.dumps({"install_id": rec["install_id"]}, separators=(",", ":")).encode()
    headers = _sign_headers(rec, APP_VERSIONS[provider], "POST", "/session/refresh", body)
    headers["Content-Type"] = "application/json"
    headers.update(_ua(provider))
    try:
        resp = _http.post(BASE + "/session/refresh", data=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("session_id"):
                rec["session_id"] = data.get("session_id", rec["session_id"])
                rec["session_secret"] = data.get("session_secret", rec["session_secret"])
                rec["expires_at"] = data.get("expires_at", rec.get("expires_at", ""))
                rec["refresh_after"] = data.get("refresh_after", "") or ""
                _save(provider, rec)
    except (requests.exceptions.RequestException, ValueError):
        pass


def _ensure_session(provider: str, progress, ask_grant) -> None:
    rec = _load(provider)
    if session_valid(rec):
        _maybe_refresh(provider, rec)
        if session_valid(_load(provider)):
            return
    _verify(provider, progress, ask_grant)


def _signed_post(provider: str, path: str, obj: dict, extra: dict = None):
    rec = _load(provider)
    if not session_valid(rec):
        raise NeedsVerify("session expired")
    body = json.dumps(obj, separators=(",", ":")).encode()
    timeout = 60 if path.startswith("/dl/") else TIMEOUT
    for attempt in range(4):
        headers = _sign_headers(rec, APP_VERSIONS[provider], "POST", path, body)
        headers["Content-Type"] = "application/json"
        headers.update(_ua(provider))
        if extra:
            headers.update(extra)
        try:
            resp = _http.post(BASE + path, data=body, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout as e:
            raise MornyeError("Network error: the gateway did not answer in time") from e
        except requests.exceptions.RequestException as e:
            raise MornyeError(f"Network error: {str(e)[:80]}") from e
        _log(f"POST {path} ({provider}) -> http {resp.status_code}"
             + ("" if resp.status_code < 400 else " " + resp.text[:200]))
        _check_blocked(resp)
        if _gateway_says_verify(resp):
            clear_session(provider)
            raise NeedsVerify(_error_text(resp))
        if resp.status_code == 429:
            env = _envelope(resp)
            try:
                wait = int(env.get("retry_after_seconds") or resp.headers.get("Retry-After") or 2)
            except (TypeError, ValueError):
                wait = 2
            if attempt < 3:
                time.sleep(min(max(wait, 1), 10))
                continue
            raise MornyeError("The server is busy - try again in a minute")
        return resp
    raise MornyeError("The server is busy - try again in a minute")


# -- Spotify side -----------------------------------------------------------------
def parse_spotify(text: str):
    """A Spotify link / URI -> (kind, id), or (None, None)."""
    m = _SPOTIFY_RE.search((text or "").strip())
    return (m.group(1), m.group(2)) if m else (None, None)


def _tidy(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\xa0", " ")).strip()


def list_tracks(kind: str, sid: str) -> dict:
    """{'title', 'tracks': [{'id', 'title', 'artist'}]} from the public embed page."""
    try:
        resp = _http.get("https://open.spotify.com/embed/%s/%s" % (kind, sid), timeout=TIMEOUT,
                         headers={"User-Agent": BROWSER_UA, "Accept": "text/html"})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
    if resp.status_code != 200:
        raise MornyeError(f"Spotify returned HTTP {resp.status_code} for this link")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                  resp.text, re.S)
    if not m:
        raise MornyeError("Could not read this Spotify page")
    try:
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
    except (ValueError, KeyError, TypeError) as e:
        raise MornyeError("Spotify page format changed - cannot read it") from e
    title = _tidy(entity.get("title") or entity.get("name"))
    artist = _tidy(entity.get("subtitle"))
    tracks = []
    if kind == "track":
        names = [str(a.get("name") or "") for a in (entity.get("artists") or [])
                 if isinstance(a, dict)]
        artist = _tidy(", ".join(n for n in names if n)) or artist
        tracks.append({"id": sid, "title": title, "artist": artist})
    else:
        for item in entity.get("trackList") or []:
            uri = str(item.get("uri") or "")
            if not uri.startswith("spotify:track:"):
                continue
            tracks.append({"id": uri.rsplit(":", 1)[-1], "title": _tidy(item.get("title")),
                           "artist": _tidy(item.get("subtitle"))})
    if not tracks:
        raise MornyeError("No tracks found in this Spotify link")
    return {"title": title, "tracks": tracks}


_TRACK_LINK_RES = (
    re.compile(r"open\.spotify\.com/(?:intl-[a-z]+/)?track/([A-Za-z0-9]{22})"),
    re.compile(r"open\.spotify\.com\s*(?:\u203a|&rsaquo;|&#8250;|&gt;)\s*track\s*"
               r"(?:\u203a|&rsaquo;|&#8250;|&gt;)\s*([A-Za-z0-9]{22})"),
)
_SEARCH_ENGINES = (
    ("DuckDuckGo", "https://html.duckduckgo.com/html/", "q"),
    ("Bing", "https://www.bing.com/search", "q"),
    ("Brave", "https://search.brave.com/search", "q"),
    ("Yahoo", "https://search.yahoo.com/search", "p"),
)


def search_spotify(query: str, limit: int = 5) -> list:
    """A song name -> [{'id', 'title', 'artist'}]. No Spotify login: the track
    links come from a web search (several engines, first one that answers), the
    names from each track's embed page."""
    query = _tidy(query)
    if not query:
        raise MornyeError("Type a song name or paste a Spotify link")
    ids, tried, answered = [], [], False
    for name, url, param in _SEARCH_ENGINES:
        try:
            resp = _http.get(url, params={param: "site:open.spotify.com/track " + query},
                             timeout=TIMEOUT,
                             headers={"User-Agent": BROWSER_UA, "Accept": "text/html"})
        except requests.exceptions.RequestException:
            tried.append(f"{name}: no network")
            continue
        if resp.status_code != 200:
            tried.append(f"{name}: HTTP {resp.status_code}")
            continue
        answered = True
        text = unquote(resp.text)
        for rx in _TRACK_LINK_RES:
            for found in rx.findall(text):
                if found not in ids:
                    ids.append(found)
        if ids:
            break
        tried.append(f"{name}: no links")
    del _LOG[:]
    _log("search '%s': %s" % (query[:40], "; ".join(tried) or "ok"))
    if not ids:
        if not answered:
            raise MornyeError("Search failed (" + "; ".join(tried) +
                              ") - paste the Spotify link instead")
        return []
    results = []
    for sid in ids[:limit + 2]:
        try:
            info = list_tracks("track", sid)["tracks"][0]
        except (MornyeError, KeyError, IndexError):
            continue
        results.append({"id": sid, "title": info["title"], "artist": info["artist"]})
        if len(results) >= limit:
            break
    return results


def resolve_ids(spotify_track_id: str) -> dict:
    """Spotify track id -> {'tidal': id, 'qobuz': id, 'deezer': id} (only the ones that exist)."""
    payload = {"url": "https://open.spotify.com/track/" + spotify_track_id}
    last = ""
    for attempt in range(3):
        try:
            resp = _http.post(RESOLVE_URL, json=payload, timeout=TIMEOUT,
                              headers={"User-Agent": BROWSER_UA})
        except requests.exceptions.RequestException as e:
            last = f"Network error: {str(e)[:60]}"
            time.sleep(1.5 * (attempt + 1))
            continue
        _check_blocked(resp)
        if resp.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {resp.status_code}"
            time.sleep(2 * (attempt + 1))
            continue
        if resp.status_code != 200:
            raise MornyeError(f"Resolver returned HTTP {resp.status_code}")
        env = _envelope(resp)
        if not env.get("success"):
            return {}
        urls = env.get("songUrls") or {}
        ids = {}
        for key, name in (("Tidal", "tidal"), ("Qobuz", "qobuz"), ("Deezer", "deezer")):
            link = urls.get(key)
            if isinstance(link, dict):
                link = link.get("url") or link.get("link")
            m = re.search(r"/track/([A-Za-z0-9]+)", str(link or ""))
            if m:
                ids[name] = m.group(1)
        return ids
    raise MornyeError(last or "Resolver did not answer")


# -- provider links -------------------------------------------------------------
def _expand(template: str, number: int) -> str:
    def fill(match):
        width = match.group(1)
        return str(number).zfill(int(width)) if width else str(number)
    return re.sub(r"\$Number(?:%0(\d+)d)?\$", fill, template)


def parse_dash_template(text: str) -> dict:
    """A DASH manifest -> {'init', 'media' (still with $Number$), 'count', 'start'},
    as the Mornye extension reads it: the templates + the number of <S> segments."""
    init = re.search(r'initialization="([^"]+)"', text, re.I)
    media = re.search(r'media="([^"]+)"', text, re.I)
    if not init or not media:
        raise MornyeError("The manifest has no segment templates")
    count = 0
    for m in re.finditer(r'<S\s+[^>]*?d="(\d+)"(?:\s+r="(-?\d+)")?[^>]*/?>', text, re.I):
        repeat = int(m.group(2) or 0)
        count += (repeat if repeat > 0 else 0) + 1
    if count <= 0:
        raise MornyeError("The manifest lists no media segments")
    start = re.search(r'startNumber="(\d+)"', text, re.I)
    return {"init": init.group(1).replace("&amp;", "&"),
            "media": media.group(1).replace("&amp;", "&"),
            "count": count, "start": int(start.group(1)) if start else 1}


def parse_dash(text: str) -> list:
    """A DASH manifest -> [init url, media url 1, media url 2, ...]."""
    t = parse_dash_template(text)
    return [t["init"]] + [_expand(t["media"], t["start"] + i) for i in range(t["count"])]


def _ticket(app: str, code: str, resource: str) -> str:
    resource_hash = hashlib.sha256(
        ("%s:track:%s" % (code, resource)).lower().encode()).hexdigest()
    resp = _signed_post(app, "/tickets", {"capability": "download_ticket", "provider": code,
                                          "resource_hash": resource_hash})
    if resp.status_code >= 400:
        raise MornyeError(f"Ticket refused: {_error_text(resp)}")
    env = _envelope(resp)
    ticket = str(env.get("ticket_id") or env.get("ticket") or "").strip()
    if not ticket:
        raise MornyeError("The gateway gave no download ticket")
    return ticket


def get_tidal_download(tidal_id: str, quality: str = "LOSSLESS") -> dict:
    """{'kind': 'direct', 'url', 'ext', 'info'} or {'kind': 'dash', 'segments', 'info'}."""
    ticket = _ticket("tidal", "tid", str(tidal_id))
    resp = _signed_post("tidal", "/dl/tid", {"id": str(tidal_id), "quality": quality},
                        {"X-Zarz-Ticket": ticket})
    if resp.status_code >= 400:
        raise MornyeError(f"Tidal: {_error_text(resp)}")
    data = _envelope(resp).get("data") or {}
    if str(data.get("assetPresentation") or "").upper() == "PREVIEW":
        raise MornyeError("Only a 30-second preview is available")
    manifest_b64 = data.get("manifest")
    if not manifest_b64:
        raise MornyeError("Tidal gave no manifest for this track")
    try:
        text = base64.b64decode(manifest_b64).decode("utf-8", "replace")
    except ValueError as e:
        raise MornyeError("Unreadable manifest") from e
    bits, rate = data.get("bitDepth"), data.get("sampleRate")
    info = str(data.get("audioQuality") or quality)
    if bits and rate:
        info += " %s-bit %.1f kHz" % (bits, float(rate) / 1000.0)
    if text.lstrip().startswith("{"):
        try:
            bts = json.loads(text)
            url = str((bts.get("urls") or [""])[0])
        except ValueError as e:
            raise MornyeError("Unreadable manifest") from e
        if not url:
            raise MornyeError("The manifest has no direct link")
        mime = str(bts.get("mimeType") or data.get("manifestMimeType")
                   or "audio/flac").lower()
        _log("tidal: direct link, host " + (urlparse(url).netloc or "?"))
        return {"kind": "direct", "url": url, "ext": _EXT_BY_MIME.get(mime, ".flac"),
                "info": info}
    template = parse_dash_template(text)
    segments = [template["init"]] + [
        _expand(template["media"], template["start"] + i) for i in range(template["count"])]
    _log("tidal: DASH, %d media segments, host %s"
         % (len(segments) - 1, urlparse(segments[0]).netloc or "?"))
    return {"kind": "dash", "segments": segments, "template": template, "info": info}


def get_qobuz_download(qobuz_id: str, quality: str = "LOSSLESS") -> dict:
    """A direct FLAC link from Qobuz: {'kind': 'direct', 'url', 'ext', 'info'}."""
    track_url = "https://open.qobuz.com/track/" + str(qobuz_id)
    ticket = _ticket("qobuz", "qbz", track_url)
    resp = _signed_post("qobuz", "/dl/qbz", {
        "quality": "hi-res-max" if quality == "HI_RES_LOSSLESS" else "cd",
        "upload_to_r2": False, "id": str(qobuz_id), "type": "track", "url": track_url,
    }, {"X-Zarz-Ticket": ticket})
    if resp.status_code != 200:
        raise MornyeError(f"Qobuz: {_error_text(resp)}")
    env = _envelope(resp)
    if env.get("error") or env.get("detail"):
        raise MornyeError("Qobuz: " + str(env.get("error") or env.get("detail"))[:120])
    if env.get("success") is False:
        raise MornyeError("Qobuz: " + str(env.get("message") or "request failed")[:120])
    nested = env.get("data") if isinstance(env.get("data"), dict) else {}
    url = ""
    for source in (env, nested):
        for key in ("download_url", "url", "link"):
            if not url and str(source.get(key) or "").strip():
                url = str(source[key]).strip()
    if not url:
        raise MornyeError("Qobuz gave no download link")
    bits = env.get("bit_depth") or nested.get("bit_depth")
    rate = env.get("sampling_rate") or nested.get("sampling_rate")
    info = "Qobuz FLAC"
    if bits and rate:
        rate = float(rate)
        info += " %s-bit %.1f kHz" % (bits, rate if rate < 1000 else rate / 1000.0)
    _log("qobuz: direct link, host " + (urlparse(url).netloc or "?"))
    return {"kind": "direct", "url": url, "ext": ".flac", "info": info}


def _flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
    return None


def get_deezer_download(deezer_id: str, quality: str = "LOSSLESS") -> dict:
    """A direct FLAC link from Deezer. Streams that need client-side decryption
    (Blowfish) are not supported yet and raise MornyeError."""
    track_url = "https://www.deezer.com/track/" + quote(str(deezer_id), safe="")
    ticket = _ticket("deezer", "dzr", track_url)
    resp = _signed_post("deezer", "/dl/dzr", {"id": str(deezer_id), "type": "track",
                                    "platform": "deezer", "url": track_url},
                        {"X-Zarz-Ticket": ticket})
    if resp.status_code != 200:
        raise MornyeError(f"Deezer: {_error_text(resp)}")
    d = _envelope(resp)
    if d.get("success") is not True:
        raise MornyeError("Deezer: " + str(d.get("message") or d.get("error")
                                           or "no link")[:120])
    direct = _flag(d.get("direct_downloadable"))
    url = ""
    if direct is True and d.get("direct_download_url"):
        url = str(d["direct_download_url"])
    url = url or str(d.get("download_url") or d.get("direct_download_url") or "")
    if not url:
        raise MornyeError("Deezer gave no download link")
    needs = _flag(d.get("requires_client_decryption"))
    if needs is None:
        needs = (not direct) if direct is not None else bool(_flag(d.get("deezer_encrypted")))
    if needs:
        raise MornyeError("Deezer: this stream needs decryption (not supported yet)")
    fmt = str(d.get("deezer_format") or "flac").lower()
    if fmt != "flac":
        raise MornyeError("Deezer gave %s, not lossless" % fmt.upper())
    _log("deezer: direct link, host " + (urlparse(url).netloc or "?"))
    return {"kind": "direct", "url": url, "ext": ".flac", "info": "Deezer FLAC"}


PROVIDERS = {"tidal": get_tidal_download, "qobuz": get_qobuz_download,
             "deezer": get_deezer_download}


def _tidal_get(path: str, params: dict) -> dict:
    try:
        resp = _http.get(TIDAL_API + path, params=params, timeout=TIMEOUT,
                         headers={"X-Tidal-Token": TIDAL_TOKEN, "User-Agent": BROWSER_UA,
                                  "Accept": "application/json"})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:60]}") from e
    if resp.status_code != 200:
        raise MornyeError(f"Tidal metadata HTTP {resp.status_code}")
    data = resp.json()
    return data if isinstance(data, dict) else {}


def tidal_meta(tidal_id: str, cache: dict) -> dict:
    """{'tags': {...}, 'cover_url': '...'} for a Tidal track ({} if Tidal does not
    answer). Album details are kept in cache, so an album costs one extra call."""
    params = {"countryCode": "US"}
    track = _tidal_get("/tracks/" + str(tidal_id), params)
    album = track.get("album") or {}
    album_id = str(album.get("id") or "")
    details = cache.get("album:" + album_id) if album_id else {}
    if details is None:
        try:
            details = _tidal_get("/albums/" + album_id, params)
        except MornyeError:
            details = {}
        cache["album:" + album_id] = details
    details = details or {}
    title = str(track.get("title") or "").strip()
    if track.get("version"):
        title += " (%s)" % track["version"]
    artists = ", ".join(str(a.get("name")) for a in (track.get("artists") or [])
                        if isinstance(a, dict) and a.get("name"))
    tags = {
        "TITLE": title, "ARTIST": artists, "ALBUM": album.get("title"),
        "ALBUMARTIST": (details.get("artist") or {}).get("name"),
        "DATE": details.get("releaseDate") or str(track.get("streamStartDate") or "")[:10],
        "TRACKNUMBER": track.get("trackNumber"), "TRACKTOTAL": details.get("numberOfTracks"),
        "DISCNUMBER": track.get("volumeNumber"), "DISCTOTAL": details.get("numberOfVolumes"),
        "ISRC": track.get("isrc"), "COPYRIGHT": track.get("copyright"),
    }
    tags = {k: str(v) for k, v in tags.items() if v not in (None, "", 0)}
    cover = str(album.get("cover") or "")
    cover_url = ("https://resources.tidal.com/images/%s/1280x1280.jpg"
                 % cover.replace("-", "/")) if cover else ""
    return {"tags": tags, "cover_url": cover_url}


def track_meta(track: dict, ids: dict, cache: dict) -> dict:
    """Tags + cover link: Spotify's title/artist, overridden by Tidal's richer data."""
    meta = {"tags": {k: v for k, v in (("TITLE", track.get("title")),
                                       ("ARTIST", track.get("artist"))) if v},
            "cover_url": ""}
    if ids.get("tidal"):
        try:
            found = tidal_meta(ids["tidal"], cache)
            meta["tags"].update(found.get("tags") or {})
            meta["cover_url"] = found.get("cover_url") or ""
        except Exception as e:
            _log("metadata failed: %s" % str(e)[:100])
    return meta


def _safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", _tidy(text)).strip(" .")
    return text[:110]


def file_name(index: int, total: int, track: dict, ext: str, numbered: bool) -> str:
    base = " - ".join(p for p in (_safe_name(track["artist"]), _safe_name(track["title"])) if p)
    base = base or "track"
    if numbered:
        width = max(2, len(str(total)))
        base = "%s - %s" % (str(index).zfill(width), base)
    return base + ext


def run_tracks(url: str, quality: str, order, progress, ask_grant, cancel, handle) -> dict:
    """Runs the whole flow on the phone's network. For each track, in order, the
    providers are tried; handle(pos, total, track, item, numbered) downloads and
    saves it and returns the saved file name (raise to try the next provider).
    Returns {'title', 'kind', 'saved', 'failed'}; raises MornyeError."""
    progress = progress or (lambda text: None)
    quality = quality or "LOSSLESS"
    order = [p for p in (order or ["tidal", "qobuz"]) if p in PROVIDERS] or ["tidal", "qobuz"]
    del _LOG[:]
    _log("providers: " + ",".join(order))
    kind, sid = parse_spotify(url)
    if not kind:
        raise MornyeError("Paste a Spotify track, album, playlist or artist link")

    listing = list_tracks(kind, sid)
    tracks = listing["tracks"]
    total = len(tracks)
    _log(f"spotify {kind}: {total} track(s)")
    notes = []
    if total >= 100 and kind in ("playlist", "artist"):
        notes.append("note: Spotify shows only the first 100 tracks of this link "
                     "without a login")
    progress(f"{total} track(s) found - looking them up...")

    matched, failed = [], []
    for pos, track in enumerate(tracks, 1):
        if cancel and cancel():
            raise Cancelled("Cancelled")
        progress(f"Looking up {pos}/{total}")
        label = " - ".join(p for p in (track["artist"], track["title"]) if p) or track["id"]
        try:
            ids = resolve_ids(track["id"])
        except MornyeError as e:
            failed.append(f"{label}: {e}")
            continue
        if not any(ids.get(p) for p in order):
            failed.append(f"{label}: not found on " + "/".join(order))
            continue
        matched.append((pos, track, ids, label))
        time.sleep(0.25)
    _log(f"found on a provider: {len(matched)}/{total}")
    for line in failed:
        _log("lookup failed: " + line)
    if not matched:
        raise MornyeError("None of the tracks were found on " + "/".join(order))

    numbered = kind == "album"
    saved = []
    meta_cache = {}
    for pos, track, ids, label in matched:
        if cancel and cancel():
            raise Cancelled("Cancelled")
        meta = track_meta(track, ids, meta_cache)
        errors, done = [], False
        for provider in order:
            pid = ids.get(provider)
            if not pid:
                continue
            for attempt in range(3):
                try:
                    _ensure_session(provider, progress, ask_grant)
                    progress(f"{pos}/{total} {label[:40]} - {provider}")
                    item = PROVIDERS[provider](pid, quality)
                    item["provider"] = provider
                    item["meta"] = meta
                    saved.append(handle(pos, total, track, item, numbered))
                    done = True
                    break
                except Cancelled:
                    raise
                except NeedsVerify:
                    # the session was cleared: the next attempt asks for the check again
                    if attempt == 2:
                        errors.append(f"{provider}: session refused repeatedly")
                        break
                except Exception as e:
                    text = str(e)
                    transient = text.startswith("Network error") or "busy" in text.lower()
                    if transient and attempt < 2:
                        _log(f"{provider} transient error, retrying: {text[:120]}")
                        time.sleep(3)
                        continue
                    errors.append(f"{provider}: {text[:140]}")
                    _log(f"{provider} failed for {label}: {text[:200]}")
                    break
            if done:
                break
        if not done:
            failed.append(f"{label}: " + "; ".join(errors or ["no provider"]))
        time.sleep(0.2)
    _log(f"saved: {len(saved)}/{len(matched)}")
    if not saved:
        raise MornyeError("Nothing could be downloaded. " + (failed[-1] if failed else ""))
    return {"title": listing["title"], "kind": kind, "saved": saved,
            "failed": failed + notes}
