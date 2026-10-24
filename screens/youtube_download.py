"""YouTube Download screen: the home menu's first entry.

ONE smart link box (tall and multi-line, like Any site; one link per line).
What is in the box decides which buttons appear below it, so the screen stays
short:
  - video link(s)   -> "Get qualities" (full flow, uses the first link) or
    "Quick Download" (jump straight to a height-capped format; with several
    links every link gets its own GitHub run). A single video also offers
    "More from this video's channel": the latest / most viewed videos of the
    channel the video belongs to.
  - playlist link   -> "Choose videos from playlist" (tick the ones you want)
    or the quick-quality buttons that download every video of the playlist.
    A video link that carries a playlist (watch?v=..&list=..) shows both.
  - channel / page link -> latest or most viewed videos, then tick the ones
    you want.
core/youtube_links.py decides what a link is.
"""
import threading

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import youtube_links
from screens.common import GAP, back_button, paste_row

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
_REFRESH_DELAY = 0.35   # seconds after the last key before the buttons change


def build(nav, video_url="", playlist_url=""):
    nav.clear()
    nav.add(Label(text="YouTube Download", size_hint_y=None, height=44))

    box = TextInput(
        text="\n".join(t for t in (video_url, playlist_url) if t),
        hint_text="YouTube link (video, playlist or channel)", multiline=True,
        size_hint_y=None, height=_BOX_HEIGHT,
    )
    nav.add(box)
    nav.add(paste_row(box, append=True))

    # shared by the channel buttons (channel link, or the channel of a video)
    count_input = TextInput(
        text="30", hint_text="How many videos (1-500)", multiline=False, input_filter="int",
        size_hint_y=None, height=48,
    )

    # the part that changes with the link
    section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    section.bind(minimum_height=section.setter("height"))
    nav.add(section)

    def refresh(*_args):
        section.clear_widgets()
        _fill(section, nav, box, count_input)

    pending = []

    def on_text(_instance, _value):
        if pending:
            pending[0].cancel()
        pending[:] = [Clock.schedule_once(refresh, _REFRESH_DELAY)]

    box.bind(text=on_text)
    refresh()

    nav.add(back_button(nav))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)


def _add_label(section, text):
    section.add_widget(Label(text=text, size_hint_y=None, height=32))


def _add_button(section, text, on_press, height=48):
    btn = Button(text=text, size_hint_y=None, height=height)
    btn.bind(on_press=on_press)
    section.add_widget(btn)


def _fill(section, nav, box, count_input):
    info = youtube_links.analyze(box.text)
    if not info["has_links"]:
        _add_label(section, "Paste a YouTube link: a video, a playlist or a channel")
        return
    if not (info["videos"] or info["playlist"] or info["channel"]):
        _add_label(section, "This is not a YouTube link")
        return

    other = nav.run_mode_other_side()
    other_name = "this phone" if other == "phone" else "GitHub"

    # -- video(s) ------------------------------------------------------------
    if info["videos"]:
        _add_label(section, "Video link detected")
        _add_button(section, "Get qualities (single video)",
                    lambda i: nav.handle_fetch_single(_videos_text(box), False), 56)
        # the Settings default ("Run on") decides where the button above runs; this
        # one runs just this step on the other side
        _add_button(section, f"Get qualities on {other_name}",
                    lambda i: nav.handle_fetch_single(_videos_text(box), False, where=other))
        _add_label(section, "Quick Download (every link = its own run)")
        for label, format_id in _QUICK_SINGLE_QUALITIES:
            _add_button(section, label,
                        lambda i, fid=format_id: nav.start_downloads(_videos_text(box), fid, False))
        _add_button(section, "Audio only (MP3)",
                    lambda i: nav.start_downloads(_videos_text(box), "bestaudio", True))

    # -- playlist --------------------------------------------------------------
    if info["playlist"]:
        _add_label(section, "Playlist link detected")
        _add_button(section, "Choose videos from playlist",
                    lambda i: nav.handle_pick_playlist(_playlist_link(box)), 56)
        _add_button(section, f"Choose videos on {other_name}",
                    lambda i: nav.handle_pick_playlist(_playlist_link(box), where=other))
        _add_label(section, "This is a playlist (all videos)")
        for label, target_height, want_hdr in _PLAYLIST_QUALITIES:
            _add_button(section, label,
                        lambda i, h=target_height, hd=want_hdr:
                        _start_playlist_quality(nav, box, h, hd, audio_only=False))
        _add_button(section, "Audio only (MP3)",
                    lambda i: _start_playlist_quality(nav, box, 0, False, audio_only=True))

    # -- channel / page: its own link, or the channel of a single video ---------
    if info["channel"]:
        _add_label(section, "Channel or page link detected")
        _add_label(section, "Channel or page videos (latest / most viewed)")
        section.add_widget(count_input)
        _add_button(section, "Choose from latest videos",
                    lambda i: nav.handle_pick_channel(_channel_link(box), "latest", count_input.text), 56)
        _add_button(section, "Choose from most viewed videos",
                    lambda i: nav.handle_pick_channel(_channel_link(box), "popular", count_input.text), 56)
    elif len(info["videos"]) == 1:
        _add_label(section, "More from this video's channel (latest / most viewed)")
        section.add_widget(count_input)
        _add_button(section, "Choose from latest videos",
                    lambda i: _pick_video_channel(nav, _videos_links(box), "latest", count_input.text), 56)
        _add_button(section, "Choose from most viewed videos",
                    lambda i: _pick_video_channel(nav, _videos_links(box), "popular", count_input.text), 56)


# What the box holds right now (read when a button is pressed, not when it was drawn)
def _videos_links(box):
    return youtube_links.analyze(box.text)["videos"]


def _videos_text(box):
    return "\n".join(_videos_links(box))


def _playlist_link(box):
    return youtube_links.analyze(box.text)["playlist"] or ""


def _channel_link(box):
    return youtube_links.analyze(box.text)["channel"] or ""


def _start_playlist_quality(nav, box, target_height, want_hdr, audio_only):
    url = _playlist_link(box)
    if not url:
        nav.set_status("Enter a playlist link")
        return
    nav.start_playlist_from_link(url, target_height, want_hdr, audio_only)


def _pick_video_channel(nav, videos, sort, count_text):
    """Finds the channel the (single) video belongs to, then lists its latest /
    most viewed videos like a pasted channel link would."""
    if len(videos) != 1:
        nav.set_status("Enter a YouTube link")
        return
    text = str(count_text or "").strip()
    if not text.isdigit() or not (1 <= int(text) <= 500):
        nav.set_status("Type how many videos: a number from 1 to 500")
        return
    nav.set_status("Finding the channel of this video...")

    def work():
        channel = youtube_links.channel_url_from_video(videos[0])

        def done():
            if channel:
                nav.handle_pick_channel(channel, sort, text)
            else:
                nav.set_status("Could not find the channel of this video")

        nav.schedule(done)

    threading.Thread(target=work, daemon=True).start()
