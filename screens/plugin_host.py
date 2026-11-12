"""The ``host`` object every plugin receives (see LAB.md for the full guide).

A plugin is a Python file with ``def build(host)``. Everything it needs from
the app goes through ``host``; the plugin may also import anything that is
inside the APK (kivy, requests, yt_dlp, plyer, jnius ...).

Screens and menus
    host.show(fn, *args)     open screen ``fn(host, *args)``; Back returns here
    host.replace(fn, *args)  same, but without adding a Back step
    host.back() / host.home() / host.exit()
    host.title(text)  host.text(text)  host.button(text, fn)  host.row([(text, fn)])
    host.input(hint, text, multiline)  host.choice(options, default, on_change)
    host.dropdown(options, default, on_change, title)   (a box that opens a popup window)
    host.status()  host.set_status(text)  host.back_button(text="Back")
    host.working(msg)  host.result(msg, link=None, links=None)  host.add(widget)

Work and network
    host.background(fn, *args, done=cb)   fn runs in a thread, cb(result, error) on the UI thread
    host.every(seconds, fn)  host.after(seconds, fn)  (cancelled when the screen changes)
    host.get / host.post / host.http / host.get_json   plain HTTP, never sends the GitHub token
    host.gh.dispatch / wait / cancel / release_links / request / read_file   this repo, with the token
    host.run_action(action, values)   run a workflow like a Download Anything action (job, notification, result)

Phone and data
    host.store.get/set/delete/all    saved values for this plugin
    host.log(...)  host.show_log()   plugin log (kept on the phone)
    host.copy(text) host.paste() host.open_url(url) host.share_text(text) host.notify(title, text)
    host.android()                   pyjnius handles (autoclass, cast, activity) or None
"""
import json
import os
import threading
import time
import traceback

import requests
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import plugin_loader
from core.async_utils import run_in_background
from core.config import API_BASE, APP_VERSION, REQUEST_TIMEOUT, SETTINGS_STORE_FILE
from screens import common
from screens.common import BTN_H, GAP

_DATA_DIR = os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "plugin_data")
_OFF = (1, 1, 1, 1)
_ON = (0.35, 0.85, 0.45, 1)
# One plain session for plugins: it never carries the GitHub token.
_HTTP = requests.Session()


def _file_stem(plugin_id) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(plugin_id))


class Store:
    """Saved values of one plugin (a small JSON file on the phone)."""

    def __init__(self, plugin_id):
        self._path = os.path.join(_DATA_DIR, _file_stem(plugin_id) + ".json")
        self._lock = threading.Lock()
        self._data = None

    def _load(self):
        if self._data is None:
            try:
                with open(self._path, encoding="utf-8") as f:
                    data = json.load(f)
                self._data = data if isinstance(data, dict) else {}
            except Exception:
                self._data = {}
        return self._data

    def _save(self):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            os.replace(tmp, self._path)
        except Exception:
            pass

    def get(self, key, default=None):
        with self._lock:
            return self._load().get(key, default)

    def set(self, key, value):
        with self._lock:
            self._load()[key] = value
            self._save()

    def delete(self, key):
        with self._lock:
            self._load().pop(key, None)
            self._save()

    def all(self) -> dict:
        with self._lock:
            return dict(self._load())


class _Log:
    MAX_LINES = 400

    def __init__(self, plugin_id):
        self._path = os.path.join(_DATA_DIR, _file_stem(plugin_id) + ".log")
        self._lock = threading.Lock()
        try:
            with open(self._path, encoding="utf-8") as f:
                self.lines = f.read().splitlines()[-self.MAX_LINES:]
        except Exception:
            self.lines = []

    def add(self, text):
        stamp = time.strftime("%H:%M:%S")
        with self._lock:
            new = [f"{stamp} {line}" for line in str(text).splitlines() or [""]]
            self.lines = (self.lines + new)[-self.MAX_LINES:]
            try:
                os.makedirs(_DATA_DIR, exist_ok=True)
                with open(self._path, "w", encoding="utf-8") as f:
                    f.write("\n".join(self.lines))
            except Exception:
                pass

    def text(self) -> str:
        with self._lock:
            return "\n".join(self.lines)

    def clear(self):
        with self._lock:
            self.lines = []
            try:
                os.remove(self._path)
            except OSError:
                pass


