#!/usr/bin/env python3
"""Runs inside the aparat-download.yml GitHub Actions workflow.

Resolves an Aparat video / playlist / channel link, then either
  - downloads every video into --outdir (separate files, or one zip), or
  - writes only links.txt (output=links).
Writes a release notes file for the workflow to attach to the Release.
Exit code 0 means at least one file was produced.
"""
import argparse
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import requests

import aparat_core as core

# GitHub rejects Release assets of 2 GiB or more.
MAX_ASSET = 2 * 1024 ** 3 - 1
CHUNK = 256 * 1024
DOWNLOAD_ATTEMPTS = 3


def log(*args):
    print(*args, flush=True)


def download(url, dest):
    """One download attempt. Raises on any problem."""
    with requests.get(url, headers=core.HEADERS, stream=True, timeout=(15, 60)) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        next_mark = 25
        with open(dest, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                if total and done * 100 // total >= next_mark:
                    log(f"    {next_mark}%")
                    next_mark += 25
    if done == 0:
        raise IOError("empty download")
    if total and done != total:
        raise IOError(f"incomplete download ({done} of {total} bytes)")
    return done


def download_with_retry(entry, quality, dest):
    """Tries up to DOWNLOAD_ATTEMPTS times; after a failure the link is
    re-fetched from the API in case the signed URL went stale."""
    url = entry["link"]["url"]
    last = None
    for attempt in range(1, DOWNLOAD_ATTEMPTS + 1):
        try:
            return download(url, dest), None
        except Exception as e:
            last = e
            if os.path.exists(dest):
                os.remove(dest)
            log(f"    attempt {attempt} failed: {e}")
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(3 * attempt)
                fresh = core.get_video(entry["uid"], entry["playlist"])
                if fresh:
                    match, _ = core.pick_link(fresh["links"], quality)
                    if match:
                        url = match["url"]
    return None, str(last)


def write_notes(path, args, out_name, entries, fallback, failed, note_lines):
    lines = [
        "Aparat download",
        "",
        f"Source: {args.url}",
        f"Quality requested: {args.quality}",
        f"Output: {args.output}",
        f"Videos found: {len(entries) + len(failed)}",
        f"Videos delivered: {len(entries)}",
    ]
    if note_lines:
        lines += [""] + note_lines
    if fallback:
        lines += ["", "Nearest quality used (requested one not available):"]
        lines += [f"- {t} -> {p}" for t, p in fallback]
    if failed:
        lines += ["", "Failed:"]
        lines += [f"- {what}: {why}" for what, why in failed]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--quality", default="best")
    p.add_argument("--output", default="upload_separate",
                   choices=["upload_separate", "upload_zip", "links"])
    p.add_argument("--limit", default="count:5")
    p.add_argument("--outdir", required=True)
    p.add_argument("--notes", required=True)
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    ids, out_name, info = core.resolve_simple(args.url, args.limit)
    if not ids:
        log("Nothing to download.")
        return 1

    playlist_id = info.get("playlist_id")
    log(f"{len(ids)} video(s) found, output name: {out_name}")

    with ThreadPoolExecutor(max_workers=5) as ex:
        videos = list(ex.map(lambda u: core.get_video(u, playlist_id), ids))

    entries, fallback, failed = [], [], []
    for n, (uid, video) in enumerate(zip(ids, videos), 1):
        if not video:
            failed.append((uid, "could not load video info"))
            continue
        match, exact = core.pick_link(video["links"], args.quality)
        if not match:
            failed.append((video["title"], "no downloadable link"))
            continue
        if not exact:
            fallback.append((video["title"], match["profile"]))
        entries.append({
            "n": n, "uid": uid, "playlist": playlist_id,
            "title": video["title"], "link": match,
        })

    if not entries:
        log("No downloadable videos.")
        write_notes(args.notes, args, out_name, entries, fallback, failed, [])
        return 1

    note_lines = []

    # ----- links only -----
    if args.output == "links":
        path = os.path.join(args.outdir, "links.txt")
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(e["link"]["url"] + "\n")
        log(f"links.txt written with {len(entries)} link(s)")
        note_lines.append("Links expire after a few days. Download them soon.")
        write_notes(args.notes, args, out_name, entries, fallback, failed, note_lines)
        return 0

    # ----- download -----
    delivered = []  # entries that ended up as files
    paths = []
    for e in entries:
        fname = core.make_filename(out_name, e["n"], e["title"])
        dest = os.path.join(args.outdir, fname)
        log(f"[{e['n']}] {e['title']} ({e['link']['profile']})")
        size, err = download_with_retry(e, args.quality, dest)
        if err:
            failed.append((e["title"], err))
            continue
        if size > MAX_ASSET:
            os.remove(dest)
            failed.append((e["title"], "file is 2 GB or larger, too big for a Release"))
            continue
        delivered.append(e)
        paths.append(dest)
        log(f"    done, {size / 1024 / 1024:.1f} MB")

    if not paths:
        log("All downloads failed.")
        write_notes(args.notes, args, out_name, delivered, fallback, failed, [])
        return 1

    # ----- optional zip -----
    if args.output == "upload_zip" and len(paths) > 1:
        total = sum(os.path.getsize(x) for x in paths)
        if total + 1_000_000 < MAX_ASSET:
            zip_path = os.path.join(
                args.outdir, core.clean_name(out_name, 120) + ".zip")
            log("Creating zip...")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
                for x in paths:
                    z.write(x, arcname=os.path.basename(x))
            for x in paths:
                os.remove(x)
            log(f"zip ready, {os.path.getsize(zip_path) / 1024 / 1024:.1f} MB")
        else:
            note_lines.append(
                "Zip would be 2 GB or larger, so files were uploaded separately.")
            log("Zip too large, uploading separate files instead.")

    write_notes(args.notes, args, out_name, delivered, fallback, failed, note_lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
