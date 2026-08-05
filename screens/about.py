from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.base import BaseScreen


class AboutScreen(BaseScreen):

    def show(self):
        self.clear()

        app = self.app

        about_text = f"""YT Bridge Git v{app.APP_VERSION}

Download from YouTube to GitHub

Developer: Mohsen Mah

Telegram: t.me/moh3n2016

Note: files are auto-deleted after 2 days"""

        self.add(Label(
            text=about_text,
            size_hint_y=None,
            height=220
        ))

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda i: app.show_home()
        )

        self.add(back_btn)
