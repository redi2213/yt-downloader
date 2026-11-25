from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput

from kivy.metrics import dp

from core import cron_text, i18n, run_labels
from core.config import LOCAL_UTC_OFFSET_MINUTES, run_url
from services import runs_service
from services import actions_service
from screens import dialogs
from screens.common import (BTN_H, GAP, STATUS_COLORS, content_width, fa_font_kwargs, fa_text,
                            wrapped_label_height)


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
    reports = Button(text="Playlist reports", size_hint_y=None, height=52)
    reports.bind(on_press=lambda i: nav.show_playlist_reports())
    nav.add(reports)


def add_run_rows(nav, runs, origin="status"):
    """One coloured row per run: tap = its steps, GitHub = open it in the browser."""
    for run in runs:
        word, kind = run_labels.status_word(run["status"], run["conclusion"])
        title = run.get("tool") or run["workflow"]
        if run.get("short_title"):
            title = f"{title} - {run['short_title']}"
        row_width = content_width() * 0.74 - dp(16)
        raw_text = f"{run['created_at']}  {title}\n{word}"
        row_text = fa_text(raw_text, row_width)  # Persian titles joined and in the right order
        row_height = max(BTN_H, wrapped_label_height(row_text, extra_padding=dp(18), width=row_width))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=row_height, spacing=dp(6))
        row_btn = Button(text=row_text, size_hint_x=0.74, halign="left", valign="middle",
                         background_color=STATUS_COLORS[kind], **fa_font_kwargs(raw_text))
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


# (status filter, button text, picker label)
STATUS_CHOICES = (
    (None, "Status: All", "Show all"),
    ("running", "Status: Running", "Only running"),
    ("success", "Status: Success", "Only successful"),
    ("failed", "Status: Failed", "Only failed"),
)
_DANGER = (1.0, 0.55, 0.55, 1)
_ACTIVE_TAB = (0.55, 0.80, 1.0, 1)
_SELECTED_TINT = (0.55, 0.75, 1.0, 1)


def _row(*buttons):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for button in buttons:
        row.add_widget(button)
    return row


def _btn(text, fn, **kwargs):
    button = Button(text=text, **kwargs)
    button.bind(on_press=lambda i: fn())
    return button


def _add_section_tabs(nav, view, cb):
    runs_btn = _btn("Runs", lambda: cb["set"](section="runs"))
    sched_btn = _btn("Scheduled runs", lambda: cb["set"](section="schedule"))
    (sched_btn if view["section"] == "schedule" else runs_btn).background_color = _ACTIVE_TAB
    nav.add(_row(runs_btn, sched_btn))


def _pick_workflow(view, cb):
    options = [(None, "All workflows")]
    for wf in view.get("workflows") or []:
        label = wf["tool"] if wf["tool"] == wf["file"] else f"{wf['tool']}  ({wf['file']})"
        options.append((wf["file"], label))
    dialogs.pick("Choose workflow", options, lambda value: cb["set"](wf=value))


def _pick_status(cb):
    dialogs.pick("Choose status", [(key, label) for key, _text, label in STATUS_CHOICES],
                 lambda value: cb["set"](status=value))


def _ask_days(on_ok):
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    label = Label(text="Delete runs older than how many days?", size_hint_y=None, height=dp(60),
                  halign="center", valign="middle")
    label.text_size = (content_width() * 0.84, None)
    box.add_widget(label)
    field = TextInput(multiline=False, input_filter="int", size_hint_y=None, height=BTN_H)
    box.add_widget(field)
    dialog = ModalView(size_hint=(0.92, None), height=dp(230), background="",
                       background_color=(0.13, 0.10, 0.09, 1))

    def go():
        try:
            days = int(field.text)
        except ValueError:
            return
        if days >= 1:
            dialog.dismiss()
            on_ok(days)

    box.add_widget(_row(_btn("Cancel", dialog.dismiss), _btn("Find runs", go)))
    dialog.add_widget(box)
    dialog.open()


def _cleanup_menu(cb):
    dialogs.menu("Clean up runs", [
        ("Delete failed runs", lambda: cb["cleanup"]("failed", 0), True),
        ("Delete runs older than 7 days", lambda: cb["cleanup"]("older", 7), True),
        ("Delete runs older than 30 days", lambda: cb["cleanup"]("older", 30), True),
        ("Delete runs older than N days...",
         lambda: _ask_days(lambda days: cb["cleanup"]("older", days)), False),
    ])


