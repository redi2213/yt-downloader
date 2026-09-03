"""GitHub App Device Flow authentication.

Lets a user sign in with their own GitHub account (and their own
rate limits / repo access) instead of the app shipping a single shared
token. No server, no redirect URL, no webview needed - the user just
visits a URL and types a short code.

Flow:
  1. request_device_code() -> device_code, user_code, verification_uri
  2. Show user_code + verification_uri to the user
  3. poll_for_token(device_code) -> access_token once the user has approved
"""
import json
import time
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = "Iv23liUqs3TdHaUcIYEz"

DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"

_TIMEOUT_SECONDS = 10


def request_device_code() -> dict:
    """Returns {"device_code", "user_code", "verification_uri",
    "expires_in", "interval"}."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": "repo workflow",
    }).encode()
    request = urllib.request.Request(
        DEVICE_CODE_URL, data=data,
        headers={"Accept": "application/json", "User-Agent": "YTBridge-App"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


class AuthPending(Exception):
    """User hasn't approved yet - caller should keep polling."""
    pass


class AuthSlowDown(Exception):
    """Server is asking us to poll less frequently."""
    pass


class AuthExpired(Exception):
    """The device_code expired before the user approved it."""
    pass


class AuthDenied(Exception):
    """The user explicitly denied the request."""
    pass


def poll_once(device_code: str) -> str:
    """Single poll attempt. Returns the access_token on success, or raises
    one of AuthPending/AuthSlowDown/AuthExpired/AuthDenied."""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "device_code": device_code,
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Accept": "application/json", "User-Agent": "YTBridge-App"},
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        result = json.loads(response.read())

    if "access_token" in result:
        return result["access_token"]

    error = result.get("error", "")
    if error == "authorization_pending":
        raise AuthPending()
    if error == "slow_down":
        raise AuthSlowDown()
    if error == "expired_token":
        raise AuthExpired()
    if error == "access_denied":
        raise AuthDenied()
    raise RuntimeError(f"Unexpected device flow error: {error}")
