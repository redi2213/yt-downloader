"""Settings > App tools > Share favorites: pick the tools that appear at the top of the
"Link received - choose a tool" list (screens/share_chooser.py). The list holds every tool of the
app: built-in screens, the Download Anything actions, the Lab tools and the quick buttons inside
Lab tools (for example Link Lab > Get links only (this phone)).
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from api import share_favorites_prefs as prefs
from screens.common import wrapped_label

BUILTIN = [
    ("builtin:youtube", "YouTube Download"),
    ("builtin:upload", "Upload a file (any link)"),
    ("builtin:browser", "Open in the Browser"),
]


def lab_entries(plugins, skip_id=None):
    """(id, title) for every Lab tool and every quick button listed under "quick" in lab/index.json."""
    out = []
    for e in plugins or []:
        pid = e.get("id")
        if not pid or pid == skip_id:
            continue
        title = e.get("title") or pid
        out.append(("lab:" + pid, title))
        for q in e.get("quick") or []:
            if q.get("id"):
                out.append(("lab:%s:%s" % (pid, q["id"]), "%s > %s" % (title, q.get("title") or q["id"])))
    return out


def action_entries(actions):
    return [("action:" + str(a.get("id")), a.get("title") or str(a.get("id")))
            for a in actions or [] if a.get("id")]


def build(nav):
    cat = list(BUILTIN)
    state = {"query": "", "pending": 2}
    nav.add(wrapped_label("Tools you pick here appear at the top of the list when you share a link "
                          "to the app. A Lab quick button opens the tool and runs it at once."))
    info = Label(text="Loading actions and Lab tools...", size_hint_y=None, height=32)
    nav.add(info)
    search = TextInput(hint_text="Search tools", multiline=False, size_hint_y=None, height=48)
    nav.add(search)
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
    box.bind(minimum_height=box.setter("height"))
    nav.add(box)

    def title_of(item_id):
        for k, t in cat:
            if k == item_id:
                return t
        return item_id

    def small(text, fn):
        b = Button(text=text, size_hint_x=None, width=56)
        b.bind(on_press=lambda i: fn())
        return b

    def change(fn, *args):
        fn(*args)
        refresh()

    def refresh():
        box.clear_widgets()
        favs = prefs.get_ids()
        box.add_widget(Label(text="Favorites (top of the share list)", size_hint_y=None, height=36))
        if not favs:
            box.add_widget(wrapped_label("None yet. Tap a tool below to add it."))
        for item_id in favs:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=48, spacing=4)
            lbl = Label(text=title_of(item_id), halign="left", valign="middle", shorten=True)
            lbl.bind(size=lambda inst, size: setattr(inst, "text_size", size))
            row.add_widget(lbl)
            row.add_widget(small("Up", lambda i=item_id: change(prefs.move, i, -1)))
            row.add_widget(small("Down", lambda i=item_id: change(prefs.move, i, 1)))
            row.add_widget(small("X", lambda i=item_id: change(prefs.toggle, i)))
            box.add_widget(row)
        box.add_widget(Label(text="All tools (tap to add or remove)", size_hint_y=None, height=36))
        q = state["query"].strip().lower()
        for item_id, title in cat:
            if q and q not in title.lower():
                continue
            mark = "[ON]  " if item_id in favs else "[   ]  "
            b = Button(text=mark + title, size_hint_y=None, height=48)
            b.bind(on_press=lambda inst, i=item_id: change(prefs.toggle, i))
            box.add_widget(b)

    def add(items):
        known = set(k for k, _ in cat)
        cat.extend(x for x in items if x[0] not in known)
        refresh()

    def finish():
        state["pending"] -= 1
        if state["pending"] <= 0:
            info.text = ""
            info.height = 0

    def on_search(_inst, value):
        state["query"] = value
        refresh()

    search.bind(text=on_search)

    def load_actions():
        try:
            from services import remote_config_service

            def done(res):
                items = action_entries((res or {}).get("actions", []))
                nav.schedule(lambda: (add(items), finish()))

            remote_config_service.start_load_actions(on_complete=done)
        except Exception:
            finish()

    def load_lab():
        try:
            from core import plugin_loader
            from core.async_utils import run_in_background
            from screens import lab
        except Exception:
            finish()
            return

        def work():
            try:
                items = lab_entries(plugin_loader.load_index(lab.SOURCE)["plugins"], lab.ADD_WORKFLOW_ID)
            except Exception:
                items = []
            nav.schedule(lambda: (add(items), finish()))

        run_in_background(work)

    refresh()
    load_actions()
    load_lab()
