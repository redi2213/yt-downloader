from kivy.uix.button import Button
from kivy.uix.label import Label

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

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda x: app.show_home()
        )

        self.add(back_btn)
