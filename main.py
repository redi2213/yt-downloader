"""Composition root for YT Bridge Git.

This module's only job is to build the Kivy application shell (window, top bar) and hand control to the
tabs (screens/tabs.py): every tab has its own Navigator - where screen flow and app-level state actually
live - and its own scroll area / bottom bar. No download, upload, playlist, or GitHub logic belongs here -
see ``services`` and ``api.github`` for that.
"""
from kivy.app import App
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.widget import Widget

import os

from screens import style
from screens.common import PAD
from screens.tabs import TabManager


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"
        # Theme, font, size and Persian texts for every widget made from here on.
        style.install(os.path.join(self.user_data_dir, "ui"))

        # Slim bar above every screen: a "Home" button (drop-down with the main menu, screens/home_menu.py) on
        # one side and the "Tabs" button (screens/tabs.py: tab count + running/finished mark) on the other.
        # Home screen: Tabs button only. Browser page: no bar. Created BEFORE the first tab (its screens use it).
        self.topbar = BoxLayout(orientation="horizontal", size_hint_y=None, height=0, opacity=0,
                                disabled=True, padding=(PAD, dp(4)))
        self.home_btn = Button(text="Home", size_hint_x=None, width=dp(140))
        self.home_btn.bind(on_release=self._open_home_menu)
        self.tabs_btn = Button(text="Tabs (1)", size_hint_x=None, width=dp(150))
        self.tabs_btn.bind(on_release=lambda b: self.tabs.open_overlay())
        self.topbar.add_widget(self.home_btn)
        self.topbar.add_widget(Widget())
        self.topbar.add_widget(self.tabs_btn)

        self.tabs = TabManager(self)
        self.tabs.new_tab()                 # the first tab opens on Home
        # The phone's own Back key (key code 27) goes one screen back.
        Window.bind(on_keyboard=self._on_keyboard)
        root = BoxLayout(orientation="vertical")
        root.add_widget(self.topbar)
        root.add_widget(self.tabs.body)
        return root

    # -- the tab on screen (the old single-screen attributes now point at it) ----------
    @property
    def nav(self):
        return self.tabs.active.nav

    @property
    def content(self):
        return self.tabs.active.content

    @property
    def footer(self):
        return self.tabs.active.footer

    @property
    def scroll(self):
        return self.tabs.active.scroll

    @property
    def status_label(self):
        return self.tabs.active.status_label

    def clear_content(self):
        self.tabs.active.clear_content()

    def set_footer(self, widget):
        self.tabs.active.set_footer(widget)

    def add_widget_to_content(self, widget):
        self.tabs.active.add_widget_to_content(widget)

    # -- top bar -----------------------------------------------------------------------
    def set_topbar_mode(self, mode):
        """"full": Home + Tabs. "tabs": Tabs only (Home screen). "hidden": no bar (browser page)."""
        if mode is True:
            mode = "full"
        elif mode is False or mode is None:
            mode = "hidden"
        show = mode != "hidden"
        self.topbar.height = dp(48) if show else 0
        self.topbar.opacity = 1 if show else 0
        self.topbar.disabled = not show
        home = mode == "full"
        self.home_btn.width = dp(140) if home else 0
        self.home_btn.opacity = 1 if home else 0
        self.home_btn.disabled = not home

    def show_topbar(self, visible):
        self.set_topbar_mode(visible)

    def _open_home_menu(self, button):
        from screens import home_menu
        home_menu.open(self.nav, button)

    def _on_keyboard(self, window, key, *args):
        if key == 27:
            # True = handled here; False on the home screen = default (close the app)
            return bool(self.nav.go_back())
        return False

    def on_pause(self):
        # Stay alive in the background: downloads and builds go on in every tab. Kivy's clock stops meanwhile,
        # so the navigator starts everything that matters from worker threads.
        for tab in self.tabs.tabs:
            tab.nav.app_active = False
        return True

    def on_resume(self):
        for tab in self.tabs.tabs:
            tab.nav.app_active = True
            try:
                tab.nav.mornye_resumed()
            except Exception:
                pass

    def on_start(self):
        # Links and files shared into the app from other apps (Android Share menu): always a new tab.
        # No-op on desktop or if the Android hooks are unavailable.
        from core import android_notify, android_share
        android_notify.request_permission()
        android_share.setup(self.tabs.handle_shared_text, self.tabs.handle_shared_file,
                            self.tabs.open_from_notification)
        try:
            self.nav.refresh_arvan_in_background()   # quietly brings the Arvan file list up to date
        except Exception:
            pass


if __name__ == "__main__":
    YTBridgeApp().run()
