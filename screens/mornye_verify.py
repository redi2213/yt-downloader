from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens import common
from screens.common import BTN_H, wrapped_label


def build(nav, on_submit, on_open, on_cancel, title="One-time check"):
    """The one-time Mornye check: the browser shows a code, the person pastes it
    here. on_submit(text) -> bool; on_open() opens the browser page again."""
    nav.clear()
    nav.add(Label(text=title, size_hint_y=None, height=40))
    nav.add(wrapped_label(
        "1. In the browser, pass the check. The page closes by itself - that is normal.\n"
        "2. Back in the app, the page opens once more by itself. Tap Copy on the box "
        "with the code (if it does not open, use the button below).\n"
        "3. Come back here, tap Paste, then Continue."))
    status = Label(text="", size_hint_y=None, height=dp(30))
    nav.add(status)
    nav.set_status_label(status)

    open_btn = Button(text="Open the page again", size_hint_y=None, height=BTN_H)
    open_btn.bind(on_press=lambda i: on_open())
    nav.add(open_btn)

    code_input = TextInput(hint_text="Pasted code", multiline=False,
                           size_hint_y=None, height=dp(48))
    nav.add(code_input)
    nav.add(common.paste_row(code_input))

    go_btn = Button(text="Continue", size_hint_y=None, height=BTN_H)
    go_btn.bind(on_press=lambda i: on_submit(code_input.text))
    nav.add(go_btn)

    cancel_btn = Button(text="Cancel", size_hint_y=None, height=BTN_H)
    cancel_btn.bind(on_press=lambda i: on_cancel())
    nav.add(cancel_btn)
