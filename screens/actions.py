import threading

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.base import BaseScreen
from backend.github_api import (
    get_recent_runs,
    get_run_steps,
    GitHubAuthError,
)


class ActionsScreen(BaseScreen):

    def show(self):
        self.clear()

        app = self.app

        self.add(
            Label(
                text="Recent GitHub Actions runs",
                size_hint_y=None,
                height=40
            )
        )

        self.add(
            Label(
                text="Loading...",
                size_hint_y=None,
                height=40
            )
        )

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )
        back_btn.bind(on_press=lambda i: app.show_home())
        self.add(back_btn)

        threading.Thread(
            target=self.load_thread,
            daemon=True
        ).start()

    def load_thread(self):
        app = self.app
        try:
            runs = get_recent_runs()
            Clock.schedule_once(
                lambda dt: self.render(runs)
            )
        except GitHubAuthError:
            Clock.schedule_once(
                lambda dt: app.show_result(
                    "GitHub token invalid or expired. Update it and retry."
                )
            )
        except Exception as e:
            Clock.schedule_once(
                lambda dt: app.show_result(
                    f"Could not fetch status: {str(e)[:60]}"
                )
            )

    def render(self, runs):
        self.clear()

        app = self.app

        self.add(
            Label(
                text="Recent GitHub Actions runs",
                size_hint_y=None,
                height=40
            )
        )

        if not runs:
            self.add(
                Label(
                    text="No runs found",
                    size_hint_y=None,
                    height=40
                )
            )

        content_width = Window.width - 20
        chars_per_line = max(10, int(content_width / 15))

        for run in runs:
            status = run["status"]

            if status == "completed":
                status_text = run["conclusion"] or "unknown"
            else:
                status_text = status

            text = f"{run['created_at']}  [{run['workflow']}]\n{status_text}"

            lines = text.count("\n") + 1
            wrapped = sum(
                max(1, (len(x)+chars_per_line-1)//chars_per_line)
                for x in text.split("\n")
            )

            btn = Button(
                text=text,
                size_hint_y=None,
                height=max(lines, wrapped)*40+20,
                halign="left",
                valign="top"
            )

            btn.text_size = (content_width, None)
            btn.bind(
                on_press=lambda i, r=run: self.show_detail(r)
            )

            self.add(btn)

        refresh = Button(
            text="Refresh",
            size_hint_y=None,
            height=48
        )
        refresh.bind(on_press=lambda i: self.show())
        self.add(refresh)

        back = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )
        back.bind(on_press=lambda i: app.show_home())
        self.add(back)

    def show_detail(self, run):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=f"[{run['workflow']}]\nrun #{run['run_id']}",
                size_hint_y=None,
                height=60
            )
        )

        self.add(
            Label(
                text="Loading steps...",
                size_hint_y=None,
                height=40
            )
        )

        threading.Thread(
            target=self.load_steps,
            args=(run["run_id"],),
            daemon=True
        ).start()

    def load_steps(self, run_id):
        try:
            steps = get_run_steps(run_id)
        except Exception:
            steps = None

        Clock.schedule_once(
            lambda dt: self.render_steps(run_id, steps)
        )

    def render_steps(self, run_id, steps):
        self.clear()

        self.add(
            Label(
                text=f"Run #{run_id}",
                size_hint_y=None,
                height=40
            )
        )

        if not steps:
            self.add(
                Label(
                    text="Could not load steps",
                    size_hint_y=None,
                    height=40
                )
            )

        else:
            for step in steps:
                text = f"{step.get('name','?')}\n{step.get('conclusion') or step.get('status','?')}"

                self.add(
                    Label(
                        text=text,
                        size_hint_y=None,
                        height=80
                    )
                )

        back = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )
        back.bind(on_press=lambda i: self.show())
        self.add(back)
