"""In-app browser: what was found on the page (pure Python: no Kivy, no network).

``Session`` keeps the media the Java WebView helper reported (see java/org/redi2213/ytbridge/BrowserHelper.java)
and the quality list read by yt-dlp for supported pages (YouTube). The screens only draw it.
"""
import re
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlsplit

VIDEO_EXT = {".mp4", ".m4v", ".webm", ".mkv", ".mov"}
AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".wav"}
HEIGHTS = (144, 240, 360, 480, 540, 576, 720, 1080, 1440, 2160)
SORT_MODES = ("newest", "oldest", "size", "quality", "name", "type")
MAX_ITEMS = 3000          # a safety cap: the list stays light even on a page that never stops loading

# -- file types the browser looks for (the rules live here, in Python: changing them needs no new build) ---------
# A category groups some kinds: "video" = video files + HLS / DASH streams + YouTube qualities. "other" is a file
# the server called a download but whose type is unknown (always shown, it has no switch).
CATEGORIES = ("video", "audio", "archive", "apk", "pkg", "doc", "custom")
CATEGORY_EXT = {
    "video": VIDEO_EXT | {".m3u8", ".mpd"},
    "audio": AUDIO_EXT,
    "archive": {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"},
    "apk": {".apk", ".apks", ".xapk", ".aab"},
    "pkg": {".pkg", ".deb", ".rpm"},
    "doc": {".pdf", ".epub", ".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"},
}
FILE_KINDS = ("video", "audio", "archive", "apk", "pkg", "doc", "custom", "other")     # one direct link each
DIRECT_KINDS = FILE_KINDS + ("hls",)        # what the phone can download itself (HLS: joined into one file)
_STREAM_CATEGORY = {"hls": "video", "dash": "video", "ytdlp": "video"}
_KIND_RANK = {"ytdlp": 0, "video": 1, "audio": 2, "hls": 3, "dash": 4, "archive": 5, "apk": 6, "pkg": 7,
              "doc": 8, "custom": 9, "other": 10}
_YT_PAGE = re.compile(r"(?:youtube\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|live/)|youtu\.be/)[\w-]{6,}", re.I)


def is_ytdlp_page(url):
    """A page yt-dlp can list the qualities of (YouTube video pages in this version)."""
    return bool(_YT_PAGE.search(url or ""))


def ext_of(url):
    m = re.search(r"(\.[a-z0-9]{2,8})$", urlsplit(url or "").path.lower())
    return m.group(1) if m else ""


_TAIL_EXT = re.compile(r"(\.[a-z0-9]{1,8})$")


def tail_ext(text):
    """".ZIP" from "Archive.ZIP" (a file name or a query value), or ""."""
    m = _TAIL_EXT.search((text or "").strip().lower())
    return m.group(1) if m else ""


def category_of(entry):
    """The category (see CATEGORIES, or "other") of a row: streams and YouTube qualities are "video"."""
    kind = (entry or {}).get("kind")
    if kind in _STREAM_CATEGORY:
        return _STREAM_CATEGORY[kind]
    return kind if kind in CATEGORIES else "other"


def filter_entries(entries, category):
    return list(entries) if category in (None, "", "all") else [e for e in entries if category_of(e) == category]


def count_by_category(entries):
    out = {}
    for e in entries:
        cat = category_of(e)
        out[cat] = out.get(cat, 0) + 1
    return out


def disposition_name(disp):
    """The file name a server gives in a Content-Disposition header (filename*= first), or ""."""
    disp = (disp or "").strip()
    if not disp:
        return ""
    name = ""
    m = re.search(r"filename\*\s*=\s*([^;]+)", disp, re.I)
    if m:
        val = m.group(1).strip().strip('"')
        parts = val.split("'", 2)
        name = unquote(parts[2] if len(parts) == 3 else val)
    else:
        m = re.search(r'filename\s*=\s*(?:"([^"]*)"|([^;]+))', disp, re.I)
        if m:
            name = (m.group(1) if m.group(1) is not None else m.group(2)).strip()
            try:        # a UTF-8 name that arrived as Latin-1 characters
                name = name.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip().strip(".")


_MIME_KIND = {
    "application/vnd.apple.mpegurl": "hls", "application/x-mpegurl": "hls", "audio/mpegurl": "hls",
    "audio/x-mpegurl": "hls", "application/dash+xml": "dash",
    "application/zip": "archive", "application/x-zip-compressed": "archive",
    "application/x-rar-compressed": "archive", "application/vnd.rar": "archive",
    "application/x-7z-compressed": "archive", "application/x-tar": "archive", "application/gzip": "archive",
    "application/x-gzip": "archive", "application/x-bzip2": "archive", "application/x-xz": "archive",
    "application/vnd.android.package-archive": "apk", "application/xapk-package-archive": "apk",
    "application/x-debian-package": "pkg", "application/vnd.debian.binary-package": "pkg",
    "application/x-rpm": "pkg", "application/x-redhat-package-manager": "pkg",
    "application/pdf": "doc", "application/epub+zip": "doc", "application/msword": "doc",
    "application/vnd.ms-excel": "doc", "application/vnd.ms-powerpoint": "doc",
}


def kind_from_mime(mime):
    """The kind a Content-Type points to ("" when it says nothing, like application/octet-stream)."""
    mime = (mime or "").split(";")[0].strip().lower()
    if mime in _MIME_KIND:
        return _MIME_KIND[mime]
    if mime.startswith("application/vnd.openxmlformats-officedocument."):
        return "doc"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return ""


def clean_length(value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def check_custom(text):
    """A custom extension typed by hand -> (".ext", error). error: "" ok, "invalid", "builtin"."""
    t = (text or "").strip().lower().lstrip(".")
    if not re.fullmatch(r"[a-z0-9]{1,8}", t):
        return "", "invalid"
    ext = "." + t
    if any(ext in exts for exts in CATEGORY_EXT.values()):
        return ext, "builtin"
    return ext, ""


class Rules:
    """Which file types the browser looks for: the switched-on categories plus the custom extensions.
    Immutable: a change makes a new Rules (Session.set_rules)."""

    def __init__(self, enabled=None, custom=()):
        self.enabled = frozenset(CATEGORIES if enabled is None else (c for c in enabled if c in CATEGORIES))
        out = []
        for c in custom or ():
            ext, err = check_custom(c)
            if not err and ext not in out:
                out.append(ext)
        self.custom = tuple(out)

    def with_enabled(self, enabled):
        return Rules(enabled, self.custom)

    def with_custom(self, custom):
        return Rules(self.enabled, custom)

    def signature(self):
        return (tuple(sorted(self.enabled)), self.custom)

    def ext_category(self, ext):
        """The category an extension belongs to (switched on or not), or ""."""
        for cat, exts in CATEGORY_EXT.items():
            if ext in exts:
                return cat
        return "custom" if ext in self.custom else ""

    def ext_for(self, url):
        """The extension of a link: its path first; else a known one inside a query value (?file=a.zip)."""
        ext = ext_of(url)
        if ext and self.ext_category(ext):
            return ext
        try:
            for vals in parse_qs(urlsplit(url or "").query).values():
                for v in vals:
                    e = tail_ext(unquote(v))
                    if e and self.ext_category(e):
                        return e
        except ValueError:
            pass
        return ext

    def classify(self, url, mime="", disp=""):
        """(kind, ext) of a file. The name the server gives wins, then the link, then the Content-Type."""
        ext = tail_ext(disposition_name(disp))
        cat = self.ext_category(ext) if ext else ""
        if not cat:
            ext = self.ext_for(url)
            cat = self.ext_category(ext) if ext else ""
        if cat == "video":
            return ("hls" if ext == ".m3u8" else "dash" if ext == ".mpd" else "video"), ext
        if cat:
            return cat, ext
        kind = kind_from_mime(mime)
        return (kind or "other"), ""

    def allows(self, kind):
        cat = category_of({"kind": kind})
        return cat == "other" or cat in self.enabled

    def active_exts(self):
        """The extensions to look for, without dots (what the native helper is told)."""
        exts = set()
        for cat in self.enabled:
            if cat == "custom":
                exts.update(c.lstrip(".") for c in self.custom)
            else:
                exts.update(e.lstrip(".") for e in CATEGORY_EXT[cat])
        return exts

    def csv(self):
        return ",".join(sorted(self.active_exts()))


def apply_headers(item, info, rules):
    """A file's answer to HEAD (or a one-byte GET): {mime, disp, length} -> name, kind and size of the row.
    Streams and YouTube rows keep their kind."""
    info = info or {}
    if info.get("mime"):
        item["mime"] = info["mime"]
    dname = disposition_name(info.get("disp"))
    if item.get("kind") not in ("hls", "dash", "ytdlp"):
        kind, ext = rules.classify(item.get("url"), info.get("mime"), info.get("disp"))
        if kind not in ("hls", "dash") and (kind != "other" or item.get("kind") == "other"):
            item["kind"] = kind
            item["ext"] = ext or item.get("ext") or ""
    if dname:
        item["name"] = dname
    size = clean_length(info.get("length"))
    if size:
        item["size"] = size


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


_IP_BOUND = re.compile(r"[?&]ip=[0-9a-f.:]{7,}", re.I)


def real_link(url):
    """A link made of several addresses joined by commas (ad redirect, ad redirect, real file: the download buttons of
    mod sites): the last address is the real one. Any other link is returned as it is."""
    text = (url or "").strip()
    low = text.lower()
    cut = max(low.rfind(",http"), low.rfind("%2chttp"))
    if cut <= 0:
        return text
    tail = text[cut + (1 if text[cut] == "," else 3):]
    host_a, host_b = urlsplit(text).netloc.lower(), urlsplit(tail).netloc.lower()
    if not host_b or host_a == host_b:
        return text
    return tail


def is_mediafire(url):
    host = urlsplit(url or "").netloc.lower()
    return host == "mediafire.com" or host.endswith(".mediafire.com")


_MF_SCRAMBLED = re.compile(r'data-scrambled-url="([^"]+)"')
_MF_HREF = re.compile(r'href="(https?://download[0-9a-z.-]*\.mediafire\.com/[^"]+)"', re.I)


def mediafire_direct(html):
    """The direct file address inside a MediaFire file page (the Download button), or an empty text."""
    html = html or ""
    m = _MF_SCRAMBLED.search(html)
    if m:
        try:
            import base64
            raw = m.group(1)
            link = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "ignore").strip()
            if link.startswith("http"):
                return link
        except Exception:
            pass
    m = _MF_HREF.search(html)
    return m.group(1).replace("&amp;", "&") if m else ""


def is_ip_bound(url):
    """A CDN link signed for one IP (``...&ip=1.2.3.4``): it works from the phone only, GitHub gets 404 / timeout."""
    return bool(_IP_BOUND.search(url or ""))


def workflow_url(entry):
    """The link to send to the GitHub workflows for a row: its own link, except an IP-bound direct file link,
    where the page it was found on is sent instead (the workflow reads the page itself)."""
    url = (entry or {}).get("url") or ""
    if (entry or {}).get("kind") in DIRECT_KINDS and is_ip_bound(url):
        page = (entry.get("found_on") or "").strip()
        if page.startswith(("http://", "https://")) and urlsplit(page).netloc != urlsplit(url).netloc:
            return page
    return url


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
    if kind not in ("video", "audio"):
        return seg or title or "file"
    if not seg or "." not in seg[-6:]:
        seg = (seg or title or "video") + (".mp3" if kind == "audio" else ".mp4")
    return seg


def name_has_ext(name):
    """True when a file name ends with a short extension (\".mp4\", \".zip\")."""
    return bool(re.search(r"\.[A-Za-z0-9]{1,6}$", name or ""))


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
        key = lambda e: (_KIND_RANK.get(e.get("kind"), 11), e.get("ext") or "", _natural(e.get("name")))  # noqa: E731
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


_Q_PATH = re.compile(r"(?<![0-9])(\d{3,4})p(?![a-z0-9])", re.I)
_Q_STEM = re.compile(r"[_\-.](\d{3,4})$")
_Q_NAME_P = re.compile(r"[\s_\-.]*\(?(?<![0-9])(\d{3,4})p\)?(?![a-z0-9])", re.I)
_Q_NAME_N = re.compile(r"[_\-.](\d{3,4})(?=(?:\.[a-z0-9]{2,5})?$)")


def group_base(url):
    """The link with its quality token (720p / _720) cut out, or "" when it has none.
    Two links with the same base are one video in two qualities (same host, same path, only the token differs)."""
    parts = urlsplit(url or "")
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = unquote(parts.path)
    m = _Q_PATH.search(path)
    if m and int(m.group(1)) in HEIGHTS:
        return host + path[:m.start()] + "{q}" + path[m.end():]
    head, slash, last = path.rpartition("/")
    stem, dot, ext = last.rpartition(".")
    if not dot:
        stem, ext = last, ""
    m = _Q_STEM.search(stem)
    if m and int(m.group(1)) in HEIGHTS:
        return host + head + slash + stem[:m.start(1)] + "{q}" + dot + ext
    return ""


def strip_quality(name):
    """"Movie_720p.mp4" -> "Movie.mp4" (the name of a group of qualities)."""
    def cut(m):
        return "" if int(m.group(1)) in HEIGHTS else m.group(0)
    out = _Q_NAME_P.sub(cut, name or "")
    if out == name:
        out = _Q_NAME_N.sub(cut, out)
    stem = out.rpartition(".")[0] if "." in out else out
    return out if stem.strip(" _-.") else (name or "")


def group_units(entries):
    """The rows as units: one unit per file, or one unit for a video listed in several qualities.
    A unit is {"key", "entry", "members", "name"}; ``members`` is None for a single file.
    Only a certain relation groups rows: the yt-dlp qualities of one page, the qualities of one HLS master
    playlist (both carry a ``gid``) and files whose links differ only in the quality token. Anything else
    stays a row of its own. A "group" of one row is just that row."""
    order, buckets = [], {}
    for e in entries:
        gid = e.get("gid")
        if not gid and e.get("kind") in ("video", "audio"):
            base = group_base(e.get("url"))
            if base:
                gid = "d:" + base
        if not gid:
            order.append((None, e))
            continue
        if gid not in buckets:
            buckets[gid] = []
            order.append((gid, None))
        buckets[gid].append(e)
    units = []
    for gid, e in order:
        members = buckets[gid] if gid else None
        if members is not None and len(members) >= 2:
            name = members[0].get("gname") or strip_quality(members[0].get("name") or "")
            units.append({"key": "g:" + gid, "entry": None, "members": members, "name": name})
        else:
            one = e if members is None else members[0]
            units.append({"key": one["key"], "entry": one, "members": None, "name": one.get("name") or ""})
    return units


def sort_members(members, mode):
    """The qualities inside a group: by size when sorting by size, otherwise best quality first."""
    return sort_entries(members, "size" if mode == "size" else "quality")


def sort_units(units, mode):
    """The units in one of SORT_MODES order. A group sorts by its best member (newest / oldest: by its
    newest / oldest member, size: by its biggest), so Sort works the same with and without groups."""
    reps, by_key = [], {}
    for u in units:
        by_key[u["key"]] = u
        ms = u["members"]
        if ms is None:
            reps.append(u["entry"])
            continue
        best = max(ms, key=lambda m: (quality_height(m), m.get("size") or 0))
        seqs = [m.get("seq", 0) for m in ms]
        sizes = [m["size"] for m in ms if m.get("size")]
        reps.append({**best, "key": u["key"], "name": u["name"],
                     "seq": min(seqs) if mode == "oldest" else max(seqs),
                     "size": max(sizes) if sizes else None})
    out = []
    for r in sort_entries(reps, mode):
        u = by_key[r["key"]]
        if u["members"] is not None:
            u = {**u, "members": sort_members(u["members"], mode)}
        out.append(u)
    return out


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


def hls_duration(text):
    """Seconds of an HLS media playlist (the sum of its #EXTINF lines); 0 when there are none."""
    return sum(float(x) for x in re.findall(r"#EXTINF:([\d.]+)", text or ""))


def headers_from(rec):
    headers = {}
    for key, name in (("referer", "Referer"), ("ua", "User-Agent"), ("cookie", "Cookie")):
        if rec.get(key):
            headers[name] = rec[key]
    return headers


class Session:
    """Everything the browser knows about the pages visited. What was found stays until Clear / Refresh."""

    def __init__(self, rules=None):
        self.rules = rules or Rules()
        self.needs_rescan = False   # a file type was switched on: the page is scanned again when the browser opens
        self.type_filter = "all"    # the list's filter: "all" or a category
        self.notice = []            # names of downloads the page started (shown once, when the list opens)
        self.epoch = None
        self.page = ""
        self.title = ""
        self.items = {}
        self.selected = set()
        self.open_groups = set()    # the groups of qualities opened in the list
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

    def set_rules(self, rules):
        """New file-type rules (Browser settings). A type that was switched on needs a new scan of the page."""
        if rules.signature() == self.rules.signature():
            return
        if rules.active_exts() - self.rules.active_exts():
            self.needs_rescan = True
        self.rules = rules
        self.version += 1
        keys = {e["key"] for e in self.all_entries()}
        self.selected = {k for k in self.selected if k in keys}

    def take_notice(self):
        out, self.notice = self.notice, []
        return out

    def visible(self, e):
        """A row is shown when its type is switched on; a download the page started and YouTube rows always are."""
        return e.get("kind") == "ytdlp" or bool(e.get("caught")) or self.rules.allows(e.get("kind"))

    def _reset_page(self):
        """A new page: only the yt-dlp qualities belong to one page. Found files are kept."""
        self.selected = {k for k in self.selected if not k.startswith("yt:")}
        self.ytdlp, self.ytdlp_for, self.ytdlp_error = [], None, ""
        self.version += 1

    def clear(self):
        """The list's Clear: everything found and selected goes."""
        self.items, self.selected, self.open_groups = {}, set(), set()
        self.ytdlp, self.ytdlp_error = [], ""
        self.notice = []
        self.ytdlp_for = self.page if is_ytdlp_page(self.page) else None    # not read again by itself
        self.version += 1

    def restart_scan(self):
        """The list's Refresh: like Clear, and the qualities of a YouTube page are read again."""
        self.clear()
        self.ytdlp_for = None

    def trim(self, limit=300):
        """A tab left in the background keeps only its newest files (less memory with many tabs)."""
        if len(self.items) > limit:
            keep = sorted(self.items.values(), key=lambda i: i["seq"], reverse=True)[:limit]
            self.items = {i["key"]: i for i in keep}
            self.selected = set()
            self.open_groups = set()
            self.version += 1
        self._cache = None

    def _new_item(self, key, url, kind, ext, rec, caught):
        size = clean_length(rec.get("len"))
        return {
            "key": key, "url": url, "kind": kind, "src": rec.get("src", ""), "ext": ext or ext_of(url),
            "name": disposition_name(rec.get("disp")) or name_from_url(url, kind, self.title),
            "quality": quality_hint(url) if kind in ("video", "audio") else "",
            "size": size, "size_label": "", "headers": headers_from(rec), "mime": rec.get("mime") or "",
            "variants": None, "probed": bool(caught and size),
            "caught": bool(caught),
            "seq": self._next_seq(), "found_on": rec.get("referer") or self.page,
        }

    def _catch(self, item, rec):
        """The page started a download of a file the list already has: now the server's headers are known."""
        apply_headers(item, {"mime": rec.get("mime"), "disp": rec.get("disp"), "length": rec.get("len")}, self.rules)
        if clean_length(rec.get("len")):
            item["probed"] = True
        item["caught"] = True
        item["seq"] = self._next_seq()      # the newest row
        self.notice.append(item["name"])

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
            if not url:
                continue
            key = dedupe_key(url)
            caught = rec.get("src") == "download"
            old = self.items.get(key)
            if old is not None:
                if caught:
                    self._catch(old, rec)
                    changed = True
                continue
            if len(self.items) >= MAX_ITEMS:
                break
            kind, ext = self.rules.classify(url, rec.get("mime"), rec.get("disp"))
            if not caught and not self.rules.allows(kind):
                continue            # its type is switched off in Browser settings
            item = self._new_item(key, url, kind, ext, rec, caught)
            self.items[key] = item
            if caught:
                self.notice.append(item["name"])
            changed = True
        if changed:
            self.version += 1
        return changed

    def add_link(self, url, title=""):
        """A link picked by hand (the long-press menu of a link): it joins the list like a file the page started,
        whatever its type, so the actions menu can work on it. Returns its key."""
        url = real_link(url)
        key = dedupe_key(url)
        if key not in self.items:
            kind, ext = self.rules.classify(url)
            rec = {"src": "link", "referer": self.page}
            item = self._new_item(key, url, kind, ext, rec, True)
            if title and kind not in ("hls", "dash") and not name_has_ext(item["name"]):
                item["name"] = title.strip()[:120]
            self.items[key] = item
            self.version += 1
        return key

    def count(self):
        return sum(1 for item in self.items.values() if self.visible(item))

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
                                "variants": None, "probed": True, "size": v.get("size") or item.get("size"),
                                "gid": "m:" + item["key"], "gname": item["name"]})
            elif item["key"] not in variant_keys:
                out.append(item)
        return out

    def all_entries(self):
        """Every row that is shown, each once (kept until the next change, so the list can ask every second)."""
        if self._cache is not None and self._cache[0] == self.version:
            return self._cache[1]
        out, seen = [], set()
        for e in list(self.ytdlp) + self.entries():
            if e["key"] not in seen and self.visible(e):
                seen.add(e["key"])
                out.append(e)
        self._cache = (self.version, out)
        return out

    def set_ytdlp(self, formats):
        """formats: yt-dlp qualities as (format_id, label, size_label, codec_label), ascending."""
        name = self.title or "YouTube video"
        seq = self._next_seq()
        rows = [{"key": "yt:" + fid, "kind": "ytdlp", "url": self.page, "format_id": fid, "name": name,
                 "gid": "yt:" + self.page, "gname": name,
                 "quality": label, "size_label": size_label or "", "codec": codec or "", "audio": False,
                 "size": parse_size_label(size_label), "headers": {}, "probed": True, "seq": seq}
                for fid, label, size_label, codec in reversed(formats)]
        rows.append({"key": "yt:audio", "kind": "ytdlp", "url": self.page, "format_id": "bestaudio", "name": name,
                     "gid": "yt:" + self.page, "gname": name,
                     "quality": "Audio only (MP3)", "size_label": "", "codec": "", "audio": True,
                     "size": None, "headers": {}, "probed": True, "seq": seq})
        self.ytdlp = rows
        self.version += 1
