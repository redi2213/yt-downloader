"""YouTube Download screen: the home menu's first entry. Groups every
single-video and playlist action that used to live directly on the home
screen, now behind one menu button.

Two independent link boxes:
  - single video link -> "Get qualities" (full flow) or "Quick Download"
    (skip the list-formats step, jump straight to a height-capped format)
  - playlist link -> "This is a playlist" quick-quality buttons, which
    download every video in the playlist at the closest available quality
    with no per-video prompting
"""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from screens.common import back_button

# (label, format_id) for the single-video Quick Download row. Height-capped
# selectors so yt-dlp itself picks the closest available quality at or
# below the target - see download.yml's FORMAT_SPEC handling.
_QUICK_SINGLE_QUALITIES = [
    ("360p", "bestvideo[height<=360]"),
    ("480p", "bestvideo[height<=480]"),
    ("720p", "bestvideo[height<=720]"),
    ("1080p", "bestvideo[height<=1080]"),
    ("Best", "bestvideo"),
]

# (label, target_height, want_hdr) for the playlist quick-quality row.
# Reuses download_service.pick_format's existing "closest available height"
# matching per-video - no separate matching logic needed.
_PLAYLIST_QUALITIES = [
    ("360p", 360, False),
    ("480p", 480, False),
    ("720p", 720, False),
    ("1080p", 1080, False),
]


def build(nav):
    nav.clear()
    nav.add(Label(text="YouTube Download", size_hint_y=None, height=44))

    # -- single video -----------------------------------------------------
    single_url_input = TextInput(
        hint_text="YouTube video link", multiline=False,
        size_hint_y=None, height=48,
    )
    nav.add(single_url_input)

    audio_toggle = ToggleButton(
        text=f"Audio only (MP3): {'ON' if nav.audio_only else 'OFF'}",
        size_hint_y=None, height=48,
    )
    audio_toggle.bind(on_press=lambda i: _toggle_audio(nav, audio_toggle))
    nav.add(audio_toggle)

    fetch_btn = Button(text="Get qualities (single video)", size_hint_y=None, height=56)
    fetch_btn.bind(on_press=lambda i: nav.handle_fetch_single(single_url_input.text, nav.audio_only))
    nav.add(fetch_btn)

    nav.add(Label(text="Quick Download", size_hint_y=None, height=32))
    for label, format_id in _QUICK_SINGLE_QUALITIES:
        btn = Button(text=label, size_hint_y=None, height=48)
        btn.bind(on_press=lambda i, fid=format_id: _start_quick_single(nav, single_url_input, fid))
        nav.add(btn)
    audio_only_btn = Button(text="Audio only (MP3)", size_hint_y=None, height=48)
    audio_only_btn.bind(on_press=lambda i: _start_quick_single_audio(nav, single_url_input))
    nav.add(audio_only_btn)

    # -- playlist -----------------------------------------------------------
    playlist_url_input = TextInput(
        hint_text="YouTube playlist link", multiline=False,
        size_hint_y=None, height=48,
    )
    nav.add(playlist_url_input)

    nav.add(Label(text="This is a playlist", size_hint_y=None, height=32))
    for label, target_height, want_hdr in _PLAYLIST_QUALITIES:
        btn = Button(text=label, size_hint_y=None, height=48)
        btn.bind(on_press=lambda i, h=target_height, hd=want_hdr:
                  _start_playlist_quality(nav, playlist_url_input, h, hd, audio_only=False))
        nav.add(btn)
    playlist_audio_btn = Button(text="Audio only (MP3)", size_hint_y=None, height=48)
    playlist_audio_btn.bind(on_press=lambda i: _start_playlist_quality(
        nav, playlist_url_input, 0, False, audio_only=True))
    nav.add(playlist_audio_btn)

    nav.add(back_button(nav))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)


def _toggle_audio(nav, instance):
    nav.audio_only = not nav.audio_only
    instance.text = f"Audio only (MP3): {'ON' if nav.audio_only else 'OFF'}"


def _start_quick_single(nav, url_input, format_id):
    url = url_input.text.strip()
    if not url:
        nav.set_status("Enter a YouTube link")
        return
    nav.start_download(url, format_id, False)


def _start_quick_single_audio(nav, url_input):
    url = url_input.text.strip()
    if not url:
        nav.set_status("Enter a YouTube link")
        return
    nav.start_download(url, "bestaudio", True)


def _start_playlist_quality(nav, url_input, target_height, want_hdr, audio_only):
    url = url_input.text.strip()
    if not url:
        nav.set_status("Enter a playlist link")
        return
    nav.start_playlist_from_link(url, target_height, want_hdr, audio_only)
