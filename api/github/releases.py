"""GitHub Releases API calls (used as the file-hosting/download-link backend)."""
import json
import re
import time

from api.github import client
from api.github.auth import auth_headers
from core import timeutil
from core.config import API_BASE
from core.exceptions import NetworkError

# A release whose description starts with this hidden block was written by
# scripts/storage_publish.py: it lists the files kept on Arvan Cloud (and any
# warning). Arvan-only releases carry no asset at all, only this block.
_STORAGE_RE = re.compile(r"<!--ytb-storage:(.*?)-->", re.S)
# Result of the Arvan info / cleanup workflow (scripts/arvan_maintenance.py)
_ARVAN_INFO_RE = re.compile(r"<!--ytb-arvan:(.*?)-->", re.S)
# Quality/codec info written by the download workflow via ffprobe
_QUALITY_RE = re.compile(r"<!--ytb-quality:(.*?)-->", re.S)


def _parse_block(regex, body):
    m = regex.search(body or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def parse_storage_meta(body):
    """The storage block of a release description as a dict, or None."""
    return _parse_block(_STORAGE_RE, body)


def parse_arvan_info(body):
    """The info/cleanup block of an Arvan maintenance release, or None."""
    return _parse_block(_ARVAN_INFO_RE, body)


def parse_quality_meta(body):
    """The quality block of a release description as a dict, or None.
    Keys: resolution, codec, fps, bitrate_mbps, duration_s, size_bytes,
          quality_tag, audio_only."""
    return _parse_block(_QUALITY_RE, body)


def quality_label(body) -> str:
    """A short human-readable quality string from the release body.
    e.g. '1080p VP9' or '720p H264 60fps' or 'Audio MP3' or ''."""
    q = parse_quality_meta(body)
    if not q:
        return ""
    if q.get("audio_only"):
        codec = q.get("codec", "").upper()
        return f"Audio {codec}".strip()
    parts = []
    if q.get("resolution"):
        parts.append(q["resolution"])
    if q.get("codec"):
        parts.append(q["codec"].upper())
    fps = q.get("fps", 0)
    if fps and float(fps) > 30.5:
        parts.append(f"{int(round(float(fps)))}fps")
    return " ".join(parts)


def _arvan_files(release_json) -> list:
    meta = parse_storage_meta(release_json.get("body")) or {}
    return [f for f in meta.get("files", []) if isinstance(f, dict) and f.get("url")]


def _asset_links(release_json) -> list:
    assets = sorted(release_json.get("assets", []), key=lambda a: a.get("id", 0))
    return [a["browser_download_url"] for a in assets]


def get_release_link(run_id=None, tag: str = None, attempts: int = 10, delay: float = 2):
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        try:
            r = client.get_allow_missing(url)
        except NetworkError:   # connection dropped: try again
            time.sleep(delay)
            continue
        if r.status_code == 200:
            rel = r.json()
            assets = rel.get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
            arvan = _arvan_files(rel)   # Arvan-only release: no asset, the link is in the description
            if arvan:
                return arvan[0]["url"]
        time.sleep(delay)
    return None


def get_release_links(run_id=None, tag: str = None, attempts: int = 10, delay: float = 2):
    """Download links of ALL assets of a release (a multi-file upload puts
    several files in one release). [] when there is no release/asset yet."""
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            rel = r.json()
            links = _asset_links(rel)
            if links:
                return links
            arvan = _arvan_files(rel)
            if arvan:
                return [f["url"] for f in arvan]
        time.sleep(delay)
    return []


def get_release_extras(run_id=None, tag: str = None) -> dict:
    """What the app shows besides the main link(s): the Arvan links of a
    release that also has GitHub assets, any storage warning, and quality info.
    {} when the release has nothing extra. One request, no polling."""
    if tag is None:
        tag = f"run-{run_id}"
    r = client.get_allow_missing(f"{API_BASE}/releases/tags/{tag}")
    if r.status_code != 200:
        return {}
    body = r.json().get("body") or ""
    extras = {}
    meta = parse_storage_meta(body)
    if meta:
        arvan = [f["url"] for f in meta.get("files", []) if isinstance(f, dict) and f.get("url")]
        if arvan:
            extras["arvan_links"] = arvan
        warns = [str(w) for w in meta.get("warn", [])]
        if warns:
            extras["storage_warn"] = "\n".join(warns)
    # Quality info — available even for plain GitHub releases
    qlabel = quality_label(body)
    if qlabel:
        extras["quality_label"] = qlabel
    qmeta = parse_quality_meta(body)
    if qmeta:
        extras["quality_meta"] = qmeta
    return extras


def get_release_body(run_id=None, tag: str = None, attempts: int = 10, delay: float = 2):
    """Description of a release (None while it does not exist yet). Used for
    the Arvan info / cleanup results."""
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            return r.json().get("body") or ""
        time.sleep(delay)
    return None


# A release whose only asset is this file carries a link as its *content*
# (e.g. Filimo's temporary HLS link), not a file to download.
TEXT_LINK_ASSET = "direct-link.txt"


def get_release_result(run_id=None, tag: str = None, attempts: int = 10, delay: float = 2):
    """Like get_release_link, but when the release's asset is a
    ``direct-link.txt`` file, returns the link written INSIDE it instead of
    the URL of the .txt file itself."""
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            rel = r.json()
            assets = rel.get("assets", [])
            if assets:
                asset = assets[0]
                if asset.get("name") == TEXT_LINK_ASSET:
                    return _read_text_asset(asset)
                return asset["browser_download_url"]
            arvan = _arvan_files(rel)
            if arvan:
                return arvan[0]["url"]
        time.sleep(delay)
    return None


def _tag_for(run_id):
    """Tag of a run's release; an Auto follow release is addressed by its tag ('auto-<slug>')."""
    return run_id if str(run_id).startswith("auto-") else f"run-{run_id}"


def get_release_asset(run_id, attempts: int = 3, delay: float = 2):
    """The first file of release ``run-<run_id>`` as ``{"name", "api_url"}``,
    or None. ``api_url`` + ``Accept: application/octet-stream`` + the token
    downloads the file even when the repo is private (the plain
    browser_download_url answers 404 there)."""
    url = f"{API_BASE}/releases/tags/{_tag_for(run_id)}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return {"name": assets[0].get("name"), "api_url": assets[0]["url"]}
        time.sleep(delay)
    return None


def get_release_assets(run_id, attempts: int = 2, delay: float = 1.5):
    """Every file of release ``run-<run_id>`` as ``[{"name", "api_url"}]``
    (empty list when there is no such release / no files). Same download
    rules as ``get_release_asset``."""
    url = f"{API_BASE}/releases/tags/{_tag_for(run_id)}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            return [{"name": a.get("name"), "api_url": a["url"], "size": a.get("size")}
                    for a in r.json().get("assets", [])]
        time.sleep(delay)
    return []


