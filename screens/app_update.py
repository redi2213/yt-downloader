"""Settings > Update from update.zip: the confirmation screen."""
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import zip_tools
from services import repo_update_service


def _label(nav, text, height):
    label = Label(text=text, size_hint_y=None, height=height, halign="center", valign="middle")
    label.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
    nav.add(label)


def build_zip_confirm(nav, data):
    nav.clear()
    try:
        summary = repo_update_service.summarize_zip(data)
    except zip_tools.ZipError as e:
        nav.show_result(str(e))
        return
    nav.add(Label(text="Update from zip", size_hint_y=None, height=44))
    lines = "\n".join(f"{branch}: {count} file(s)" for branch, count in sorted(summary.items()))
    _label(nav, lines, 40 + 28 * len(summary))
    _label(nav, "Only changed files are uploaded, one commit per branch. A backup of the "
                "branch is saved first (not for config; last 5 kept). Folders missing "
                "from the zip are left untouched.", 150)
    go = Button(text="Update", size_hint_y=None, height=56)
    go.bind(on_press=lambda i: nav.start_repo_update(data))
    nav.add(go)
    cancel = Button(text="Cancel", size_hint_y=None, height=48)
    cancel.bind(on_press=lambda i: nav.show_settings())
    nav.add(cancel)
