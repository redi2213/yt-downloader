"""Updating the app's own repo from update.zip.

update.zip has one top-level folder per branch (``main/``, ``config/``).
For each folder present: read the branch -> compare -> (back the branch up
as a dated zip on the ``backup`` branch, last 5 kept; not for ``config``) ->
upload only the changed files -> ONE commit on that branch. Files that are
in the repo but not in the zip are left alone.
"""
import json
from datetime import datetime, timedelta, timezone

import requests

from api.github import repo_files
from core import zip_tools
from core.async_utils import run_in_background
from core.config import LOCAL_UTC_OFFSET_MINUTES
from core.exceptions import AuthenticationError, NetworkError

BACKUPS_KEPT = 5
NO_BACKUP_BRANCHES = ("config",)
CONFIG_FILE = "config.json"
_PERMISSION_HINT = (
    "GitHub refused the change. The sign-in needs write access to Contents "
    "and Workflows (GitHub App settings), then sign in again."
)


def summarize_zip(data: bytes) -> dict:
    """{branch: file_count}. Raises zip_tools.ZipError."""
    update = zip_tools.read_update_zip(data)
    return {branch: len(files) for branch, files in update.items()}


def start_repo_update(data: bytes, on_status, on_done) -> None:
    run_in_background(_update_thread, data, on_status, on_done)


def validate_config(data: bytes) -> dict:
    """Parsed config.json, or raises ValueError with a readable message."""
    try:
        obj = json.loads(data.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{CONFIG_FILE} is not valid JSON: {str(e)[:50]}")
    if not isinstance(obj, dict) or not isinstance(obj.get("actions"), list):
        raise ValueError(f'{CONFIG_FILE} must be an object with an "actions" list.')
    return obj


def _backup_name() -> str:
    local = datetime.now(timezone.utc) + timedelta(minutes=LOCAL_UTC_OFFSET_MINUTES)
    return local.strftime("%Y-%m-%d_%H%M") + ".zip"


def _explain(e: Exception) -> str:
    if isinstance(e, AuthenticationError):
        return _PERMISSION_HINT
    if isinstance(e, NetworkError):
        return f"Network error: {str(e)[:60]}"
    if isinstance(e, requests.exceptions.HTTPError):
        code = getattr(getattr(e, "response", None), "status_code", "?")
        if code in (403, 404, 422):
            return f"{_PERMISSION_HINT} (HTTP {code})"
        return f"GitHub error (HTTP {code})."
    return f"Error: {str(e)[:80]}"


def _update_branch(branch, files, on_status):
    """Returns (changed_count, [changed paths])."""
    on_status(f"{branch}: reading...")
    head, tree_sha = repo_files.get_branch_head(branch)
    remote = repo_files.get_tree_files(tree_sha)
    changed = [
        (path, content, mode) for path, (content, mode) in files.items()
        if remote.get(path) != zip_tools.git_blob_sha(content)
    ]
    if not changed:
        return 0, []

    if branch not in NO_BACKUP_BRANCHES:
        on_status(f"{branch}: backing up...")
        repo_files.add_backup(_backup_name(), repo_files.download_zipball(branch), keep=BACKUPS_KEPT)

    entries, total = [], len(changed)
    for i, (path, content, mode) in enumerate(changed, 1):
        on_status(f"{branch}: uploading {i}/{total}...")
        entries.append((path, repo_files.create_blob(content), mode))

    on_status(f"{branch}: committing...")
    repo_files.commit_files(
        branch, head, tree_sha, entries,
        f"Update from app ({total} file{'s' if total != 1 else ''})",
    )
    return total, [p for p, _, _ in changed]


def _update_thread(data, on_status, on_done):
    try:
        on_status("Checking branches...")
        branches = repo_files.list_branches()
        update = zip_tools.read_update_zip(data, branches)

        # check EVERYTHING before touching the repo
        for branch, files in update.items():
            if branch not in branches:
                raise zip_tools.ZipError(
                    f'The repo has no branch named "{branch}". Folder names in the zip must match branch names.')
            if branch == repo_files.BACKUP_BRANCH:
                raise zip_tools.ZipError("The backup branch cannot be updated from a zip.")
            if branch == "config" and CONFIG_FILE in files:
                validate_config(files[CONFIG_FILE][0])

        lines, project_changed = [], False
        for branch in sorted(update):
            count, paths = _update_branch(branch, update[branch], on_status)
            if not count:
                lines.append(f"{branch}: already up to date")
                continue
            if branch not in NO_BACKUP_BRANCHES:
                project_changed = True
            shown = ", ".join(paths[:5]) + (f" +{count - 5} more" if count > 5 else "")
            lines.append(f"{branch}: {count} file(s) changed ({shown})")
        on_done({"ok": True, "changed": project_changed, "message": "\n".join(lines)})
    except zip_tools.ZipError as e:
        on_done({"ok": False, "changed": False, "message": str(e)})
    except ValueError as e:
        on_done({"ok": False, "changed": False, "message": str(e)})
    except Exception as e:
        on_done({"ok": False, "changed": False, "message": _explain(e)})
