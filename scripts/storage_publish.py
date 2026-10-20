"""Publishes workflow output to a GitHub Release and/or Arvan Cloud.

    storage_publish.py publish  --dir out --tag run-1 --title "..."   one-shot: creates the release
    storage_publish.py publish  ... --append   (auto follow) the release is shared by many runs: add
                                the files to it, creating it the first time; a name already there gets a
                                date in front; with --split a file of 2 GB or more is cut into playable parts
    storage_publish.py upload   --dir out --tag run-1 --idx 3 --meta-out m.json   one leg of a matrix, release already exists
    storage_publish.py finalize --tag run-1 --meta-dir metas          merge the legs' results into the release description

Environment: STORAGE = github | arvan | both (default github), ARVAN_BUCKET
(id of the preferred bucket), ALL_SECRETS (JSON of the repo secrets),
GH_TOKEN and GITHUB_REPOSITORY for the gh CLI.

github -> exactly what the old steps did. arvan -> files go to Arvan only
(a file Arvan rejects is put on the release instead, so it is never lost,
and the reason is written in the description). both -> every file goes to both.
"""
import argparse
import glob
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage_core as core  # noqa: E402

MODES = ("github", "arvan", "both")
GITHUB_ASSET_LIMIT = 2 * 1024 ** 3  # a Release asset must be smaller than 2 GiB


def gh(*args, check=True):
    """Runs the gh CLI (tests replace this function)."""
    return subprocess.run(["gh", *args], check=check)


def get_mode() -> str:
    mode = os.environ.get("STORAGE", "github").strip().lower()
    return mode if mode in MODES else "github"


def _files_in(directory: str, extra=()) -> list:
    found = []
    if directory:
        found = sorted(p for p in glob.glob(os.path.join(directory, "*")) if os.path.isfile(p))
    found += [p for p in (extra or []) if os.path.isfile(p) and p not in found]
    return found


def _notes_text(args) -> str:
    text = args.notes or ""
    if getattr(args, "notes_file", ""):
        try:
            with open(args.notes_file, encoding="utf-8") as fh:
                text = fh.read().strip()
        except OSError:
            pass
    return text


def _repo_args():
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    return ["--repo", repo] if repo else []


def _arvan_phase(files, mode, tag, client_factory=core.make_client):
    """Uploads each file to Arvan when the mode asks for it.
    Returns (arvan_infos, warnings, files_for_github)."""
    if mode == "github":
        return [], [], list(files)
    secrets = core.load_secrets()
    buckets = core.discover_buckets(secrets)
    preferred = os.environ.get("ARVAN_BUCKET", "")
    infos, warnings, for_github = [], [], []
    for path in files:
        info, warns = core.upload_to_arvan(path, buckets, preferred, tag,
                                           client_factory=client_factory)
        warnings += warns
        if info:
            infos.append(info)
            if mode == "both":
                if os.path.getsize(path) >= GITHUB_ASSET_LIMIT:
                    warnings.append(f"{os.path.basename(path)} is 2 GB or larger: only on Arvan, not on GitHub")
                else:
                    for_github.append(path)
        else:
            # Arvan did not take it: keep the file on GitHub instead of losing it
            for_github.append(path)
            warnings.append(f"{os.path.basename(path)} was kept on GitHub (Arvan upload failed)")
    return infos, _dedupe(warnings), for_github


def _dedupe(items):
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _write_body(text: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


# -- shared release (auto follow) --------------------------------------------------------------------------------
SPLIT_AT = GITHUB_ASSET_LIMIT - 64 * 1024 ** 2    # a margin under the limit
PART_TARGET = int(1.7 * 1024 ** 3)


def _quiet(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def _byte_split(path, parts):
    """Last resort: plain pieces name.part1, name.part2 (join them with cat)."""
    size = os.path.getsize(path)
    piece = math.ceil(size / parts)
    out = []
    with open(path, "rb") as src:
        for n in range(1, parts + 1):
            name = f"{path}.part{n}"
            with open(name, "wb") as dst:
                left = piece
                while left > 0:
                    chunk = src.read(min(left, 8 * 1024 * 1024))
                    if not chunk:
                        break
                    dst.write(chunk)
                    left -= len(chunk)
            out.append(name)
    os.remove(path)
    return out


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def split_file(path):
    """Cuts a media file of 2 GB or more into playable parts (name.part1.mkv, ...).
    The parts are cut at key frames, so sizes vary: when one is still too big the
    file is cut again into more parts."""
    size = os.path.getsize(path)
    stem, ext = os.path.splitext(path)
    duration = _duration(path) if shutil.which("ffmpeg") and shutil.which("ffprobe") else 0.0
    parts = max(2, math.ceil(size * 1.12 / PART_TARGET))
    for _ in range(4):
        if not duration:
            break
        seg = math.ceil(duration / parts) + 1
        pattern = f"{stem}.part%d{ext}"
        for old in glob.glob(f"{stem}.part*{ext}"):
            os.remove(old)
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path, "-map", "0",
                            "-c", "copy", "-f", "segment", "-segment_time", str(seg), "-segment_start_number", "1",
                            "-reset_timestamps", "1", pattern], capture_output=True, text=True)
        made = sorted(glob.glob(f"{stem}.part*{ext}"))
        if r.returncode == 0 and made and all(os.path.getsize(m) < SPLIT_AT for m in made):
            os.remove(path)
            print(f"Cut {os.path.basename(path)} into {len(made)} playable parts")
            return made
        parts += 1
    for old in glob.glob(f"{stem}.part*{ext}"):
        os.remove(old)
    parts = max(2, math.ceil(size / PART_TARGET))
    print(f"::warning::{os.path.basename(path)}: could not cut it at key frames, using plain pieces ({parts}); join them with cat")
    return _byte_split(path, parts)


