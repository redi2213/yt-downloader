from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label

from screens.base import BaseScreen


class HomeScreen(BaseScreen):

    def build(self):
        self.clear_content()

        self.url_input = TextInput(
            hint_text="YouTube video or playlist link",
            multiline=False,
            size_hint_y=None,
            height=48
        )
        self.add(self.url_input)

        self.audio_toggle = ToggleButton(
            text="Audio only (MP3): OFF",
            size_hint_y=None,
            height=48
        )
        self.add(self.audio_toggle)

        fetch_btn = Button(
            text="Get qualities (single video)",
            size_hint_y=None,
            height=56
        )
        self.add(fetch_btn)

        playlist_btn = Button(
            text="This is a playlist",
            size_hint_y=None,
            height=48
        )
        self.add(playlist_btn)

        self.add(Label(
            text="Home Screen",
            size_hint_y=None,
            height=40
        ))
