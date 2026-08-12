from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens.common import back_button

_QUALITY_PRESETS = [
    ("480p", 480, False), ("720p", 720, False), ("1080p", 1080, False),
    ("2160p", 2160, False), ("Best", 99999, False), ("Best HDR", 99999, True),
]


def build_quality_picker(nav, urls):
    nav.clear()
    nav.add(Label(text=f"{len(urls)} videos found. Choose quality for ALL:", size_hint_y=None, height=50))
    for name, target_height, want_hdr in _QUALITY_PRESETS:
        btn = Button(text=name, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, h=target_height, hd=want_hdr: nav.start_playlist_download(urls, h, hd))
        nav.add(btn)
    nav.add(back_button(nav))


def build_results(nav, links, errors=None):
    errors = errors or []
    nav.clear()
    nav.add(Label(text=f"{len(links)} links ready:", size_hint_y=None, height=40))
    for link in links:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
        box = TextInput(text=link, readonly=True, multiline=False, size_hint_x=0.7)
        copy_btn = Button(text="Copy", size_hint_x=0.3)
        copy_btn.bind(on_press=lambda i, l=link: Clipboard.copy(l))
        row.add_widget(box)
        row.add_widget(copy_btn)
        nav.add(row)

    if errors:
        nav.add(Label(text=f"{len(errors)} failed:", size_hint_y=None, height=40))
        for url, reason in errors:
            short_url = url if len(url) <= 45 else url[:42] + "..."
            nav.add(Label(text=f"{short_url}\n{reason}", size_hint_y=None, height=44))

    home_btn = Button(text="Back to home", size_hint_y=None, height=48)
    home_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(home_btn)
