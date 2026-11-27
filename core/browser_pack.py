"""Browser pack: the in-app browser's Python code, updated from GitHub without a new APK.

Nothing in here uses Kivy. Only ``check_update`` uses the network (call it from a background thread);
``activate`` and the other functions run on the main thread and never raise.

How it works
------------
The browser is plain Python (core/browser_media.py ... screens/browser.py, the files in ``PACK_FILES``). The APK
holds one copy of them ("built-in"). The workflow publish-browser-pack.yml copies the same files from ``main`` to
the ``config`` branch (``plugins/browser/``) together with a ``manifest.json`` (version + SHA-256 of every file).
The app downloads that pack, checks it, keeps it on the phone, and the next time the browser opens it loads
those files *instead of* the built-in ones (they take the place of the modules in ``sys.modules``).

Checks before a downloaded pack is used (all of them, every time it is loaded):
  1. manifest: schema, version name, ``api`` equal to ``PACK_API``, ``native_api`` not above ``NATIVE_API``,
     exactly the files of ``PACK_FILES`` (nothing else, nothing missing), each one of a sane size
  2. SHA-256 of every file equals the manifest (a half-downloaded or edited file is refused)
  3. every file is valid Python and has no eval / exec / __import__ / subprocess / ctypes / pickle ...
  4. the loaded modules have the names the app's fixed parts need (``_REQUIRED``) and a small self-test passes
If any step fails the built-in code is put back untouched and that version is blocked.

Safety net: the version being tried is marked "pending" until the browser screen was built once
(``confirm``). A start that never reached it (crash) blocks that version and the previous good one (or the
built-in code) is used. ``fall_back`` does the same when building the screen raises.

Not online (needs a new APK): java/.../BrowserHelper.java, core/android_browser.py, api/browser_prefs.py and
this file. Bump ``NATIVE_API`` when new pack code needs a newer BrowserHelper: older apps then refuse that pack.
"""
import ast
import hashlib
import importlib
import json
import linecache
import os
import re
import shutil
import sys
import threading
import time
import traceback
import types

PACK_API = 1        # the contract between pack code and the fixed parts of the app (navigator, settings)
NATIVE_API = 3      # BrowserHelper.java / core/android_browser.py level of this APK (3: inspect("storage") for the Full page export)

# Dependency order: the core logic first, then services, then the screens (a screen imports the ones above it).
PACK_FILES = (
    "core/browser_media.py",
    "core/browser_tabs.py",
    "core/browser_tools.py",
    "core/browser_cookies.py",
    "services/browser_service.py",
    "screens/browser_tools.py",
    "screens/browser_pages.py",
    "screens/browser.py",
    "screens/browser_cookies.py",
)
REMOTE_FOLDER = "plugins/browser"       # on the config branch
MAX_FILE = 250_000
KEEP_OLD = 2                            # older good versions kept on the phone (for Go back)
CHECK_EVERY = 6 * 3600                  # automatic check: at most this often (seconds)

_REQUIRED = {
    "core/browser_media.py": ("Session", "Rules", "SORT_MODES", "CATEGORIES", "DIRECT_KINDS", "group_units",
                              "sort_units", "normalize_input", "is_ytdlp_page", "fmt_size"),
    "core/browser_tabs.py": ("Tabs", "LinkList", "MAX_TABS"),
    "core/browser_tools.py": ("translate_url", "original_url", "host_of"),
    "core/browser_cookies.py": ("to_netscape", "cookie_header", "build_jar", "redact"),
    "services/browser_service.py": ("state", "load_rules", "save_rules", "default_sort", "start_probe",
                                    "fetch_headers"),
    "screens/browser.py": ("build", "build_list", "open_actions", "open_details", "open_settings", "_copy"),
    "screens/browser_pages.py": ("open_menu", "open_tabs", "open_history", "open_bookmarks", "open_bookmark"),
    "screens/browser_tools.py": ("add_menu", "open_confirm", "FindBar", "apply_saved"),
    "screens/browser_cookies.py": ("open_export", "open_output", "open_send", "reset"),
}
_BANNED_CALLS = {"eval", "exec", "__import__", "compile"}
_BANNED_MODULES = {"subprocess", "ctypes", "pickle", "marshal", "socket", "multiprocessing"}
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,39}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_MISSING = object()

