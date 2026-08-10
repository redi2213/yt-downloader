"""Home screen: entry point for starting a download, playlist job, or
upload, and for navigating to history/status/about."""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from services import token_service


def build(nav):
    nav.clear()

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

    url_input = TextInput(
        hint_text="YouTube video or playlist link", multiline=False,
        size_hint_y=None, height=48,
    )
    nav.add(url_input)

    audio_toggle = ToggleButton(
        text=f"Audio only (MP3): {'ON' if nav.audio_only else 'OFF'}",
        size_hint_y=None, height=48,
    )
    audio_toggle.bind(on_press=lambda i: _toggle_audio(nav, audio_toggle))
    nav.add(audio_toggle)

    fetch_btn = Button(text="Get qualities (single video)", size_hint_y=None, height=56)
    fetch_btn.bind(on_press=lambda i: _on_fetch_single(nav, token_input, url_input))
    nav.add(fetch_btn)

    playlist_btn = Button(text="This is a playlist", size_hint_y=None, height=48)
    playlist_btn.bind(on_press=lambda i: _on_fetch_playlist(nav, token_input, url_input))
    nav.add(playlist_btn)

    upload_btn = Button(text="Upload a file (any link)", size_hint_y=None, height=48)
    upload_btn.bind(on_press=lambda i: nav.show_upload_screen())
    nav.add(upload_btn)

    history_btn = Button(text="Download history", size_hint_y=None, height=48)
    history_btn.bind(on_press=lambda i: nav.show_live_history())
    nav.add(history_btn)

    about_btn = Button(text="About", size_hint_y=None, height=48)
    about_btn.bind(on_press=lambda i: nav.show_about())
    nav.add(about_btn)

    current_job = nav.job_manager.current_job
    if current_job is not None:
        label_text = "Check on last job" if not current_job.is_done else "View last result"
        check_btn = Button(text=label_text, size_hint_y=None, height=48)
        check_btn.bind(on_press=lambda i: nav.resume_job_screen())
        nav.add(check_btn)

    status_btn = Button(text="Check GitHub Actions status", size_hint_y=None, height=48)
    status_btn.bind(on_press=lambda i: nav.show_actions_status())
    nav.add(status_btn)

    history_count = len(nav.job_manager.history)
    if history_count:
        recent_btn = Button(text=f"Recent jobs ({history_count})", size_hint_y=None, height=48)
        recent_btn.bind(on_press=lambda i: nav.show_job_history())
        nav.add(recent_btn)

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)


def _reveal_token_field(nav):
    nav.show_token_field = True
    nav.show_home()


def _save_token_and_refresh(nav, token_input):
    if token_input is not None:
        token_service.save_token(token_input.text.strip())
    nav.show_token_field = False
    nav.show_home()


def _toggle_audio(nav, instance):
    nav.audio_only = not nav.audio_only
    instance.text = f"Audio only (MP3): {'ON' if nav.audio_only else 'OFF'}"


def _on_fetch_single(nav, token_input, url_input):
    if token_input is not None:
        token_service.save_token(token_input.text.strip())
    nav.handle_fetch_single(url_input.text, nav.audio_only)


def _on_fetch_playlist(nav, token_input, url_input):
    if token_input is not None:
        token_service.save_token(token_input.text.strip())
    nav.handle_fetch_playlist(url_input.text)
