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


def download_to_downloads(url, name=None, on_progress=None, headers=None):
    """Downloads ``url`` into the Downloads folder and returns a short text
    like ``Download/project-backup-2026-10-14_17-51.zip``. Raises on failure.
    ``on_progress(done_bytes, total_bytes)`` may be called from this thread
    (total is 0 when the server does not say)."""
    name = name or file_name_from_url(url)
    fd, tmp_path = tempfile.mkstemp(suffix=".part")
    os.close(fd)
    try:
        _fetch(url, tmp_path, on_progress, headers)
        return _save_in_downloads(tmp_path, name)
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


def _save_in_downloads(src, name):
    try:
        from jnius import autoclass
    except Exception:
        return _save_plain(src, name, os.path.join(os.path.expanduser("~"), "Downloads"))
    sdk = autoclass("android.os.Build$VERSION").SDK_INT
    if sdk >= 29:
        return _save_mediastore(src, name, autoclass)
    env = autoclass("android.os.Environment")
    folder = env.getExternalStoragePublicDirectory(env.DIRECTORY_DOWNLOADS).getAbsolutePath()
    return _save_plain(src, name, str(folder))


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
    return "Download/" + os.path.basename(path)


def _save_mediastore(src, name, autoclass):
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
    values.put("relative_path", String("Download"))
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
    return "Download/" + (read_uri_name(uri) or name)  # Android may add " (1)"
