"""A short ASCII name for a run, taken from what it works on: the YouTube
video's title, an uploaded file's name, or the link itself. It is sent to the
workflow as ``run_title`` and becomes the run's name on GitHub (and in the
app's lists). Titles keep their own language (Persian stays Persian; the app
shows it joined and in the right order); a lookup that fails is tried again once
before the run falls back to the video id.
"""
import json
import re
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

from core import translit
from core.links import split_links

# Workflow input that carries a URL, by priority
URL_INPUT_KEYS = ("video_url", "url", "aparat_url", "telegram_url", "file_url", "playlist_url", "play_url", "urls")

_YT_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_YT_ID_RE = re.compile(r"(?:v=|youtu\.be/|shorts/|embed/|live/)([A-Za-z0-9_-]{11})")
_OEMBED = "https://www.youtube.com/oembed?format=json&url="


def _is_youtube(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _YT_HOSTS)


def _file_name(url):
    """'https://x/y/My%20Video_480p.mkv?dl=1' -> 'My Video_480p'."""
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    name = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", name)
    return name.replace("_", " ").replace(".", " ")


def _play_package(url):
    """The app's package name from a Google Play link (or a bare package name)."""
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+", url or ""):
        return url
    parsed = urlparse(url)
    if (parsed.hostname or "").lower() == "play.google.com":
        return (parse_qs(parsed.query).get("id") or [""])[0]
    return ""


def _url_slug(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.strip("/")
    return f"{host}/{path}" if path else host


def youtube_title(url, fetch):
    """Video title through YouTube's oEmbed (no key needed); None on any
    failure. ``fetch(oembed_url)`` returns the response text or raises."""
    try:
        data = json.loads(fetch(_OEMBED + quote(url, safe="")))
        return data.get("title") or None
    except Exception:
        return None


def _default_fetch(url):
    """oEmbed text. Tried twice (a slow or busy reply is common when several
    links are started together); the last error is raised."""
    import requests
    last = None
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=4)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(0.7 * (attempt + 1))
    raise last


def clean_title(text, max_len=70):
    """A title as the run name: no brackets / control characters, one line, shortened.
    Unlike ascii_title it keeps Persian and other languages."""
    text = re.sub(r"[\[\]{}\x00-\x1f\u200e\u200f\u202a-\u202e]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip(" _.-")
    return text if len(text) <= max_len else text[: max_len - 3].rstrip() + "..."


def aparat_title(url):
    """The title of an Aparat video link (None for playlists / channels or on any failure)."""
    try:
        from scripts import aparat_core
        kind, value = aparat_core.parse_link(url)
        if kind != "video":
            return None
        video = aparat_core.get_video(value)
        return (video or {}).get("title") if isinstance(video, dict) else None
    except Exception:
        return None


def build_title(inputs, fetch=_default_fetch):
    """The run title for a workflow's inputs, or '' when there is nothing
    worth showing (the run then keeps its link as its name)."""
    url = next((inputs[k] for k in URL_INPUT_KEYS if inputs.get(k)), "")
    if not url or not isinstance(url, str):
        return ""
    # Several links in one box: name the run after the first one (+N more)
    links = split_links(url)
    extra = max(0, len(links) - 1)
    if links:
        url = links[0]
    title = ""
    if inputs.get("play_url"):
        title = _play_package(url)
    elif _is_youtube(url):
        raw = youtube_title(url, fetch)
        title = clean_title(raw) if raw else ""
        if not title:
            m = _YT_ID_RE.search(url)
            if m:
                title = m.group(1)
    elif "aparat.com" in url:
        title = clean_title(aparat_title(url) or "")
    elif inputs.get("file_url"):
        title = clean_title(_file_name(url))
    if not title:
        title = clean_title(_url_slug(url))
    if title and extra:
        title = f"{title} +{extra}"
    return title
