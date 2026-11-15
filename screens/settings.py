"""Settings: a short main menu, and one screen per group (nothing long on the first page).

Main menu -> Appearance and language / Downloads and storage / Notifications and health /
Account and sign-in / App tools / About. Every group screen goes back to this menu.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.uix.boxlayout import BoxLayout

from api import (auto_build_prefs, download_folder_prefs, download_manager_prefs, filimo, ntfy_prefs,
                 release_delete_prefs)
from core import android_downloads
from screens.common import back_button, GAP, paste_row, wrapped_label
from services import ntfy_service, token_service

# (button text, section id) of the main menu, in this order
MENU = [
    ("Appearance and language", "appearance"),
    ("Downloads and storage", "downloads"),
    ("Notifications and health", "notify"),
    ("Account and sign-in", "account"),
    ("App tools", "tools"),
]


def build(nav):
    nav.clear()
    nav.add(Label(text="Settings", size_hint_y=None, height=44))
    for text, section in MENU:
        btn = Button(text=text, size_hint_y=None, height=52)
        if section == "appearance":
            btn.bind(on_press=lambda i: nav.show_appearance())
        else:
            btn.bind(on_press=lambda i, s=section: nav.show_settings_section(s))
        nav.add(btn)
    about_btn = Button(text="About", size_hint_y=None, height=52)
    about_btn.bind(on_press=lambda i: nav.show_about())
    nav.add(about_btn)
    nav.add(back_button(nav))


def build_section(nav, section):
    nav.clear()
    titles = dict((s, t) for t, s in MENU)
    nav.add(Label(text=titles.get(section, "Settings"), size_hint_y=None, height=44))
    {"downloads": _downloads, "notify": _notify, "account": _account, "tools": _tools}.get(section, _downloads)(nav)
    nav.add(back_button(nav, to=nav.show_settings))


# -- Downloads and storage ----------------------------------------------------------------------------------------
def _downloads(nav):
    tree = download_folder_prefs.get_tree()
    where = android_downloads.folder_label()
    nav.add(wrapped_label(f"Save folder: {where}" + ("" if tree else "  (default)")))
    info = Label(text="", size_hint_y=None, height=40, color=(1, 0.75, 0.4, 1))

    change_btn = Button(text="Change folder", size_hint_y=None, height=48)
    change_btn.bind(on_press=lambda i: nav.pick_save_folder())
    nav.add(change_btn)
    nav.add(wrapped_label("Android does not allow the top Download folder itself: pick or create a folder "
                          "inside it (for example Download/Yt-bridge)."))
    if tree:
        reset_btn = Button(text="Reset to default folder", size_hint_y=None, height=48)
        reset_btn.bind(on_press=lambda i: nav.reset_save_folder())
        nav.add(reset_btn)
    layout_names = {"source": "By source (APK, YouTube...)", "type": "By file type (Videos, Audio...)",
                    "one": "One folder for everything"}
    layout_btn = Button(text=f"Folders: {layout_names[download_folder_prefs.layout()]}  (tap to change)",
                        size_hint_y=None, height=48)
    layout_btn.bind(on_press=lambda i: nav.toggle_save_subfolders())
    nav.add(layout_btn)
    watched_btn = Button(text="Watched folders (files saved by other apps)", size_hint_y=None, height=48)
    watched_btn.bind(on_press=lambda i: nav.show_watched_folders())
    nav.add(watched_btn)
    after_names = {"ask": "Ask me to delete it from the release", "always": "Always delete it from the release",
                   "never": "Keep it in the release"}
    after_btn = Button(text=f"After a release download: {after_names[release_delete_prefs.mode()]}",
                       size_hint_y=None, height=48)
    after_btn.bind(on_press=lambda i: nav.cycle_release_delete_mode())
    nav.add(after_btn)

    nav.add(Label(text="Download manager", size_hint_y=None, height=32))
    pieces_btn = Button(text=f"Pieces per file: {download_manager_prefs.segments()}  (tap to change)",
                        size_hint_y=None, height=48)
    pieces_btn.bind(on_press=lambda i: nav.cycle_download_segments())
    nav.add(pieces_btn)
    parallel_btn = Button(text=f"Files at the same time: {download_manager_prefs.parallel()}  (tap to change)",
                          size_hint_y=None, height=48)
    parallel_btn.bind(on_press=lambda i: nav.cycle_download_parallel())
    nav.add(parallel_btn)
    empty_on = download_manager_prefs.preallocate()
    empty_btn = Button(text=f"Create empty file first: {'ON' if empty_on else 'OFF'}", size_hint_y=None, height=48)
    empty_btn.bind(on_press=lambda i: nav.toggle_download_preallocate())
    nav.add(empty_btn)
    nav.add(wrapped_label("Create empty file first makes the file at its final size before the download "
                          "starts (Java RandomAccessFile.setLength), so Android does not scatter it in "
                          "pieces. More pieces download one file faster when the server allows it."))

    run_mode_btn = Button(text=f"Run on: {nav.run_mode_label()}  (tap to change)", size_hint_y=None, height=48)
    run_mode_btn.bind(on_press=lambda i: nav.cycle_run_mode())
    nav.add(run_mode_btn)

    proxy_btn = Button(text="Proxy / v2ray config (for Any site)", size_hint_y=None, height=48)
    proxy_btn.bind(on_press=lambda i: nav.show_proxy_settings())
    nav.add(proxy_btn)

    nav.add(info)
    nav.set_status_label(info)


# -- Notifications and health -------------------------------------------------------------------------------------
def _notify(nav):
    _add_ntfy_section(nav)
    health_btn = Button(text="Health check", size_hint_y=None, height=48)
    health_btn.bind(on_press=lambda i: nav.show_health())
    nav.add(health_btn)
    site_log_btn = Button(text="Site log (which sites work)", size_hint_y=None, height=48)
    site_log_btn.bind(on_press=lambda i: nav.show_site_log())
    nav.add(site_log_btn)


# -- Account and sign-in ------------------------------------------------------------------------------------------
def _account(nav):
    saved_token = token_service.get_token()
    token_input = None
    if saved_token and not nav.show_token_field:
        update_token_btn = Button(text="Update GitHub token", size_hint_y=None, height=44)
        update_token_btn.bind(on_press=lambda i: _reveal_token_field(nav))
        nav.add(update_token_btn)
    else:
        token_input = TextInput(
            text=saved_token, hint_text="GitHub Token", multiline=False,
            size_hint_y=None, height=48,
        )
        nav.add(token_input)
        save_token_btn = Button(text="Save token", size_hint_y=None, height=40)
        save_token_btn.bind(on_press=lambda i: _save_token_and_refresh(nav, token_input))
        nav.add(save_token_btn)

    saved_filimo = filimo.get_token()
    if saved_filimo and not nav.show_filimo_field:
        # token already saved: no field, just an "Update" button (like GitHub)
        update_filimo_btn = Button(text="Update Filimo token", size_hint_y=None, height=44)
        update_filimo_btn.bind(on_press=lambda i: _reveal_filimo_field(nav))
        nav.add(update_filimo_btn)
    else:
        nav.add(Label(text="Filimo token (kept only on this phone)", size_hint_y=None, height=28))
        filimo_input = TextInput(
            text=saved_filimo, hint_text="Filimo token", multiline=False,
            password=True, size_hint_y=None, height=48,
        )
        nav.add(filimo_input)
        save_filimo_btn = Button(text="Save Filimo token", size_hint_y=None, height=40)
        save_filimo_btn.bind(on_press=lambda i: _save_filimo_and_refresh(nav, filimo_input))
        nav.add(save_filimo_btn)

    github_signin_btn = Button(text="Sign in with GitHub", size_hint_y=None, height=48)
    github_signin_btn.bind(on_press=lambda i: nav.show_github_signin())
    nav.add(github_signin_btn)


# -- App tools ----------------------------------------------------------------------------------------------------
def _flag_row(text, active, on_change):
    """One tick-box with its text on a full-width row. Returns (row, check box)."""
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=52, spacing=GAP)
    box = CheckBox(active=bool(active), size_hint_x=None, width=52)
    box.bind(active=lambda _instance, value: on_change(value))
    label = Label(text=text, halign="left", valign="middle")
    label.bind(size=lambda instance, size: setattr(instance, "text_size", size))
    row.add_widget(box)
    row.add_widget(label)
    return row, box


def _tools(nav):
    nav.add(Label(text="App update", size_hint_y=None, height=32))

    # What happens by itself - saved, so the choice stays after the app is closed.
    boxes = {}

    def on_download(value):
        auto_build_prefs.set_download_after_build(value)
        if not value and boxes["install"].active:
            boxes["install"].active = False

    def on_install(value):
        auto_build_prefs.set_install_after_download(value)
        if value and not boxes["download"].active:
            boxes["download"].active = True

    build_row, _build_box = _flag_row("Build automatically after the update",
                                      auto_build_prefs.build_after_update(),
                                      auto_build_prefs.set_build_after_update)
    download_row, boxes["download"] = _flag_row("Download automatically after the build",
                                                auto_build_prefs.download_after_build(), on_download)
    install_row, boxes["install"] = _flag_row("Install automatically after the download",
                                              auto_build_prefs.install_after_download(), on_install)
    nav.add(build_row)
    nav.add(download_row)
    nav.add(install_row)

    update_btn = Button(text="Update project (zip or files)", size_hint_y=None, height=48)
    update_btn.bind(on_press=lambda i: nav.pick_file_for_update())
    nav.add(update_btn)
    build_btn = Button(text="Build APK", size_hint_y=None, height=48)
    build_btn.bind(on_press=lambda i: nav.start_build_apk())
    nav.add(build_btn)
    backup_btn = Button(text="Backup project (zip to release)", size_hint_y=None, height=48)
    backup_btn.bind(on_press=lambda i: nav.start_project_backup())
    nav.add(backup_btn)
    browser_btn = Button(text="Browser online update", size_hint_y=None, height=48)
    browser_btn.bind(on_press=lambda i: nav.show_browser_pack())
    nav.add(browser_btn)


def _reveal_token_field(nav):
    nav.show_token_field = True
    nav.show_settings_section("account")


def _save_token_and_refresh(nav, token_input):
    if token_input is not None:
        token_service.save_token(token_input.text.strip())
    nav.show_token_field = False
    nav.show_settings_section("account")


def _reveal_filimo_field(nav):
    nav.show_filimo_field = True
    nav.show_settings_section("account")


def _save_filimo_and_refresh(nav, filimo_input):
    filimo.save_token(filimo_input.text.strip())
    nav.show_filimo_field = False
    nav.show_settings_section("account")


def _add_ntfy_section(nav):
    """Notifications when the app is closed: the workflows send a message to this
    ntfy topic (typed once here; saving puts it in ntfy.json on the config branch)."""
    nav.add(Label(text="Notifications (ntfy)", size_hint_y=None, height=32))
    nav.add(wrapped_label("Install the ntfy app and subscribe to the same topic. Every run then sends "
                          "its result (OK / FAILED, tool, link) to your phone, even when this app is closed. "
                          "The topic works like a password: use a long random one."))
    topic_input = TextInput(text=ntfy_prefs.get_topic(), hint_text="ntfy topic", multiline=False,
                            size_hint_y=None, height=48)
    nav.add(topic_input)
    info = Label(text="", size_hint_y=None, height=40, color=(1, 0.75, 0.4, 1))

    def say(text):
        nav.set_status(text)

    gen_btn = Button(text="Make a random topic", size_hint_y=None, height=44)
    gen_btn.bind(on_press=lambda i: setattr(topic_input, "text", ntfy_service.generate_topic()))
    nav.add(gen_btn)
    save_btn = Button(text="Save topic (for all workflows)", size_hint_y=None, height=44)
    save_btn.bind(on_press=lambda i: nav.save_ntfy_topic(topic_input.text, say))
    nav.add(save_btn)
    test_btn = Button(text="Send a test notification", size_hint_y=None, height=44)
    test_btn.bind(on_press=lambda i: nav.test_ntfy(topic_input.text, say))
    nav.add(test_btn)
    nav.add(info)
    nav.set_status_label(info)
