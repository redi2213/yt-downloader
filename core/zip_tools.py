"""Reading an update.zip for the in-app update. Pure Python (no Kivy, no
network).

Layout of update.zip - one top-level folder per BRANCH, named exactly like
the branch:

    update.zip
    +-- main/     files of the main branch (the whole project)
    +-- config/   files of the config branch (config.json)

A folder that is present is updated; a missing one is left alone.
"""
import hashlib
import io
import zipfile

# Never sent to the repo
SKIP_DIRS = {".git", "__pycache__", ".buildozer", "bin", ".idea", ".vscode", "__MACOSX"}
SKIP_FILES = {"core/_branch.py"}  # generated at build time
SKIP_SUFFIXES = (".pyc", ".pyo", ".apk", ".aab")
MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_BRANCHES = ("main", "config")


class ZipError(Exception):
    pass


def git_blob_sha(data: bytes) -> str:
    """The sha git gives a file with this content (to skip unchanged files)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def is_zip(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _clean_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def read_update_zip(data: bytes, known_branches=None) -> dict:
    """{branch: {path: (bytes, git_mode)}} for every branch folder in the zip.

    If the whole zip sits inside ONE extra folder (e.g. ``update/main/...``)
    that folder is removed first. Raises ZipError with a readable message."""
    known = set(known_branches or DEFAULT_BRANCHES)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ZipError("This is not a valid zip file.")

    entries = []
    for info in zf.infolist():
        name = _clean_name(info.filename)
        if info.is_dir() or not name or name.startswith("__MACOSX/"):
            continue
        entries.append((info, name))
    if not entries:
        raise ZipError("The zip is empty.")

    # one wrapper folder around the branch folders -> remove it
    tops = {n.split("/")[0] for _, n in entries}
    if len(tops) == 1 and next(iter(tops)) not in known:
        wrapper = next(iter(tops)) + "/"
        children = {n[len(wrapper):].split("/")[0] for _, n in entries if "/" in n[len(wrapper):]}
        if children & known:
            entries = [(i, n[len(wrapper):]) for i, n in entries if n.startswith(wrapper)]

    result = {}
    for info, name in entries:
        parts = name.split("/")
        if len(parts) < 2:
            raise ZipError(
                f'"{name}" is outside any folder. Put files inside folders named like '
                'branches, e.g. main/ and config/.'
            )
        branch, path = parts[0], "/".join(parts[1:])
        inner = path.split("/")
        if ".." in inner or any(p in SKIP_DIRS for p in inner[:-1]) or path in SKIP_FILES:
            continue
        if path.endswith(SKIP_SUFFIXES) or inner[-1] == ".DS_Store":
            continue
        if info.file_size > MAX_FILE_BYTES:
            raise ZipError(f"{name} is too large ({info.file_size // (1024 * 1024)} MB).")
        executable = (info.external_attr >> 16) & 0o111
        result.setdefault(branch, {})[path] = (zf.read(info), "100755" if executable else "100644")

    if not result:
        raise ZipError("No files found. Use folders named like branches, e.g. main/ and config/.")
    return result
