"""Settings > App tools > Browser online update: which browser code is running (built-in or an online
version), Check for update, Apply now, Go back, Use the built-in version, automatic check on or off.

This screen is not part of the pack (it must stay reachable when a pack misbehaves). Logic: core/browser_pack.py.
"""
import threading
import time

from kivy.uix.button import Button
from kivy.uix.label import Label

from core import browser_pack
from screens.common import back_button, wrapped_label


def _back(nav):
    nav.show_settings_section("tools")


def _button(text, action):
    btn = Button(text=text, size_hint_y=None, height=48)
    btn.bind(on_press=lambda i: action())
    return btn


def _ago(ts):
    if not ts:
        return ""
    minutes = int((time.time() - ts) / 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def build(nav, note=""):
    nav.clear()
    st = browser_pack.status()
    nav.add(Label(text="Browser online update", size_hint_y=None, height=44))
    if st["source"] == "pack":
        nav.add(wrapped_label(f"Running: online version {st['version']}"))
    else:
        nav.add(wrapped_label("Running: built-in version"))
    if st["waiting"]:
        nav.add(wrapped_label(f"Ready: {st['current'] or 'built-in version'} (tap Apply now)"))
    if st["last_check"]:
        nav.add(wrapped_label(f"Last check: {_ago(st['last_check'])}"))
    if st["last_error"]:
        nav.add(wrapped_label(f"Last problem: {st['last_error']}"))
    if note:
        nav.add(wrapped_label(note))

    nav.add(_button("Check for update", lambda: _check(nav)))
    if st["waiting"]:
        nav.add(_button("Apply now", lambda: _apply(nav, "Applied")))
    if st["previous"]:
        nav.add(_button("Go back to the previous version", lambda: _go_back(nav)))
    if st["source"] == "pack" or st["current"]:
        nav.add(_button("Use the built-in version", lambda: _builtin(nav)))
    nav.add(_button(f"Automatic check: {'ON' if st['auto'] else 'OFF'}", lambda: _toggle_auto(nav, st["auto"])))
    nav.add(wrapped_label(
        "The browser's Python code (tabs, lists, sort, file types, cookies, menus) can be updated from GitHub "
        "without a new APK. A downloaded version is checked first; if it fails, the built-in version is used. "
        "Changes to the native part (Java) still need a new APK."))
    nav.add(back_button(nav, to=lambda: _back(nav)))


def _check(nav):
    build(nav, note="Checking for a new version...")

    def work():
        res = browser_pack.check_update(force=True)
        nav.schedule(lambda: build(nav, note=_message(res)))

    threading.Thread(target=work, daemon=True).start()


def _message(res):
    kind, version, text = res["result"], res["version"], res["message"]
    if kind == "new":
        return f"New version downloaded: {version}"
    if kind == "same":
        return "Already up to date"
    if kind == "none":
        return "No online browser version is published yet"
    if kind == "refused":
        return f"This version was refused: {text}"
    if kind == "blocked":
        return f"This version was blocked earlier: {version}"
    return f"Could not check: {text}"


def _apply(nav, word):
    st = browser_pack.activate(force=True)
    if st["source"] == "pack":
        build(nav, note=f"{word}: online version {st['version']}")
    else:
        build(nav, note=f"{word}: built-in version")


def _go_back(nav):
    if browser_pack.go_back():
        _apply(nav, "Went back")
    else:
        build(nav, note="There is no previous version")


def _builtin(nav):
    browser_pack.use_builtin()
    _apply(nav, "Using")


def _toggle_auto(nav, on):
    browser_pack.set_auto(not on)
    build(nav)
