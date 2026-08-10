"""Small, purely-visual helpers shared by several screens - building a
label/button is not worth its own file per screen, but repeating the same
five lines everywhere is worse. Nothing here knows about services or
business logic; it only builds and wires widgets.
"""
from kivy.core.window import Window
from kivy.uix.button import Button
from kivy.uix.label import Label


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
                          on_cancel=None, extra_buttons=None):
    """The screen shown while a background job runs. "Back" just navigates
    home - the job keeps running regardless, and writes its result into the
    job manager so 'check on last job' can pick it up later. If on_cancel is
    given, a Cancel button is also shown."""
    nav.clear()
    label = Label(text=message, size_hint_y=None, height=60)
    nav.add(label)
    nav.set_status_label(label)

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