class _GitHub:
    """This repo through the GitHub API, with the app's token. Every call
    blocks: use them inside ``host.background``."""

    def __init__(self, source="config"):
        self._source = source

    def dispatch(self, workflow, inputs=None, ref=None):
        """Starts a workflow file (e.g. "mornye-download.yml") and returns its run id.
        A Lab tool runs the workflow from the ``lab`` branch (the file only has
        to be registered on main, see LAB.md); other plugins use the app's branch."""
        from api.github import workflows
        from api.github.remote_config import LAB_BRANCH
        if ref is None and self._source == "lab":
            ref = LAB_BRANCH
        return workflows.dispatch_and_find_run(workflow, dict(inputs or {}), ref=ref)

    def wait(self, run_id, on_status=None, stop_event=None):
        from api.github import workflows
        return workflows.wait_for_run(run_id, on_status=on_status, stop_event=stop_event)

    def cancel(self, run_id):
        from api.github import workflows
        return workflows.cancel_run(run_id)

    def release_links(self, run_id, attempts=10, delay=2):
        from api.github import releases
        return releases.get_release_links(run_id, attempts=attempts, delay=delay)

    def release_result(self, run_id):
        from api.github import releases
        return releases.get_release_result(run_id)

    def request(self, method, path, **kwargs):
        """``path`` is relative to this repo ("/actions/runs") or a full
        https://api.github.com/ URL. The token is never sent anywhere else."""
        from api.github import client
        if path.startswith("https://"):
            if not path.startswith("https://api.github.com/"):
                raise ValueError("Only api.github.com may be called with the GitHub token.")
            url = path
        else:
            url = API_BASE + (path if path.startswith("/") else "/" + path)
        return client.request(method, url, **kwargs)

    def read_file(self, path, ref=None):
        """Text of a file in this repo (a Lab tool reads the ``lab`` branch by
        default, other plugins the ``config`` branch)."""
        from api.github.auth import auth_headers
        if ref is None:
            ref = "lab" if self._source == "lab" else "config"
        headers = dict(auth_headers())
        headers["Accept"] = "application/vnd.github.raw+json"
        r = self.request("GET", f"/contents/{path}", params={"ref": ref}, headers=headers)
        return r.content.decode("utf-8")


class Choice:
    """A group of option buttons. ``.value`` is the value of the picked one."""

    def __init__(self, host, pairs, default, on_change):
        self._host = host
        self.pairs = pairs
        self.value = default
        self._on_change = on_change
        self._buttons = []
        self._build()

    def _build(self):
        nav = self._host.nav
        labels = [str(label) for label, _ in self.pairs]
        longest = max((len(t) for t in labels), default=0)
        per_row = 3 if longest <= 10 else (2 if longest <= 20 else 1)
        width = (common.content_width() - GAP * (per_row - 1)) / per_row
        for start in range(0, len(labels), per_row):
            chunk = labels[start:start + per_row]
            height = max([BTN_H] + [
                common.wrapped_label_height(t, extra_padding=dp(18), width=width - dp(16)) for t in chunk])
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=GAP)
            for offset, label in enumerate(chunk):
                index = start + offset
                btn = Button(text=label, halign="center", valign="middle")
                btn.text_size = (width - dp(16), None)
                btn.bind(on_press=lambda inst, i=index: self.select(self.pairs[i][1], notify=True))
                row.add_widget(btn)
                self._buttons.append(btn)
            nav.add(row)
        self._paint()

    def _paint(self):
        for btn, (_, value) in zip(self._buttons, self.pairs):
            on = value == self.value
            btn.bold = on
            btn.background_color = _ON if on else _OFF

    def select(self, value, notify=False):
        self.value = value
        self._paint()
        if notify and self._on_change is not None:
            self._host._safe(self._on_change, value)


class Dropdown:
    """A box with the picked option; a tap opens a window with every option.
    Same API as Choice: ``.value``, ``.select(value, notify)``."""

    def __init__(self, host, pairs, default, on_change, title=""):
        self._host = host
        self.pairs = pairs
        self.value = default
        self._on_change = on_change
        self._title = title
        self._btn = Button(text="", size_hint_y=None, height=BTN_H, halign="center", valign="middle")
        self._btn.bind(on_press=lambda inst: self._open())
        host.nav.add(self._btn)
        self._paint()

    def _label_of(self, value):
        for label, val in self.pairs:
            if val == value:
                return str(label)
        return str(value)

    def _paint(self):
        self._btn.text = "%s   \u25be" % self._label_of(self.value)

    def _open(self):
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView
        box = BoxLayout(orientation="vertical", spacing=GAP, size_hint_y=None)
        box.bind(minimum_height=box.setter("height"))
        popup = Popup(title=self._title or "Choose", size_hint=(0.9, 0.7))
        for label, value in self.pairs:
            btn = Button(text=str(label), size_hint_y=None, height=BTN_H)
            if value == self.value:
                btn.background_color = _ON
            btn.bind(on_press=lambda inst, v=value: self._pick(v, popup))
            box.add_widget(btn)
        scroll = ScrollView()
        scroll.add_widget(box)
        popup.content = scroll
        popup.open()

    def _pick(self, value, popup):
        popup.dismiss()
        self.select(value, notify=True)

    def select(self, value, notify=False):
        self.value = value
        self._paint()
        if notify and self._on_change is not None:
            self._host._safe(self._on_change, value)


