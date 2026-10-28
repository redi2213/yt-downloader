"""Opens a plugin: downloads it, runs it, and shows an error screen when
something goes wrong. Used by the Lab (screens/lab.py) and by Download
Anything actions that carry ``"plugin": "<id>"`` (see LAB.md).

A plugin is only run when the user opens it, never while the app starts.
"""
import traceback

from kivy.core.clipboard import Clipboard
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import plugin_loader
from core.async_utils import run_in_background
from screens import common
from screens.plugin_host import Host


def _on_screen(nav, marker) -> bool:
    """False once the user has left the screen that showed ``marker`` - a slow
    download must not draw over whatever they opened meanwhile."""
    try:
        return marker in nav._content_widgets()
    except Exception:
        return False


def open_plugin(nav, source, entry, exit_to, prefill=None):
    title = entry.get("title") or entry.get("id")
    again = lambda: open_plugin(nav, source, entry, exit_to, prefill)

    nav.clear()
    nav.remember(again)
    marker = Label(text=f"Loading {title}...", size_hint_y=None, height=48)
    nav.add(marker)
    nav.add(common.back_button(nav, to=exit_to))

    def work():
        try:
            result = {"bundle": plugin_loader.fetch_bundle(source, entry)}
        except Exception as e:
            result = {"error": e}
        nav.schedule(lambda: _after_fetch(nav, marker, source, entry, exit_to, prefill, again, result))

    run_in_background(work)


def _after_fetch(nav, marker, source, entry, exit_to, prefill, again, result):
    if not _on_screen(nav, marker):
        return
    title = entry.get("title") or entry.get("id")
    try:
        if "error" in result:
            raise result["error"]
        bundle = result["bundle"]
        module = plugin_loader.build_module(bundle)   # plugin code runs here, on the UI thread
        host = Host(nav, entry, source, exit_to, reload=again,
                    origin=bundle["origin"], prefill=prefill)
        host.start(module)
    except Exception as e:
        show_error(nav, title, e, again, exit_to)


def open_from_action(nav, action, prefill=None, share_url=None):
    """Download Anything button with ``"plugin": "<id>"`` in config.json.
    Optional keys: "source" (config | lab | bundled, default config), "file"
    (default "<id>.py"), "modules", "min_host"."""
    source = action.get("source") or "config"
    entry = plugin_loader.entry_from_action(action)
    exit_to = nav.show_home if share_url else nav.show_dynamic_actions
    open_plugin(nav, source, entry, exit_to, prefill=prefill or share_url)


def show_error(nav, title, exc, again, exit_to):
    detail = getattr(exc, "detail", "") or "".join(
        traceback.format_exception(type(exc), exc, exc.__traceback__))
    full = f"{exc}\n\n{detail}".strip()
    nav.clear()
    nav.remember(again)
    nav.add(Label(text=f"{title}: could not start", size_hint_y=None, height=48))
    nav.add(common.wrapped_label(full[-1800:]))
    copy_btn = Button(text="Copy error", size_hint_y=None, height=52)
    copy_btn.bind(on_press=lambda i: (Clipboard.copy(full), nav.set_status("Copied")))
    nav.add(copy_btn)
    retry = Button(text="Try again", size_hint_y=None, height=52)
    retry.bind(on_press=lambda i: again())
    nav.add(retry)
    status = Label(text="", size_hint_y=None, height=40)
    nav.add(status)
    nav.set_status_label(status)
    nav.add(common.back_button(nav, to=exit_to))
