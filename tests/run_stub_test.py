"""Runs the Lab code against a fake Kivy/app so logic bugs show up before a build."""
import json, os, shutil, sys, tempfile, threading, time, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp()

def mod(name, **attrs):
    m = types.ModuleType(name); m.__dict__.update(attrs); sys.modules[name] = m; return m

# ---- fake kivy ----
class Widget:
    def __init__(self, **kw):
        self.text = kw.pop("text", ""); self.children = []; self._b = {}
        self.__dict__.update(kw)
    def bind(self, **kw): self._b.update(kw)
    def dispatch(self, ev): self._b[ev](self)
    def add_widget(self, w): self.children.append(w)
class Button(Widget): pass
class Label(Widget): pass
class TextInput(Widget): pass
class BoxLayout(Widget): pass
class _Ev:
    def __init__(s): s.cancelled = False
    def cancel(s): s.cancelled = True
class _Clock:
    def schedule_once(self, fn, t=0): return _Ev()
    def schedule_interval(self, fn, t): return _Ev()
class _Clip:
    v = ""
    def copy(self, t): self.v = t
    def paste(self): return self.v
mod("kivy"); mod("kivy.clock", Clock=_Clock()); mod("kivy.core"); mod("kivy.core.clipboard", Clipboard=_Clip())
mod("kivy.metrics", dp=lambda x: x); mod("kivy.uix")
mod("kivy.uix.boxlayout", BoxLayout=BoxLayout); mod("kivy.uix.button", Button=Button)
mod("kivy.uix.label", Label=Label); mod("kivy.uix.textinput", TextInput=TextInput)

# ---- fake app modules ----
class _Err(Exception):
    def __init__(s, msg, code=None):
        super().__init__(msg); s.response = types.SimpleNamespace(status_code=code) if code else None
REMOTE = {}            # path -> text ; the fake "config" branch
STATE = {"online": True}
def fake_request(method, url, **kw):
    if not STATE["online"]: raise _Err("network down")
    path = url.split("/contents/")[1]
    if path not in REMOTE: raise _Err("404", 404)
    return types.SimpleNamespace(content=REMOTE[path].encode())
mod("api"); mod("api.github"); mod("api.github.client", request=fake_request)
mod("api.github.auth", auth_headers=lambda: {"Authorization": "token x"})
mod("api.github.remote_config", CONFIG_BRANCH="config")
mod("core.config", API_BASE="https://api.github.com/repos/o/r", APP_VERSION="t", REQUEST_TIMEOUT=5,
    SETTINGS_STORE_FILE=os.path.join(TMP, "s.json"))
mod("core.async_utils", run_in_background=lambda f, *a, **k: (lambda t: (t.start(), t)[1])(threading.Thread(target=f, args=a, kwargs=k, daemon=True)))
mod("screens"); sys.modules["screens"].__path__ = [os.path.join(ROOT, "screens")]
def wrapped_label(t, height=None, halign="left", valign="top"): return Label(text=t)
mod("screens.common", BTN_H=46, GAP=10, content_width=lambda: 400, wrapped_label_height=lambda *a, **k: 40,
    wrapped_label=wrapped_label, paste_row=lambda f, append=False: Label(text="paste"),
    back_button=lambda nav, text="Back", to=None: (lambda b: (b.bind(on_press=lambda i: to()), b)[1])(Button(text=text)))
sys.modules["screens"].common = sys.modules["screens.common"]
mod("services"); mod("services.notify_service", notify=lambda t, m: None)
# make `core` a real package pointing at the repo folder (plus the stubs above)
import importlib
core_pkg = types.ModuleType("core"); core_pkg.__path__ = [os.path.join(ROOT, "core")]
for n in ("core.config", "core.async_utils"): setattr(core_pkg, n.split(".")[1], sys.modules[n])
sys.modules["core"] = core_pkg
sys.path.insert(0, ROOT)

