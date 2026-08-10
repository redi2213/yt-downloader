"""Centralized configuration and constants for the app.

Nothing in this module depends on Kivy or on any specific backend (GitHub),
so it can be imported from core, api, services, or screens without risk of
circular imports.
"""

import os

APP_VERSION = "1.3"

# --- GitHub backend -----------------------------------------------------
REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def _load_github_branch() -> str:
    """Determines which branch this build's APK should target for ALL
    workflow dispatches (list-formats, list-playlist, download, upload-file,
    etc). Resolution order:

    1. APP_GIT_BRANCH env var - set by build-apk.yml at build time via
       github.ref_name, so whichever branch "Build APK" was run on.
    2. branch.txt - a plain-text file written by build-apk.yml right next
       to this module and packaged into the APK via buildozer. This is the
       one that actually survives into the installed APK, since env vars
       don't persist into the running Android app.
    3. "main" - safe fallback for local/dev runs outside CI where neither
       of the above exists.

    Deliberately NOT hardcoded and NOT written back to the repo - this only
    affects the artifact produced by this specific build run.
    """
    env_val = os.environ.get("APP_GIT_BRANCH")
    if env_val:
        return env_val.strip()

    try:
        branch_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "branch.txt")
        with open(branch_file, "r", encoding="utf-8") as f:
            file_val = f.read().strip()
            if file_val:
                return file_val
    except OSError:
        pass

    return "main"


# The branch every GitHub Actions workflow dispatch from this build targets.
GITHUB_BRANCH = _load_github_branch()

# GitHub Actions free tier allows ~20 concurrent jobs; stay under that so
# dispatched runs don't queue behind each other.
MAX_PARALLEL_JOBS = 5

# Seconds; avoids requests hanging forever on flaky mobile networks.
REQUEST_TIMEOUT = 15

# Local settings/token storage file (Kivy JsonStore).
SETTINGS_STORE_FILE = "ytdl_settings.json"

# Cap on how many finished jobs are kept in the in-memory job history.
MAX_JOB_HISTORY = 5

ABOUT_TEXT_TEMPLATE = """YT Bridge Git v{version}

Download from YouTube to GitHub

Developer: Mohsen Mah

Telegram: t.me/moh3n2016

Note: files are auto-deleted after 2 days"""
