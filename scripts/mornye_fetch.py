"""Downloads the Mornye tracks listed in TRACKS_JSON into out/ (mornye-from-links.yml).

The links come from the phone (api.zarz.moe blocks GitHub's IPs, the CDN links do
not need it). Each track is either
  {"stem": "01 - A - B", "kind": "direct", "url": "...", "ext": ".flac"}
  {"stem": "...", "kind": "dash", "init": "...", "media": ".../$Number$.mp4?..",
   "count": 56, "start": 1}
A DASH track is joined into a .flac by core/fmp4_flac.py (a .m4a when the stream is
not FLAC). One track failing does not stop the others; the reasons go to
meta/notes.txt (the release description). Exit code 1 only when nothing was made.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.environ.get("OUT_DIR", "out")
META = os.environ.get("META_DIR", "meta")
UA = ("Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
WORKERS = 4


def load_fmp4():
    spec = importlib.util.spec_from_file_location(
        "fmp4_flac", os.path.join(ROOT, "core", "fmp4_flac.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_stem(text):
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", str(text or "")).strip(" .")
    return text[:120] or "track"


def expand(template, number):
    def fill(match):
        width = match.group(1)
        return str(number).zfill(int(width)) if width else str(number)
    return re.sub(r"\$Number(?:%0(\d+)d)?\$", fill, template)


def fetch(url, path, tries=3):
    last = None
    host = url.split("/")[2] if "//" in url else url[:30]
    for attempt in range(tries):
        try:
            with requests.get(url, stream=True, timeout=(15, 40),
                              headers={"User-Agent": UA}) as resp:
                if resp.status_code != 200:
                    raise IOError("HTTP %d" % resp.status_code)
                with open(path, "wb") as f:
                    for chunk in resp.iter_content(65536):
                        f.write(chunk)
            return
        except (requests.RequestException, IOError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise IOError("%s: %s" % (host, str(last)[:120]))


def make_track(track, fmp4):
    """Returns the finished file's path inside OUT."""
    stem = safe_stem(track.get("stem"))
    work = tempfile.mkdtemp(prefix="mornye_")
    try:
        if track.get("kind") == "dash":
            init = os.path.join(work, "init.mp4")
            fetch(track["init"], init)
            urls = [expand(track["media"], int(track.get("start", 1)) + i)
                    for i in range(int(track["count"]))]
            paths = [os.path.join(work, "seg-%05d.m4s" % i) for i in range(len(urls))]
            errors = []

            def one(i):
                if errors:
                    return
                try:
                    fetch(urls[i], paths[i])
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                list(pool.map(one, range(len(urls))))
            if errors:
                raise errors[0]
            target = os.path.join(OUT, stem + ".flac")
            try:
                fmp4.assemble(init, paths, target)
            except fmp4.NotFlacError:
                target = os.path.join(OUT, stem + ".m4a")
                with open(target, "wb") as out:
                    for p in [init] + paths:
                        with open(p, "rb") as f:
                            shutil.copyfileobj(f, out)
            return target
        ext = track.get("ext") or ".flac"
        target = os.path.join(OUT, stem + ext)
        fetch(track["url"], target)
        return target
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    tracks = json.loads(os.environ.get("TRACKS_JSON") or "[]")
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(META, exist_ok=True)
    fmp4 = load_fmp4()
    made, failed = [], []
    for i, track in enumerate(tracks, 1):
        name = safe_stem(track.get("stem"))
        print("[%d/%d] %s" % (i, len(tracks), name), flush=True)
        try:
            path = make_track(track, fmp4)
            print("   ok: %s (%d bytes)" % (os.path.basename(path), os.path.getsize(path)),
                  flush=True)
            made.append(path)
        except Exception as e:
            print("::warning::%s failed: %s" % (name, e), flush=True)
            failed.append("%s: %s" % (name, str(e)[:160]))
    notes = "%d file(s) from Mornye links." % len(made)
    if failed:
        notes += "\n\nFailed:\n" + "\n".join("- " + f for f in failed)
    with open(os.path.join(META, "notes.txt"), "w", encoding="utf-8") as f:
        f.write(notes + "\n")
    if not made:
        print("::error::No track could be downloaded (an expired or blocked link?)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
