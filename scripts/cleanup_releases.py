#!/usr/bin/env python3
"""Release cleanup (run by cleanup-releases.yml).

Rules, for the app's own releases (tag run-* / job-* / auto-*):
  1. EMPTY: a run-* / job-* release with no file at all (its file was deleted, the Source code
     zip/tar GitHub adds is not a file) is removed, together with its tag. Not touched: a release
     that keeps files on Arvan (the files are listed in its description, so it has no GitHub
     asset), and anything younger than EMPTY_GRACE_HOURS (a workflow may create the release first
     and upload the files a bit later).
  2. OLD: a FILE of a run-* release or of an Auto follow release (auto-*) is removed OLD_DAYS after
     it was uploaded, unless the user extended it in the app (the hidden keep block of the release
     description) or it is the app's own APK build / project backup (they have their own button).
     When a run-* release loses its last file the release goes too; an Auto follow release stays
     (it keeps growing). job-* releases (Upload File) are not touched by this rule.
  See scripts/retention_core.py for the exact dates (and the grace period of Auto follow files).
Age is the upload time of the file (asset created_at).

DRY_RUN=true only prints what would be deleted.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import retention_core as retention  # noqa: E402

REPO = os.environ["GITHUB_REPOSITORY"]
DRY_RUN = os.environ.get("DRY_RUN", "false").strip().lower() == "true"
EMPTY_GRACE_HOURS = 2


def gh(*args):
    p = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout).strip()[:200])
    return p.stdout


def all_releases():
    out = gh("api", "--paginate", f"repos/{REPO}/releases?per_page=100", "--jq", ".[]")
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def when(rel):
    return retention.parse_iso(rel.get("published_at") or rel.get("created_at") or "")


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


def plan(rel, now):
    """What to do with one release: ``("release", reason)``, ``("assets", [(asset, reason)])`` or None."""
    tag = rel.get("tag_name") or ""
    kind = retention.kind_of(tag)
    published = when(rel)
    if kind is None or published is None or rel.get("draft"):
        return None
    assets = rel.get("assets") or []
    if not assets:
        if kind == "auto" or keeps_arvan_files(rel):
            return None
        if now - published > timedelta(hours=EMPTY_GRACE_HOURS):
            return ("release", "empty (no file left)")
        return None
    if is_app_release(rel):
        return None
    keep = retention.parse_keep(rel.get("body"))
    old = []
    for a in assets:
        due = retention.expires_at(kind, a.get("created_at") or rel.get("published_at"), keep, a.get("id"))
        if due is not None and now > due:
            old.append((a, f"older than {retention.OLD_DAYS} days (due {retention.iso(due)})"))
    if not old:
        return None
    if len(old) == len(assets) and kind != "auto":
        return ("release", old[0][1])
    return ("assets", old)


def main():
    now = datetime.now(timezone.utc)
    deleted = failed = kept = 0
    label = "WOULD DELETE" if DRY_RUN else "Deleting"
    for rel in all_releases():
        tag = rel.get("tag_name") or ""
        todo = plan(rel, now)
        if not todo:
            kept += 1
            continue
        try:
            if todo[0] == "release":
                print(f"{label} {tag} ({rel.get('name')}): {todo[1]}", flush=True)
                if not DRY_RUN:
                    gh("release", "delete", tag, "--repo", REPO, "--yes", "--cleanup-tag")
                deleted += 1
            else:
                for asset, reason in todo[1]:
                    print(f"{label} file {asset.get('name')} of {tag}: {reason}", flush=True)
                    if not DRY_RUN:
                        gh("api", "-X", "DELETE", f"repos/{REPO}/releases/assets/{asset['id']}")
                    deleted += 1
        except RuntimeError as e:
            failed += 1
            print(f"::warning::could not delete {tag}: {e}")
    print(f"Done: {deleted} {'would be ' if DRY_RUN else ''}deleted, {kept} kept, {failed} failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
