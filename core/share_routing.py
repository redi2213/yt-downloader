"""Deciding what to do with a link/text shared into the app from another app
(Android's Share menu). Pure Python - no Kivy, no network - so it can be
tested anywhere.

Routing, in order:
  1. YouTube link  -> the YouTube Download screen (video box, or playlist box
     for a pure playlist link). Built in; never depends on config.json.
  2. A link whose host matches an action's ``"domains"`` list in the remote
     config.json (aparat.com, mediafire.com, ...) -> that action's input form.
  3. Anything else -> a chooser screen listing every tool.
"""
import re
from urllib.parse import urlparse, parse_qs

YOUTUBE_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?)]}>»،؛"


# Redirect links that wrap the real address: (host suffix, path, query keys).
# Chrome shares search results as google.com/url?...&url=<real link>.
_REDIRECTS = (
    ("google.com", "/url", ("url", "q")),
    ("youtube.com", "/redirect", ("q",)),
    ("facebook.com", "/l.php", ("u",)),
)


def unwrap_redirect(url):
    """If ``url`` is a Google/YouTube/Facebook redirect link, the address it
    points to (also through several layers); otherwise ``url`` unchanged."""
    for _ in range(3):
        try:
            parsed = urlparse(url)
        except ValueError:
            return url
        host = host_of(url)
        target = None
        for suffix, path, keys in _REDIRECTS:
            is_google = suffix == "google.com" and re.search(r"(^|\.)google\.[a-z.]+$", host)
            if (is_google or host_matches(host, suffix)) and parsed.path == path:
                query = parse_qs(parsed.query)
                for key in keys:
                    value = (query.get(key) or [""])[0]
                    if value.lower().startswith(("http://", "https://")):
                        target = value
                        break
            if target:
                break
        if not target:
            return url
        url = target
    return url


def extract_url(text):
    """First http(s) link inside shared text (apps often add a title or a
    sentence around the link), without trailing punctuation, with redirect
    wrappers (Google's url?...&url=) removed. None if there is no link."""
    if not text:
        return None
    m = _URL_RE.search(text)
    if not m:
        return None
    return unwrap_redirect(m.group(0).rstrip(_TRAILING_PUNCT))


def host_of(url):
    """Lower-cased host without port/userinfo and without a leading 'www.'."""
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def host_matches(host, domain):
    """True if host is the domain or one of its subdomains."""
    domain = (domain or "").strip().lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if not host or not domain:
        return False
    return host == domain or host.endswith("." + domain)


def is_youtube(url):
    host = host_of(url)
    return any(host_matches(host, d) for d in YOUTUBE_DOMAINS)


def is_youtube_playlist(url):
    """A pure playlist link (youtube.com/playlist?list=...). A watch link that
    merely carries a list= parameter is treated as a single video."""
    if not is_youtube(url):
        return False
    parsed = urlparse(url)
    return parsed.path.rstrip("/") == "/playlist" and "list" in parse_qs(parsed.query)


def match_action(url, actions):
    """First enabled action whose ``domains`` list matches the url's host."""
    host = host_of(url)
    for action in actions or []:
        if action.get("enabled", True) is False:
            continue
        for domain in action.get("domains") or []:
            if host_matches(host, domain):
                return action
    return None


def classify_quick(text):
    """Decision that needs no network: YouTube links. None otherwise."""
    url = extract_url(text)
    if url and is_youtube(url):
        kind = "youtube_playlist" if is_youtube_playlist(url) else "youtube_video"
        return {"kind": kind, "url": url, "action": None}
    return None


def classify(text, actions):
    """Full decision, once the remote action list is available."""
    quick = classify_quick(text)
    if quick:
        return quick
    url = extract_url(text)
    value = url or (text or "").strip()
    if url:
        action = match_action(url, actions)
        if action:
            return {"kind": "action", "url": url, "action": action}
    return {"kind": "chooser", "url": value, "action": None}
