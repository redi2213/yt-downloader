"""Small, purely-visual helpers shared by several screens - building a
label/button is not worth its own file per screen, but repeating the same
five lines everywhere is worse. Nothing here knows about services or
business logic; it only builds and wires widgets.
"""
import os
import textwrap

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


def paste_row(text_input, append=False):
    """A "Paste" / "Clear" button row for a text box.

    The phone's own long-press Paste bubble does not appear inside the app,
    so the app reads the clipboard itself. ``append=True`` (several links in
    one box): pasted text goes on a new line after what is already there.
    Otherwise it replaces the box content (newlines become spaces)."""
    from kivy.core.clipboard import Clipboard

    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=GAP)
    paste_btn = Button(text="Paste")
    clear_btn = Button(text="Clear")

    def _paste(_instance):
        try:
            data = Clipboard.paste() or ""
        except Exception:
            data = ""
        data = data.replace("\r", "").strip()
        if not data:
            return
        if append:
            current = text_input.text.rstrip()
            text_input.text = f"{current}\n{data}" if current else data
        else:
            text_input.text = " ".join(data.split())

    def _clear(_instance):
        text_input.text = ""

    paste_btn.bind(on_press=_paste)
    clear_btn.bind(on_press=_clear)
    row.add_widget(paste_btn)
    row.add_widget(clear_btn)
    return row


def back_button(nav, text="Back", to=None):
    """A Back button. ``to`` is a function (no arguments) that opens the
    PARENT screen - every screen passes its own parent so Back goes exactly
    one screen back. Without ``to`` it goes to the home menu (only right for
    screens that are opened straight from home)."""
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: (to or nav.show_home)())
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
    """The screen shown while a background job runs. "Back" returns to the
    screen the job was started from - the job keeps running regardless, and writes its result into the
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
    back_btn.bind(on_press=lambda i: nav.back_from_working())
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


# ---- Persian / Arabic text ---------------------------------------------------
# Kivy draws text left to right with every letter in its separate form, so
# Persian shows as loose, reversed letters. For DISPLAY ONLY (the real title
# stays untouched) the text is joined (arabic_reshaper) and put in visual
# order (python-bidi), and drawn with a font that has the Arabic letters.
# If those two packages are not in the build the text is shown as it is.
_FONT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "assets", "fonts", "DejaVuSans.ttf")
FA_FONT = _FONT_FILE if os.path.exists(_FONT_FILE) else None

try:
    from arabic_reshaper import reshape as _reshape
    from bidi.algorithm import get_display as _get_display
except Exception:   # not installed: show the raw text
    _reshape = _get_display = None


def has_rtl(text):
    return any("\u0600" <= c <= "\u06ff" or "\u0750" <= c <= "\u077f" or "\ufb50" <= c <= "\ufeff"
               for c in (text or ""))


def fa_text(text, width=None):
    """Display form of ``text``. Text without Persian/Arabic letters is
    returned unchanged. Otherwise it is cut into lines that fit ``width``
    (pixels) first and each line is shaped on its own, so the lines stay in
    the right order."""
    if not text or not has_rtl(text) or _reshape is None:
        return text
    width = width or content_width()
    chars = max(8, int(width / (font_px() * 0.65)))
    lines = []
    for part in text.split("\n"):
        for line in (textwrap.wrap(part, chars) or [""]):
            lines.append(_get_display(_reshape(line)))
    return "\n".join(lines)


def fa_font_kwargs(text):
    """``font_name`` for a label/button that shows ``text`` (nothing for
    plain English text: it keeps the app's normal font)."""
    return {"font_name": FA_FONT} if (FA_FONT and has_rtl(text) and _reshape is not None) else {}
