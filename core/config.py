"""Centralized configuration and constants for the app.

Nothing in this module depends on Kivy or on any specific backend (GitHub),
so it can be imported from core, api, services, or screens without risk of
circular imports.
"""

APP_VERSION = "1.3"

# --- GitHub backend -----------------------------------------------------
REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


def _load_github_branch() -> str:
    """Determines which branch this build's APK should target for ALL
    workflow dispatches (list-formats, list-playlist, download, upload-file,
    etc).

    build-apk.yml generates core/_branch.py at build time (containing
    GITHUB_BRANCH = "<github.ref_name>") right before buildozer runs. This
    has to be a .py file, not a .txt/env var, because buildozer.spec's
    source.include_exts only packages py/png/jpg/kv/atlas into the APK -
    anything else (including env vars, which don't survive into the
    installed app anyway) never makes it onto the device.

    core/_branch.py is git-ignored and only exists inside a given CI build's
    workspace, so this never gets committed/pushed back to the repo - it
    only affects the artifact produced by that specific run.

    Falls back to "main" for local/dev runs where core/_branch.py doesn't
    exist (e.g. running straight from a git checkout, not a built APK).
    """
    try:
        from core._branch import GITHUB_BRANCH as _branch
        if _branch:
            return _branch.strip()
    except ImportError:
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

Download from YouTube and hundreds of other sites (anything yt-dlp supports) to GitHub

Developer: Mohsen Mah

Telegram: t.me/moh3n2016

Note: files are auto-deleted after 2 days"""
