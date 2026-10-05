"""The jobs that are running right now. Several can run at once (e.g. two or
three links sent one after another), each with its own status line, so this
screen shows them side by side. Each one can be reopened, inspected
step by step, or opened on GitHub. Refresh is at the bottom - the list is a
snapshot, not live.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import timeutil
from screens.common import content_width


def job_title(job):
    """Short human description of what a job was started with."""
    kind = job.type or "?"
    value = job.input
    action = (job.extra or {}).get("action") or {}
    if isinstance(value, dict):
        # dynamic action: show the tool and its first value
        first = next((str(v) for v in value.values() if v), "")
        kind = action.get("title") or kind
        value = first
    elif isinstance(value, (list, tuple)):
        value = f"{len(value)} videos"
    value = str(value) if value else ""
    if len(value) > 45:
        value = value[:42] + "..."
    return f"[{kind}] {value}".strip()


def build(nav):
    nav.clear()
    jobs = nav.job_manager.active_jobs
    nav.add(Label(text=f"Running jobs ({len(jobs)})", size_hint_y=None, height=40))
    if not jobs:
        nav.add(Label(text="No jobs running", size_hint_y=None, height=40))

    width = content_width()
    chars_per_line = max(10, int(width / 15))

    for job in jobs:
        status = job.status or "starting"
        if status == "starting" and not job.run_id:
            status = "waiting for the run to appear"
        started = timeutil.datetime_to_local(job.created_at, "%H:%M")
        if started:
            status = f"{status} - started {started}"
        text = f"{job_title(job)}\n{status}"
        lines = sum(max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                    for line in text.split("\n"))
        text_height = lines * 40 + 12
        row = BoxLayout(orientation="vertical", size_hint_y=None,
                        height=text_height + 44 + 6 + 8, spacing=2, padding=(0, 4))
        label = Label(text=text, size_hint_y=None, height=text_height,
                      halign="left", valign="top", text_size=(width, None))
        row.add_widget(label)

        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
        open_btn = Button(text="Open")
        open_btn.bind(on_press=lambda i, j=job: nav.view_job_from_history(j))
        steps_btn = Button(text="Steps")
        steps_btn.bind(on_press=lambda i, j=job: nav.show_job_steps(j))
        github_btn = Button(text="GitHub")
        github_btn.bind(on_press=lambda i, j=job: nav.open_job_on_github(j))
        buttons.add_widget(open_btn)
        buttons.add_widget(steps_btn)
        buttons.add_widget(github_btn)
        row.add_widget(buttons)
        nav.add(row)

    status_label = Label(text="", size_hint_y=None, height=32)
    nav.add(status_label)
    nav.set_status_label(status_label)

    history_count = len(nav.job_manager.history)
    if history_count:
        recent_btn = Button(text=f"Recent jobs ({history_count})", size_hint_y=None, height=48)
        recent_btn.bind(on_press=lambda i: nav.show_job_history())
        nav.add(recent_btn)

    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: nav.show_running_jobs())
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)