BASE_DIR = None                         # tests set a folder; None = next to the app's settings file
_LOCK = threading.RLock()
_ACTIVE = {"done": False, "version": "", "snapshot": None, "error": ""}


class PackError(Exception):
    pass


def flat(path):
    return path.replace("/", "__")


def dotted(path):
    return path[:-3].replace("/", ".")


def _base():
    if BASE_DIR:
        return BASE_DIR
    from core.config import SETTINGS_STORE_FILE
    return os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "browser_pack")


def _pack_dir(version):
    return os.path.join(_base(), "packs", version)


# -- state kept on the phone ---------------------------------------------------------------------------------
def _default_state():
    return {"current": "", "previous": [], "blocked": [], "pending": "", "auto": True,
            "last_check": 0, "last_error": ""}


def load_state():
    st = _default_state()
    try:
        with open(os.path.join(_base(), "state.json"), encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            for key in ("current", "pending", "last_error"):
                if isinstance(raw.get(key), str):
                    st[key] = raw[key]
            for key in ("previous", "blocked"):
                if isinstance(raw.get(key), list):
                    st[key] = [v for v in raw[key] if isinstance(v, str) and _VERSION.match(v)]
            if isinstance(raw.get("auto"), bool):
                st["auto"] = raw["auto"]
            if isinstance(raw.get("last_check"), (int, float)):
                st["last_check"] = raw["last_check"]
    except Exception:
        pass
    if not _VERSION.match(st["current"] or "a"):
        st["current"] = ""
    return st


def save_state(st):
    try:
        os.makedirs(_base(), exist_ok=True)
        path = os.path.join(_base(), "state.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f)
        os.replace(tmp, path)
    except Exception:
        pass            # a state that could not be saved only costs a repeated check


def _block(st, version, why=""):
    if version and version not in st["blocked"]:
        st["blocked"].append(version)
        st["blocked"] = st["blocked"][-20:]
    if why:
        st["last_error"] = f"{version}: {why}"[:300]


def _prune(st):
    keep = {v for v in [st["current"]] + st["previous"] if v}
    root = os.path.join(_base(), "packs")
    try:
        for name in os.listdir(root):
            if name not in keep:
                shutil.rmtree(os.path.join(root, name), ignore_errors=True)
    except OSError:
        pass


# -- checking a pack ------------------------------------------------------------------------------------------
def check_manifest(m):
    """"" when the manifest is acceptable, else the reason."""
    if not isinstance(m, dict) or m.get("schema") != 1:
        return "Not a browser pack manifest"
    version = m.get("version")
    if not isinstance(version, str) or not _VERSION.match(version):
        return "Bad version name"
    api = m.get("api")
    if not isinstance(api, int) or isinstance(api, bool) or api != PACK_API:
        return f"Made for another app version (pack API {api}, this app {PACK_API})"
    native = m.get("native_api", 1)
    if not isinstance(native, int) or isinstance(native, bool) or native > NATIVE_API:
        return f"Needs a newer app build (native level {native}, this app {NATIVE_API})"
    files = m.get("files")
    if not isinstance(files, dict) or set(files) != set(PACK_FILES):
        return "The file list does not match what the app expects"
    for path, meta in files.items():
        if not isinstance(meta, dict) or not _HEX64.match(str(meta.get("sha256") or "")):
            return f"No checksum for {path}"
        size = meta.get("size")
        if not isinstance(size, int) or size <= 0 or size > MAX_FILE:
            return f"Bad size for {path}"
    return ""


def _scan(path, text):
    """Syntax and red flags of one file: "" when fine."""
    try:
        tree = ast.parse(text, filename=path)
    except SyntaxError as e:
        return f"{path}: syntax error, line {e.lineno}"
    except ValueError:
        return f"{path}: not readable as Python"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALLS:
            return f"{path}: uses {node.func.id}() (line {node.lineno})"
        names = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module]
        for name in names:
            if name.split(".")[0] in _BANNED_MODULES:
                return f"{path}: imports {name} (line {node.lineno})"
    return ""


def validate(manifest, texts):
    """Static checks of a downloaded pack (no code runs): "" when fine, else the reason."""
    err = check_manifest(manifest)
    if err:
        return err
    for path in PACK_FILES:
        text = texts.get(path)
        if not isinstance(text, str):
            return f"{path} is missing"
        data = text.encode("utf-8")
        if len(data) > MAX_FILE or "\x00" in text:
            return f"{path}: bad file"
        if hashlib.sha256(data).hexdigest() != manifest["files"][path]["sha256"]:
            return f"{path}: checksum does not match"
        err = _scan(path, text)
        if err:
            return err
    return ""


def _selftest(mods):
    bm = mods.get("core/browser_media.py")
    if bm is not None:
        sess = bm.Session()
        sess.merge({"epoch": 1, "page": "https://a.test/", "title": "t", "items": [
            {"url": "https://c.test/v_720p.mp4", "src": "net"}, {"url": "https://c.test/v_480p.mp4", "src": "net"}]})
        entries = sess.all_entries()
        if not entries:
            raise PackError("self-test: the session found nothing")
        bm.sort_units(bm.group_units(entries), "size")
    bt = mods.get("core/browser_tabs.py")
    if bt is not None:
        tabs = bt.Tabs()
        tabs.new("https://x.test/")
        if bt.Tabs.from_data(tabs.to_data()).count() < 1:
            raise PackError("self-test: tabs were not read back")


# -- loading the code -----------------------------------------------------------------------------------------
def _exec_module(name, text, filename):
    module = types.ModuleType(name)
    module.__file__ = filename
    module.__package__ = name.rpartition(".")[0]
    sys.modules[name] = module
    parent, _, leaf = name.rpartition(".")
    setattr(importlib.import_module(parent), leaf, module)      # "from core import browser_media" reads this
    linecache.cache[filename] = (len(text), None, text.splitlines(True), filename)
    exec(compile(text, filename, "exec"), module.__dict__)
    return module


def _take_snapshot():
    snap = {}
    for path in PACK_FILES:
        name = dotted(path)
        parent, _, leaf = name.rpartition(".")
        pkg = importlib.import_module(parent)
        snap[name] = (sys.modules.get(name), getattr(pkg, leaf, _MISSING))
    return snap


def _restore(snap):
    for name, (module, attr) in snap.items():
        parent, _, leaf = name.rpartition(".")
        pkg = sys.modules.get(parent)
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
        if pkg is not None:
            if attr is _MISSING:
                if hasattr(pkg, leaf):
                    try:
                        delattr(pkg, leaf)
                    except AttributeError:
                        pass
            else:
                setattr(pkg, leaf, attr)
        linecache.cache.pop(f"<browserpack {leaf}>", None)


def _install(version, texts):
    """Runs the pack's code in place of the built-in modules. Raises (built-in code put back) when anything
    is wrong."""
    snap = _take_snapshot()
    mods = {}
    try:
        for path in PACK_FILES:
            mods[path] = _exec_module(dotted(path), texts[path], f"<browserpack {path.rpartition('/')[2][:-3]}>")
        for path, names in _REQUIRED.items():
            if path in mods:
                for name in names:
                    if not hasattr(mods[path], name):
                        raise PackError(f"{path} has no {name}")
        _selftest(mods)
    except BaseException:
        _restore(snap)
        raise
    _ACTIVE["snapshot"] = snap
    _ACTIVE["version"] = version


def _flush_browser_state():
    """Tabs, history and bookmarks are written to the phone before the code that holds them is swapped."""
    mod = sys.modules.get("services.browser_service")
    try:
        if mod is not None:
            mod.state().flush()
    except Exception:
        pass


def deactivate():
    """Puts the built-in modules back (no-op when the built-in code is running)."""
    if _ACTIVE["snapshot"]:
        _flush_browser_state()
        _restore(_ACTIVE["snapshot"])
    _ACTIVE["snapshot"] = None
    _ACTIVE["version"] = ""


def _load_dir(version):
    """(manifest, texts) of a pack kept on the phone, checked again; raises PackError."""
    folder = _pack_dir(version)
    try:
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            manifest = json.load(f)
        texts = {}
        for path in PACK_FILES:
            with open(os.path.join(folder, flat(path)), encoding="utf-8") as f:
                texts[path] = f.read()
    except (OSError, ValueError) as e:
        raise PackError(f"The saved copy cannot be read: {e}") from e
    if not isinstance(manifest, dict) or manifest.get("version") != version:
        raise PackError("The saved copy is of another version")
    err = validate(manifest, texts)
    if err:
        raise PackError(err)
    return manifest, texts


def activate(force=False):
    """Main thread, no network, never raises. Loads the pack chosen as current (or keeps the built-in code).
    Done once per app start; ``force`` runs it again (Apply now, Go back, fall_back).
    Returns ``status()``."""
    with _LOCK:
        if _ACTIVE["done"] and not force:
            return status()
        try:
            _activate()
        except BaseException as e:      # whatever happens the browser must still open (built-in code)
            try:
                deactivate()
            except BaseException:
                pass
            _ACTIVE["error"] = f"{e.__class__.__name__}: {e}"[:300]
        _ACTIVE["done"] = True
        return status()


def _activate():
    st = load_state()
    deactivate()
    _ACTIVE["error"] = ""
    if st["pending"]:
        # the last start tried this version and never got the browser screen built
        _block(st, st["pending"], "the browser did not open with it")
        if st["current"] == st["pending"]:
            st["current"] = ""
        st["previous"] = [v for v in st["previous"] if v != st["pending"]]
        st["pending"] = ""
    candidates = [v for v in [st["current"]] + st["previous"] if v and v not in st["blocked"]]
    chosen = ""
    for version in candidates:
        try:
            _manifest, texts = _load_dir(version)
            _install(version, texts)
            chosen = version
            break
        except BaseException as e:
            _block(st, version, str(e) or e.__class__.__name__)
    if chosen:
        st["previous"] = [v for v in candidates if v != chosen and v not in st["blocked"]][:KEEP_OLD]
        st["current"] = chosen
        st["pending"] = chosen
    else:
        st["current"] = ""
        st["previous"] = []
    save_state(st)
    _prune(st)


def confirm():
    """The browser screen was built with the running code: it is good (clears the pending mark)."""
    with _LOCK:
        st = load_state()
        if st["pending"]:
            st["pending"] = ""
            save_state(st)


def fall_back(reason=""):
    """Building the browser screen failed with a pack running: block that version and switch to the previous
    good one (or the built-in code). False when the built-in code was already running."""
    with _LOCK:
        version = _ACTIVE["version"]
        if not version:
            return False
        st = load_state()
        _block(st, version, (reason or "the browser failed to open")[:200])
        if st["current"] == version:
            st["current"] = ""
        st["previous"] = [v for v in st["previous"] if v != version]
        st["pending"] = ""
        save_state(st)
        activate(force=True)
        return True


# -- choices of the user --------------------------------------------------------------------------------------
def set_auto(on):
    with _LOCK:
        st = load_state()
        st["auto"] = bool(on)
        save_state(st)


def go_back():
    """The previous good version becomes the current one (the one left is blocked). False when there is none."""
    with _LOCK:
        st = load_state()
        older = [v for v in st["previous"] if v not in st["blocked"]]
        if not older:
            return False
        _block(st, st["current"])
        st["current"] = older[0]
        st["previous"] = older[1:]
        st["pending"] = ""
        save_state(st)
        return True


def use_builtin():
    """Back to the code that is inside the APK. The online version in use is blocked so the automatic check does
    not bring it back (Check for update does, on purpose)."""
    with _LOCK:
        st = load_state()
        _block(st, st["current"])
        st["current"] = ""
        st["previous"] = []
        st["pending"] = ""
        save_state(st)


def status():
    st = load_state()
    return {"source": "pack" if _ACTIVE["version"] else "builtin", "version": _ACTIVE["version"],
            "current": st["current"], "previous": list(st["previous"]), "blocked": list(st["blocked"]),
            "auto": st["auto"], "last_check": st["last_check"],
            "last_error": st["last_error"] or _ACTIVE["error"],
            "waiting": st["current"] != _ACTIVE["version"]}


# -- downloading ----------------------------------------------------------------------------------------------
def _fetch(rel):
    from api.github.remote_config import CONFIG_BRANCH
    from core import plugin_loader
    return plugin_loader._fetch_remote(f"{REMOTE_FOLDER}/{rel}", CONFIG_BRANCH)


def _is_missing(e):
    return getattr(getattr(e, "response", None), "status_code", None) == 404


def check_update(force=False):
    """Network step (background thread). Downloads and checks the published pack and, when it is new and fine,
    saves it as the current one (``activate(force=True)`` or the next start loads it).
    Returns {"result": "none" | "same" | "blocked" | "refused" | "new" | "error", "version": str, "message": str}."""
    def done(result, version="", message=""):
        with _LOCK:
            st = load_state()
            st["last_check"] = time.time()
            if result in ("refused", "error"):
                st["last_error"] = (f"{version}: " if version else "") + message[:250]
            elif result in ("new", "same"):
                st["last_error"] = ""
            save_state(st)
        return {"result": result, "version": version, "message": message}

    try:
        try:
            manifest = json.loads(_fetch("manifest.json"))
        except Exception as e:
            if _is_missing(e):
                return done("none", message="No online browser version is published yet")
            raise
        err = check_manifest(manifest)
        version = manifest.get("version") if isinstance(manifest, dict) else ""
        if err:
            return done("refused", version if isinstance(version, str) else "", err)
        with _LOCK:
            st = load_state()
        if version == st["current"]:
            return done("same", version, "Already up to date")
        if version in st["blocked"] and not force:
            return done("blocked", version, "This version was blocked earlier")
        texts = {path: _fetch(flat(path)) for path in PACK_FILES}
        err = validate(manifest, texts)
        if err:
            return done("refused", version, err)
        folder = _pack_dir(version)
        tmp = folder + ".tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp, exist_ok=True)
        for path, text in texts.items():
            with open(os.path.join(tmp, flat(path)), "w", encoding="utf-8", newline="") as f:
                f.write(text)
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        shutil.rmtree(folder, ignore_errors=True)
        os.replace(tmp, folder)
        with _LOCK:
            st = load_state()
            if st["current"] and st["current"] != version:
                st["previous"] = [st["current"]] + [v for v in st["previous"] if v != st["current"]]
            st["previous"] = [v for v in st["previous"] if v != version][:KEEP_OLD]
            st["blocked"] = [v for v in st["blocked"] if v != version]
            st["current"] = version
            st["pending"] = ""
            save_state(st)
            _prune(st)
        return done("new", version, "New version downloaded")
    except Exception as e:
        text = str(e).strip().splitlines()[0][:120] if str(e).strip() else e.__class__.__name__
        return done("error", message=text)


def start_background_check():
    """The silent check when the browser opens (at most every CHECK_EVERY seconds, only when it is switched on)."""
    st = load_state()
    if not st["auto"] or time.time() - st["last_check"] < CHECK_EVERY:
        return False
    threading.Thread(target=lambda: _quiet(check_update), daemon=True).start()
    return True


def _quiet(fn):
    try:
        fn()
    except Exception:
        traceback.print_exc()
