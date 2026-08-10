from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import back_button


def build_quality_list(nav, url, formats):
    nav.clear()
    nav.add(Label(text="Choose quality", size_hint_y=None, height=40))
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
    nav.add(back_button(nav))
