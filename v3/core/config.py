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
