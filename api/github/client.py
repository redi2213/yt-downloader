"""Low-level HTTP plumbing shared by every GitHub API call: a retrying
session and a single place that turns HTTP-level failures into the app's
own exceptions.
"""
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from api.github.auth import auth_headers
from core.config import REQUEST_TIMEOUT
from core.exceptions import AuthenticationError, NetworkError

# Kept for backward compatibility with any code still expecting the old name.
GitHubAuthError = AuthenticationError


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


http = _build_session()


def check_response(r: requests.Response) -> None:
    if r.status_code in (401, 403):
        raise AuthenticationError(
            "GitHub token is invalid, expired, or missing required permissions."
        )
    r.raise_for_status()


def request(method: str, url: str, **kwargs) -> requests.Response:
    """Thin wrapper around ``requests`` that applies the shared timeout,
    auth headers, retrying session, and error mapping used by every GitHub
    API call."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("headers", auth_headers())
    try:
        r = http.request(method, url, **kwargs)
    except requests.exceptions.RequestException as e:
        raise NetworkError(str(e)) from e
    check_response(r)
    return r


def get_allow_missing(url: str, **kwargs) -> requests.Response:
    """Like ``get``, but doesn't raise for a plain 404 - used for polling
    endpoints (e.g. "has this release been created yet?") where "not found
    yet" is an expected, non-error outcome."""
    kwargs.setdefault("timeout", REQUEST_TIMEOUT)
    kwargs.setdefault("headers", auth_headers())
    try:
        r = http.request("GET", url, **kwargs)
    except requests.exceptions.RequestException as e:
        raise NetworkError(str(e)) from e
    if r.status_code in (401, 403):
        raise AuthenticationError("GitHub token is invalid or lacks permission to read releases.")
    return r


def get(url: str, **kwargs) -> requests.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> requests.Response:
    return request("POST", url, **kwargs)


def patch(url: str, **kwargs) -> requests.Response:
    return request("PATCH", url, **kwargs)


def delete(url: str, **kwargs) -> requests.Response:
    return request("DELETE", url, **kwargs)