def asset_download_headers() -> dict:
    headers = dict(auth_headers())
    headers["Accept"] = "application/octet-stream"
    return headers


def _read_text_asset(asset) -> str:
    # The asset API URL + octet-stream also works for private repos.
    headers = dict(auth_headers())
    headers["Accept"] = "application/octet-stream"
    r = client.get(asset["url"], headers=headers)
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("direct-link.txt is empty")
    return lines[0]


def _history_items(rel):
    """The History items of one release: one per file."""
    tag = rel.get("tag_name", "")
    assets = rel.get("assets", [])
    body = rel.get("body") or ""
    qlabel = quality_label(body)   # "" when no quality block
    items = []
    if not assets:
        # Arvan-only release: the file lives on Arvan, listed in the description
        when = timeutil.utc_iso_to_local(rel.get("published_at") or rel.get("created_at"))
        for f in _arvan_files(rel):
            items.append({
                "title": f.get("name") or "file",
                "link": f["url"],
                "date": when,
                "release_id": rel["id"],
                "asset_id": None,          # not a GitHub asset
                "tag_name": tag,
                "size": f.get("size", 0),
                "storage": "arvan",
                "quality_label": qlabel,
            })
        return items
    # One item per file: a multi-file upload keeps all its files in one release
    for asset in sorted(assets, key=lambda a: a.get("id", 0)):
        items.append({
            "title": asset["name"],
            "link": asset["browser_download_url"],
            # published_at, not created_at: GitHub's created_at for a release is
            # the date of the commit its tag points to, not when it was made.
            "date": timeutil.utc_iso_to_local(rel.get("published_at") or rel.get("created_at")),
            "release_id": rel["id"],
            "asset_id": asset["id"],
            "tag_name": tag,
            "size": asset.get("size", 0),
            "quality_label": qlabel,
        })
    return items


