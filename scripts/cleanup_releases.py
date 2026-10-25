#!/usr/bin/env python3
"""Release cleanup (run by cleanup-releases.yml).

Two rules, both for the app's own releases (tag run-* / job-*):
  1. EMPTY: a release with no file at all (its file was deleted, the Source code
     zip/tar GitHub adds is not a file) is removed, together with its tag. Not
     touched: a release that keeps files on Arvan (the files are listed in its
     description, so it has no GitHub asset), the "Arvan info" release, and
     anything younger than EMPTY_GRACE_HOURS (a workflow may create the release
     first and upload the files a bit later).
  2. OLD: a run-* release older than OLD_DAYS is removed, EXCEPT the app's own
     APK builds and project backups (they have their own button in Release History).
Age is published_at: GitHub's created_at is the date of the tagged commit.

DRY_RUN=true only prints what would be deleted.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

REPO = os.environ["GITHUB_REPOSITORY"]
DRY_RUN = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
EMPTY_GRACE_HOURS = 2
OLD_DAYS = 7


def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:200])
    return p.stdout


def all_releases():
    out = gh("api", "--paginate", f"repos/{REPO}/releases?per_page=100", "--jq", ".[]")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def when(rel):
    text = rel.get("published_at") or rel.get("created_at") or ""
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_app_release(rel):
    """An APK build (build-apk.yml) or a project backup (backup-project.yml)."""
    name = str(rel.get("name") or "")
    files = [str(a.get("name", "")).lower() for a in rel.get("assets", [])]
    if name.startswith("YT Bridge ") and any(f.endswith(".apk") for f in files):
        return True
    return name.startswith("Project backup ") and any(f.endswith(".zip") for f in files)


def keeps_arvan_files(rel):
    body = rel.get("body") or ""
    return "ytb-arvan" in body or bool(re.search(r'"files"\s*:\s*\[\s*\{', body))


def reason_to_delete(rel, now):
    """Why this release should go, or None to keep it."""
    tag = rel.get("tag_name") or ""
    published = when(rel)
    if published is None or not tag.startswith(("run-", "job-")):
        return None
    if rel.get("draft"):
        return None
    if not rel.get("assets"):
        if keeps_arvan_files(rel):
            return None
        if now - published > timedelta(hours=EMPTY_GRACE_HOURS):
            return "empty (no file left)"
        return None
    if tag.startswith("run-") and now - published > timedelta(days=OLD_DAYS) and not is_app_release(rel):
        return f"older than {OLD_DAYS} days"
    return None


def main():
    now = datetime.now(timezone.utc)
    deleted = failed = kept = 0
    for rel in all_releases():
        tag = rel.get("tag_name") or ""
        reason = reason_to_delete(rel, now)
        if not reason:
            kept += 1
            continue
        print(f"{'WOULD DELETE' if DRY_RUN else 'Deleting'} {tag} ({rel.get('name')}): {reason}", flush=True)
        if DRY_RUN:
            deleted += 1
            continue
        try:
            gh("release", "delete", tag, "--repo", REPO, "--yes", "--cleanup-tag")
            deleted += 1
        except RuntimeError as e:
            failed += 1
            print(f"::warning::could not delete {tag}: {e}")
    print(f"Done: {deleted} {'would be ' if DRY_RUN else ''}deleted, {kept} kept, {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
