"""Saving a file from a link into the phone's Downloads folder.

* Android 10+ (API 29+): through MediaStore - no storage permission needed,
  the file shows up in the Files app / Downloads right away.
* Older Android: a plain copy into /storage/emulated/0/Download.
* Desktop (no pyjnius): ~/Downloads, so the code can be tried on a computer.

The file is fetched in chunks (optionally with request headers, e.g. a GitHub
token for a private repo), so a big APK never sits in memory. Pure helpers, no Kivy.
"""
import mimetypes
import os
import shutil
import tempfile
import time
from urllib.parse import unquote, urlsplit

import requests

ROOT_FOLDER = "Yt-bridge"
CATEGORIES = ("APK", "Backup", "YouTube", "Aparat", "Telegram", "Filimo", "Any-site", "Logs", "Other")

# workflow file -> subfolder of Download/Yt-bridge
_WORKFLOW_CATEGORY = {
    "build-apk.yml": "APK",
    "backup-project.yml": "Backup",
    "download.yml": "YouTube",
    "list-formats.yml": "YouTube",
    "list-playlist.yml": "YouTube",
    "aparat-download.yml": "Aparat",
    "telegram-download.yml": "Telegram",
    "filimo-direct-link.yml": "Filimo",
    "Any-Site-Upload.yml": "Any-site",
    "Series-Links.yml": "Any-site",
}


def category_for_workflow(workflow_file):
    """Subfolder name for the files a workflow produced (\"Other\" if unknown)."""
    return _WORKFLOW_CATEGORY.get(workflow_file or "", "Other")


class Saved(str):
    """The short text shown to the user (``Download/Yt-bridge/APK/x.apk``).
    ``.location`` is the content uri (Android 10+) or the file path - what an
    installer / opener needs."""
    location = None


CHUNK = 256 * 1024
PROGRESS_EVERY = 0.4  # seconds between progress reports

_MIME = {
    ".apk": "application/vnd.android.package-archive",
    ".zip": "application/zip",
}


def file_name_from_url(url, default="download.bin"):
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return name or default


def _mime_for(name):
    ext = os.path.splitext(name)[1].lower()
    return _MIME.get(ext) or mimetypes.guess_type(name)[0] or "application/octet-stream"


def download_to_downloads(url, name=None, on_progress=None, headers=None, category="Other"):
    """Downloads ``url`` into Download/Yt-bridge/<category> and returns a short
    text like ``Download/Yt-bridge/Backup/project-backup-2026-10-14_17-51.zip``
    (a ``Saved``, with ``.location``). Raises on failure.
    ``on_progress(done_bytes, total_bytes)`` may be called from this thread
    (total is 0 when the server does not say)."""
    name = name or file_name_from_url(url)
    fd, tmp_path = tempfile.mkstemp(suffix=".part")
    os.close(fd)
    try:
        _fetch(url, tmp_path, on_progress, headers)
        return _save_in_downloads(tmp_path, name, category)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _fetch(url, path, on_progress, headers=None):
    with requests.get(url, stream=True, timeout=(15, 60), headers=headers) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        with open(path, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                now = time.monotonic()
                if on_progress and now - last >= PROGRESS_EVERY:
                    last = now
                    on_progress(done, total)
        if on_progress:
            on_progress(done, total or done)


def save_text_file(text, name, category="Logs"):
    """Saves ``text`` as a file in Download/Yt-bridge/<category>. Returns the
    same kind of ``Saved`` text as ``download_to_downloads``."""
    fd, tmp_path = tempfile.mkstemp(suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write((text or "").encode("utf-8"))
        return _save_in_downloads(tmp_path, name, category)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def safe_file_name(name, default="file"):
    """A name that is fine in any folder (no slashes etc.)."""
    cleaned = "".join("_" if ch in '\\/:*?"<>|' else ch for ch in (name or "")).strip().strip(".")
    return cleaned or default


def _save_in_downloads(src, name, category="Other"):
    category = category if category in CATEGORIES else "Other"
    name = safe_file_name(name)
    try:
        from jnius import autoclass
    except Exception:
        return _save_plain(src, name, os.path.join(os.path.expanduser("~"), "Downloads", ROOT_FOLDER, category))
    sdk = autoclass("android.os.Build$VERSION").SDK_INT
    if sdk >= 29:
        return _save_mediastore(src, name, autoclass, category)
    env = autoclass("android.os.Environment")
    base = env.getExternalStoragePublicDirectory(env.DIRECTORY_DOWNLOADS).getAbsolutePath()
    return _save_plain(src, name, os.path.join(str(base), ROOT_FOLDER, category))


def _unique_path(folder, name):
    base, ext = os.path.splitext(name)
    path, n = os.path.join(folder, name), 1
    while os.path.exists(path):
        path = os.path.join(folder, f"{base} ({n}){ext}")
        n += 1
    return path


def _save_plain(src, name, folder):
    os.makedirs(folder, exist_ok=True)
    path = _unique_path(folder, name)
    shutil.copyfile(src, path)
    saved = Saved(_plain_label(path))
    saved.location = path
    return saved


def _plain_label(path):
    parts = path.replace("\\", "/").split("/Download/", 1)
    if len(parts) == 2:
        return "Download/" + parts[1]
    parts = path.replace("\\", "/").split("/Downloads/", 1)
    return "Download/" + parts[1] if len(parts) == 2 else path


def _save_mediastore(src, name, autoclass, category="Other"):
    String = autoclass("java.lang.String")
    ContentValues = autoclass("android.content.ContentValues")
    Downloads = autoclass("android.provider.MediaStore$Downloads")
    FileInputStream = autoclass("java.io.FileInputStream")
    FileUtils = autoclass("android.os.FileUtils")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    resolver = activity.getContentResolver()

    values = ContentValues()
    values.put("_display_name", String(name))
    values.put("mime_type", String(_mime_for(name)))
    values.put("relative_path", String(f"Download/{ROOT_FOLDER}/{category}"))
    uri = resolver.insert(Downloads.EXTERNAL_CONTENT_URI, values)
    if uri is None:
        raise OSError("Android would not create the file in Downloads")

    stream_in = FileInputStream(src)
    stream_out = resolver.openOutputStream(uri)
    try:
        FileUtils.copy(stream_in, stream_out)
    finally:
        try:
            stream_in.close()
        finally:
            stream_out.close()

    from core.android_files import read_uri_name
    shown = read_uri_name(uri) or name  # Android may add " (1)"
    saved = Saved(f"Download/{ROOT_FOLDER}/{category}/{shown}")
    saved.location = str(uri.toString())
    return saved
