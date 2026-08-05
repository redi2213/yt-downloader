from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.base import BaseScreen


class DownloadScreen(BaseScreen):

    def show_quality_list(self, url, formats):
        self.clear()

        app = self.app

        self.add(
            Label(
                text="Choose quality",
                size_hint_y=None,
                height=40
            )
        )

        for fmt_id, label, size_label, codec_label in formats:
            details = []

            if size_label:
                details.append(f"~{size_label}")

            if codec_label:
                details.append(codec_label)

            btn_text = (
                f"{label} ({', '.join(details)})"
                if details
                else label
            )

            btn = Button(
                text=btn_text,
                size_hint_y=None,
                height=50
            )

            btn.bind(
                on_press=lambda inst, fid=fmt_id:
                app.start_download(
                    url,
                    fid,
                    audio_only=False,
                    formats_for_reselect=formats
                )
            )

            self.add(btn)

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda i: app.show_home()
        )

        self.add(back_btn)
