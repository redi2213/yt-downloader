"""Lab: the test area for new tools.

Lists the plugins in ``lab/index.json`` (branch ``lab``) and opens them
through screens/plugin_runner.py. To remove the Lab from the final build just
delete this file: the button on the home screen disappears with it.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import plugin_loader
from core.async_utils import run_in_background
from screens import common, plugin_runner

SOURCE = "lab"


def show(nav):
    nav.clear()
    nav.remember(lambda: show(nav))
    nav.add(Label(text="Lab - test tools", size_hint_y=None, height=48))
    marker = Label(text="Loading the tool list...", size_hint_y=None, height=40)
    nav.add(marker)
    nav.add(common.back_button(nav, to=nav.show_home))

    def work():
        try:
            res = plugin_loader.load_index(SOURCE)
        except Exception as e:
            res = {"error": e}
        nav.schedule(lambda: _render(nav, marker, res))

    run_in_background(work)


def _render(nav, marker, res):
    if not plugin_runner._on_screen(nav, marker):
        return
    nav.clear()
    nav.remember(lambda: show(nav))
    nav.add(Label(text="Lab - test tools", size_hint_y=None, height=48))

    error = res.get("error")
    if error:
        nav.add(common.wrapped_label(
            f"Could not load the tool list.\n{error}\n\n"
            "Put lab/index.json on the lab branch (see LAB.md on the lab branch)."))
    else:
        if res.get("origin") == "cache":
            nav.add(common.wrapped_label("Offline: showing the saved tool list."))
        plugins = res["plugins"]
        if not plugins:
            nav.add(common.wrapped_label("No tools yet. Add one to lab/index.json (see LAB.md on the lab branch)."))
        for entry in plugins:
            btn = Button(text=entry.get("title") or entry["id"], size_hint_y=None, height=52)
            btn.bind(on_press=lambda i, e=entry: plugin_runner.open_plugin(
                nav, SOURCE, e, exit_to=lambda: show(nav)))
            nav.add(btn)
            if entry.get("description"):
                nav.add(common.wrapped_label(str(entry["description"])))

    reload_btn = Button(text="Reload list", size_hint_y=None, height=52)
    reload_btn.bind(on_press=lambda i: show(nav))
    nav.add(reload_btn)

    clear_btn = Button(text="Forget saved copies", size_hint_y=None, height=52)
    clear_btn.bind(on_press=lambda i: (plugin_loader.clear_cache(),
                                       nav.set_status("Saved copies removed")))
    nav.add(clear_btn)

    status = Label(text="", size_hint_y=None, height=40)
    nav.add(status)
    nav.set_status_label(status)
    nav.add(common.back_button(nav, to=nav.show_home))
