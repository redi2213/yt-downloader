#!/usr/bin/env python3
"""Commits the failure logs in ./lab_logs_out/ to the `config` branch, folder `lab-logs/`.

Always exits 0 (a logging problem must not fail the workflow). Keeps the newest KEEP files.
Several runs may push at the same time, so every try starts from a fresh clone.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import time

SRC = "lab_logs_out"
BRANCH = "config"
FOLDER = "lab-logs"
KEEP = 300
WORK = "lab_logs_cfg"


def _hide(text, token):
    text = text or ""
    if token:
        text = text.replace(token, "<hidden>")
    return re.sub(r"x-access-token:[^@\s]+@", "x-access-token:<hidden>@", text)


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.txt")))
    if not files:
        print("No failure logs to save")
        return 0
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("No token / repository: logs are not saved")
        return 0
    url = "https://x-access-token:%s@github.com/%s.git" % (token, repo)

    for attempt in range(1, 5):
        shutil.rmtree(WORK, ignore_errors=True)
        r = subprocess.run(["git", "clone", "--quiet", "--depth", "1", "--branch", BRANCH, url, WORK],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print("clone failed:", _hide(r.stderr, token).strip()[-300:])
            time.sleep(3 * attempt)
            continue
        dest = os.path.join(WORK, FOLDER)
        os.makedirs(dest, exist_ok=True)
        for f in files:
            shutil.copy(f, os.path.join(dest, os.path.basename(f)))
        names = sorted(n for n in os.listdir(dest) if n.endswith(".txt"))
        for old in names[:-KEEP] if len(names) > KEEP else []:
            os.remove(os.path.join(dest, old))

        def git(*args):
            return subprocess.run(["git", "-C", WORK, *args], capture_output=True, text=True)

        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("add", "-A", FOLDER)
        if git("diff", "--cached", "--quiet").returncode == 0:
            print("Nothing new to commit")
            break
        git("commit", "--quiet", "-m", "lab logs: %d failure log(s) from run %s" % (len(files), os.environ.get("GITHUB_RUN_ID", "")))
        p = git("push", "--quiet", "origin", "HEAD:" + BRANCH)
        if p.returncode == 0:
            print("Saved %d failure log(s) to %s/%s" % (len(files), BRANCH, FOLDER))
            break
        print("push failed (try %d):" % attempt, _hide(p.stderr, token).strip()[-300:])
        time.sleep(3 * attempt)
    shutil.rmtree(WORK, ignore_errors=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print("lab_log_push: %s" % e)
        sys.exit(0)