def _run_cards(nav, runs, view, cb, on_selection_change):
    """One simple card per run: tap = its details (or select it in selection
    mode), hold = start selecting."""
    from screens.history import _PressCard      # a card that tells a tap from a hold
    selected = view["selected"]
    cards = {}
    row_width = content_width() - dp(16)

    def paint(run):
        btn, kind = cards[run["run_id"]]
        btn.background_color = _SELECTED_TINT if run["run_id"] in selected else STATUS_COLORS[kind]

    def toggle(run):
        rid = run["run_id"]
        if rid in selected:
            selected.discard(rid)
        else:
            selected.add(rid)
        paint(run)
        on_selection_change()

    def tap(run):
        if view["select"]:
            toggle(run)
        else:
            nav.show_run_detail({**run, "origin": "status"})

    def hold(run):
        if view["select"]:
            toggle(run)
        else:
            view["select"] = True
            selected.add(run["run_id"])
            cb["rerender"]()

    for run in runs:
        word, kind = run_labels.status_word(run["status"], run["conclusion"])
        title = run.get("tool") or run["workflow"]
        if run.get("short_title"):
            title = f"{title} - {run['short_title']}"
        raw_text = f"{title}\n{word}   {run['created_at']}"
        text = fa_text(raw_text, row_width)
        height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(18), width=row_width))
        btn = _PressCard(on_tap=lambda r=run: tap(r), on_hold=lambda r=run: hold(r), text=text,
                         size_hint_y=None, height=height, halign="left", valign="middle",
                         **fa_font_kwargs(raw_text))
        btn.text_size = (row_width, None)
        cards[run["run_id"]] = (btn, kind)
        paint(run)
        nav.add(btn)


def _selection_bar(nav, runs, view, cb):
    """The bar shown in selection mode; returns the function that refreshes its count."""
    selected = view["selected"]
    count = Label(text="", size_hint_y=None, height=dp(30))
    delete_btn = _btn("Delete selected", lambda: cb["delete_ids"](list(selected)), background_color=_DANGER)

    def refresh():
        count.text = f"{len(selected)} / {len(runs)}"
        delete_btn.disabled = not selected

    def select_all():
        selected.update(r["run_id"] for r in runs)
        cb["rerender"]()

    def clear():
        selected.clear()
        cb["rerender"]()

    def finish():
        selected.clear()
        view["select"] = False
        cb["rerender"]()

    nav.add(_row(_btn("Select all", select_all), _btn("Clear", clear), _btn("Finish selecting", finish)))
    nav.add(count)
    nav.add(_row(delete_btn))
    refresh()
    return refresh


def _build_runs(nav, view, res, cb):
    runs = res.get("runs") or []
    wf_name = run_labels.tool_label(view["wf"]) if view["wf"] else "All workflows"
    status_text = next(text for key, text, _label in STATUS_CHOICES if key == view["status"])
    half = content_width() / 2 - dp(16)
    wf_btn = _btn(f"Workflow: {wf_name}", lambda: _pick_workflow(view, cb),
                  shorten=True, shorten_from="right", halign="center", valign="middle")
    wf_btn.text_size = (half, None)
    nav.add(_row(wf_btn, _btn(status_text, lambda: _pick_status(cb))))

    refresh = lambda: None
    if view["select"]:
        refresh = _selection_bar(nav, runs, view, cb)
    else:
        nav.add(_row(_btn("Select", lambda: (view.update(select=True), cb["rerender"]())),
                     _btn("Clean up", lambda: _cleanup_menu(cb))))

    if not runs:
        nav.add(Label(text="No runs found", size_hint_y=None, height=40))
    _run_cards(nav, runs, view, cb, refresh)

    page = view["page"]
    if page > 1 or res.get("has_next"):
        prev_btn = _btn("Previous", lambda: cb["set"](page=page - 1), disabled=page <= 1)
        next_btn = _btn("Next", lambda: cb["set"](page=page + 1), disabled=not res.get("has_next"))
        nav.add(_row(prev_btn, next_btn))
        nav.add(Label(text=f"Page {page}", size_hint_y=None, height=32))


