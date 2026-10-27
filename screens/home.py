"""Home screen: the app's top-level menu. Everything that used to be a
flat list of ~12 buttons is now grouped behind a few menu entries, each
leading to its own screen - see youtube_download.py, actions_dynamic.py
(via Download Anything), history.py, actions_status.py, and settings.py.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label


def build(nav):
    nav.clear()
    try:
        _add_quick_link(nav)
    except Exception:
        pass   # a convenience: the menu below must always appear


    running = nav.job_manager.active_jobs
    if running:
        running_btn = Button(text=f"Running jobs ({len(running)})", size_hint_y=None, height=52)
        running_btn.bind(on_press=lambda i: nav.show_running_jobs())
        nav.add(running_btn)

    youtube_btn = Button(text="YouTube Download", size_hint_y=None, height=52)
    youtube_btn.bind(on_press=lambda i: nav.show_youtube_download())
    nav.add(youtube_btn)

    dynamic_actions_btn = Button(text="Download Anything", size_hint_y=None, height=52)
    dynamic_actions_btn.bind(on_press=lambda i: nav.show_dynamic_actions())
    nav.add(dynamic_actions_btn)

    follow_btn = Button(text="Auto follow", size_hint_y=None, height=52)
    follow_btn.bind(on_press=lambda i: nav.show_follow_menu())
    nav.add(follow_btn)

    from core import download_manager
    live = len([t for t in download_manager.snapshot() if t.active])
    downloads_btn = Button(text=f"Downloads ({live})" if live else "Downloads", size_hint_y=None, height=52)
    downloads_btn.bind(on_press=lambda i: nav.show_downloads())
    nav.add(downloads_btn)

    history_btn = Button(text="Release History", size_hint_y=None, height=52)
    history_btn.bind(on_press=lambda i: nav.show_release_history())
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


def _add_quick_link(nav):
    """One box on top: paste any link and the app opens the right tool for it
    (the same routing as the Android Share menu: YouTube, a tool whose domains
    match the link, or a chooser)."""
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from screens import common

    box = TextInput(hint_text="Paste any link here", multiline=False,
                    size_hint_y=None, height=common.BTN_H)
    nav.add(box)
    nav.add(common.paste_row(box))

    def go(_instance):
        link = box.text.strip()
        if not link:
            nav.set_status("Paste a link first")
            return
        nav.handle_shared_text(link)

    go_btn = Button(text="Go", size_hint_y=None, height=52)
    go_btn.bind(on_press=go)
    nav.add(go_btn)
    box.bind(on_text_validate=go)   # the keyboard's Enter key
