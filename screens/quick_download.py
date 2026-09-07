"""Quick Download screen: skip the "fetch available qualities" step
entirely. The user picks a well-known quality up front, and we hand
yt-dlp a height-capped selector (e.g. bestvideo[height<=720]) so it
picks the closest available quality at or below that target - no
list-formats run needed. Useful when queuing many videos back to back.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens.common import back_button

# (label shown to user, format_id sent to the download workflow)
QUICK_QUALITIES = [
    ("Best", "bestvideo"),
    ("1080p", "bestvideo[height<=1080]"),
    ("720p", "bestvideo[height<=720]"),
    ("480p", "bestvideo[height<=480]"),
    ("360p", "bestvideo[height<=360]"),
]


def build(nav):
    nav.clear()
    nav.add(Label(text="Quick Download", size_hint_y=None, height=40))

    url_input = TextInput(
        hint_text="YouTube video link", multiline=False,
        size_hint_y=None, height=48,
    )
    nav.add(url_input)

    nav.add(Label(text="Choose a quality to start immediately:", size_hint_y=None, height=30))

    for label, fmt_id in QUICK_QUALITIES:
        btn = Button(text=label, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, fid=fmt_id: _start(nav, url_input, fid))
        nav.add(btn)

    nav.add(back_button(nav))


def _start(nav, url_input, format_id):
    url = url_input.text.strip()
    if not url:
        nav.set_status("Enter a YouTube link")
        return
    nav.start_download(url, format_id, False)
