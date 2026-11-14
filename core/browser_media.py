"""In-app browser: what was found on the page (pure Python: no Kivy, no network).

``Session`` keeps the media the Java WebView helper reported (see java/org/redi2213/ytbridge/BrowserHelper.java)
and the quality list read by yt-dlp for supported pages (YouTube). The screens only draw it.
"""
import re
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

VIDEO_EXT = {".mp4", ".m4v", ".webm", ".mkv", ".mov"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
HEIGHTS = (144, 240, 360, 480, 540, 576, 720, 1080, 1440, 2160)
_YT_PAGE = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/)|youtu\.be/)[\w-]{6,}", re.I)


def is_ytdlp_page(url):
    """A page yt-dlp can list the qualities of (YouTube video pages in this version)."""
    return bool(_YT_PAGE.search(url or ""))


def ext_of(url):
    m = re.search(r"(\.[a-z0-9]{2,5})$", urlsplit(url or "").path.lower())
    return m.group(1) if m else ""


def kind_of(url):
    ext = ext_of(url)
    if ext == ".m3u8":
        return "hls"
    if ext == ".mpd":
        return "dash"
    if ext in AUDIO_EXT:
        return "audio"
    return "video"


def dedupe_key(url):
    parts = urlsplit(url or "")
    return parts.netloc.lower() + parts.path


def quality_hint(url):
    path = unquote(urlsplit(url or "").path)
    m = re.search(r"(?<![0-9])(\d{3,4})p(?![a-z0-9])", path, re.I)
    if m and int(m.group(1)) in HEIGHTS:
        return f"{int(m.group(1))}p"
    stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    m = re.search(r"[_\-.](\d{3,4})$", stem)
    if m and int(m.group(1)) in HEIGHTS:
        return f"{int(m.group(1))}p"
    return ""


def name_from_url(url, kind, title=""):
    seg = unquote(urlsplit(url or "").path.rstrip("/").rsplit("/", 1)[-1]).strip()
    if kind in ("hls", "dash"):
        return (title or urlsplit(url).netloc or "stream").strip()
    if not seg or "." not in seg[-6:]:
        seg = (seg or title or "video") + (".mp3" if kind == "audio" else ".mp4")
    return seg


def fmt_size(size):
    if not size:
        return ""
    mib = size / (1024 * 1024)
    if mib >= 1024:
        return f"{mib / 1024:.2f} GB"
    return f"{mib:.1f} MB" if mib >= 1 else f"{size / 1024:.0f} KB"


def normalize_input(text):
    """What the address box holds -> a link to open (a search for plain words)."""
    t = (text or "").strip()
    if not t:
        return ""
    if re.match(r"^[a-z][a-z0-9+.\-]*://", t, re.I):
        return t
    if " " not in t and "." in t:
        return "https://" + t
    return "https://www.google.com/search?q=" + quote_plus(t)


def parse_m3u8_variants(text, base_url):
    """Qualities of an HLS master playlist: [{url, height, bandwidth, label}], best first.
    [] for a plain media playlist."""
    lines = [l.strip() for l in (text or "").splitlines()]
    out, seen = [], set()
    for i, line in enumerate(lines):
        if not line.startswith("#EXT-X-STREAM-INF:"):
            continue
        attrs = line.split(":", 1)[1]
        res = re.search(r"RESOLUTION=(\d+)x(\d+)", attrs)
        bw = re.search(r"(?:^|,)BANDWIDTH=(\d+)", attrs)
        uri = next((x for x in lines[i + 1:] if x and not x.startswith("#")), "")
        if not uri:
            continue
        url = urljoin(base_url, uri)
        if url in seen:
            continue
        seen.add(url)
        height = min(int(res.group(1)), int(res.group(2))) if res else 0
        bandwidth = int(bw.group(1)) if bw else 0
        label = f"{height}p" if height else ""
        if bandwidth:
            label += f" - {bandwidth / 1e6:.1f} Mbps"
        out.append({"url": url, "height": height, "bandwidth": bandwidth, "label": label.strip(" -") or "stream"})
    out.sort(key=lambda v: (-v["height"], -v["bandwidth"]))
    return out


def headers_from(rec):
    headers = {}
    for key, name in (("referer", "Referer"), ("ua", "User-Agent"), ("cookie", "Cookie")):
        if rec.get(key):
            headers[name] = rec[key]
    return headers


class Session:
    """Everything the browser knows about the page on screen."""

    def __init__(self):
        self.epoch = None
        self.page = ""
        self.title = ""
        self.items = {}
        self.selected = set()
        self.ytdlp = []
        self.ytdlp_for = None
        self.ytdlp_error = ""

    def _reset_page(self):
        self.items, self.selected = {}, set()
        self.ytdlp, self.ytdlp_for, self.ytdlp_error = [], None, ""

    def merge(self, data):
        """Adds one poll of the Java helper. True when something new appeared."""
        if data.get("epoch") != self.epoch:
            self.epoch = data.get("epoch")
            self._reset_page()
        self.page = data.get("page") or ""
        self.title = data.get("title") or ""
        changed = False
        for rec in data.get("items") or []:
            url = rec.get("url") or ""
            key = dedupe_key(url)
            if not url or key in self.items:
                continue
            kind = kind_of(url)
            self.items[key] = {
                "key": key, "url": url, "kind": kind, "src": rec.get("src", ""),
                "name": name_from_url(url, kind, self.title), "quality": quality_hint(url),
                "size": None, "size_label": "", "headers": headers_from(rec),
                "variants": None, "probed": False,
            }
            changed = True
        return changed

    def count(self):
        return len(self.items)

    def entries(self):
        """What the list shows: one row per file, an HLS master playlist as one row per quality."""
        out = []
        for item in self.items.values():
            if item.get("variants"):
                for v in item["variants"]:
                    out.append({**item, "key": "v:" + v["url"], "url": v["url"], "kind": "hls",
                                "quality": v["label"], "variants": None, "probed": True})
            else:
                out.append(item)
        return out

    def all_entries(self):
        return list(self.ytdlp) + self.entries()

    def set_ytdlp(self, formats):
        """formats: yt-dlp qualities as (format_id, label, size_label, codec_label), ascending."""
        name = self.title or "YouTube video"
        rows = [{"key": "yt:" + fid, "kind": "ytdlp", "url": self.page, "format_id": fid, "name": name,
                 "quality": label, "size_label": size_label or "", "codec": codec or "", "audio": False,
                 "size": None, "headers": {}, "probed": True}
                for fid, label, size_label, codec in reversed(formats)]
        rows.append({"key": "yt:audio", "kind": "ytdlp", "url": self.page, "format_id": "bestaudio", "name": name,
                     "quality": "Audio only (MP3)", "size_label": "", "codec": "", "audio": True,
                     "size": None, "headers": {}, "probed": True})
        self.ytdlp = rows