def split_large(files):
    out = []
    for path in files:
        out += split_file(path) if os.path.getsize(path) >= SPLIT_AT else [path]
    return out


def _unique_names(tag, files):
    """A file whose name is already in the shared release gets the date in front."""
    r = _quiet("release", "view", tag, *_repo_args(), "--json", "assets", "-q", ".assets[].name")
    taken = set(r.stdout.split("\n")) if r.returncode == 0 else set()
    stamp = time.strftime("%Y%m%d-%H%M")
    out = []
    for path in files:
        name = os.path.basename(path)
        if name in taken:
            new = os.path.join(os.path.dirname(path), f"{stamp}_{name}")
            os.rename(path, new)
            path = new
        taken.add(os.path.basename(path))
        out.append(path)
    return out


def _publish_append(args, files):
    """Adds the files to the release ``tag``, creating it the first time."""
    if args.split:
        files = split_large(files)
    exists = _quiet("release", "view", args.tag, *_repo_args()).returncode == 0
    if not exists:
        body = _notes_text(args) or "Files added automatically by Auto follow."
        made = gh("release", "create", args.tag, *files, *_repo_args(), "--prerelease",
                  "--title", args.title or args.tag, "--notes", body, check=False)
        if made.returncode == 0:
            return 0
        # another run created it a moment ago: fall through and add to it
    files = _unique_names(args.tag, files)
    gh("release", "upload", args.tag, *files, *_repo_args())
    return 0


def cmd_publish(args, client_factory=core.make_client) -> int:
    mode = get_mode()
    files = _files_in(args.dir, args.file)
    if not files:
        print("::error::No file to publish")
        return 1
    if getattr(args, "append", False):
        return _publish_append(args, files)
    infos, warnings, for_github = _arvan_phase(files, mode, args.tag, client_factory)
    for w in warnings:
        print(f"::warning::{w}")
    notes = _notes_text(args)
    create = ["release", "create", args.tag, *for_github, *_repo_args(),
              "--prerelease", "--title", args.title or args.tag]
    if mode == "github":
        body = notes
    else:
        body = core.build_body(mode, infos, warnings, notes)
    if body:
        create += ["--notes-file", _write_body(body)]
    else:
        create += ["--notes", ""]
    gh(*create)
    for i in infos:
        print(f"Arvan link: {i['url']}")
    return 0


def cmd_upload(args, client_factory=core.make_client) -> int:
    """One matrix leg: the release exists already (created by the prepare job)."""
    mode = get_mode()
    files = _files_in(args.dir, args.file)
    if not files:
        print("::error::No file to upload")
        return 1
    infos, warnings, for_github = _arvan_phase(files, mode, args.tag, client_factory)
    for w in warnings:
        print(f"::warning::{w}")
    for path in for_github:
        # same name already in the release -> retry with the link number in front
        if gh("release", "upload", args.tag, path, *_repo_args(), check=False).returncode != 0:
            print("Upload failed, retrying with a numbered name")
            numbered = os.path.join(os.path.dirname(path), f"{args.idx}_{os.path.basename(path)}")
            os.rename(path, numbered)
            gh("release", "upload", args.tag, numbered, *_repo_args())
    if args.meta_out:
        os.makedirs(os.path.dirname(os.path.abspath(args.meta_out)), exist_ok=True)
        with open(args.meta_out, "w", encoding="utf-8") as fh:
            json.dump({"files": infos, "warn": warnings}, fh)
    return 0


def cmd_finalize(args) -> int:
    mode = get_mode()
    if mode == "github":
        return 0  # nothing to add: behaves exactly as before
    infos, warnings = [], []
    for path in sorted(glob.glob(os.path.join(args.meta_dir, "**", "*.json"), recursive=True)):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        infos += data.get("files", [])
        warnings += data.get("warn", [])
    body = core.build_body(mode, infos, _dedupe(warnings), args.notes or "")
    gh("release", "edit", args.tag, *_repo_args(), "--notes-file", _write_body(body))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("publish")
    a.add_argument("--dir", default="")
    a.add_argument("--file", action="append", default=[])
    a.add_argument("--tag", required=True)
    a.add_argument("--title", default="")
    a.add_argument("--notes", default="")
    a.add_argument("--notes-file", default="")
    a.add_argument("--append", action="store_true", help="shared release (auto follow): add to it, create if missing")
    a.add_argument("--split", action="store_true", help="with --append: cut files of 2 GB or more into parts")
    b = sub.add_parser("upload")
    b.add_argument("--dir", default="")
    b.add_argument("--file", action="append", default=[])
    b.add_argument("--tag", required=True)
    b.add_argument("--idx", default="1")
    b.add_argument("--meta-out", default="")
    c = sub.add_parser("finalize")
    c.add_argument("--tag", required=True)
    c.add_argument("--meta-dir", required=True)
    c.add_argument("--notes", default="")
    args = p.parse_args(argv)
    return {"publish": cmd_publish, "upload": cmd_upload, "finalize": cmd_finalize}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
