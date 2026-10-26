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

BASE = "https://api.zarz.moe/v2"
RESOLVE_URL = "https://api.zarz.moe/v1/resolve"
APP_VERSION = "tidal-web@1.2.5"
PLATFORM = "extension"
SCHEME = "ZARZ-HMAC-V1"
PREFIX = "X-Zarz-"
WINDOW_SECONDS = 300
TIMEOUT = 25
SESSION_KEY = "mornye_session"
GATEWAY_UA = "SpotiFLAC-Mobile/" + APP_VERSION
BROWSER_UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")

_SPOTIFY_RE = re.compile(
    r"(?:open\.spotify\.com/(?:intl-[a-z]+/)?|spotify:)(track|album|playlist|artist)[/:]([A-Za-z0-9]+)")
_EXT_BY_MIME = {"audio/flac": ".flac", "audio/x-flac": ".flac", "audio/mp4": ".m4a",
                "audio/mpeg": ".mp3"}

_http = requests.Session()
_http.headers.update({"Accept": "application/json", "Accept-Encoding": "gzip",
                      "User-Agent": GATEWAY_UA})


class MornyeError(Exception):
    pass


class NeedsVerify(MornyeError):
    """The gateway wants the browser check again."""


class Cancelled(MornyeError):
    pass


# -- session record -------------------------------------------------------------
def _load() -> dict:
    rec = {}
    if _settings_store.exists(SESSION_KEY):
        rec = dict(_settings_store.get(SESSION_KEY))
    if not rec.get("install_id"):
        rec["install_id"] = secrets.token_hex(16)
        _save(rec)
    return rec


def _save(rec: dict) -> None:
    _settings_store.put(SESSION_KEY, **rec)


def clear_session() -> None:
    rec = _load()
    for key in ("session_id", "session_secret", "expires_at", "refresh_after"):
        rec.pop(key, None)
    _save(rec)


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


def session_valid(rec: dict = None) -> bool:
    rec = rec or _load()
    if not rec.get("session_id") or not rec.get("session_secret"):
        return False
    expires = _parse_time(rec.get("expires_at"))
    if expires and datetime.now(timezone.utc) >= expires:
        return False
    return True


def _store_session(rec: dict, data: dict) -> None:
    rec["session_id"] = data["session_id"]
    rec["session_secret"] = data["session_secret"]
    rec["expires_at"] = data.get("expires_at", "")
    rec["refresh_after"] = data.get("refresh_after", "") or ""
    _save(rec)


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
    """True when a 401/428 is the gateway's own (not Tidal's)."""
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


