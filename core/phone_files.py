"""Which files are already on the phone, by file name + size.

Sources: the files this app saved (api/downloads_history) and the "watched folders" (folders other
apps save in, read with Android's folder access, refreshed in the background). Android adds
" (1)" to a name that exists: that suffix is ignored when names are compared."""
import re
import threading
import time

from api import downloads_history, watched_folders_prefs

TTL = 120
MAX_FILES = 30000
MAX_DEPTH = 12
_SUFFIX = re.compile(r"\s\(\d+\)(?=\.[^./\\]*$|$)")
_cache = {"files": [], "time": 0.0, "busy": False, "counts": {}}
_DIR = "vnd.android.document/directory"


def _safe(name):
    from core import android_downloads
    return android_downloads.safe_file_name(name)


def norm(name):
    return _SUFFIX.sub("", _safe(name)).lower()


def key(name, size):
    return f"{norm(name)}|{int(size or 0)}"


class Index:
    def __init__(self, pairs):
        self._keys = {key(n, s) for n, s in pairs if n and s}

    def has(self, name, size):
        return bool(size) and key(name, size) in self._keys


def index():
    """An ``Index`` of everything known to be on the phone (``.has(name, size)``)."""
    pairs = [(e.get("name"), e.get("size")) for e in downloads_history.load()]
    pairs += list(_cache["files"])
    refresh_watched()
    return Index(pairs)


def watched_count():
    return len(_cache["files"])


def is_scanning():
    return bool(_cache["busy"])


def folder_count(uri):
    """Files found in one watched folder (and all its sub folders) by the last scan."""
    return _cache["counts"].get(str(uri), 0)


def refresh_watched(force=False):
    folders = watched_folders_prefs.load()
    if not folders:
        _cache["files"] = []
        _cache["counts"] = {}
        return
    if _cache["busy"] or (not force and time.time() - _cache["time"] < TTL):
        return
    _cache["busy"] = True

    def work():
        files = []
        counts = {}
        try:
            for folder in folders:
                try:
                    found = _scan_tree(folder["uri"], MAX_FILES - len(files))
                    counts[str(folder["uri"])] = len(found)
                    files.extend(found)
                except Exception:
                    pass
        finally:
            _cache["files"] = files
            _cache["counts"] = counts
            _cache["time"] = time.time()
            _cache["busy"] = False

    threading.Thread(target=work, daemon=True).start()


def _scan_tree(tree_uri, cap, depth=MAX_DEPTH):
    """[(name, size)] of the files inside a picked folder and ALL its sub folders (up to ``depth``
    levels), level by level so the sub folders are never skipped because the top one is big."""
    from jnius import autoclass
    Uri = autoclass("android.net.Uri")
    Docs = autoclass("android.provider.DocumentsContract")
    resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
    tree = Uri.parse(str(tree_uri))
    out = []
    queue = [(Docs.getTreeDocumentId(tree), 0)]
    while queue and len(out) < cap:
        doc_id, level = queue.pop(0)
        try:
            cursor = resolver.query(Docs.buildChildDocumentsUriUsingTree(tree, doc_id), None, None, None, None)
        except Exception:
            continue
        if cursor is None:
            continue
        try:
            id_i = cursor.getColumnIndex("document_id")
            name_i = cursor.getColumnIndex("_display_name")
            mime_i = cursor.getColumnIndex("mime_type")
            size_i = cursor.getColumnIndex("_size")
            while cursor.moveToNext() and len(out) < cap:
                if str(cursor.getString(mime_i)) == _DIR:
                    if level < depth:
                        queue.append((cursor.getString(id_i), level + 1))
                else:
                    out.append((str(cursor.getString(name_i)), int(cursor.getLong(size_i))))
        finally:
            cursor.close()
    return out
