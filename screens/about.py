from kivy.uix.button import Button
from kivy.uix.label import Label

from core.config import APP_VERSION, ABOUT_TEXT_TEMPLATE


def build(nav):
    nav.clear()
    about_text = ABOUT_TEXT_TEMPLATE.format(version=APP_VERSION)
    nav.add(Label(text=about_text, size_hint_y=None, height=220))
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)