def _build_schedule(nav, view, res, cb):
    items = res.get("schedules") or []
    if not items:
        nav.add(Label(text="No scheduled workflows", size_hint_y=None, height=40))
    fa = i18n.is_fa()
    width = content_width() * 0.62 - dp(16)
    for wf in items:
        active = wf.get("state") == "active"
        head = wf["tool"] if wf["tool"] == wf["file"] else f"{wf['tool']}  ({wf['file']})"
        lines = [head] + [cron_text.describe(c, LOCAL_UTC_OFFSET_MINUTES, fa) for c in wf["crons"]]
        lines.append(i18n.tr("Active" if active else "Disabled"))
        raw_text = "\n".join(lines)
        text = fa_text(raw_text, width)
        height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(18), width=width))
        info = Button(text=text, size_hint_x=0.62, halign="left", valign="middle",
                      background_color=STATUS_COLORS["ok" if active else "waiting"],
                      **fa_font_kwargs(raw_text))
        info.text_size = (width, None)
        info.bind(on_press=lambda i, f=wf["file"]: cb["set"](section="runs", wf=f, status=None))
        toggle = Button(text="Turn off" if active else "Turn on", size_hint_x=0.38)
        toggle.bind(on_press=lambda i, f=wf["file"], on=active: cb["toggle_wf"](f, not on))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=dp(6))
        row.add_widget(info)
        row.add_widget(toggle)
        nav.add(row)


def build(nav, view, res, cb):
    """The status screen. ``view``: {"wf", "status", "page", "section", "select",
    "selected", "workflows"}; ``res``: runs (+ has_next) or schedules;
    ``cb``: set / reload / rerender / delete_ids / cleanup / toggle_wf."""
    nav.clear()
    _add_job_status_section(nav)
    _add_section_tabs(nav, view, cb)
    note = view.pop("notice", None)
    if note:
        nav.add(Label(text=note, size_hint_y=None, height=36, color=(1, 0.93, 0.6, 1)))
    if view["section"] == "schedule":
        _build_schedule(nav, view, res, cb)
    else:
        _build_runs(nav, view, res, cb)
    _add_browse_buttons(nav)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: cb["reload"]())
    nav.add(refresh_btn)
    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build_deleting(nav, total):
    """Progress screen of a delete; returns the label to update with 'done / total'."""
    nav.clear()
    nav.add(Label(text="Deleting runs...", size_hint_y=None, height=44))
    info = Label(text=f"0 / {total}", size_hint_y=None, height=40)
    nav.add(info)
    return info


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


def _add_log_panel(nav, run_id, jobs, origin="status"):
    """A run without a failure: the same Copy log / Download log buttons, and
    Result (the files the run left behind)."""
    info = Label(text="", size_hint_y=None, height=dp(30), halign="left", valign="top")
    info.text_size = (content_width(), None)

    def show(message):
        def apply(_dt):
            info.text = message
            info.height = max(dp(30), wrapped_label_height(message, extra_padding=dp(8), width=content_width()))
        Clock.schedule_once(apply)

    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    copy_btn = Button(text="Copy log")
    copy_btn.bind(on_press=lambda i: nav.copy_run_log(run_id, jobs, show))
    log_btn = Button(text="Download log")
    log_btn.bind(on_press=lambda i: nav.save_run_log(run_id, jobs, show))
    row.add_widget(copy_btn)
    row.add_widget(log_btn)
    nav.add(row)
    nav.add(info)


def _add_failure_panel(nav, run_id, jobs, origin="status"):
    """A failed run: the failed step on top, a button that copies the error
    text (to paste in the chat) and one that saves the whole job log."""
    job, step = runs_service.find_failure(jobs)
    if job is None:
        _add_log_panel(nav, run_id, jobs)
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


def _live_signature(jobs):
    return tuple((j.get("status"), tuple((s.get("status"), s.get("conclusion")) for s in j.get("steps", [])))
                 for j in jobs)


