"""A short ASCII name for a run, taken from what it works on: the YouTube
video's title, an uploaded file's name, or the link itself. It is sent to the
workflow as ``run_title`` and becomes the run's name on GitHub (and in the
app's lists). Non-English titles are shown in Finglish - see core/translit.py.
"""
import json
import re
from urllib.parse import parse_qs, quote, unquote, urlparse

from core import translit

# Workflow input that carries a URL, by priority
URL_INPUT_KEYS = ("video_url", "url", "aparat_url", "telegram_url", "file_url", "playlist_url")

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
    import requests
    r = requests.get(url, timeout=2.5)
    r.raise_for_status()
    return r.text


def build_title(inputs, fetch=_default_fetch):
    """The run title for a workflow's inputs, or '' when there is nothing
    worth showing (the run then keeps its link as its name)."""
    url = next((inputs[k] for k in URL_INPUT_KEYS if inputs.get(k)), "")
    if not url or not isinstance(url, str):
        return ""
    title = ""
    if _is_youtube(url):
        raw = youtube_title(url, fetch)
        title = translit.ascii_title(raw) if raw else ""
        if not title:
            m = _YT_ID_RE.search(url)
            if m:
                title = m.group(1)
    elif inputs.get("file_url"):
        title = translit.ascii_title(_file_name(url))
    if not title:
        title = translit.ascii_title(_url_slug(url))
    return title
