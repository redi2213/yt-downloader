"""YouTube Download screen: the home menu's first entry. Groups every
single-video and playlist action that used to live directly on the home
screen, now behind one menu button.

Two independent link boxes. Both are tall multi-line boxes (like Any site), so
a shared link is shown in full; one link per line:
  - video links -> "Get qualities" (full flow, uses the first link) or "Quick
    Download" (skip the list-formats step, jump straight to a height-capped
    format). With several links every link gets its own GitHub run.
  - playlist link (the first link is used) -> "Choose videos from playlist"
    lists the video titles to tick (Select all / Clear), then downloads only
    the chosen ones; or the "This is a playlist" quick-quality buttons, which
    download every video in the playlist at the closest available quality
    with no per-video prompting
"""
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core.links import split_links
from screens.common import back_button, paste_row

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
    ("Best", 99999, False),
]

_BOX_HEIGHT = dp(130)


def _first_link(text):
    """The first link of a multi-line box (or the plain text when it has no http link)."""
    links = split_links(text)
    return links[0] if links else (text or "").strip()


def build(nav, video_url="", playlist_url=""):
    nav.clear()
    nav.add(Label(text="YouTube Download", size_hint_y=None, height=44))

    # -- single video(s) -----------------------------------------------------
    single_url_input = TextInput(
        text=video_url, hint_text="YouTube video links (one per line)", multiline=True,
        size_hint_y=None, height=_BOX_HEIGHT,
    )
    nav.add(single_url_input)
    nav.add(paste_row(single_url_input, append=True))

    fetch_btn = Button(text="Get qualities (single video)", size_hint_y=None, height=56)
    fetch_btn.bind(on_press=lambda i: nav.handle_fetch_single(single_url_input.text, False))
    nav.add(fetch_btn)

    nav.add(Label(text="Quick Download (every link = its own run)", size_hint_y=None, height=32))
    for label, format_id in _QUICK_SINGLE_QUALITIES:
        btn = Button(text=label, size_hint_y=None, height=48)
        btn.bind(on_press=lambda i, fid=format_id: nav.start_downloads(single_url_input.text, fid, False))
        nav.add(btn)
    audio_only_btn = Button(text="Audio only (MP3)", size_hint_y=None, height=48)
    audio_only_btn.bind(on_press=lambda i: nav.start_downloads(single_url_input.text, "bestaudio", True))
    nav.add(audio_only_btn)

    # -- playlist -----------------------------------------------------------
    playlist_url_input = TextInput(
        text=playlist_url, hint_text="YouTube playlist link", multiline=True,
        size_hint_y=None, height=_BOX_HEIGHT,
    )
    nav.add(playlist_url_input)
    nav.add(paste_row(playlist_url_input, append=True))

    pick_btn = Button(text="Choose videos from playlist", size_hint_y=None, height=56)
    pick_btn.bind(on_press=lambda i: nav.handle_pick_playlist(_first_link(playlist_url_input.text)))
    nav.add(pick_btn)

    nav.add(Label(text="This is a playlist (all videos)", size_hint_y=None, height=32))
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


def _start_playlist_quality(nav, url_input, target_height, want_hdr, audio_only):
    url = _first_link(url_input.text)
    if not url:
        nav.set_status("Enter a playlist link")
        return
    nav.start_playlist_from_link(url, target_height, want_hdr, audio_only)
