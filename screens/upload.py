from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from screens.common import back_button


def build(nav):
    nav.clear()
    nav.add(Label(text="Upload a file from a link", size_hint_y=None, height=40))

    url_input = TextInput(hint_text="Direct file link", multiline=False, size_hint_y=None, height=48)
    nav.add(url_input)

    rename_input = TextInput(
        hint_text="New name (optional, leave blank to keep original)",
        multiline=False, size_hint_y=None, height=48,
    )
    nav.add(rename_input)

    zip_toggle = ToggleButton(text="Zip before upload: OFF", size_hint_y=None, height=48)
    zip_toggle.bind(on_press=lambda i: _toggle_zip(zip_toggle))
    nav.add(zip_toggle)

    start_btn = Button(text="Upload", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.handle_start_upload(
        url_input.text, zip_toggle.state == "down", rename_input.text))
    nav.add(start_btn)

    nav.add(back_button(nav))


def _toggle_zip(instance):
    is_on = instance.state == "down"
    instance.text = f"Zip before upload: {'ON' if is_on else 'OFF'}"
