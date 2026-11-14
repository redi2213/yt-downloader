"""Which files are already on the phone, by file name + size.

Sources: the files this app saved (api/downloads_history) and the "watched folders" (folders other
apps save in, read with Android's folder access, refreshed in the background). Android adds
" (1)" to a name that exists: that suffix is ignored when names are compared."""
import re
import threading
import time

from api import downloads_history, watched_folders_prefs

TTL = 120
MAX_FILES = 4000
_SUFFIX = re.compile(r"\s\(\d+\)(?=\.[^./\\]*$|$)")
_cache = {"files": [], "time": 0.0, "busy": False}
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


def refresh_watched(force=False):
    folders = watched_folders_prefs.load()
    if not folders:
        _cache["files"] = []
        return
    if _cache["busy"] or (not force and time.time() - _cache["time"] < TTL):
        return
    _cache["busy"] = True

    def work():
        files = []
        try:
            for folder in folders:
                try:
                    files.extend(_scan_tree(folder["uri"], MAX_FILES - len(files)))
                except Exception:
                    pass
        finally:
            _cache["files"] = files
            _cache["time"] = time.time()
            _cache["busy"] = False

    threading.Thread(target=work, daemon=True).start()


def _scan_tree(tree_uri, cap, depth=3):
    """[(name, size)] of the files inside a picked folder (and its sub folders, 3 levels)."""
    from jnius import autoclass
    Uri = autoclass("android.net.Uri")
    Docs = autoclass("android.provider.DocumentsContract")
    resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
    tree = Uri.parse(str(tree_uri))
    out = []

    def walk(doc_id, level):
        if len(out) >= cap:
            return
        cursor = resolver.query(Docs.buildChildDocumentsUriUsingTree(tree, doc_id), None, None, None, None)
        if cursor is None:
            return
        subdirs = []
        try:
            id_i = cursor.getColumnIndex("document_id")
            name_i = cursor.getColumnIndex("_display_name")
            mime_i = cursor.getColumnIndex("mime_type")
            size_i = cursor.getColumnIndex("_size")
            while cursor.moveToNext() and len(out) < cap:
                if str(cursor.getString(mime_i)) == _DIR:
                    subdirs.append(cursor.getString(id_i))
                else:
                    out.append((str(cursor.getString(name_i)), int(cursor.getLong(size_i))))
        finally:
            cursor.close()
        if level < depth:
            for child in subdirs:
                walk(child, level + 1)

    walk(Docs.getTreeDocumentId(tree), 0)
    return out
