from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, back_button, card_box, content_width,
    paint_card, wrapped_label_height,
)

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
    nav.add(back_button(nav, to=nav.show_youtube_download))


# (label, target_height, want_hdr) for the quality of the chosen videos
_SELECTED_QUALITIES = [
    ("360p", 360, False), ("480p", 480, False), ("720p", 720, False),
    ("1080p", 1080, False), ("Best", 99999, False),
]


def build_picker(nav, entries, playlist_url, selected):
    """The playlist's videos as tap-to-select cards (like Release History):
    Select all / Clear, then "Download selected". ``selected`` is a list of
    bools, one per entry, edited in place."""
    nav.clear()
    total = len(entries)
    nav.add(Label(text=f"Playlist ({total} videos)", size_hint_y=None, height=BTN_H))

    cards = []   # card colour of every video, in display order
    info = Label(text="", size_hint_y=None, height=BTN_H)

    def update_info():
        info.text = f"Selected: {sum(selected)} of {total}"

    def set_selected(idx, value):
        selected[idx] = value
        cards[idx].rgba = CARD_ON if value else CARD
        update_info()

    def set_all(value):
        for idx in range(total):
            set_selected(idx, value)

    def download_selected(_inst):
        urls = [e["url"] for e, on in zip(entries, selected) if on]
        if not urls:
            info.text = "Tap the videos you want first"
            return
        nav.show_playlist_selected_quality(entries, playlist_url, selected, urls)

    select_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    select_all_btn = Button(text="Select all")
    select_all_btn.bind(on_press=lambda i: set_all(True))
    clear_btn = Button(text="Clear")
    clear_btn.bind(on_press=lambda i: set_all(False))
    select_row.add_widget(select_all_btn)
    select_row.add_widget(clear_btn)
    nav.add(select_row)
    nav.add(info)

    go_btn = Button(text="Download selected", size_hint_y=None, height=BTN_H)
    go_btn.bind(on_press=download_selected)
    nav.add(go_btn)

    inner_width = content_width() - 2 * dp(8)
    for idx, entry in enumerate(entries):
        text = f"{idx + 1}. {entry['title']}"
        height = wrapped_label_height(text, extra_padding=dp(14), width=inner_width - dp(16))
        row = card_box([height])
        cards.append(paint_card(row, CARD_ON if selected[idx] else CARD))
        title_btn = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                           background_normal="", background_color=(0, 0, 0, 0))
        title_btn.text_size = (inner_width - dp(16), None)
        title_btn.bind(on_press=lambda i, n=idx: set_selected(n, not selected[n]))
        row.add_widget(title_btn)
        nav.add(row)

    update_info()
    nav.add(back_button(nav, to=lambda: nav.show_youtube_download(playlist_url=playlist_url)))


def build_selected_quality(nav, urls, back):
    """Quality for the chosen videos only; audio-only (MP3) is offered too."""
    nav.clear()
    nav.add(Label(text=f"{len(urls)} selected video(s). Choose quality:", size_hint_y=None, height=50))

    def again():
        build_selected_quality(nav, urls, back)

    for name, target_height, want_hdr in _SELECTED_QUALITIES:
        btn = Button(text=name, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, h=target_height, hd=want_hdr:
                 nav.start_playlist_download(urls, h, hd, quality_screen=again))
        nav.add(btn)
    audio_btn = Button(text="Audio only (MP3)", size_hint_y=None, height=50)
    audio_btn.bind(on_press=lambda inst: nav.start_playlist_download(
        urls, 0, False, audio_only=True, quality_screen=again))
    nav.add(audio_btn)
    nav.add(back_button(nav, to=back))


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
