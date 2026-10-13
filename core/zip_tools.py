"""Reading zips for the in-app update. Pure Python (no Kivy, no network).

Two kinds of zip are understood:

1. A zip with one top-level folder per BRANCH (the layout of the project
   backup and of the old update.zip)::

       update.zip
       +-- main/     (or main-branch/)    files of the main branch
       +-- config/   (or config-branch/)  files of the config branch

   -> ``read_update_zip`` (every file goes to the same path in that branch)

2. Any other zip (loose files, maybe in folders) -> ``read_loose_files``;
   the app then works out where each file belongs (core/file_router.py).
"""
import hashlib
import io
import zipfile

# Never sent to the repo
SKIP_DIRS = {".git", "__pycache__", ".buildozer", "bin", ".idea", ".vscode", "__MACOSX"}
SKIP_FILES = {"core/_branch.py"}  # generated at build time
SKIP_SUFFIXES = (".pyc", ".pyo", ".apk", ".aab")
# Secret-like files: the repo is public, so these are never sent, even if a
# zip contains them by mistake (signing keystore, its base64 copy, keys).
SKIP_SECRET_SUFFIXES = (".keystore", ".jks", ".b64", ".pem", ".p12", ".pfx", ".key")
SKIP_SECRET_NAMES = {".env", "cookies.txt", "local.properties", "keystore.properties"}
MAX_FILE_BYTES = 25 * 1024 * 1024
DEFAULT_BRANCHES = ("main", "config")
# The project backup names its folders "<branch>-branch"
BRANCH_ALIASES = {"main-branch": "main", "config-branch": "config"}


class ZipError(Exception):
    pass


def git_blob_sha(data: bytes) -> str:
    """The sha git gives a file with this content (to skip unchanged files)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def is_zip(data: bytes) -> bool:
    return data[:4] == b"PK\x03\x04"


def _clean_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def is_skipped_path(path: str) -> bool:
    """True for files that are never sent to the repo (caches, build output,
    secrets...). ``path`` may use / or \\ ."""
    path = _clean_name(path)
    inner = path.split("/")
    if ".." in inner:
        return True
    if any(p in SKIP_DIRS for p in inner[:-1]) or path in SKIP_FILES:
        return True
    if path.endswith(SKIP_SUFFIXES) or inner[-1] == ".DS_Store":
        return True
    if path.lower().endswith(SKIP_SECRET_SUFFIXES) or inner[-1] in SKIP_SECRET_NAMES:
        return True
    return False


def _open_entries(data: bytes, known_branches=None):
    """(ZipFile, [(info, name)]) with one wrapper folder around the branch
    folders removed. Raises ZipError."""
    known = set(known_branches or DEFAULT_BRANCHES) | set(BRANCH_ALIASES)
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
    return zf, entries


def has_branch_folders(data: bytes, known_branches=None) -> bool:
    """True if the zip has top-level folders named like branches."""
    known = set(known_branches or DEFAULT_BRANCHES) | set(BRANCH_ALIASES)
    try:
        _, entries = _open_entries(data, known_branches)
    except ZipError:
        return False
    return any("/" in n and n.split("/")[0] in known for _, n in entries)


def _mode(info) -> str:
    return "100755" if (info.external_attr >> 16) & 0o111 else "100644"


def read_update_zip(data: bytes, known_branches=None) -> dict:
    """{branch: {path: (bytes, git_mode)}} for every branch folder in the zip.

    If the whole zip sits inside ONE extra folder (e.g. ``update/main/...``)
    that folder is removed first. Folders ``main-branch`` / ``config-branch``
    (the project backup) count as ``main`` / ``config``.
    Raises ZipError with a readable message."""
    zf, entries = _open_entries(data, known_branches)

    result = {}
    for info, name in entries:
        parts = name.split("/")
        if len(parts) < 2:
            raise ZipError(
                f'"{name}" is outside any folder. Put files inside folders named like '
                'branches, e.g. main/ and config/.'
            )
        branch, path = BRANCH_ALIASES.get(parts[0], parts[0]), "/".join(parts[1:])
        if is_skipped_path(path):
            continue
        if info.file_size > MAX_FILE_BYTES:
            raise ZipError(f"{name} is too large ({info.file_size // (1024 * 1024)} MB).")
        result.setdefault(branch, {})[path] = (zf.read(info), _mode(info))

    if not result:
        raise ZipError("No files found. Use folders named like branches, e.g. main/ and config/.")
    return result


def read_loose_files(data: bytes) -> list:
    """[(path_in_zip, bytes, git_mode)] of every file in a zip that has no
    branch folders. Skipped files (caches, secrets...) are left out."""
    zf, entries = _open_entries(data)
    out = []
    for info, name in entries:
        if is_skipped_path(name):
            continue
        if info.file_size > MAX_FILE_BYTES:
            raise ZipError(f"{name} is too large ({info.file_size // (1024 * 1024)} MB).")
        out.append((name, zf.read(info), _mode(info)))
    return out
