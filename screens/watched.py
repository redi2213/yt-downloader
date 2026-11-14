"""Settings > Downloads > Watched folders: folders other apps save files in. The app only looks at
the file names and sizes there, to warn about a download that is already on the phone."""
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
    add = Button(text="Add folder", size_hint_y=None, height=BTN_H)
    add.bind(on_press=lambda i: nav.add_watched_folder())
    nav.add(add)
    count = phone_files.watched_count()
    if watched_folders_prefs.load():
        nav.add(wrapped_label(f"Files seen in these folders: {count}"))
    nav.add(back_button(nav, to=lambda: nav.show_settings_section("downloads")))
