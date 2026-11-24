"""Manual tool picker for a link shared into the app: shown when the link is
not obviously YouTube and no tool's ``domains`` matched it. Lists every tool
the app has (built-in screens + the remote-config actions + the Lab tools);
tapping one opens it with the link already filled in.

The Lab tools come from ``lab/index.json`` (branch ``lab``). They are loaded in the
background, so the rest of the list is there at once. When the Lab is removed from the
final build (screens/lab.py deleted) this section simply does not appear.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Link received - loading tools...", size_hint_y=None, height=60))
    nav.add(common.back_button(nav))


def build(nav, url, actions):
    nav.clear()
    nav.add(Label(text="Link received - choose a tool", size_hint_y=None, height=44))
    nav.add(common.wrapped_label(url))

    youtube_btn = Button(text="YouTube Download", size_hint_y=None, height=52)
    youtube_btn.bind(on_press=lambda i: nav.show_youtube_download(video_url=url))
    nav.add(youtube_btn)

    upload_btn = Button(text="Upload a file (any link)", size_hint_y=None, height=52)
    upload_btn.bind(on_press=lambda i: nav.show_upload_screen(url))
    nav.add(upload_btn)

    if str(url).lower().startswith(("http://", "https://")):
        browser_btn = Button(text="Open in the Browser", size_hint_y=None, height=52)
        browser_btn.bind(on_press=lambda i: _open_in_browser(nav, url))
        nav.add(browser_btn)

    for action in actions or []:
        btn = Button(text=action.get("title", action.get("id", "?")),
                     size_hint_y=None, height=52)
        btn.bind(on_press=lambda i, a=action: nav.show_action_input(a, prefill=url))
        nav.add(btn)

    lab_box = _lab_section(nav, url)

    nav.add(common.back_button(nav))
    if lab_box is not None:
        _load_lab_tools(nav, url, lab_box)


def _open_in_browser(nav, url):
    """The shared link opens in a new browser tab (the tab that was open stays as it is)."""
    try:
        from services import browser_service
        st = browser_service.state()
        if st.tabs.new(url) is not None:
            st.flush()
            nav.show_browser()
            return
    except Exception:
        pass
    nav.show_browser(url)


def _lab_section(nav, url):
    """An empty box for the Lab tools, put in the list now and filled later."""
    try:
        from screens import lab, plugin_runner  # noqa: F401  (missing = no Lab in this build)
    except Exception:
        return None
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
    box.bind(minimum_height=box.setter("height"))
    box.add_widget(Label(text="Loading Lab tools...", size_hint_y=None, height=40))
    nav.add(box)
    return box


def _load_lab_tools(nav, url, box):
    from core import plugin_loader
    from core.async_utils import run_in_background
    from screens import lab, plugin_runner

    def work():
        try:
            res = {"plugins": plugin_loader.load_index(lab.SOURCE)["plugins"]}
        except Exception as e:
            res = {"error": e}
        nav.schedule(lambda: fill(res))

    def fill(res):
        if not plugin_runner._on_screen(nav, box):
            return                                   # the user already left this screen
        box.clear_widgets()
        plugins = [e for e in res.get("plugins", []) if e.get("id") != lab.ADD_WORKFLOW_ID]
        if res.get("error") or not plugins:
            box.height = 0
            return
        box.add_widget(Label(text="Lab tools", size_hint_y=None, height=40))
        for entry in plugins:
            btn = Button(text=entry.get("title") or entry["id"], size_hint_y=None, height=52)
            btn.bind(on_press=lambda i, e=entry: plugin_runner.open_plugin(
                nav, lab.SOURCE, e, exit_to=lambda: nav.show_share_chooser(url), prefill=url))
            box.add_widget(btn)

    run_in_background(work)
