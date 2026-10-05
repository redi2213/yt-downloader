"""Small, purely-visual helpers shared by several screens - building a
label/button is not worth its own file per screen, but repeating the same
five lines everywhere is worse. Nothing here knows about services or
business logic; it only builds and wires widgets.
"""
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label

from core import run_labels

# Button tints by status kind (see run_labels.status_word): the button's
# normal grey background is multiplied by these.
STATUS_COLORS = {
    "ok": (0.45, 0.85, 0.50, 1),
    "fail": (0.95, 0.45, 0.45, 1),
    "running": (1.0, 0.85, 0.35, 1),
    "waiting": (0.80, 0.80, 0.85, 1),
    "other": (0.75, 0.75, 0.80, 1),
}


def back_button(nav, text="Back"):
    btn = Button(text=text, size_hint_y=None, height=48)
    btn.bind(on_press=lambda i: nav.show_home())
    return btn


def content_width():
    # The app is portrait-locked and content width is always the window
    # width minus the outer padding (10px each side, set when building the
    # root layout).
    return Window.width - 20


def wrapped_label_height(text, extra_padding=12):
    """Estimates wrapped line count up front instead of binding to
    texture_size - avoids any live layout feedback loop entirely.
    ~15px average character width at the default font size."""
    width = content_width()
    chars_per_line = max(10, int(width / 15))
    explicit_lines = text.count("\n") + 1
    wrapped_lines = sum(
        max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        for line in text.split("\n")
    )
    return max(explicit_lines, wrapped_lines) * 40 + extra_padding


def wrapped_label(text, height=None, halign="left", valign="top"):
    height = height if height is not None else wrapped_label_height(text)
    label = Label(text=text, size_hint_y=None, height=height, halign=halign, valign=valign)
    label.text_size = (content_width(), None)
    return label


def build_working_screen(nav, message, back_text="Back (job keeps running)",
                          on_cancel=None, extra_buttons=None, job=None):
    """The screen shown while a background job runs. "Back" just navigates
    home - the job keeps running regardless, and writes its result into the
    job manager so 'check on last job' can pick it up later. If on_cancel is
    given, a Cancel button is also shown."""
    nav.clear()
    label = Label(text=message, size_hint_y=None, height=60)
    nav.add(label)
    nav.set_status_label(label)

    if job is not None:
        github_btn = Button(text="Open run on GitHub", size_hint_y=None, height=48)
        github_btn.bind(on_press=lambda i: nav.open_job_on_github(job))
        nav.add(github_btn)

    back_btn = Button(text=back_text, size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)

    if on_cancel is not None:
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: on_cancel())
        nav.add(cancel_btn)

    for btn_text, callback in (extra_buttons or []):
        btn = Button(text=btn_text, size_hint_y=None, height=48)
        btn.bind(on_press=lambda i, cb=callback: cb())
        nav.add(btn)

    if job is not None:
        add_run_progress_panel(nav, job)


def add_run_progress_panel(nav, job):
    """"Run progress" under a job's working screen: the run's steps with
    their status and the last line of its log. Refreshes by itself every few
    seconds while this screen is shown (the timer stops when the screen
    changes) and has a Refresh button at the bottom."""
    nav.add(Label(text="Run progress", size_hint_y=None, height=40))

    steps_label = Label(text="Waiting for the run to start...", markup=True,
                        size_hint_y=None, height=52, halign="left", valign="top")
    steps_label.text_size = (content_width(), None)
    last_label = Label(text="", size_hint_y=None, height=52, halign="left", valign="top")
    last_label.text_size = (content_width(), None)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    nav.add(steps_label)
    nav.add(last_label)
    nav.add(refresh_btn)

    busy = {"on": False}

    def apply(payload):
        busy["on"] = False
        if not payload.get("ok"):
            last_label.text = payload.get("error", "Could not load progress")
            last_label.height = wrapped_label_height(last_label.text)
            return
        current = payload.get("job")
        if current:
            text, count = run_labels.progress_markup(current)
            steps_label.text = text or "No steps yet"
            steps_label.height = max(1, count) * 40 + 12
        line = payload.get("last_line")
        last_label.text = f"Last line: {line}" if line else "Last line: not available yet"
        last_label.height = wrapped_label_height(last_label.text)

    def refresh(*_args):
        run_id = job.run_id
        if not run_id:
            steps_label.text = "Waiting for the run to start..."
            return
        if busy["on"]:
            return
        busy["on"] = True
        nav.load_run_progress(run_id, lambda payload: nav.schedule(lambda: apply(payload)))
        if job.is_done:
            nav.stop_progress_timer()

    refresh_btn.bind(on_press=refresh)
    nav.start_progress_timer(refresh)