def _bootstrap(rec: dict) -> dict:
    try:
        resp = _http.get(BASE + "/bootstrap", timeout=30,
                         params={"install_id": rec["install_id"], "app_version": APP_VERSION})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
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
    Without a callback the page stays open and, a few seconds after the check,
    shows the code with a Copy button."""
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


def _exchange(rec: dict, grant: str) -> None:
    try:
        resp = _http.post(BASE + "/session/exchange", timeout=TIMEOUT, json={
            "grant": grant, "install_id": rec["install_id"],
            "app_version": APP_VERSION, "platform": PLATFORM})
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
    _check_blocked(resp)
    if resp.status_code != 200:
        raise MornyeError(f"Verification was not accepted: {_error_text(resp)}")
    try:
        _store_session(rec, resp.json())
    except (ValueError, KeyError) as e:
        raise MornyeError("Unexpected reply to the verification") from e


def _verify(progress, ask_grant) -> None:
    """Bootstrap; if the gateway wants a human check, ask_grant(url) opens it for
    the person and blocks until they paste the code (returns the pasted text)."""
    rec = _load()
    data = _bootstrap(rec)
    if data.get("session_id") and data.get("session_secret"):
        _store_session(rec, data)
        return
    url = _challenge_url(data)
    progress("One-time check: finish it in the browser, then paste the code...")
    grant = parse_grant(ask_grant(url))
    if not grant:
        raise MornyeError("That is not a verification code")
    progress("Check done, starting the session...")
    _exchange(rec, grant)


def _sign_headers(rec: dict, method: str, path: str, body: bytes) -> dict:
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
                               rec["session_id"], APP_VERSION, PLATFORM])
    sig = base64.urlsafe_b64encode(
        hmac.new(key_text.encode(), signing_input.encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return {PREFIX + "Session": rec["session_id"], PREFIX + "Timestamp": stamp,
            PREFIX + "Nonce": nonce, PREFIX + "Body-Sha256": body_hash,
            PREFIX + "Signature": sig, PREFIX + "App-Version": APP_VERSION,
            PREFIX + "Platform": PLATFORM}


def _maybe_refresh(rec: dict) -> None:
    """Extends the session when the gateway's refresh_after has passed. A failed
    refresh is ignored - the session stays valid until it expires."""
    refresh_at = _parse_time(rec.get("refresh_after"))
    if not refresh_at or datetime.now(timezone.utc) < refresh_at:
        return
    body = json.dumps({"install_id": rec["install_id"]}, separators=(",", ":")).encode()
    headers = _sign_headers(rec, "POST", "/session/refresh", body)
    headers["Content-Type"] = "application/json"
    try:
        resp = _http.post(BASE + "/session/refresh", data=body, headers=headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("session_id"):
                rec["session_id"] = data.get("session_id", rec["session_id"])
                rec["session_secret"] = data.get("session_secret", rec["session_secret"])
                rec["expires_at"] = data.get("expires_at", rec.get("expires_at", ""))
                rec["refresh_after"] = data.get("refresh_after", "") or ""
                _save(rec)
    except (requests.exceptions.RequestException, ValueError):
        pass


def _ensure_session(progress, ask_grant) -> None:
    if session_valid():
        _maybe_refresh(_load())
        if session_valid():
            return
    _verify(progress, ask_grant)


def _signed_post(path: str, obj: dict, extra: dict = None):
    rec = _load()
    if not session_valid(rec):
        raise NeedsVerify("session expired")
    body = json.dumps(obj, separators=(",", ":")).encode()
    headers = _sign_headers(rec, "POST", path, body)
    headers["Content-Type"] = "application/json"
    if extra:
        headers.update(extra)
    try:
        resp = _http.post(BASE + path, data=body, headers=headers, timeout=TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise MornyeError(f"Network error: {str(e)[:80]}") from e
    _check_blocked(resp)
    if _gateway_says_verify(resp):
        clear_session()
        raise NeedsVerify(_error_text(resp))
    if resp.status_code == 429:
        raise MornyeError("Too many requests - wait a minute and refresh")
    return resp


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


def resolve_tidal_id(spotify_track_id: str) -> str:
    """Spotify track id -> Tidal track id ('' if the song is not on Tidal)."""
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
            return ""
        tidal = (env.get("songUrls") or {}).get("Tidal")
        if isinstance(tidal, dict):
            tidal = tidal.get("url") or tidal.get("link")
        m = re.search(r"/track/(\d+)", str(tidal or ""))
        return m.group(1) if m else ""
    raise MornyeError(last or "Resolver did not answer")


# -- Tidal link ---------------------------------------------------------------------
def get_download(tidal_id: str, quality: str = "LOSSLESS") -> dict:
    """Direct CDN link for one Tidal track: {'url', 'ext', 'info'}."""
    resource_hash = hashlib.sha256(("tid:track:" + tidal_id).lower().encode()).hexdigest()
    resp = _signed_post("/tickets", {"capability": "download_ticket", "provider": "tid",
                                     "resource_hash": resource_hash})
    if resp.status_code >= 400:
        raise MornyeError(f"Ticket refused: {_error_text(resp)}")
    env = _envelope(resp)
    ticket = str(env.get("ticket_id") or env.get("ticket") or "").strip()
    if not ticket:
        raise MornyeError("The gateway gave no download ticket")

    resp = _signed_post("/dl/tid", {"id": str(tidal_id), "quality": quality},
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
    if not text.lstrip().startswith("{"):
        raise MornyeError("This quality comes in segments (not supported yet)")
    try:
        bts = json.loads(text)
        url = str((bts.get("urls") or [""])[0])
    except ValueError as e:
        raise MornyeError("Unreadable manifest") from e
    if not url:
        raise MornyeError("The manifest has no direct link")
    mime = str(bts.get("mimeType") or data.get("manifestMimeType") or "audio/flac").lower()
    bits = data.get("bitDepth")
    rate = data.get("sampleRate")
    info = str(data.get("audioQuality") or quality)
    if bits and rate:
        info += " %s-bit %.1f kHz" % (bits, float(rate) / 1000.0)
    return {"url": url, "ext": _EXT_BY_MIME.get(mime, ".flac"), "info": info}


def _safe_name(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", _tidy(text)).strip(" .")
    return text[:110]


def _file_name(index: int, total: int, track: dict, ext: str, numbered: bool) -> str:
    base = " - ".join(p for p in (_safe_name(track["artist"]), _safe_name(track["title"])) if p)
    base = base or "track"
    if numbered:
        width = max(2, len(str(total)))
        base = "%s - %s" % (str(index).zfill(width), base)
    return base + ext


def fetch_links(url: str, quality: str, progress, ask_grant, cancel=None) -> dict:
    """Runs the whole flow on the phone's network. Returns
    {'title', 'kind', 'links', 'names', 'named_links', 'info', 'failed'};
    raises MornyeError. named_links carry the wanted file name in the link's
    #name=... fragment (never sent to the server)."""
    progress = progress or (lambda text: None)
    quality = quality or "LOSSLESS"
    kind, sid = parse_spotify(url)
    if not kind:
        raise MornyeError("Paste a Spotify track, album, playlist or artist link")

    listing = list_tracks(kind, sid)
    tracks = listing["tracks"]
    total = len(tracks)
    progress(f"{total} track(s) found - matching on Tidal...")

    matched, failed = [], []
    for i, track in enumerate(tracks, 1):
        if cancel and cancel():
            raise Cancelled("Cancelled")
        progress(f"Matching on Tidal {i}/{total}")
        label = " - ".join(p for p in (track["artist"], track["title"]) if p) or track["id"]
        try:
            tidal_id = resolve_tidal_id(track["id"])
        except MornyeError as e:
            failed.append(f"{label}: {e}")
            continue
        if not tidal_id:
            failed.append(f"{label}: not found on Tidal")
            continue
        matched.append((track, tidal_id, label))
        time.sleep(0.25)
    if not matched:
        raise MornyeError("None of the tracks were found on Tidal")

    _ensure_session(progress, ask_grant)

    numbered = kind == "album"
    links, names, infos = [], [], []
    for i, (track, tidal_id, label) in enumerate(matched, 1):
        if cancel and cancel():
            raise Cancelled("Cancelled")
        progress(f"Getting link {i}/{len(matched)}")
        result = None
        for attempt in range(2):
            try:
                result = get_download(tidal_id, quality)
                break
            except NeedsVerify:
                if attempt == 1:
                    raise MornyeError("The session was refused twice - try again")
                _verify(progress, ask_grant)
            except MornyeError as e:
                failed.append(f"{label}: {e}")
                break
        if result:
            links.append(result["url"])
            names.append(_file_name(len(links), len(matched), track, result["ext"], numbered))
            infos.append(result["info"])
        time.sleep(0.2)
    if not links:
        raise MornyeError("No link could be made. " + (failed[0] if failed else ""))
    named = [u + "#name=" + quote(n, safe="") for u, n in zip(links, names)]
    return {"title": listing["title"], "kind": kind, "links": links, "names": names,
            "named_links": named, "info": infos[0] if infos else "", "failed": failed}
