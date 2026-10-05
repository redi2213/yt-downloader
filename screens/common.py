"""Small, purely-visual helpers shared by several screens - building a
label/button is not worth its own file per screen, but repeating the same
five lines everywhere is worse. Nothing here knows about services or
business logic; it only builds and wires widgets.
"""
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
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


# Sizes follow the phone's screen density (dp/sp), not raw pixels: a 48 px
# button is only ~17 dp tall on a modern phone - too small to hit with a
# thumb, and too short for the text it holds.
PAD = dp(10)        # outer padding of the content area
GAP = dp(10)        # space between stacked widgets
BTN_H = dp(46)      # a tappable button
SMALL_BTN_H = dp(40)


def font_px():
    """Height in pixels of the default label font (15sp)."""
    return sp(15)


def line_height(lines=1):
    """Pixel height of ``lines`` lines of default-size text."""
    return int(lines * font_px() * 1.35)


CARD = (0.14, 0.14, 0.17, 1)       # list item background
CARD_ON = (0.12, 0.40, 0.22, 1)    # a selected list item


def paint_card(widget, rgba=CARD):
    """Gives a layout a coloured background (so list items are visibly
    separate from each other) and returns the Color, whose ``rgba`` can be
    changed later - e.g. to show a selection."""
    from kivy.graphics import Color, Rectangle
    with widget.canvas.before:
        color = Color(*rgba)
        rect = Rectangle(pos=widget.pos, size=widget.size)

    def _update(*_args):
        rect.pos = widget.pos
        rect.size = widget.size

    widget.bind(pos=_update, size=_update)
    return color


def card_box(child_heights, padding=None, spacing=None):
    """A vertical layout sized to hold children of the given heights. Its
    height follows its children exactly (minimum_height) when Kivy can."""
    padding = dp(8) if padding is None else padding
    spacing = dp(8) if spacing is None else spacing
    box = BoxLayout(orientation="vertical", size_hint_y=None, padding=padding, spacing=spacing)
    box.height = 2 * padding + sum(child_heights) + spacing * max(0, len(child_heights) - 1)
    try:
        box.bind(minimum_height=box.setter("height"))
    except Exception:
        pass
    return box


def back_button(nav, text="Back"):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: nav.show_home())
    return btn


def content_width():
    # The app is portrait-locked and content width is always the window
    # width minus the outer padding (set when building the root layout).
    return Window.width - 2 * PAD


def wrapped_label_height(text, extra_padding=12, width=None):
    """Estimates wrapped line count up front instead of binding to
    texture_size - avoids any live layout feedback loop entirely. Based on
    the real font size, so it holds on any screen density (an average
    character is ~0.6 of the font height wide; a line is ~1.35 high)."""
    width = width or content_width()
    chars_per_line = max(8, int(width / (font_px() * 0.6)))
    wrapped_lines = sum(
        max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        for line in text.split("\n")
    )
    return line_height(wrapped_lines) + extra_padding


def wrapped_label(text, height=None, halign="left", valign="top"):
    height = height if height is not None else wrapped_label_height(text)
    label = Label(text=text, size_hint_y=None, height=height, halign=halign, valign=valign)
    label.text_size = (content_width(), None)
    return label


_MARKUP_RE = __import__("re").compile(r"\[/?(?:color|b|i|u|s|size|font|ref|anchor|sub|sup)[^\]]*\]")


def fit_height(widget):
    """Makes sure a fixed-height label or button is tall enough for its text
    (lines, wrapping and - for buttons - a comfortable touch height) so text
    never spills into its neighbours. Only grows a widget, never shrinks it."""
    if getattr(widget, "size_hint_y", 1) is not None:
        return
    if not isinstance(widget, Label):
        return
    text = widget.text if isinstance(widget.text, str) else ""
    text = _MARKUP_RE.sub("", text)
    text_size = getattr(widget, "text_size", None)
    width = text_size[0] if text_size and text_size[0] else None
    pad = dp(18) if isinstance(widget, Button) else dp(6)
    if width:
        need = wrapped_label_height(text, extra_padding=pad, width=width)
    else:
        need = line_height(text.count("\n") + 1) + pad
    floor = BTN_H if isinstance(widget, Button) else 0
    widget.height = max(widget.height, need, floor)


