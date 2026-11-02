"""Loading plugin code (Lab tools and Download Anything plugins).

A plugin is a normal Python file with a ``build(host)`` function (see LAB.md).
Where its code comes from (``source``):

  "lab"      branch ``lab``,    folder ``lab/``      - tools being tried out
  "config"   branch ``config``, folder ``plugins/``  - finished tools, live in
                                                       Download Anything
  "bundled"  the ``plugins_bundled/`` folder inside the APK - frozen tools of
                                                       the final build

Remote files are read through the GitHub API with the app's own token (the
repo is private). The last good copy is saved on the phone, so a plugin still
opens when the network is down.

Nothing in here runs plugin code while the app starts: a plugin is only
executed when the user opens it, so a broken plugin can never stop the app
from opening.

No Kivy import. ``fetch_bundle`` uses the network (call it from a background
thread); ``build_module`` runs the plugin's code (call it on the main thread).
"""
import json
import linecache
import os
import shutil
import sys
import traceback
import types

from api.github import client
from api.github.auth import auth_headers
from api.github.remote_config import CONFIG_BRANCH, LAB_BRANCH
from core.config import API_BASE, SETTINGS_STORE_FILE

# Bump when a Host method is removed or changes meaning. A plugin can say
# "min_host": N in its index entry; an older app then refuses it politely.
HOST_API_VERSION = 1

SOURCES = ("lab", "config", "bundled")
_REMOTE_FOLDER = {"lab": "lab", "config": "plugins"}
_REMOTE_BRANCH = {"lab": LAB_BRANCH, "config": CONFIG_BRANCH}
_FETCH_TIMEOUT = 15

_PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BUNDLED_DIR = os.path.join(_PROJECT_DIR, "plugins_bundled")
_CACHE_DIR = os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "plugins_cache")