# ---- fake navigator ----
class Nav:
    def __init__(s): s.content = []; s.queue = []; s.status = None; s.remembered = None; s.where = "start"
    def clear(s): s.content = []
    def _content_widgets(s): return list(s.content)
    def add(s, w): s.content.append(w)
    def remember(s, f): s.remembered = f
    def set_status_label(s, l): s.status = l
    def set_status(s, t): s.queue.append(lambda: setattr(s.status, "text", t)) if s.status else None
    def schedule(s, f): s.queue.append(f)
    def show_home(s): s.clear(); s.where = "home"
    def show_dynamic_actions(s): s.clear(); s.where = "dynamic"
    def pump(s, wait=2.0):
        end = time.time() + wait
        while time.time() < end:
            if s.queue:
                f = s.queue.pop(0); f(); end = time.time() + 0.2
            else: time.sleep(0.01)
    def buttons(s): return [w for w in s.content if isinstance(w, Button)]
    def press(s, text):
        for b in s.buttons():
            if b.text == text: b.dispatch("on_press"); return
        raise AssertionError(f"no button {text!r}; have {[b.text for b in s.buttons()]}")
    def phone_back(s):
        back = [b for b in s.buttons() if b.text.startswith("Back")]; back[-1].dispatch("on_press")
    def texts(s): return [w.text for w in s.content]

