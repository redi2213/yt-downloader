from kivy.core.clipboard import Clipboard
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


def build(nav, message, link=None, retry=None, retry_message="Working..."):
    nav.clear()
    nav.add(Label(text=message, size_hint_y=None, height=60))
    if link:
        link_box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
        nav.add(link_box)
        copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
        copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
        nav.add(copy_btn)
    if retry:
        retry_btn = Button(text="Try again", size_hint_y=None, height=48)
        retry_btn.bind(on_press=lambda i: nav.retry_action(retry, retry_message))
        nav.add(retry_btn)
    home_btn = Button(text="Back to home", size_hint_y=None, height=48)
    home_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(home_btn)
