#!/usr/bin/env python3
"""Runs inside the aparat-download.yml GitHub Actions workflow.

Resolves an Aparat video / playlist / channel link, then either
  - downloads every video into --outdir (separate files with Finglish names,
    or one zip whose files keep their Persian titles), or
  - writes only links.txt and names.txt (output=links).
With --ids only those videos (picked in the app) are used.
Writes a release notes file for the workflow to attach to the Release.
Exit code 0 means at least one file was produced.
"""
import argparse
import os
import shutil
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor

import requests

import aparat_core as core
import finglish_name

# GitHub rejects Release assets of 2 GiB or more.
MAX_ASSET = 2 * 1024 ** 3 - 1
CHUNK = 256 * 1024
# One zip stays under this size (MB); more videos than that go into more zips.
ZIP_MAX = int(float(os.environ.get("ZIP_MAX_MB", "1900") or 1900) * 1024 * 1024)
DOWNLOAD_ATTEMPTS = 3


def log(*args):
    print(*args, flush=True)


def download(url, dest, tag=""):
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
                    log(f"    [{tag}] {next_mark}%")
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
            log(f"    [{entry.get('n', '')}] attempt {attempt} failed: {e}")
            if attempt < DOWNLOAD_ATTEMPTS:
                time.sleep(3 * attempt)
                fresh = core.get_video(entry["uid"], entry["playlist"])
                if fresh:
                    match, _ = core.pick_link(fresh["links"], quality)
                    if match:
                        url = match["url"]
    return None, str(last)


def ascii_file_name(out_name, n, title, uid):
    """Release asset name: Finglish only (a Release can't keep Persian)."""
    base = finglish_name.safe_name(out_name, fallback="aparat", max_len=60)
    name = finglish_name.safe_name(title, fallback=uid, max_len=100)
    return f"{base}_{n:02d} - {name}.mp4"


def zip_member_name(title, used):
    """Name inside a zip: the full Persian title (zip files can hold it)."""
    base = core.clean_name(title, 150)
    name, k = f"{base}.mp4", 2
    while name.lower() in used:
        name = f"{base} ({k}).mp4"
        k += 1
    used.add(name.lower())
    return name


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
                   choices=["upload_separate", "upload_zip", "links", "links_phone"])
    p.add_argument("--ids", default="",
                   help="only these video ids (comma separated), picked in the app")
    p.add_argument("--limit", default="count:5")
    p.add_argument("--outdir", required=True)
    p.add_argument("--notes", required=True)
    args = p.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    if args.output == "links_phone":
        args.output = "links"  # the app handles that itself; here it is plain links

    if core.parse_ids(args.ids):
        ids, out_name, info = core.resolve_selected(args.url, args.ids)
    else:
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
        with open(os.path.join(args.outdir, "names.txt"), "w", encoding="utf-8") as f:
            for e in entries:
                f.write(f"{e['n']:02d} - {core.clean_name(e['title'], 150)}\n")
        log(f"links.txt and names.txt written with {len(entries)} video(s)")
        note_lines.append("Links expire after a few days. Download them soon.")
        write_notes(args.notes, args, out_name, entries, fallback, failed, note_lines)
        return 0

    # ----- download -----
    # Separate files go straight to outdir under a Finglish name. For a zip the
    # files wait in a work folder under a plain number, and get their Persian
    # titles only as names inside the zip. Aparat is slow per connection, so
    # several videos download at the same time.
    zip_mode = args.output == "upload_zip"
    workdir = args.outdir.rstrip("/\\") + "_work"
    if zip_mode:
        os.makedirs(workdir, exist_ok=True)
    workers = max(1, int(os.environ.get("DOWNLOAD_WORKERS", "5") or 5))

    def fetch(e):
        ascii_name = ascii_file_name(out_name, e["n"], e["title"], e["uid"])
        if zip_mode:
            dest = os.path.join(workdir, f"{e['n']:03d}.mp4")
        else:
            dest = os.path.join(args.outdir, ascii_name)
        log(f"[{e['n']}] {e['title']} ({e['link']['profile']})")
        size, err = download_with_retry(e, args.quality, dest)
        if not err:
            log(f"    [{e['n']}] done, {size / 1024 / 1024:.1f} MB")
        return e, dest, ascii_name, size, err

    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(fetch, entries))

    delivered = []  # entries that ended up as files
    parts = []      # (path, ascii release name, title)
    for e, dest, ascii_name, size, err in results:
        if err:
            failed.append((e["title"], err))
            continue
        if size > MAX_ASSET:
            os.remove(dest)
            failed.append((e["title"], "file is 2 GB or larger, too big for a Release"))
            continue
        delivered.append(e)
        parts.append((dest, ascii_name, e["title"]))

    if not parts:
        log("All downloads failed.")
        write_notes(args.notes, args, out_name, delivered, fallback, failed, [])
        return 1

    # ----- optional zip (split into several zips when one would be 2 GB or more) -----
    if zip_mode:
        limit = min(ZIP_MAX, MAX_ASSET - 1_000_000)
        zipped = [p for p in parts if os.path.getsize(p[0]) <= limit]
        loose = [p for p in parts if os.path.getsize(p[0]) > limit]
        groups, cur, cur_size = [], [], 0
        for p in zipped:
            s = os.path.getsize(p[0])
            if cur and cur_size + s > limit:
                groups.append(cur)
                cur, cur_size = [], 0
            cur.append(p)
            cur_size += s
        if cur:
            groups.append(cur)

        base = finglish_name.safe_name(out_name, fallback="aparat", max_len=100)
        used = set()
        for i, group in enumerate(groups, 1):
            name = f"{base}.zip" if len(groups) == 1 else f"{base}_zip{i}of{len(groups)}.zip"
            zip_path = os.path.join(args.outdir, name)
            log(f"Creating {name} ({len(group)} video(s))...")
            # Python marks non-ASCII member names as UTF-8 in the zip, so
            # Persian titles show correctly when it is opened.
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as z:
                for path, _ascii, title in group:
                    z.write(path, arcname=zip_member_name(title, used))
                    os.remove(path)  # frees disk as we go
            log(f"zip ready, {os.path.getsize(zip_path) / 1024 / 1024:.1f} MB")
        for path, ascii_name, _title in loose:
            shutil.move(path, os.path.join(args.outdir, ascii_name))
        if len(groups) > 1:
            note_lines.append(
                f"One zip would be 2 GB or larger (GitHub's limit for a file), so the "
                f"videos are split into {len(groups)} zips (about 1.9 GB each, whole videos).")
        if loose:
            note_lines.append(
                f"{len(loose)} video(s) were too big for a zip and were uploaded as plain files "
                "(Finglish names).")
        shutil.rmtree(workdir, ignore_errors=True)

    write_notes(args.notes, args, out_name, delivered, fallback, failed, note_lines)
    return 0


if __name__ == "__main__":
    sys.exit(main())
