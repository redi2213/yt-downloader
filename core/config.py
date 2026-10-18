"""Centralized configuration and constants for the app.

Nothing in this module depends on Kivy or on any specific backend (GitHub),
so it can be imported from core, api, services, or screens without risk of
circular imports.
"""

def _load_app_version() -> str:
    """The version of this build. build-apk.yml writes core/_version.py (from
    version.txt, 2.1, 2.2, ...) right before buildozer runs; it is not
    committed. Falls back to \"2\" for local runs without that file."""
    try:
        from core._version import APP_VERSION as _version
        if _version:
            return str(_version).strip()
    except ImportError:
        pass
    return "2"


APP_VERSION = _load_app_version()

# --- GitHub backend -----------------------------------------------------
REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"


# Times from GitHub are UTC; they are shown in Tehran time. Iran has had no
# daylight saving since 2022, so a fixed +03:30 offset is correct (the device
# clock/timezone is not used on purpose: Python on Android often reports UTC).
LOCAL_UTC_OFFSET_MINUTES = 210


def run_url(run_id) -> str:
    """The GitHub Actions page of a run (live logs and steps), for opening
    in the browser."""
    return f"https://github.com/{REPO_OWNER}/{REPO_NAME}/actions/runs/{run_id}"


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
MAX_PARALLEL_JOBS = 3

# Seconds; avoids requests hanging forever on flaky mobile networks.
REQUEST_TIMEOUT = 25

# How long (seconds) a run's polling keeps trying after the connection to
# GitHub drops (VPN hiccup, weak mobile signal) before giving up. The run
# itself keeps going on GitHub meanwhile.
NETWORK_GRACE_SECONDS = 300

# Seconds between status checks of each playlist video (gentler than the
# default so several videos at once don't flood a weak connection).
PLAYLIST_POLL_INTERVAL = 6

# Local settings/token storage file (Kivy JsonStore).
_SETTINGS_FILE_NAME = "ytdl_settings.json"


def _settings_store_path() -> str:
    """Where tokens are kept. A bare file name lands in the app's code folder
    (files/app on Android), which Android wipes on every APK update - that
    is why tokens were lost after an update. ANDROID_PRIVATE (the app's files
    folder) survives updates. On desktop the file stays in the working folder."""
    import os
    private = os.environ.get("ANDROID_PRIVATE")
    if not private:
        return _SETTINGS_FILE_NAME
    new_path = os.path.join(private, _SETTINGS_FILE_NAME)
    old_path = _SETTINGS_FILE_NAME
    # if an old file is still there (not wiped yet), carry it over once
    if not os.path.exists(new_path) and os.path.exists(old_path):
        try:
            import shutil
            shutil.copyfile(old_path, new_path)
        except OSError:
            pass
    return new_path


SETTINGS_STORE_FILE = _settings_store_path()

# Cap on how many finished jobs are kept in the in-memory job history.
MAX_JOB_HISTORY = 5

ABOUT_TEXT_TEMPLATE = """YT Bridge Git v{version}

Download from YouTube to GitHub

Developer: Mohsen Mah

Telegram: t.me/moh3n2016

Note: files are auto-deleted after 2 days"""
