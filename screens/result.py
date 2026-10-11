from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


def build(nav, message, link=None, retry=None, retry_message="Working...", extra_buttons=None, links=None):
    nav.clear()
    many = bool(links) and len(links) > 1
    if many:
        message = f"{message} ({len(links)} files)"
    nav.add(Label(text=message, size_hint_y=None, height=60))
    if many:
        # several files: every link on its own line, one button copies them all
        all_text = "\n".join(links)
        link_box = TextInput(text=all_text, readonly=True, multiline=True,
                             size_hint_y=None, height=dp(220))
        nav.add(link_box)
        copy_btn = Button(text="Copy all links", size_hint_y=None, height=48)
        copy_btn.bind(on_press=lambda i: Clipboard.copy(all_text))
        nav.add(copy_btn)
        first_btn = Button(text="Copy first link only", size_hint_y=None, height=48)
        first_btn.bind(on_press=lambda i: Clipboard.copy(links[0]))
        nav.add(first_btn)
    elif link:
        link_box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
        nav.add(link_box)
        copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
        copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
        nav.add(copy_btn)
    # extra_buttons: [(text, callable)] shown under "Copy link"
    for text, callback in (extra_buttons or []):
        extra_btn = Button(text=text, size_hint_y=None, height=48)
        extra_btn.bind(on_press=lambda i, cb=callback: cb())
        nav.add(extra_btn)
    if retry:
        retry_btn = Button(text="Try again", size_hint_y=None, height=48)
        retry_btn.bind(on_press=lambda i: nav.retry_action(retry, retry_message))
        nav.add(retry_btn)
    home_btn = Button(text="Back to home", size_hint_y=None, height=48)
    home_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(home_btn)
