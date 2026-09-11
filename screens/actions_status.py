from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import content_width, wrapped_label_height


def _add_job_status_section(nav):
    """The 'current job' and 'recent jobs' shortcuts that used to live on
    the home screen - shown here since this screen is now the general
    "what's happening with my work" hub."""
    current_job = nav.job_manager.current_job
    if current_job is not None:
        label_text = "Check on last job" if not current_job.is_done else "View last result"
        check_btn = Button(text=label_text, size_hint_y=None, height=48)
        check_btn.bind(on_press=lambda i: nav.resume_job_screen())
        nav.add(check_btn)

    history_count = len(nav.job_manager.history)
    if history_count:
        recent_btn = Button(text=f"Recent jobs ({history_count})", size_hint_y=None, height=48)
        recent_btn.bind(on_press=lambda i: nav.show_job_history())
        nav.add(recent_btn)


def build_loading(nav):
    nav.clear()
    _add_job_status_section(nav)
    nav.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build(nav, runs):
    nav.clear()
    _add_job_status_section(nav)
    nav.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
    if not runs:
        nav.add(Label(text="No runs found", size_hint_y=None, height=40))
    for run in runs:
        status = run["status"]
        status_text = (run["conclusion"] or "unknown") if status == "completed" else status
        row_text = f"{run['created_at']}  [{run['workflow']}]\n{status_text}"
        row_height = wrapped_label_height(row_text, extra_padding=20)
        row_btn = Button(text=row_text, size_hint_y=None, height=row_height, halign="left", valign="top")
        row_btn.text_size = (content_width(), None)
        row_btn.bind(on_press=lambda inst, r=run: nav.show_run_detail(r))
        nav.add(row_btn)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: nav.show_actions_status())
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build_run_detail_loading(nav, run):
    nav.clear()
    nav.add(Label(text=f"[{run['workflow']}]\nrun #{run['run_id']}", size_hint_y=None, height=60))
    nav.add(Label(text="Loading steps...", size_hint_y=None, height=40))
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_actions_status())
    nav.add(back_btn)


def build_run_detail(nav, run_id, steps):
    nav.clear()
    nav.add(Label(text=f"Run #{run_id}", size_hint_y=None, height=40))
    if not steps:
        nav.add(Label(text="Could not load steps", size_hint_y=None, height=40))
    else:
        width = content_width()
        for step in steps:
            name = step.get("name", "?")
            status = step.get("status", "?")
            conclusion = step.get("conclusion") or status
            text = f"{name}\n{conclusion}"
            height = wrapped_label_height(text, extra_padding=20)
            lbl = Label(text=text, size_hint_y=None, height=height, halign="left", valign="top")
            lbl.text_size = (width, None)
            nav.add(lbl)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: nav.show_run_detail({"run_id": run_id, "workflow": ""}))
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_actions_status())
    nav.add(back_btn)