class PluginError(Exception):
    """A plugin problem the user should see. ``detail`` holds the traceback
    (or other long text) for the Copy error button."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


def _short(e) -> str:
    text = str(e).strip()
    return text.splitlines()[0][:120] if text else e.__class__.__name__


def _is_not_found(e) -> bool:
    return getattr(getattr(e, "response", None), "status_code", None) == 404


def _safe_name(text) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in str(text))


def _check(source, rel):
    if source not in SOURCES:
        raise PluginError(f"Unknown plugin source '{source}' (use lab, config or bundled).")
    parts = str(rel).replace("\\", "/").split("/")
    if not rel or str(rel).startswith("/") or ".." in parts:
        raise PluginError(f"Bad plugin file path: {rel}")


# -- reading files ----------------------------------------------------------
def _fetch_remote(path: str, branch: str = CONFIG_BRANCH) -> str:
    headers = dict(auth_headers())
    headers["Accept"] = "application/vnd.github.raw+json"
    r = client.request("GET", f"{API_BASE}/contents/{path}", params={"ref": branch},
                       headers=headers, timeout=_FETCH_TIMEOUT)
    return r.content.decode("utf-8")


def _cache_file(source, rel):
    return os.path.join(_CACHE_DIR, source, rel.replace("/", "__"))


def _write_cache(source, rel, text):
    try:
        path = _cache_file(source, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        pass  # a missing saved copy is not worth failing for


def _read_cache(source, rel):
    try:
        with open(_cache_file(source, rel), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def read_text(source, rel):
    """(text, origin) with origin "remote" | "cache" | "bundled".
    A file that is gone from GitHub (404) is an error - the saved copy is used
    only when GitHub could not be reached."""
    _check(source, rel)
    if source == "bundled":
        try:
            with open(os.path.join(_BUNDLED_DIR, rel), encoding="utf-8") as f:
                return f.read(), "bundled"
        except OSError as e:
            raise PluginError(f"Bundled plugin file not found: plugins_bundled/{rel}") from e
    path = f"{_REMOTE_FOLDER[source]}/{rel}"
    try:
        text = _fetch_remote(path, _REMOTE_BRANCH[source])
    except Exception as e:
        if _is_not_found(e):
            raise PluginError(f"Not found on GitHub (branch {_REMOTE_BRANCH[source]}): {path}") from e
        cached = _read_cache(source, rel)
        if cached is None:
            raise PluginError(f"Could not load {path}: {_short(e)}") from e
        return cached, "cache"
    _write_cache(source, rel, text)
    return text, "remote"


def load_index(source="lab") -> dict:
    """{"plugins": [entry, ...], "origin": ...}; an entry is
    {"id", "title", "file", "modules"?, "description"?, "min_host"?, "enabled"?}."""
    text, origin = read_text(source, "index.json")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise PluginError(f"index.json is not valid JSON: {_short(e)}") from e
    plugins = data.get("plugins") if isinstance(data, dict) else data
    if not isinstance(plugins, list):
        raise PluginError("index.json has no \"plugins\" list.")
    plugins = [p for p in plugins
               if isinstance(p, dict) and p.get("id") and p.get("file") and p.get("enabled", True)]
    return {"plugins": plugins, "origin": origin}


def entry_from_action(action: dict) -> dict:
    """The plugin entry for a Download Anything action that has "plugin": "<id>"."""
    plugin_id = action["plugin"]
    return {
        "id": plugin_id,
        "title": action.get("title") or plugin_id,
        "file": action.get("file") or f"{plugin_id}.py",
        "modules": action.get("modules") or [],
        "min_host": action.get("min_host") or 1,
    }


def fetch_bundle(source, entry) -> dict:
    """Network step: downloads the plugin's files (helper modules first, the
    main file last). Safe to call from a background thread."""
    title = entry.get("title") or entry.get("id")
    try:
        wanted = int(entry.get("min_host") or 1)
    except (TypeError, ValueError):
        wanted = 1
    if wanted > HOST_API_VERSION:
        raise PluginError(f"'{title}' needs a newer version of the app "
                          f"(it wants plugin API {wanted}, this app has {HOST_API_VERSION}).")
    files, origins = [], set()
    for rel in list(entry.get("modules") or []) + [entry["file"]]:
        text, origin = read_text(source, rel)
        files.append((rel, text))
        origins.add(origin)
    if "cache" in origins:
        origin = "cache"
    elif origins == {"bundled"}:
        origin = "bundled"
    else:
        origin = "remote"
    return {"source": source, "entry": entry, "files": files, "origin": origin}


# -- running the code -------------------------------------------------------
def _ensure_package():
    package = sys.modules.get("labx")
    if package is None:
        package = types.ModuleType("labx")
        package.__path__ = []
        sys.modules["labx"] = package
    return package


def _exec_module(name, text, filename):
    module = types.ModuleType(name)
    module.__file__ = filename
    # registered before running: dataclasses and typing look the module up
    sys.modules[name] = module
    # lets tracebacks show the plugin's source lines
    linecache.cache[filename] = (len(text), None, text.splitlines(True), filename)
    try:
        exec(compile(text, filename, "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def build_module(bundle):
    """Main-thread step: runs the downloaded code and returns the plugin
    module. Helper modules are importable as ``labx.<file name>``."""
    source, entry = bundle["source"], bundle["entry"]
    package = _ensure_package()
    try:
        *helpers, (main_rel, main_text) = bundle["files"]
        for rel, text in helpers:
            name = _safe_name(os.path.splitext(os.path.basename(rel))[0])
            setattr(package, name, _exec_module(f"labx.{name}", text, f"<plugin {source}/{rel}>"))
        module = _exec_module(f"labx.plugin_{_safe_name(entry['id'])}", main_text,
                              f"<plugin {source}/{main_rel}>")
    except SyntaxError as e:
        raise PluginError(f"Syntax error, line {e.lineno}: {e.msg}", detail=traceback.format_exc()) from e
    except Exception as e:
        raise PluginError(f"The plugin failed while loading: {_short(e)}",
                          detail=traceback.format_exc()) from e
    if not callable(getattr(module, "build", None)):
        raise PluginError("The plugin has no build(host) function.")
    return module


def clear_cache():
    shutil.rmtree(_CACHE_DIR, ignore_errors=True)
