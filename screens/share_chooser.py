"""Manual tool picker for a link shared into the app: shown when the link is
not obviously YouTube and no tool's ``domains`` matched it. Lists every tool
the app has (built-in screens + the remote-config actions + the Lab tools);
tapping one opens it with the link already filled in. The favorites chosen in Settings > App tools >
Share favorites (screens/share_favorites.py) are shown first, including quick buttons inside Lab tools.

The Lab tools come from ``lab/index.json`` (branch ``lab``). They are loaded in the
background, so the rest of the list is there at once. When the Lab is removed from the
final build (screens/lab.py deleted) this section simply does not appear.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common


def _split_hint(text):
    """(links without the ``#quality=N`` line, N or \"\"): the quality picked in the browser."""
    keep, q = [], ""
    for ln in str(text).splitlines():
        s = ln.strip()
        if s.startswith("#quality=") and s[9:].isdigit():
            q = s[9:]
        else:
            keep.append(ln)
    return "\n".join(keep), q


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Link received - loading tools...", size_hint_y=None, height=60))
    nav.add(common.back_button(nav))


def build(nav, url, actions):
    url, quality = _split_hint(url)
    nav.clear()
    nav.add(Label(text="Link received - choose a tool", size_hint_y=None, height=44))
    nav.add(common.wrapped_label(url))

    fav_box, fav_ids = None, _fav_ids()
    if fav_ids:
        fav_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
        fav_box.bind(minimum_height=fav_box.setter("height"))
        nav.add(fav_box)
        _fill_favs(nav, url, actions, quality, fav_box, fav_ids, None)

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
        _load_lab_tools(nav, url, lab_box, quality, (fav_box, fav_ids, actions))


def _fav_ids():
    try:
        from api import share_favorites_prefs
        return share_favorites_prefs.get_ids()
    except Exception:
        return []


def _open_lab(nav, entry, qid, url, quality):
    """Open a Lab tool with the link filled in; qid = a quick button of that tool to run at once."""
    from screens import lab, plugin_runner
    back_text = url + ("\n#quality=" + quality if quality else "")
    prefill = back_text if (quality and entry.get("id") == "link_lab") else url
    if qid:
        prefill += "\n#quick=" + qid
    plugin_runner.open_plugin(nav, lab.SOURCE, entry, exit_to=lambda: nav.show_share_chooser(back_text),
                              prefill=prefill)


def _fill_favs(nav, url, actions, quality, box, fav_ids, plugins):
    """The favorites chosen in Settings > App tools > Share favorites, in the saved order.
    Lab favorites show up when the Lab list is loaded (plugins is None before that)."""
    builtin = {"builtin:youtube": ("YouTube Download", lambda: nav.show_youtube_download(video_url=url)),
               "builtin:upload": ("Upload a file (any link)", lambda: nav.show_upload_screen(url))}
    if str(url).lower().startswith(("http://", "https://")):
        builtin["builtin:browser"] = ("Open in the Browser", lambda: _open_in_browser(nav, url))
    by_action = {"action:" + str(a.get("id")): a for a in actions or []}
    by_plugin = {e.get("id"): e for e in plugins or []}
    rows = []
    for fid in fav_ids:
        if fid in builtin:
            title, fn = builtin[fid]
        elif fid in by_action:
            a = by_action[fid]
            title, fn = a.get("title", a.get("id", "?")), (lambda a=a: nav.show_action_input(a, prefill=url))
        elif fid.startswith("lab:"):
            parts = fid.split(":")
            e = by_plugin.get(parts[1])
            qid = parts[2] if len(parts) > 2 else ""
            if not e:
                continue
            title = e.get("title") or e["id"]
            if qid:
                title = next((q.get("title") or qid for q in e.get("quick") or [] if q.get("id") == qid), None)
                if title is None:
                    continue
            fn = (lambda e=e, q=qid: _open_lab(nav, e, q, url, quality))
        else:
            continue
        rows.append((title, fn))
    box.clear_widgets()
    if not rows:
        return
    box.add_widget(Label(text="Favorites", size_hint_y=None, height=40))
    for title, fn in rows:
        btn = Button(text=title, size_hint_y=None, height=52)
        btn.bind(on_press=lambda i, f=fn: f())
        box.add_widget(btn)


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


def _load_lab_tools(nav, url, box, quality="", fav=None):
    back_text = url + ("\n#quality=" + quality if quality else "")
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
        if fav and fav[0] is not None:
            _fill_favs(nav, url, fav[2], quality, fav[0], fav[1], res.get("plugins", []))
        box.clear_widgets()
        plugins = [e for e in res.get("plugins", []) if e.get("id") != lab.ADD_WORKFLOW_ID]
        if res.get("error") or not plugins:
            box.height = 0
            return
        box.add_widget(Label(text="Lab tools", size_hint_y=None, height=40))
        for entry in plugins:
            btn = Button(text=entry.get("title") or entry["id"], size_hint_y=None, height=52)
            btn.bind(on_press=lambda i, e=entry: plugin_runner.open_plugin(
                nav, lab.SOURCE, e, exit_to=lambda: nav.show_share_chooser(back_text),
                prefill=back_text if (quality and e.get("id") == "link_lab") else url))
            box.add_widget(btn)

    run_in_background(work)
