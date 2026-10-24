"""What a pasted YouTube link is: a video, a playlist or a channel / page.

Pure Python (no Kivy; the network is only touched by ``channel_url_from_video``,
which takes the fetch function as a parameter). Used by the YouTube Download
screen's ONE smart box to decide which buttons to show.
"""
import json
import re
from urllib.parse import parse_qs, quote, urlparse

from core import share_routing
from core.links import split_links

_VIDEO_PATH_RE = re.compile(r"^/(shorts|live|embed|v)/[\w-]{6,}")
_CHANNEL_PATH_RE = re.compile(r"^/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)")
_OEMBED = "https://www.youtube.com/oembed?format=json&url="


def classify(url):
    """'video', 'playlist', 'channel' (a channel or page) or 'other'."""
    if not share_routing.is_youtube(url):
        return "other"
    try:
        parsed = urlparse(url)
    except ValueError:
        return "other"
    host = share_routing.host_of(url)
    path = parsed.path.rstrip("/")
    query = parse_qs(parsed.query)
    if share_routing.host_matches(host, "youtu.be"):
        return "video" if path.strip("/") else "other"
    if path == "/playlist":
        return "playlist" if query.get("list") else "other"
    if path == "/watch":
        return "video" if query.get("v") else "other"
    if _VIDEO_PATH_RE.match(path):
        return "video"
    if _CHANNEL_PATH_RE.match(path):
        return "channel"
    return "other"


def playlist_of_video(url):
    """The playlist link behind a video link that carries ``list=`` (a video
    opened from a playlist), or None. YouTube's automatic mixes (RD...) are
    not real playlists and are left out."""
    try:
        values = parse_qs(urlparse(url).query).get("list") or [""]
    except ValueError:
        return None
    list_id = values[0]
    if not list_id or list_id.upper().startswith("RD"):
        return None
    return f"https://www.youtube.com/playlist?list={list_id}"


def analyze(text):
    """What a (multi-line) box holds:
    ``{"videos": [links], "playlist": link or None, "channel": link or None,
    "other": [links], "has_links": bool}``. A video link taken from a playlist
    also gives the playlist."""
    videos, other = [], []
    playlist = channel = None
    links = split_links(text)
    for url in links:
        kind = classify(url)
        if kind == "video":
            videos.append(url)
            if playlist is None:
                playlist = playlist_of_video(url)
        elif kind == "playlist":
            if playlist is None or "/playlist" not in playlist:
                playlist = url
        elif kind == "channel":
            channel = channel or url
        else:
            other.append(url)
    return {"videos": videos, "playlist": playlist, "channel": channel,
            "other": other, "has_links": bool(links)}


def channel_url_from_video(video_url, fetch=None):
    """The channel link (youtube.com/@name) of a video through YouTube's oEmbed,
    or None on any failure. ``fetch(oembed_url)`` returns the response text or raises."""
    try:
        if fetch is None:
            from core import run_title
            fetch = run_title._default_fetch
        data = json.loads(fetch(_OEMBED + quote(video_url, safe="")))
        url = str(data.get("author_url") or "").strip()
        return url if url.lower().startswith("https://") else None
    except Exception:
        return None
