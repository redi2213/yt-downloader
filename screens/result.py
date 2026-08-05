from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.core.clipboard import Clipboard

from screens.base import BaseScreen


class ResultScreen(BaseScreen):

    def show(self, message, link=None, retry=None):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=message,
                size_hint_y=None,
                height=60
            )
        )

        if link:
            link_box = TextInput(
                text=link,
                readonly=True,
                multiline=False,
                size_hint_y=None,
                height=48
            )
            self.add(link_box)

            copy_btn = Button(
                text="Copy link",
                size_hint_y=None,
                height=48
            )
            copy_btn.bind(
                on_press=lambda i: Clipboard.copy(link)
            )
            self.add(copy_btn)

        if retry:
            retry_btn = Button(
                text="Try again",
                size_hint_y=None,
                height=48
            )
            retry_btn.bind(
                on_press=lambda i: retry()
            )
            self.add(retry_btn)

        home_btn = Button(
            text="Back to home",
            size_hint_y=None,
            height=48
        )
        home_btn.bind(
            on_press=lambda i: app.show_home()
        )
        self.add(home_btn)
