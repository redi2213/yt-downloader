"""In-app browser: what was found on the page (pure Python: no Kivy, no network).

``Session`` keeps the media the Java WebView helper reported (see java/org/redi2213/ytbridge/BrowserHelper.java)
and the quality list read by yt-dlp for supported pages (YouTube). The screens only draw it.
"""
import re
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

VIDEO_EXT = {".mp4", ".m4v", ".webm", ".mkv", ".mov"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
HEIGHTS = (144, 240, 360, 480, 540, 576, 720, 1080, 1440, 2160)
SORT_MODES = ("newest", "oldest", "size", "quality", "name", "type")
MAX_ITEMS = 3000          # a safety cap: the list stays light even on a page that never stops loading
_KIND_RANK = {"ytdlp": 0, "video": 1, "audio": 2, "hls": 3, "dash": 4}
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
    """Same file = same host + path (the query holds tokens that change between requests)."""
    parts = urlsplit(url or "")
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host + unquote(parts.path).rstrip("/")


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


def parse_size_label(label):
    """"123 MB" / "1.23 GB" (the yt-dlp quality rows) -> bytes, or None."""
    m = re.match(r"\s*([\d.]+)\s*(KB|MB|GB)\b", label or "", re.I)
    if not m:
        return None
    try:
        return int(float(m.group(1)) * {"kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[m.group(2).lower()])
    except ValueError:
        return None


def quality_height(entry):
    """Pixel height of a row for sorting: 1080 for "1080p60", 0 for audio, -1 when unknown."""
    m = re.search(r"(\d{3,4})p", entry.get("quality") or "")
    if m:
        return int(m.group(1))
    return 0 if (entry.get("audio") or entry.get("kind") == "audio") else -1


def _natural(text):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", (text or "").casefold())]


def sort_entries(entries, mode):
    """The rows in one of SORT_MODES order (an unknown mode = newest). Ties keep the order they came in."""
    if mode == "oldest":
        key = lambda e: e.get("seq", 0)                                                       # noqa: E731
    elif mode == "size":
        key = lambda e: (0, -e["size"]) if e.get("size") else (1, 0)                          # noqa: E731
    elif mode == "quality":
        key = lambda e: (-quality_height(e), -(e.get("size") or 0))                           # noqa: E731
    elif mode == "name":
        key = lambda e: _natural(e.get("name"))                                               # noqa: E731
    elif mode == "type":
        key = lambda e: (_KIND_RANK.get(e.get("kind"), 9), e.get("ext") or "", _natural(e.get("name")))  # noqa: E731
    else:
        key = lambda e: -e.get("seq", 0)                                                      # noqa: E731
    return sorted(entries, key=key)


def selection_summary(entries, selected):
    """(how many rows are selected, total bytes of those with a known size, how many have no size)."""
    count = total = unknown = 0
    for e in entries:
        if e["key"] in selected:
            count += 1
            if e.get("size"):
                total += e["size"]
            else:
                unknown += 1
    return count, total, unknown


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
    """Everything the browser knows about the pages visited. What was found stays until Clear / Refresh."""

    def __init__(self):
        self.epoch = None
        self.page = ""
        self.title = ""
        self.items = {}
        self.selected = set()
        self.ytdlp = []
        self.ytdlp_for = None
        self.ytdlp_error = ""
        self.version = 0        # grows on every change: the list redraws only when it moved
        self.probing = False    # a batch of size probes is running (see services/browser_service.py)
        self._seq = 0
        self._cache = None

    def touch(self):
        self.version += 1

    def _next_seq(self):
        self._seq += 1
        return self._seq

    def _reset_page(self):
        """A new page: only the yt-dlp qualities belong to one page. Found files are kept."""
        self.selected = {k for k in self.selected if not k.startswith("yt:")}
        self.ytdlp, self.ytdlp_for, self.ytdlp_error = [], None, ""
        self.version += 1

    def clear(self):
        """The list's Clear: everything found and selected goes."""
        self.items, self.selected = {}, set()
        self.ytdlp, self.ytdlp_error = [], ""
        self.ytdlp_for = self.page if is_ytdlp_page(self.page) else None    # not read again by itself
        self.version += 1

    def restart_scan(self):
        """The list's Refresh: like Clear, and the qualities of a YouTube page are read again."""
        self.clear()
        self.ytdlp_for = None

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
            if len(self.items) >= MAX_ITEMS:
                break
            kind = kind_of(url)
            self.items[key] = {
                "key": key, "url": url, "kind": kind, "src": rec.get("src", ""), "ext": ext_of(url),
                "name": name_from_url(url, kind, self.title), "quality": quality_hint(url),
                "size": None, "size_label": "", "headers": headers_from(rec),
                "variants": None, "probed": False,
                "seq": self._next_seq(), "found_on": rec.get("referer") or self.page,
            }
            changed = True
        if changed:
            self.version += 1
        return changed

    def count(self):
        return len(self.items)

    def entries(self):
        """What the list shows: one row per file, an HLS master playlist as one row per quality.
        A playlist that is only a quality of a master is not shown twice."""
        variant_keys = {dedupe_key(v["url"]) for item in self.items.values() for v in (item.get("variants") or ())}
        out, seen = [], set()
        for item in self.items.values():
            if item.get("variants"):
                for v in item["variants"]:
                    key = "v:" + dedupe_key(v["url"])
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({**item, "key": key, "url": v["url"], "kind": "hls", "quality": v["label"],
                                "variants": None, "probed": True})
            elif item["key"] not in variant_keys:
                out.append(item)
        return out

    def all_entries(self):
        """Every row, each once (kept until the next change, so the list can ask every second)."""
        if self._cache is not None and self._cache[0] == self.version:
            return self._cache[1]
        out, seen = [], set()
        for e in list(self.ytdlp) + self.entries():
            if e["key"] not in seen:
                seen.add(e["key"])
                out.append(e)
        self._cache = (self.version, out)
        return out

    def set_ytdlp(self, formats):
        """formats: yt-dlp qualities as (format_id, label, size_label, codec_label), ascending."""
        name = self.title or "YouTube video"
        seq = self._next_seq()
        rows = [{"key": "yt:" + fid, "kind": "ytdlp", "url": self.page, "format_id": fid, "name": name,
                 "quality": label, "size_label": size_label or "", "codec": codec or "", "audio": False,
                 "size": parse_size_label(size_label), "headers": {}, "probed": True, "seq": seq}
                for fid, label, size_label, codec in reversed(formats)]
        rows.append({"key": "yt:audio", "kind": "ytdlp", "url": self.page, "format_id": "bestaudio", "name": name,
                     "quality": "Audio only (MP3)", "size_label": "", "codec": "", "audio": True,
                     "size": None, "headers": {}, "probed": True, "seq": seq})
        self.ytdlp = rows
        self.version += 1