def get_live_history(tag=None):
    """The files of the app's releases (run-* / job-*), newest release first.
    With ``tag`` only the files of that one release (an Auto follow channel's
    ``auto-<slug>``): those releases are not part of the normal list, so the
    automatic downloads never crowd it."""
    if tag:
        r = client.get_allow_missing(f"{API_BASE}/releases/tags/{tag}")
        return _history_items(r.json()) if r.status_code == 200 else []
    url = f"{API_BASE}/releases?per_page=30"
    r = client.get(url)
    items = []
    for rel in r.json():
        t = rel.get("tag_name", "")
        if not (t.startswith("run-") or t.startswith("job-")):
            continue
        items.extend(_history_items(rel))
    return items


HISTORY_PAGE_SIZE = 20


def get_live_history_page(page=0, page_size=HISTORY_PAGE_SIZE):
    """One page of the History: ``(items, has_next, page)``.

    GitHub lists releases newest first, 100 per request. Releases that are not
    the app's own (run-* / job-*, e.g. auto-*) are skipped and a release with
    several files counts once per file, so the list is read request by request
    until the wanted page is full AND one more file proves there is a next
    page. A page past the end (e.g. after deleting the last file of the last
    page) falls back to the last page."""
    page = max(0, int(page or 0))
    items, github_page, more = [], 1, True
    while more:
        r = client.get(f"{API_BASE}/releases?per_page=100&page={github_page}")
        batch = r.json()
        for rel in batch:
            t = rel.get("tag_name", "")
            if t.startswith("run-") or t.startswith("job-"):
                items.extend(_history_items(rel))
        more = len(batch) >= 100
        github_page += 1
        if len(items) > (page + 1) * page_size:
            break   # the wanted page is full and there is at least one more file
    last_page = max(0, (len(items) - 1) // page_size) if items else 0
    page = min(page, last_page)
    start = page * page_size
    has_next = len(items) > start + page_size
    return items[start:start + page_size], has_next, page


def delete_release(release_id, tag_name) -> None:
    """Deletes the release and its underlying git tag so it doesn't linger."""
    url = f"{API_BASE}/releases/{release_id}"
    client.delete(url)
    # Best-effort: also remove the tag itself (release deletion alone leaves it behind)
    tag_url = f"{API_BASE}/git/refs/tags/{tag_name}"
    try:
        client.delete(tag_url)
    except Exception:
        pass


def delete_history_item(item) -> None:
    """Deletes one file from History. When it is the release's last file the
    whole release (and its tag) goes; otherwise only that file is removed, so
    the other files of a multi-file upload stay."""
    r = client.get_allow_missing(f"{API_BASE}/releases/{item['release_id']}")
    if r.status_code != 200:
        return  # already gone
    assets = r.json().get("assets", [])
    if item.get("asset_id") is None or len(assets) <= 1:
        # (an Arvan-only item has no asset: the release holds only its link;
        # the file itself is removed from the bucket by the daily cleanup)
        delete_release(item["release_id"], item["tag_name"])
    else:
        client.delete(f"{API_BASE}/releases/assets/{item['asset_id']}")


def rename_release_asset(release_id, asset_id, new_filename):
    """Renames an existing release asset in place via GitHub's asset-update API
    (no need to re-download/re-upload the file)."""
    if asset_id is None:
        raise ValueError("A file kept only on Arvan cannot be renamed")
    url = f"{API_BASE}/releases/assets/{asset_id}"
    r = client.patch(url, json={"name": new_filename})
    return r.json().get("browser_download_url")
