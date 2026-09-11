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

from screens.common import back_button
from services import token_service


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