def build_working_screen(nav, message, back_text="Back (job keeps running)",
                          on_cancel=None, extra_buttons=None, job=None):
    """The screen shown while a background job runs. "Back" just navigates
    home - the job keeps running regardless, and writes its result into the
    job manager so 'check on last job' can pick it up later. If on_cancel is
    given, a Cancel button is also shown."""
    nav.clear()
    label = Label(text=message, size_hint_y=None, height=line_height(2) + 12)
    nav.add(label)
    nav.set_status_label(label)

    if job is not None:
        github_btn = Button(text="Open run on GitHub", size_hint_y=None, height=BTN_H)
        github_btn.bind(on_press=lambda i: nav.open_job_on_github(job))
        nav.add(github_btn)

    back_btn = Button(text=back_text, size_hint_y=None, height=BTN_H)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)

    if on_cancel is not None:
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=BTN_H)
        cancel_btn.bind(on_press=lambda i: on_cancel())
        nav.add(cancel_btn)

    for btn_text, callback in (extra_buttons or []):
        btn = Button(text=btn_text, size_hint_y=None, height=BTN_H)
        btn.bind(on_press=lambda i, cb=callback: cb())
        nav.add(btn)

    if job is not None:
        add_run_progress_panel(nav, job)


def add_run_progress_panel(nav, job):
    """"Run progress" under a job's working screen: the run's steps as
    buttons (tap one to see the last lines of its log), the last line of the
    log, and Refresh at the bottom. It refreshes by itself every few seconds
    while this screen is shown (the timer stops when the screen changes)."""
    nav.add(Label(text="Run progress", size_hint_y=None, height=BTN_H))

    steps_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
    steps_box.height = BTN_H
    steps_box.bind(minimum_height=steps_box.setter("height"))
    waiting = Label(text="Waiting for the run to start...", size_hint_y=None, height=BTN_H)
    steps_box.add_widget(waiting)
    last_label = Label(text="", size_hint_y=None, height=BTN_H, halign="left", valign="top")
    last_label.text_size = (content_width(), None)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=BTN_H)
    nav.add(steps_box)
    nav.add(last_label)
    nav.add(refresh_btn)

    busy = {"on": False}
    origin = f"job:{job.job_id}"

    def show_waiting(text):
        steps_box.clear_widgets()
        steps_box.add_widget(Label(text=text, size_hint_y=None, height=BTN_H))
        steps_box.height = BTN_H

    def apply(payload):
        busy["on"] = False
        if not payload.get("ok"):
            last_label.text = payload.get("error", "Could not load progress")
            last_label.height = wrapped_label_height(last_label.text)
            return
        current = payload.get("job")
        if current:
            steps_box.clear_widgets()
            total = 0
            shown = 0
            for step in current.get("steps", []):
                if step.get("conclusion") == "skipped":
                    continue
                text, kind = run_labels.step_text(step)
                height = wrapped_label_height(text, extra_padding=dp(18))
                btn = Button(text=text, size_hint_y=None, height=height, halign="left",
                             valign="middle", background_color=STATUS_COLORS[kind])
                btn.text_size = (content_width() - dp(16), None)
                btn.bind(on_press=lambda i, jid=current["id"], n=step.get("number"):
                         nav.show_step_log(job.run_id, jid, n, origin))
                steps_box.add_widget(btn)
                total += height
                shown += 1
            if not shown:
                show_waiting("No steps yet")
            else:
                steps_box.height = total + dp(6) * (shown - 1)
        line = payload.get("last_line")
        last_label.text = f"Last line: {line}" if line else "Last line: not available yet"
        last_label.height = wrapped_label_height(last_label.text)

    def refresh(*_args):
        run_id = job.run_id
        if not run_id:
            return
        if busy["on"]:
            return
        busy["on"] = True
        nav.load_run_progress(run_id, lambda payload: nav.schedule(lambda: apply(payload)))
        if job.is_done:
            nav.stop_progress_timer()

    refresh_btn.bind(on_press=refresh)
    nav.start_progress_timer(refresh)
