"""Downloading an HLS stream (.m3u8) on the phone into ONE video file - no ffmpeg needed.

``fetch(url, path, ...)`` reads the playlist (a master playlist -> the best quality), downloads every
segment a few at a time, decrypts AES-128 segments and writes them one after the other into ``path``.
The result is the plain concatenation of the segments: ``.ts`` for normal streams, ``.mp4`` for
fragmented-MP4 streams (EXT-X-MAP). ``fetch`` returns that extension.

Not supported (``HlsError``, the caller falls back to GitHub): live streams, SAMPLE-AES / other
encryption, byte-range segments. A separate audio track of a master playlist is not merged.
No Kivy in here.
"""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlsplit

import requests

from core import browser_media as bm
from core import segmented_download as sd

WORKERS = 6
RETRIES = 4
BATCH = WORKERS * 4          # segments asked for at once: memory stays small on a long video


class HlsError(Exception):
    """The stream cannot be downloaded by the phone."""


def looks_like_hls(url):
    """True for a link whose path ends with .m3u8 / .m3u (the query, e.g. wmsAuthSign, is ignored)."""
    return urlsplit(url or "").path.lower().endswith((".m3u8", ".m3u"))


def _get_text(url, headers):
    r = requests.get(url, headers=headers or None, timeout=(15, 30))
    r.raise_for_status()
    return r.text


def _attrs(line):
    body = line.split(":", 1)[1] if ":" in line else ""
    return {k: v.strip('"') for k, v in re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', body)}


def parse_media(text, base_url):
    """A media playlist -> {"segments": [{url, key, seq}], "init": url | None, "ended": bool}."""
    segments, init, key, seq, ended = [], None, None, 0, False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            seq = int(line.split(":", 1)[1].strip() or 0)
        elif line.startswith("#EXT-X-PLAYLIST-TYPE:VOD") or line.startswith("#EXT-X-ENDLIST"):
            ended = True
        elif line.startswith("#EXT-X-KEY:"):
            a = _attrs(line)
            method = a.get("METHOD", "NONE")
            if method == "NONE":
                key = None
            elif method == "AES-128" and a.get("URI"):
                key = (urljoin(base_url, a["URI"]), a.get("IV"))
            else:
                raise HlsError(f"encryption {method} is not supported on the phone")
        elif line.startswith("#EXT-X-MAP:"):
            a = _attrs(line)
            if "BYTERANGE" in a:
                raise HlsError("byte-range init segment is not supported on the phone")
            init = urljoin(base_url, a.get("URI", "")) or None
        elif line.startswith("#EXT-X-BYTERANGE"):
            raise HlsError("byte-range segments are not supported on the phone")
        elif line.startswith("#"):
            continue
        else:
            segments.append({"url": urljoin(base_url, line), "key": key, "seq": seq + len(segments)})
    return {"segments": segments, "init": init, "ended": ended}


def resolve(url, headers=None):
    """``(media playlist url, parsed)``: a master playlist is followed to its best quality."""
    for _ in range(3):
        text = _get_text(url, headers)
        if "#EXT-X-STREAM-INF" in text:
            variants = bm.parse_m3u8_variants(text, url)
            if not variants:
                raise HlsError("the playlist has no quality")
            url = variants[0]["url"]
            continue
        return url, parse_media(text, url)
    raise HlsError("too many playlists inside playlists")


def _aes():
    try:
        from Cryptodome.Cipher import AES
    except Exception:
        try:
            from Crypto.Cipher import AES
        except Exception:
            AES = None
    if AES is not None:
        return lambda data, key, iv: AES.new(key, AES.MODE_CBC, iv).decrypt(data)
    from yt_dlp.aes import aes_cbc_decrypt_bytes          # pure Python, slower, always in the build
    return lambda data, key, iv: aes_cbc_decrypt_bytes(data, key, iv)


def _unpad(data):
    n = data[-1] if data else 0
    return data[:-n] if 1 <= n <= 16 and data[-n:] == bytes([n]) * n else data


def _iv(spec, seq):
    if spec:
        return bytes.fromhex(spec[2:] if spec.lower().startswith("0x") else spec).rjust(16, b"\0")
    return seq.to_bytes(16, "big")


def _get_bytes(url, headers, control):
    last = None
    for attempt in range(RETRIES):
        control.wait_while_paused()
        try:
            r = requests.get(url, headers=headers or None, timeout=(15, 60))
            r.raise_for_status()
            return r.content
        except sd.Cancelled:
            raise
        except Exception as e:       # noqa: BLE001 - retried, then raised
            last = e
            control.check()
            time.sleep(min(2 * (attempt + 1), 8))
    raise last


def fetch(url, path, headers=None, control=None, on_progress=None, workers=WORKERS):
    """Downloads the stream at ``url`` into ``path``; returns ".ts" or ".mp4". Raises ``Cancelled``
    when stopped, ``HlsError`` when the phone cannot do this stream. ``on_progress(done, total)`` is
    in bytes (the total is an estimate from the segments that came so far)."""
    control = control or sd.Control()
    _playlist, info = resolve(url, headers)
    segments = info["segments"]
    if not segments:
        raise HlsError("the playlist has no segments")
    if not info["ended"]:
        raise HlsError("this is a live stream")
    control.check()
    keys = {}
    for seg in segments:
        if seg["key"] and seg["key"][0] not in keys:
            keys[seg["key"][0]] = _get_bytes(seg["key"][0], headers, control)
    decrypt = _aes() if keys else None

    def load(seg):
        data = _get_bytes(seg["url"], headers, control)
        if seg["key"]:
            data = _unpad(decrypt(data, keys[seg["key"][0]], _iv(seg["key"][1], seg["seq"])))
        return data

    total, done = len(segments), 0
    with open(path, "wb") as out, ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        if info["init"]:
            out.write(_get_bytes(info["init"], headers, control))
        for start in range(0, total, BATCH):
            futures = [pool.submit(load, s) for s in segments[start:start + BATCH]]
            for i, fut in enumerate(futures):
                data = fut.result()
                out.write(data)
                done += len(data)
                if on_progress:
                    on_progress(done, int(done / (start + i + 1) * total))
    if on_progress:
        on_progress(done, done)
    return ".mp4" if info["init"] else ".ts"
