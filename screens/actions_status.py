from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from kivy.metrics import dp

from core import run_labels
from core.config import run_url
from services import runs_service
from screens.common import BTN_H, GAP, STATUS_COLORS, content_width, wrapped_label_height


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
        recent_btn.bind(on_press=lambda i: nav.show_job_history("status"))
        nav.add(recent_btn)


def _add_browse_buttons(nav):
    """The two ways to find an older run: by workflow file (all of the repo's
    workflows, also the ones with no button in the app) or by the app's menus."""
    by_wf = Button(text="Runs by workflow", size_hint_y=None, height=52)
    by_wf.bind(on_press=lambda i: nav.show_workflows_browser())
    nav.add(by_wf)
    by_menu = Button(text="Runs by app menu", size_hint_y=None, height=52)
    by_menu.bind(on_press=lambda i: nav.show_menu_groups_browser())
    nav.add(by_menu)


def add_run_rows(nav, runs, origin="status"):
    """One coloured row per run: tap = its steps, GitHub = open it in the browser."""
    for run in runs:
        word, kind = run_labels.status_word(run["status"], run["conclusion"])
        title = run.get("tool") or run["workflow"]
        if run.get("short_title"):
            title = f"{title} - {run['short_title']}"
        row_text = f"{run['created_at']}  {title}\n{word}"
        row_width = content_width() * 0.74 - dp(16)
        row_height = max(BTN_H, wrapped_label_height(row_text, extra_padding=dp(18), width=row_width))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=row_height, spacing=dp(6))
        row_btn = Button(text=row_text, size_hint_x=0.74, halign="left", valign="middle",
                         background_color=STATUS_COLORS[kind])
        row_btn.text_size = (row_width, None)
        row_btn.bind(on_press=lambda inst, r=run: nav.show_run_detail({**r, "origin": origin}))
        github_btn = Button(text="GitHub", size_hint_x=0.26)
        github_btn.bind(on_press=lambda inst, r=run: nav.open_run_on_github(r["run_id"]))
        row.add_widget(row_btn)
        row.add_widget(github_btn)
        nav.add(row)


def build_loading(nav):
    nav.clear()
    _add_job_status_section(nav)
    _add_browse_buttons(nav)
    nav.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build(nav, runs):
    nav.clear()
    _add_job_status_section(nav)
    _add_browse_buttons(nav)
    nav.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
    if not runs:
        nav.add(Label(text="No runs found", size_hint_y=None, height=40))
    add_run_rows(nav, runs)
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
    origin = run.get("origin", "status")
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.back_from_run_detail(origin))
    nav.add(back_btn)


def _step_text(step):
    return run_labels.step_text(step)


def _add_failure_panel(nav, run_id, jobs, origin="status"):
    """A failed run: the failed step on top, a button that copies the error
    text (to paste in the chat) and one that saves the whole job log."""
    job, step = runs_service.find_failure(jobs)
    if job is None:
        return
    name = (step or {}).get("name") or "the job"
    text = f"Failed step: {name}"
    width = content_width() - dp(16)
    head = Button(text=text, size_hint_y=None,
                  height=max(BTN_H, wrapped_label_height(text, extra_padding=dp(18), width=width)),
                  halign="left", valign="middle", background_color=STATUS_COLORS["fail"])
    head.text_size = (width, None)
    if step and step.get("number"):
        head.bind(on_press=lambda i: nav.show_step_log(run_id, job["id"], step["number"], origin))
    nav.add(head)

    info = Label(text="", size_hint_y=None, height=dp(30), halign="left", valign="top")
    info.text_size = (content_width(), None)

    def show(message):
        def apply(_dt):
            info.text = message
            info.height = max(dp(30), wrapped_label_height(message, extra_padding=dp(8), width=content_width()))
        Clock.schedule_once(apply)

    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    copy_btn = Button(text="Copy error")
    copy_btn.bind(on_press=lambda i: nav.copy_run_error(run_id, jobs, show))
    log_btn = Button(text="Download log")
    log_btn.bind(on_press=lambda i: nav.save_run_log(run_id, jobs, show))
    row.add_widget(copy_btn)
    row.add_widget(log_btn)
    nav.add(row)
    nav.add(info)