class Host:
    api_version = plugin_loader.HOST_API_VERSION

    def __init__(self, nav, entry, source, exit_to, reload, origin="remote", prefill=None):
        self.nav = nav
        self.id = entry["id"]
        self.title_text = entry.get("title") or entry["id"]
        self.source = source          # "lab" | "config" | "bundled"
        self.origin = origin          # "remote" | "cache" | "bundled"
        self.prefill = prefill        # text shared into the app for this plugin, if any
        self.app_version = APP_VERSION
        self.data_dir = _DATA_DIR
        self.store = Store(self.id)
        self.gh = _GitHub(source)
        self._log = _Log(self.id)
        self._exit_to = exit_to
        self._reload = reload
        self._stack = []
        self._current = None
        self._epoch = 0               # changes with every screen, to drop stale callbacks
        self._timers = []

    # -- screens -------------------------------------------------------------
    def start(self, module):
        self.log(f"opened (source={self.source}, from {self.origin})")
        self._stack = []
        self.replace(module.build)

    def show(self, fn, *args):
        if self._current is not None:
            self._stack.append(self._current)
        self.replace(fn, *args)

    def replace(self, fn, *args):
        self._current = (fn, args)
        self._render()

    def back(self):
        if self._stack:
            self._current = self._stack.pop()
            self._render()
        else:
            self.exit()

    def home(self):
        if self._stack:
            self._current = self._stack[0]
            self._stack = []
            self._render()

    def exit(self):
        self._cancel_timers()
        self._epoch += 1
        self._exit_to()

    def _render(self):
        self._epoch += 1
        self._cancel_timers()
        self.nav.clear()
        self.nav.remember(self._render_current)
        fn, args = self._current
        try:
            fn(self, *args)
        except Exception as e:
            self._fail(e)

    def _render_current(self):
        self._render()

    def _safe(self, fn, *args):
        try:
            return fn(*args)
        except Exception as e:
            self._fail(e)

    def _fail(self, exc):
        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log("ERROR\n" + text)
        self._epoch += 1
        self._cancel_timers()
        nav = self.nav
        nav.clear()
        nav.remember(self._render_current)
        nav.add(Label(text=f"{self.title_text}: error", size_hint_y=None, height=48))
        nav.add(common.wrapped_label(text[-1800:]))
        copy_btn = Button(text="Copy error", size_hint_y=None, height=52)
        copy_btn.bind(on_press=lambda i: (Clipboard.copy(text), nav.set_status("Copied")))
        nav.add(copy_btn)
        again = Button(text="Reload plugin", size_hint_y=None, height=52)
        again.bind(on_press=lambda i: self._reload())
        nav.add(again)
        label = Label(text="", size_hint_y=None, height=40)
        nav.add(label)
        nav.set_status_label(label)
        nav.add(common.back_button(nav, to=self.exit))

    # -- widgets -------------------------------------------------------------
    def add(self, widget):
        self.nav.add(widget)
        return widget

    def title(self, text):
        return self.add(Label(text=str(text), size_hint_y=None, height=48))

    def text(self, text, **kwargs):
        return self.add(common.wrapped_label(str(text), **kwargs))

    def button(self, text, on_press=None, height=52):
        btn = Button(text=str(text), size_hint_y=None, height=height)
        if on_press is not None:
            btn.bind(on_press=lambda inst: self._safe(on_press))
        self.nav.add(btn)
        return btn

    def row(self, items, height=BTN_H):
        """Buttons side by side: ``host.row([("Yes", fn1), ("No", fn2)])``."""
        box = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=GAP)
        buttons = []
        for label, fn in items:
            btn = Button(text=str(label))
            btn.bind(on_press=lambda inst, f=fn: self._safe(f))
            box.add_widget(btn)
            buttons.append(btn)
        self.nav.add(box)
        return buttons

    def input(self, hint="", text="", multiline=False, height=None, paste=True):
        field = TextInput(hint_text=hint, text=text, multiline=multiline, size_hint_y=None,
                          height=height or (dp(150) if multiline else 48))
        self.nav.add(field)
        if paste:
            self.nav.add(common.paste_row(field, append=multiline))
        return field

    def choice(self, options, default=None, on_change=None):
        """``options``: strings or (label, value) pairs. Returns a Choice."""
        pairs = [(o[0], o[1]) if isinstance(o, (tuple, list)) else (o, o) for o in options]
        if default is None and pairs:
            default = pairs[0][1]
        return Choice(self, pairs, default, on_change)

    def dropdown(self, options, default=None, on_change=None, title=""):
        """Like ``choice`` but a box that opens a popup window with the options."""
        pairs = [(o[0], o[1]) if isinstance(o, (tuple, list)) else (o, o) for o in options]
        if default is None and pairs:
            default = pairs[0][1]
        return Dropdown(self, pairs, default, on_change, title)

    def status(self, height=40):
        """Adds the line where ``set_status`` writes."""
        label = Label(text="", size_hint_y=None, height=height)
        self.nav.add(label)
        self.nav.set_status_label(label)
        return label

    def set_status(self, text):
        self.nav.set_status(str(text))   # safe from any thread

    def back_button(self, text="Back", to=None):
        """Keep the text starting with "Back": the phone's Back key presses it."""
        return self.add(common.back_button(self.nav, text=text, to=to or self.back))

    def working(self, message):
        self.nav.show_working(str(message))

    def result(self, message, link=None, links=None):
        self.nav.show_result(str(message), link=link, links=links)

    # -- work ----------------------------------------------------------------
    def background(self, fn, *args, done=None, same_screen=True):
        """Runs ``fn(*args)`` in a thread. ``done(result, error)`` then runs on
        the UI thread; with ``same_screen`` (default) it is skipped when the
        user has already moved to another screen."""
        epoch = self._epoch

        def work():
            result, error = None, None
            try:
                result = fn(*args)
            except Exception as e:
                error = e
                self.log("background error\n" + "".join(
                    traceback.format_exception(type(e), e, e.__traceback__)))
            if done is None:
                return

            def deliver():
                if same_screen and epoch != self._epoch:
                    return
                self._safe(done, result, error)
            self.nav.schedule(deliver)

        return run_in_background(work)

    def every(self, seconds, fn):
        event = Clock.schedule_interval(lambda dt: self._safe(fn), seconds)
        self._timers.append(event)
        return event

    def after(self, seconds, fn):
        event = Clock.schedule_once(lambda dt: self._safe(fn), seconds)
        self._timers.append(event)
        return event

    def _cancel_timers(self):
        for event in self._timers:
            try:
                event.cancel()
            except Exception:
                pass
        self._timers = []

    def run_action(self, action, values):
        """Runs a workflow the way a Download Anything button does (progress
        screen, Running jobs, notification, result). ``action`` is a config
        action dict with at least "workflow" and "workflow_inputs"."""
        from services import generic_action_service
        nav = self.nav
        job = generic_action_service.create_action_job(nav.job_manager, action, dict(values))
        nav.show_working("Starting workflow...", job=job)
        on_status, on_complete = nav._status_and_complete_callbacks(job)
        generic_action_service.run_action_job(
            nav.job_manager, job, on_status=on_status, on_complete=on_complete)
        return job

    # -- network -------------------------------------------------------------
    def http(self, method, url, **kwargs):
        kwargs.setdefault("timeout", REQUEST_TIMEOUT)
        headers = {"User-Agent": "YTBridge-Lab"}
        headers.update(kwargs.pop("headers", None) or {})
        return _HTTP.request(method, url, headers=headers, **kwargs)

    def get(self, url, **kwargs):
        return self.http("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.http("POST", url, **kwargs)

    def get_json(self, url, **kwargs):
        r = self.get(url, **kwargs)
        r.raise_for_status()
        return r.json()

    # -- phone ---------------------------------------------------------------
    def log(self, *parts):
        self._log.add(" ".join(str(p) for p in parts))

    def show_log(self):
        def screen(h):
            h.title(f"{self.title_text} - log")
            h.text(self._log.text() or "(empty)")
            h.button("Copy log", lambda: (Clipboard.copy(self._log.text()), h.set_status("Copied")))
            h.button("Clear log", lambda: (self._log.clear(), h.replace(screen)))
            h.status()
            h.back_button()
        self.show(screen)

    def copy(self, text):
        Clipboard.copy(str(text))

    def paste(self) -> str:
        return Clipboard.paste() or ""

    def notify(self, title, text):
        from services.notify_service import notify
        notify(str(title), str(text))

    def android(self):
        try:
            from jnius import autoclass, cast
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            return type("Android", (), {"autoclass": staticmethod(autoclass),
                                        "cast": staticmethod(cast), "activity": activity})()
        except Exception:
            return None

    def open_url(self, url) -> bool:
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            activity.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(str(url))))
            return True
        except Exception:
            try:
                import webbrowser
                return bool(webbrowser.open(str(url)))
            except Exception:
                return False

    def share_text(self, text) -> bool:
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            String = autoclass("java.lang.String")
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            intent = Intent()
            intent.setAction(Intent.ACTION_SEND)
            intent.setType("text/plain")
            intent.putExtra(Intent.EXTRA_TEXT, String(str(text)))
            activity.startActivity(Intent.createChooser(intent, String("Share")))
            return True
        except Exception:
            return False
