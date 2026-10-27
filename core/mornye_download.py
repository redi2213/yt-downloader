"""Downloads one Mornye track onto the phone: a direct file or DASH segments.

Returns a temp file (a .flac, or .m4a when the stream is not FLAC); saving it into
the Download folder is the caller's job. No Kivy in here.
"""
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from core import fmp4_flac

UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
SEGMENT_WORKERS = 4


class DownloadCancelled(Exception):
    pass


def _fetch(url, path, cancel, on_bytes=None, tries=3):
    last = None
    host = url.split("/")[2] if "//" in url else url[:30]
    for attempt in range(tries):
        if cancel():
            raise DownloadCancelled()
        try:
            with requests.get(url, stream=True, timeout=(15, 40),
                              headers={"User-Agent": UA}) as resp:
                if resp.status_code != 200:
                    raise IOError("HTTP %d" % resp.status_code)
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        if cancel():
                            raise DownloadCancelled()
                        f.write(chunk)
                        if on_bytes:
                            on_bytes(len(chunk))
            return
        except DownloadCancelled:
            raise
        except (requests.RequestException, IOError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise IOError("%s: %s" % (host, str(last)[:120]))


def fetch(item: dict, work_dir: str, progress, cancel):
    """item is what api/mornye.get_*_download returned. Returns (path, ext).
    progress(text) gets short status texts."""
    if item.get("kind") == "dash":
        return _fetch_dash(item["segments"], work_dir, progress, cancel)
    ext = item.get("ext") or ".flac"
    path = os.path.join(work_dir, "track" + ext)
    state = {"bytes": 0, "last": 0.0}

    def on_bytes(n):
        state["bytes"] += n
        now = time.monotonic()
        if now - state["last"] > 0.7:
            state["last"] = now
            progress("%.1f MB" % (state["bytes"] / 1048576.0))

    _fetch(item["url"], path, cancel, on_bytes)
    return path, ext


def _fetch_dash(urls, work_dir, progress, cancel):
    init_path = os.path.join(work_dir, "init.mp4")
    _fetch(urls[0], init_path, cancel)
    media = urls[1:]
    paths = [os.path.join(work_dir, "seg-%05d.m4s" % i) for i in range(len(media))]
    lock = threading.Lock()
    state = {"done": 0, "error": None}

    def one(i):
        if state["error"] is not None:
            return
        try:
            _fetch(media[i], paths[i], cancel)
        except Exception as e:           # remembered, the others stop early
            state["error"] = state["error"] or e
            return
        with lock:
            state["done"] += 1
            progress("part %d/%d" % (state["done"], len(media)))

    with ThreadPoolExecutor(max_workers=SEGMENT_WORKERS) as pool:
        list(pool.map(one, range(len(media))))
    if state["error"] is not None:
        raise state["error"]

    flac_path = os.path.join(work_dir, "track.flac")
    try:
        progress("making the FLAC file")
        fmp4_flac.assemble(init_path, paths, flac_path)
        return flac_path, ".flac"
    except fmp4_flac.NotFlacError:
        m4a_path = os.path.join(work_dir, "track.m4a")
        with open(m4a_path, "wb") as out:
            for p in [init_path] + paths:
                with open(p, "rb") as f:
                    shutil.copyfileobj(f, out)
        return m4a_path, ".m4a"
