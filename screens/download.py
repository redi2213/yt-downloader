from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import back_button, wrapped_label


def build_quality_list(nav, url, formats, from_phone=False, on_github=None):
    """The quality buttons. ``from_phone``: the list was read by the phone - it
    has heights (and sizes) but no codec choice, so a button offers the full
    GitHub list."""
    nav.clear()
    nav.add(Label(text="Choose quality", size_hint_y=None, height=40))
    if from_phone:
        nav.add(wrapped_label("Read on this phone. Every quality uses the closest "
                              "available height; for exact codecs use the GitHub list."))
        if on_github:
            full_btn = Button(text="Full list from GitHub (codecs)", size_hint_y=None, height=50)
            full_btn.bind(on_press=lambda i: on_github())
            nav.add(full_btn)
    for fmt_id, label, size_label, codec_label in formats:
        details = []
        if size_label:
            details.append(f"~{size_label}")
        if codec_label:
            details.append(codec_label)
        btn_text = f"{label} ({', '.join(details)})" if details else label
        btn = Button(text=btn_text, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, fid=fmt_id: nav.start_download(
            url, fid, False, formats_for_reselect=formats))
        nav.add(btn)
    # back to the YouTube Download screen, with the link still filled in
    nav.add(back_button(nav, to=lambda: nav.show_youtube_download(video_url=url)))
