"""GitHub Releases API calls (used as the file-hosting/download-link backend)."""
import time

from api.github import client
from api.github.auth import auth_headers
from core import timeutil
from core.config import API_BASE


def get_release_link(run_id=None, tag: str = None, attempts: int = 10, delay: float = 2):
    if tag is None:
        tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = client.get_allow_missing(url)
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
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
            assets = r.json().get("assets", [])
            if assets:
                asset = assets[0]
                if asset.get("name") == TEXT_LINK_ASSET:
                    return _read_text_asset(asset)
                return asset["browser_download_url"]
        time.sleep(delay)
    return None


def _read_text_asset(asset) -> str:
    # The asset API URL + octet-stream also works for private repos.
    headers = dict(auth_headers())
    headers["Accept"] = "application/octet-stream"
    r = client.get(asset["url"], headers=headers)
    lines = [l.strip() for l in r.text.splitlines() if l.strip()]
    if not lines:
        raise ValueError("direct-link.txt is empty")
    return lines[0]


def get_live_history():
    url = f"{API_BASE}/releases?per_page=30"
    r = client.get(url)
    releases = r.json()
    items = []
    for rel in releases:
        tag = rel.get("tag_name", "")
        if not (tag.startswith("run-") or tag.startswith("job-")):
            continue
        assets = rel.get("assets", [])
        if not assets:
            continue
        items.append({
            "title": assets[0]["name"],
            "link": assets[0]["browser_download_url"],
            # published_at, not created_at: GitHub's created_at for a release is
            # the date of the commit its tag points to, not when it was made.
            "date": timeutil.utc_iso_to_local(rel.get("published_at") or rel.get("created_at")),
            "release_id": rel["id"],
            "asset_id": assets[0]["id"],
            "tag_name": tag,
            "size": assets[0].get("size", 0),
        })
    return items


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


def rename_release_asset(release_id, asset_id, new_filename):
    """Renames an existing release asset in place via GitHub's asset-update API
    (no need to re-download/re-upload the file)."""
    url = f"{API_BASE}/releases/assets/{asset_id}"
    r = client.patch(url, json={"name": new_filename})
    return r.json().get("browser_download_url")
