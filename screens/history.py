from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window

from screens.base import BaseScreen


class HistoryScreen(BaseScreen):

    def show(self):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=f"Recent jobs ({len(app.job_history)})",
                size_hint_y=None,
                height=40
            )
        )

        if not app.job_history:
            self.add(
                Label(
                    text="No jobs yet",
                    size_hint_y=None,
                    height=40
                )
            )

        for job in app.job_history:
            kind = job.get("kind", "?")
            result = job.get("result") or {}

            if result.get("ok"):
                if kind == "playlist_download":
                    n_ok = len(result.get("playlist_results") or [])
                    n_err = len(result.get("playlist_errors") or [])
                    outcome = f"{n_ok} ready, {n_err} failed"
                elif kind in ("formats", "playlist_links"):
                    outcome = "Ready to pick quality"
                else:
                    outcome = "Ready"
            else:
                outcome = result.get("error", "Unknown error")

            label_text = job.get("video_url") or "(upload)"

            if len(label_text) > 45:
                label_text = label_text[:42] + "..."

            content_width = Window.width - 20
            chars_per_line = max(10, int(content_width / 15))

            kind_text = f"[{kind}] {label_text}"

            row = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=130
            )

            row.add_widget(
                Label(
                    text=kind_text,
                    size_hint_y=None,
                    height=40
                )
            )

            row.add_widget(
                Label(
                    text=outcome,
                    size_hint_y=None,
                    height=40
                )
            )

            view_btn = Button(
                text="View",
                size_hint_y=None,
                height=40
            )

            view_btn.bind(
                on_press=lambda x, j=job: app.view_job_from_history(j)
            )

            row.add_widget(view_btn)

            self.add(row)

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda x: app.show_home()
        )

        self.add(back_btn)
