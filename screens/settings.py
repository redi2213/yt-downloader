"""Settings screen: everything account/app-config related that used to sit
directly on the home screen - the GitHub token field, sign-in, and About.
Room for future appearance settings (theme color, font size, etc) as noted
in the module docstring below.

Future: appearance settings (colors, font size) will be added here once
designed - kept as a placeholder section for now.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens.common import back_button, paste_row, wrapped_label
from services import ntfy_service, token_service
from api import ntfy_prefs
from api import filimo


def build(nav):
    nav.clear()
    nav.add(Label(text="Settings", size_hint_y=None, height=44))

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

    storage_mode_btn = Button(text=f"Storage: {nav.storage_mode_label()}  (tap to change)",
                              size_hint_y=None, height=48)
    storage_mode_btn.bind(on_press=lambda i: nav.cycle_storage_mode())
    nav.add(storage_mode_btn)

    run_mode_btn = Button(text=f"Run on: {nav.run_mode_label()}  (tap to change)", size_hint_y=None, height=48)
    run_mode_btn.bind(on_press=lambda i: nav.cycle_run_mode())
    nav.add(run_mode_btn)

    storage_btn = Button(text="Storage and Arvan buckets", size_hint_y=None, height=48)
    storage_btn.bind(on_press=lambda i: nav.show_storage())
    nav.add(storage_btn)

    _add_ntfy_section(nav)

    health_btn = Button(text="Health check", size_hint_y=None, height=48)
    health_btn.bind(on_press=lambda i: nav.show_health())
    nav.add(health_btn)

    nav.add(Label(text="App update", size_hint_y=None, height=32))
    update_btn = Button(text="Update project (zip or files)", size_hint_y=None, height=48)
    update_btn.bind(on_press=lambda i: nav.pick_file_for_update())
    nav.add(update_btn)
    build_btn = Button(text="Build APK", size_hint_y=None, height=48)
    build_btn.bind(on_press=lambda i: nav.start_build_apk())
    nav.add(build_btn)
    backup_btn = Button(text="Backup project (zip to release)", size_hint_y=None, height=48)
    backup_btn.bind(on_press=lambda i: nav.start_project_backup())
    nav.add(backup_btn)

    github_signin_btn = Button(text="Sign in with GitHub", size_hint_y=None, height=48)
    github_signin_btn.bind(on_press=lambda i: nav.show_github_signin())
    nav.add(github_signin_btn)

    about_btn = Button(text="About", size_hint_y=None, height=48)
    about_btn.bind(on_press=lambda i: nav.show_about())
    nav.add(about_btn)

    nav.add(back_button(nav))


def _reveal_token_field(nav):
    nav.show_token_field = True
    nav.show_settings()


def _save_token_and_refresh(nav, token_input):
    if token_input is not None:
        token_service.save_token(token_input.text.strip())
    nav.show_token_field = False
    nav.show_settings()


def _reveal_filimo_field(nav):
    nav.show_filimo_field = True
    nav.show_settings()


def _save_filimo_and_refresh(nav, filimo_input):
    filimo.save_token(filimo_input.text.strip())
    nav.show_filimo_field = False
    nav.show_settings()


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
