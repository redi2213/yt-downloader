from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from screens import common
from screens.common import back_button

# normal / ON (the button's grey is multiplied by these)
_ZIP_OFF = (1, 1, 1, 1)
_ZIP_ON = (0.35, 0.85, 0.45, 1)


def build(nav, url=""):
    nav.clear()
    nav.add(Label(text="Upload files from links", size_hint_y=None, height=40))

    # Several links at once: one per line. Uploaded together, side by side,
    # into ONE release; each file keeps the name it has in its link.
    url_input = TextInput(text=url, hint_text="Direct file links - one per line",
                          multiline=True, size_hint_y=None, height=dp(170))
    nav.add(url_input)
    nav.add(common.paste_row(url_input, append=True))

    zip_toggle = ToggleButton(text="Zip each file: OFF", size_hint_y=None, height=48)
    zip_toggle.bind(on_press=lambda i: _toggle_zip(zip_toggle))
    nav.add(zip_toggle)

    start_btn = Button(text="Upload", size_hint_y=None, height=56)
    # the rename box is gone: with several files every file keeps its own name
    start_btn.bind(on_press=lambda i: nav.handle_start_upload(
        url_input.text, zip_toggle.state == "down", ""))
    nav.add(start_btn)

    nav.add(back_button(nav))


def _toggle_zip(instance):
    is_on = instance.state == "down"
    instance.text = f"Zip each file: {'ON' if is_on else 'OFF'}"
    instance.background_color = _ZIP_ON if is_on else _ZIP_OFF