def ok(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond: ok.failed = True
ok.failed = False

from core import plugin_loader as L
from screens import lab, plugin_runner

# ---------- loader ----------
for f in ("index.json", "hello.py"): REMOTE["lab/" + f] = open(os.path.join(ROOT, "lab_examples", f)).read()
idx = L.load_index("lab")
ok(idx["origin"] == "remote" and idx["plugins"][0]["id"] == "hello", "index loads from the lab folder")
bundle = L.fetch_bundle("lab", idx["plugins"][0]); mod_ = L.build_module(bundle)
ok(callable(mod_.build) and "labx.plugin_hello" in sys.modules, "plugin module builds and is registered")
STATE["online"] = False
idx2 = L.load_index("lab"); ok(idx2["origin"] == "cache", "offline -> saved copy is used")
STATE["online"] = True
REMOTE.pop("lab/index.json")
try: L.load_index("lab"); ok(False, "deleted file must raise")
except L.PluginError as e: ok("Not found" in str(e), "file removed on GitHub is an error, not a stale cache hit")
REMOTE["lab/bad.py"] = "def build(host:\n"
try: L.build_module(L.fetch_bundle("lab", {"id": "bad", "file": "bad.py"})); ok(False, "syntax error must raise")
except L.PluginError as e: ok("Syntax error" in str(e), "syntax error reported")
REMOTE["lab/nob.py"] = "x = 1\n"
try: L.build_module(L.fetch_bundle("lab", {"id": "nob", "file": "nob.py"})); ok(False, "missing build must raise")
except L.PluginError as e: ok("build(host)" in str(e), "missing build() reported")
REMOTE["lab/boom.py"] = "raise RuntimeError('boom at import')\n"
try: L.build_module(L.fetch_bundle("lab", {"id": "boom", "file": "boom.py"})); ok(False, "import error must raise")
except L.PluginError as e: ok("boom" in str(e) and "boom.py" in e.detail, "import-time error has a traceback with plugin file name")
try: L.fetch_bundle("lab", {"id": "n", "title": "N", "file": "x.py", "min_host": 99}); ok(False, "min_host")
except L.PluginError as e: ok("newer version" in str(e), "min_host too high is refused")
try: L.read_text("lab", "../secret"); ok(False, "traversal")
except L.PluginError: ok(True, "path traversal refused")
REMOTE["lab/lib/helper.py"] = "VALUE = 41\n"
REMOTE["lab/useh.py"] = "from labx import helper\ndef build(host):\n    host.title(str(helper.VALUE + 1))\n"
m2 = L.build_module(L.fetch_bundle("lab", {"id": "useh", "file": "useh.py", "modules": ["lib/helper.py"]}))
ok(sys.modules["labx.helper"].VALUE == 41, "helper module importable as labx.helper")

# ---------- Lab + runner + Host ----------
REMOTE["lab/index.json"] = open(os.path.join(ROOT, "cfg/lab/index.json")).read()
nav = Nav(); lab.show(nav); nav.pump()
ok("Hello Lab (example)" in nav.texts(), "Lab list shows the plugin")
nav.press("Hello Lab (example)"); nav.pump()
ok("Sub-menu" in nav.texts() and "Show log" in nav.texts(), "plugin screen is drawn")
nav.press("Sub-menu"); ok("Go deeper" in nav.texts(), "sub-menu opens")
nav.press("Go deeper"); ok("Deeper" in nav.texts(), "second level opens")
nav.phone_back(); ok("Go deeper" in nav.texts(), "phone Back goes up one level")
nav.press("Back to the first screen"); ok("Sub-menu" in nav.texts(), "home() returns to the first screen")
nav.press("Input and choice")
nav.press("Use these"); nav.pump(); ok(any("Normal" in (t or "") for t in nav.texts()) or nav.status.text.endswith("Normal"), "choice default value used")
nav.phone_back(); nav.press("Saved counter"); nav.pump(); ok("0 times" in nav.status.text, "store starts at 0")
nav.phone_back(); nav.press("Saved counter"); nav.pump(); ok("1 times" in nav.status.text, "store keeps the value")
nav.phone_back(); nav.press("Ask GitHub for a quote (background HTTP)")
nav.pump(3); ok(True, "background HTTP screen ran without crashing")
nav.phone_back(); nav.phone_back(); ok(nav.content and any(b.text.startswith("Back") for b in nav.buttons()), "Back from plugin returns to the Lab list")

# error inside a button callback -> error screen, app keeps working
REMOTE["lab/index.json"] = json.dumps({"plugins": [{"id": "boom2", "title": "Boom", "file": "boom2.py"}]})
REMOTE["lab/boom2.py"] = "def build(host):\n    host.button('Crash', lambda: 1/0)\n    host.back_button()\n"
nav = Nav(); lab.show(nav); nav.pump(); nav.press("Boom"); nav.pump(); nav.press("Crash")
ok("Copy error" in nav.texts() and "Reload plugin" in nav.texts(), "callback crash -> error screen")
ok(any("ZeroDivisionError" in (t or "") for t in nav.texts()), "error screen shows the traceback")
nav.press("Copy error"); ok("ZeroDivisionError" in sys.modules["kivy.core.clipboard"].Clipboard.v, "Copy error fills the clipboard")
nav.phone_back(); nav.pump(); ok(any(b.text == "Boom" for b in nav.buttons()), "Back from error screen -> Lab list")

# stale background result is dropped after the user leaves
REMOTE["lab/index.json"] = json.dumps({"plugins": [{"id": "slow", "title": "Slow", "file": "slow.py"}]})
REMOTE["lab/slow.py"] = ("import time\nHIT = []\ndef build(host):\n    host.status()\n"
    "    host.background(lambda: time.sleep(0.3) or 'late', done=lambda r, e: HIT.append(r))\n"
    "    host.back_button()\n")
nav = Nav(); lab.show(nav); nav.pump(); nav.press("Slow"); nav.pump(0.1); nav.phone_back(); nav.pump(1)
ok(sys.modules["labx.plugin_slow"].HIT == [], "background result after leaving the screen is ignored")

# slow download must not draw over another screen
nav = Nav(); lab.show(nav); nav.pump(); nav.show_home(); nav.pump(0.3)
ok(nav.where == "home" and nav.content == [], "late index result does not draw over the home screen")

# Download Anything hook
REMOTE["plugins/hello.py"] = open(os.path.join(ROOT, "cfg/lab/hello.py")).read()
nav = Nav(); plugin_runner.open_from_action(nav, {"id": "h", "title": "Hello", "plugin": "hello", "source": "config"}); nav.pump()
ok("Sub-menu" in nav.texts(), "action with \"plugin\" opens from the config folder")
nav.phone_back(); ok(nav.where == "dynamic", "Back leaves to Download Anything")
shutil.rmtree(TMP, ignore_errors=True)
print("\nALL PASSED" if not ok.failed else "\nSOME FAILED"); sys.exit(1 if ok.failed else 0)
