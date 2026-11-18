"""Settings > Downloads > Watched folders: folders other apps save files in. The app only looks at
the file names and sizes there, to warn about a download that is already on the phone."""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from api import watched_folders_prefs
from core import phone_files
from screens.common import BTN_H, GAP, back_button, content_width, wrapped_label

_DANGER = (1.0, 0.55, 0.55, 1)


def build(nav):
    nav.clear()
    nav.add(Label(text="Watched folders", size_hint_y=None, height=44))
    nav.add(wrapped_label("Add the folders where other download apps save files. Release History and "
                          "Downloads then show a file that is already on the phone, and warn before it "
                          "is downloaded again."))
    counters = []   # (label, uri): the number of files found in each folder, updated while scanning
    for folder in watched_folders_prefs.load():
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        label = Label(text=folder.get("label", ""), halign="left", valign="middle", shorten=True,
                      shorten_from="left", size_hint_x=0.68)
        label.text_size = (content_width() * 0.62, None)
        remove = Button(text="Remove", size_hint_x=0.32, background_color=_DANGER)
        remove.bind(on_press=lambda i, u=folder.get("uri"): nav.remove_watched_folder(u))
        row.add_widget(label)
        row.add_widget(remove)
        nav.add(row)
        found = Label(text=f"Files seen in these folders: {phone_files.folder_count(folder.get('uri'))}",
                      size_hint_y=None, height=dp(26), halign="left", valign="middle", color=(0.7, 0.7, 0.7, 1))
        found.text_size = (content_width(), None)
        nav.add(found)
        counters.append((found, folder.get("uri")))
    add = Button(text="Add folder", size_hint_y=None, height=BTN_H)
    add.bind(on_press=lambda i: nav.add_watched_folder())
    nav.add(add)
    total = Label(text="", size_hint_y=None, height=dp(34), halign="center", valign="middle")
    total.text_size = (content_width(), None)
    if watched_folders_prefs.load():
        nav.add(total)
        rescan = Button(text="Scan again", size_hint_y=None, height=BTN_H)
        rescan.bind(on_press=lambda i: (phone_files.refresh_watched(force=True), poll()))
        nav.add(rescan)

    def paint(*_args):
        for label, uri in counters:
            label.text = f"Files seen in these folders: {phone_files.folder_count(uri)}"
        scanning = phone_files.is_scanning()
        total.text = "Scanning folders..." if scanning else f"Files seen in these folders: {phone_files.watched_count()}"
        return scanning

    def poll(*_args):
        # the scan runs in the background: keep the numbers fresh until it is done
        if paint():
            Clock.schedule_once(poll, 1)

    poll()
    nav.add(back_button(nav, to=lambda: nav.show_settings_section("downloads")))
