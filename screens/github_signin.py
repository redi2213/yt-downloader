"""GitHub sign-in screen using Device Flow: shows a short code and a link
for the user to visit, then polls in the background until they approve on
github.com. Once approved, the token is already saved (by auth_service)
and we just navigate back home."""
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common


def build_start(nav):
    """Initial screen: a single button to kick off the sign-in flow."""
    nav.clear()
    nav.add(Label(text="Sign in with your GitHub account", size_hint_y=None, height=60))

    start_btn = Button(text="Sign in with GitHub", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.start_github_signin())
    nav.add(start_btn)

    nav.add(common.back_button(nav))


def build_waiting(nav, user_code, verification_uri):
    """Shown once we have a code - tells the user where to go and what to
    type, while auth_service keeps polling in the background."""
    nav.clear()
    nav.add(Label(text="Go to:", size_hint_y=None, height=40))
    nav.add(common.wrapped_label(verification_uri))

    nav.add(Label(text="And enter this code:", size_hint_y=None, height=40))
    code_label = Label(text=user_code, size_hint_y=None, height=60,
                        font_size="28sp", bold=True)
    nav.add(code_label)

    status_label = Label(text="Waiting for approval...", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)

    nav.add(common.back_button(nav, text="Cancel"))
