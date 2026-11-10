"""Composition root for YT Bridge Git.

This module's only job is to build the Kivy application shell (window,
scroll view, content container) and hand control to the Navigator, which
is where screen flow and app-level state actually live. No download,
upload, playlist, or GitHub logic belongs here - see ``services`` and
``api.github`` for that.
"""
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

import os

from screens import style
from screens.common import GAP, PAD
from screens.navigator import Navigator


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"
        # Theme, font, size and Persian texts for every widget made from here on.
        style.install(os.path.join(self.user_data_dir, "ui"))

        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", padding=PAD, spacing=GAP, size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)

        # Placeholder until a screen replaces it with its own status label.
        self.status_label = Label(text="")

        # Created BEFORE show_home(): every screen build calls clear_content(), which uses it.
        # Fixed bar under the scrolling content (a screen fills it with Navigator.set_footer).
        self.footer = BoxLayout(orientation="vertical", size_hint_y=None, height=0,
                                padding=(PAD, dp(6)))
        self.nav = Navigator(self)
        self.nav.show_home()
        # The phone's own Back key (key code 27) goes one screen back.
        Window.bind(on_keyboard=self._on_keyboard)
        root = BoxLayout(orientation="vertical")
        root.add_widget(self.scroll)
        root.add_widget(self.footer)
        return root

    def _on_keyboard(self, window, key, *args):
        if key == 27:
            # True = handled here; False on the home screen = default (close the app)
            return bool(self.nav.go_back())
        return False

    def on_pause(self):
        # Stay alive in the background: downloads and builds go on. Kivy's clock stops meanwhile,
        # so the navigator starts everything that matters from worker threads.
        self.nav.app_active = False
        return True

    def on_resume(self):
        self.nav.app_active = True
        self.nav.mornye_resumed()

    def on_start(self):
        # Links shared into the app from other apps (Android Share menu).
        # No-op on desktop or if the Android hooks are unavailable.
        from core import android_notify, android_share
        android_notify.request_permission()
        android_share.setup(self.nav.handle_shared_text, self.nav.handle_shared_file,
                            self.nav.open_from_notification)

    def clear_content(self):
        self.content.clear_widgets()
        self.footer.clear_widgets()
        self.footer.height = 0

    def set_footer(self, widget):
        self.footer.clear_widgets()
        self.footer.add_widget(widget)
        self.footer.height = widget.height + dp(12)

    def add_widget_to_content(self, widget):
        self.content.add_widget(widget)


if __name__ == "__main__":
    YTBridgeApp().run()
