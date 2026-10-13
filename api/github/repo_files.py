"""Changing the repo's files through GitHub's Git Data API (no git needed):
one commit for many files, plus dated backup zips on a separate branch.

Pure API layer - no UI and no Kivy.
"""
import base64

from api.github import client
from core.config import API_BASE

BACKUP_BRANCH = "backup"
BACKUP_DIR = "backups"

_BIG_TIMEOUT = 90  # blobs / zipballs are larger than the 15 s default allows


def list_branches() -> list:
    """Names of the repo's branches."""
    names, page = [], 1
    while True:
        r = client.get(f"{API_BASE}/branches", params={"per_page": 100, "page": page}).json()
        names += [b["name"] for b in r]
        if len(r) < 100:
            return names
        page += 1


def get_branch_head(branch: str):
    """(commit_sha, tree_sha) of the branch's latest commit."""
    ref = client.get(f"{API_BASE}/git/ref/heads/{branch}").json()
    commit_sha = ref["object"]["sha"]
    commit = client.get(f"{API_BASE}/git/commits/{commit_sha}").json()
    return commit_sha, commit["tree"]["sha"]


def get_tree_files(tree_sha: str) -> dict:
    """{path: blob_sha} of every file in the tree."""
    data = client.get(f"{API_BASE}/git/trees/{tree_sha}", params={"recursive": "1"},
                      timeout=_BIG_TIMEOUT).json()
    if data.get("truncated"):
        raise RuntimeError("The repo is too large to compare through the API.")
    return {e["path"]: e["sha"] for e in data.get("tree", []) if e.get("type") == "blob"}


def get_blob(blob_sha: str) -> bytes:
    """Content of a file in the repo, by its blob sha (for showing what an
    update would change)."""
    r = client.get(f"{API_BASE}/git/blobs/{blob_sha}", timeout=_BIG_TIMEOUT).json()
    return base64.b64decode(r.get("content", ""))


def create_blob(content: bytes) -> str:
    r = client.post(f"{API_BASE}/git/blobs", timeout=_BIG_TIMEOUT, json={
        "content": base64.b64encode(content).decode("ascii"),
        "encoding": "base64",
    })
    return r.json()["sha"]


def _create_tree(entries, base_tree=None) -> str:
    body = {"tree": entries}
    if base_tree:
        body["base_tree"] = base_tree
    return client.post(f"{API_BASE}/git/trees", json=body, timeout=_BIG_TIMEOUT).json()["sha"]


def _create_commit(message, tree_sha, parents) -> str:
    r = client.post(f"{API_BASE}/git/commits", json={
        "message": message, "tree": tree_sha, "parents": parents,
    })
    return r.json()["sha"]


def commit_files(branch, parent_commit, base_tree, entries, message) -> str:
    """entries: [(path, blob_sha, mode)]. One commit on ``branch``."""
    tree = _create_tree(
        [{"path": p, "mode": m, "type": "blob", "sha": s} for p, s, m in entries],
        base_tree=base_tree,
    )
    commit = _create_commit(message, tree, [parent_commit])
    client.patch(f"{API_BASE}/git/refs/heads/{branch}", json={"sha": commit})
    return commit


def download_zipball(branch: str) -> bytes:
    """The whole repo (branch tip) as a zip - the backup content."""
    r = client.get(f"{API_BASE}/zipball/{branch}", timeout=_BIG_TIMEOUT)
    return r.content


def add_backup(name: str, zip_bytes: bytes, keep: int = 5) -> None:
    """Stores ``backups/<name>`` on the backup branch (created on first use,
    holding only the zips) and deletes the oldest ones beyond ``keep``."""
    blob = create_blob(zip_bytes)
    entries = [{"path": f"{BACKUP_DIR}/{name}", "mode": "100644", "type": "blob", "sha": blob}]
    ref = client.get_allow_missing(f"{API_BASE}/git/ref/heads/{BACKUP_BRANCH}")
    message = f"Backup {name}"

    if ref.status_code == 200:
        head = ref.json()["object"]["sha"]
        tree_sha = client.get(f"{API_BASE}/git/commits/{head}").json()["tree"]["sha"]
        existing = sorted(
            p for p in get_tree_files(tree_sha) if p.startswith(BACKUP_DIR + "/")
        )
        new_path = f"{BACKUP_DIR}/{name}"
        names = sorted(set(existing) | {new_path})
        for old in names[:max(0, len(names) - keep)]:
            if old != new_path:
                entries.append({"path": old, "mode": "100644", "type": "blob", "sha": None})
        tree = _create_tree(entries, base_tree=tree_sha)
        commit = _create_commit(message, tree, [head])
        client.patch(f"{API_BASE}/git/refs/heads/{BACKUP_BRANCH}", json={"sha": commit})
    else:
        tree = _create_tree(entries)
        commit = _create_commit(message, tree, [])
        client.post(f"{API_BASE}/git/refs", json={
            "ref": f"refs/heads/{BACKUP_BRANCH}", "sha": commit,
        })


def replace_file(branch: str, path: str, content: bytes, message: str) -> None:
    """Creates or replaces one file on ``branch`` (contents API)."""
    url = f"{API_BASE}/contents/{path}"
    current = client.get_allow_missing(url, params={"ref": branch})
    body = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if current.status_code == 200:
        body["sha"] = current.json()["sha"]
    client.request("PUT", url, json=body)
