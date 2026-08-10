"""Composition root for YT Bridge Git.

This module's only job is to build the Kivy application shell (window,
scroll view, content container) and hand control to the Navigator, which
is where screen flow and app-level state actually live. No download,
upload, playlist, or GitHub logic belongs here - see ``services`` and
``api.github`` for that.
"""
from kivy.app import App
from kivy.core.window import Window
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from screens.navigator import Navigator


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"

        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", padding=10, spacing=8, size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)

        # Placeholder until a screen replaces it with its own status label.
        self.status_label = Label(text="")

        self.nav = Navigator(self)
        self.nav.show_home()
        return self.scroll

    def clear_content(self):
        self.content.clear_widgets()

    def add_widget_to_content(self, widget):
        self.content.add_widget(widget)


if __name__ == "__main__":
    YTBridgeApp().run()
