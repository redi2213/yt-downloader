"""Home screen: the app's top-level menu. Everything that used to be a
flat list of ~12 buttons is now grouped behind 5 menu entries, each
leading to its own screen - see youtube_download.py, actions_dynamic.py
(via Download Anything), history.py, actions_status.py, and settings.py.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label


def build(nav):
    nav.clear()

    youtube_btn = Button(text="YouTube Download", size_hint_y=None, height=52)
    youtube_btn.bind(on_press=lambda i: nav.show_youtube_download())
    nav.add(youtube_btn)

    dynamic_actions_btn = Button(text="Download Anything", size_hint_y=None, height=52)
    dynamic_actions_btn.bind(on_press=lambda i: nav.show_dynamic_actions())
    nav.add(dynamic_actions_btn)

    history_btn = Button(text="Release History", size_hint_y=None, height=52)
    history_btn.bind(on_press=lambda i: nav.show_live_history())
    nav.add(history_btn)

    status_btn = Button(text="Check GitHub Actions status", size_hint_y=None, height=52)
    status_btn.bind(on_press=lambda i: nav.show_actions_status())
    nav.add(status_btn)

    settings_btn = Button(text="Settings", size_hint_y=None, height=52)
    settings_btn.bind(on_press=lambda i: nav.show_settings())
    nav.add(settings_btn)

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)