def _add_live_panel(nav, run_id, jobs, origin):
    """A run that is still going: 'Step 4 of 9 running: name', a button that opens
    its GitHub page (live log) in this app's browser, and a timer that reloads
    the jobs every few seconds and redraws the screen when a step changes (the
    redraw of a finished run shows the full log buttons)."""
    info = run_labels.progress_summary(jobs) or {}
    if info.get("waiting"):
        text = "Waiting for a runner..."
    elif info.get("name"):
        text = f"Step {info['step']} of {info['total']} running: {info['name']}"
    else:
        text = f"Step {info.get('step', 1)} of {info.get('total', 1)} running"
    shaped = fa_text(text, content_width() - dp(16))
    label = Label(text=shaped, size_hint_y=None, color=(1, 0.93, 0.6, 1), halign="left", valign="middle",
                  height=max(BTN_H, wrapped_label_height(shaped, extra_padding=dp(14), width=content_width() - dp(16))),
                  **fa_font_kwargs(text))
    label.text_size = (content_width() - dp(16), None)
    nav.add(label)
    live_btn = Button(text="Live log in browser", size_hint_y=None, height=BTN_H)
    live_btn.bind(on_press=lambda i: nav.show_browser(run_url(run_id)))
    nav.add(live_btn)

    state = {"sig": _live_signature(jobs), "busy": False, "first": True, "event": None}

    def tick():
        if state["first"]:          # start_progress_timer calls once at once: the jobs are fresh
            state["first"] = False
            return
        if state["busy"]:
            return
        state["busy"] = True

        def got(new_jobs):
            def apply():
                state["busy"] = False
                if state["event"] is not getattr(nav, "_progress_event", None):
                    return          # the screen changed meanwhile
                if new_jobs and _live_signature(new_jobs) != state["sig"]:
                    nav.render_run_detail(run_id, new_jobs, origin)
            nav.schedule(apply)

        actions_service.start_load_run_jobs(run_id, on_complete=got)

    nav.start_progress_timer(tick, interval=5)
    state["event"] = getattr(nav, "_progress_event", None)


def _add_help_label(nav, run_id, jobs):
    """Persian explanation of the failure (what it means, what to try), filled
    in a moment later from the failed job's log. The patterns come from
    config.json, so they can be edited without a build."""
    width = content_width() - dp(8)
    label = Label(text="", size_hint_y=None, height=dp(4), halign="right", valign="top",
                  color=(1, 0.93, 0.6, 1))
    label.text_size = (width, None)

    def show(text):
        def apply(_dt):
            if not text:
                label.text, label.height = "", dp(4)
                return
            shaped = fa_text(text, width)
            font = fa_font_kwargs(text)
            if font:
                label.font_name = font["font_name"]
            label.text = shaped
            label.height = wrapped_label_height(shaped, extra_padding=dp(14), width=width)
        Clock.schedule_once(apply)

    nav.add(label)
    nav.load_error_help(run_id, jobs, show)


def _add_rerun_button(nav, run_id, failed=False):
    """Sends the same workflow again with the same inputs (read from the run's
    name); when they cannot be read, the manual-run page opens with them prefilled."""
    btn = Button(text="Run again", size_hint_y=None, height=BTN_H)
    if failed:
        btn.background_color = (1.0, 0.8, 0.5, 1)
    btn.bind(on_press=lambda i: nav.rerun_run(run_id))
    nav.add(btn)


def build_run_detail(nav, run_id, jobs, origin="status"):
    """Every step of the run as a coloured button (green done, yellow running,
    red failed, grey waiting/skipped). Tap a step to see the last lines of
    its log."""
    nav.clear()
    nav.add(Label(text=f"Run #{run_id}", size_hint_y=None, height=40))
    if jobs and any(j.get("status") != "completed" for j in jobs):
        _add_live_panel(nav, run_id, jobs, origin)
    if jobs:
        _add_failure_panel(nav, run_id, jobs, origin)
        failed = runs_service.has_failure(jobs)
        if failed:
            _add_help_label(nav, run_id, jobs)
        _add_rerun_button(nav, run_id, failed=failed)
        if any(j.get("status") != "completed" for j in jobs):
            cancel_btn = Button(text="Cancel run", size_hint_y=None, height=BTN_H,
                                background_color=(1.0, 0.55, 0.55, 1))
            cancel_btn.bind(on_press=lambda i: nav.cancel_run_by_id(run_id, origin))
            nav.add(cancel_btn)
        result_btn = Button(text="Result (files of this run)", size_hint_y=None, height=BTN_H)
        result_btn.bind(on_press=lambda i: nav.show_run_result(run_id))
        nav.add(result_btn)
    if not jobs:
        _add_rerun_button(nav, run_id)
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