def build_run_detail(nav, run_id, jobs, origin="status"):
    """Every step of the run as a coloured button (green done, yellow running,
    red failed, grey waiting/skipped). Tap a step to see the last lines of
    its log."""
    nav.clear()
    nav.add(Label(text=f"Run #{run_id}", size_hint_y=None, height=40))
    if jobs:
        _add_failure_panel(nav, run_id, jobs, origin)
    if not jobs:
        nav.add(Label(text="Could not load steps", size_hint_y=None, height=40))
    else:
        width = content_width()
        for job in jobs:
            if len(jobs) > 1:
                nav.add(Label(text=job.get("name") or "job", size_hint_y=None, height=40))
            for step in job.get("steps", []):
                text, kind = _step_text(step)
                height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(18), width=width - dp(16)))
                btn = Button(text=text, size_hint_y=None, height=height, halign="left",
                             valign="middle", background_color=STATUS_COLORS[kind])
                btn.text_size = (width - dp(16), None)
                btn.bind(on_press=lambda i, jid=job["id"], n=step.get("number"):
                         nav.show_step_log(run_id, jid, n, origin))
                nav.add(btn)
    github_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    github_btn = Button(text="Open on GitHub")
    github_btn.bind(on_press=lambda i: nav.open_run_on_github(run_id))
    copy_btn = Button(text="Copy link")
    copy_btn.bind(on_press=lambda i: Clipboard.copy(run_url(run_id)))
    github_row.add_widget(github_btn)
    github_row.add_widget(copy_btn)
    nav.add(github_row)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: nav.show_run_detail(
        {"run_id": run_id, "workflow": "", "origin": origin}))
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.back_from_run_detail(origin))
    nav.add(back_btn)


def build_step_loading(nav, run_id=None, origin="status"):
    nav.clear()
    nav.add(Label(text="Loading step...", size_hint_y=None, height=60))
    if run_id is not None:
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        if isinstance(origin, str) and origin.startswith("job:"):
            back_btn.bind(on_press=lambda i: nav.back_from_run_detail(origin))
        else:
            back_btn.bind(on_press=lambda i: nav.show_run_detail(
                {"run_id": run_id, "workflow": "", "origin": origin}))
        nav.add(back_btn)


def build_step_log(nav, run_id, job_id, step_number, res, origin="status"):
    """One step: its status, and the last lines of its log. Refresh reloads
    both; Back returns to the run's steps."""
    nav.clear()
    if not res.get("ok"):
        nav.add(Label(text=res.get("error", "Could not load the step"), size_hint_y=None, height=60))
    else:
        step = res["step"]
        text, kind = _step_text(step)
        header = Button(text=text, size_hint_y=None,
                        height=max(BTN_H, wrapped_label_height(text, extra_padding=dp(18), width=content_width() - dp(16))),
                        halign="left", valign="middle", background_color=STATUS_COLORS[kind])
        header.text_size = (content_width() - dp(16), None)
        nav.add(header)

        lines = res.get("lines") or []
        if lines:
            body = "\n".join(lines)
        elif not res.get("log_available"):
            body = ("The log is not available yet.\nGitHub can take a little while to "
                    "provide it. Press Refresh, or use Open on GitHub for the live log.")
        elif not step.get("started_at"):
            body = "This step has not started yet."
        else:
            body = "No output yet."
        nav.add(Label(text="Last lines", size_hint_y=None, height=36))
        log_label = Label(text=body, size_hint_y=None, height=wrapped_label_height(body),
                          halign="left", valign="top")
        log_label.text_size = (content_width(), None)
        nav.add(log_label)
        if lines:
            copy_lines = Button(text="Copy these lines", size_hint_y=None, height=48)
            copy_lines.bind(on_press=lambda i, b=body: Clipboard.copy(b))
            nav.add(copy_lines)

    github_btn = Button(text="Open on GitHub", size_hint_y=None, height=48)
    github_btn.bind(on_press=lambda i: nav.open_run_on_github(run_id))
    nav.add(github_btn)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: nav.show_step_log(run_id, job_id, step_number, origin))
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    # opened from a job's progress panel -> Back returns to that job's screen
    if isinstance(origin, str) and origin.startswith("job:"):
        back_btn.bind(on_press=lambda i: nav.back_from_run_detail(origin))
    else:
        back_btn.bind(on_press=lambda i: nav.show_run_detail(
            {"run_id": run_id, "workflow": "", "origin": origin}))
    nav.add(back_btn)
