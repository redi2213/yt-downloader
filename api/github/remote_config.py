"""Raw fetch of the app's remote feature config from GitHub.

Unlike the rest of api/github/*, this does NOT go through the authenticated
GitHub REST API - it reads config.json directly from raw.githubusercontent.com
on a fixed 'config' branch. This is intentional:

  - No token/auth needed, so it works before the user has signed in.
  - raw.githubusercontent.com has its own (generous, unauthenticated) rate
    limit, separate from api.github.com's.
  - The 'config' branch is shared across every app version (v3, v4, ...),
    so a single edit + push updates all installed builds at once.
"""
import json
import urllib.request
import urllib.error

from core.config import REPO_OWNER, REPO_NAME

CONFIG_BRANCH = "config"
CONFIG_PATH = "config.json"
CONFIG_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/"
    f"{CONFIG_BRANCH}/{CONFIG_PATH}"
)

_TIMEOUT_SECONDS = 10


def fetch_remote_config() -> dict:
    """Fetches and parses config.json from the 'config' branch.

    Raises on any failure (network error, bad status, invalid JSON) -
    callers (services/remote_config_service.py) are responsible for
    catching and falling back to a bundled default.
    """
    import time
    url = f"{CONFIG_URL}?_={int(time.time())}"

    request = urllib.request.Request(url, headers={"User-Agent": "YTBridge-App"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected status {response.status} fetching remote config")
        raw_bytes = response.read()

    return json.loads(raw_bytes)
