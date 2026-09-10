"""Raw fetch of the app's remote feature config from GitHub.

Unlike the rest of api/github/*, this does NOT go through the authenticated
GitHub REST API - it reads config.json directly from raw.githubusercontent.com
on a fixed 'config' branch. This is intentional:

  - No token/auth needed, so it works before the user has signed in.
  - raw.githubusercontent.com has its own (generous, unauthenticated) rate
    limit, separate from api.github.com's.
  - The 'config' branch is shared across every app version (v3, v4, ...),
    so a single edit + push updates all installed builds at once.

SSL note: Android builds (python-for-android) don't expose the OS's CA
certificate store the way desktop Python does, so urllib's default SSL
context can't verify raw.githubusercontent.com's certificate and raises
CERTIFICATE_VERIFY_FAILED. We build an explicit SSL context using
certifi's bundled CA file (already a buildozer.spec requirement) instead
of relying on the platform default.
"""
import json
import ssl
import urllib.request
import urllib.error

import certifi

from core.config import REPO_OWNER, REPO_NAME

CONFIG_BRANCH = "config"
CONFIG_PATH = "config.json"
CONFIG_URL = (
    f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/"
    f"{CONFIG_BRANCH}/{CONFIG_PATH}"
)

_TIMEOUT_SECONDS = 10

# Built once at import time; certifi.where() just returns a bundled file
# path, cheap to call, but no need to rebuild the SSLContext on every fetch.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def fetch_remote_config() -> dict:
    """Fetches and parses config.json from the 'config' branch.

    Raises on any failure (network error, bad status, invalid JSON) -
    callers (services/remote_config_service.py) are responsible for
    catching and falling back to a bundled default.
    """
    import time
    url = f"{CONFIG_URL}?_={int(time.time())}"

    request = urllib.request.Request(url, headers={"User-Agent": "YTBridge-App"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS, context=_SSL_CONTEXT) as response:
        if response.status != 200:
            raise ValueError(f"Unexpected status {response.status} fetching remote config")
        raw_bytes = response.read()

    return json.loads(raw_bytes)
