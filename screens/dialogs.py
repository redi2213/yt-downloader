"""Small popups shared by the screens (a list of actions, a yes/no question)."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView

from screens.common import BTN_H, GAP, content_width

_DANGER = (1.0, 0.55, 0.55, 1)


def menu(title, buttons):
    """A popup with one button per action (``buttons``: (text, function or None, danger)) and Close."""
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    head = Label(text=title, size_hint_y=None, height=dp(44), shorten=True, shorten_from="right")
    head.text_size = (content_width() * 0.84, None)
    box.add_widget(head)
    dialog = ModalView(size_hint=(0.92, None), background="", background_color=(0.13, 0.10, 0.09, 1))
    for text, fn, danger in list(buttons) + [("Close", None, False)]:
        btn = Button(text=text, size_hint_y=None, height=BTN_H, **({"background_color": _DANGER} if danger else {}))
        btn.bind(on_press=lambda i, f=fn: (dialog.dismiss(), f() if f else None))
        box.add_widget(btn)
    dialog.height = 2 * dp(12) + dp(44) + (len(buttons) + 1) * (BTN_H + GAP)
    dialog.add_widget(box)
    dialog.open()


def confirm(text, yes_text, on_yes, no_text="Cancel", danger=True):
    """A yes/no question; ``on_yes`` runs only on the yes button."""
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    label = Label(text=text, halign="center", valign="middle")
    label.text_size = (content_width() * 0.84, None)
    box.add_widget(label)
    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    no_btn = Button(text=no_text)
    yes_btn = Button(text=yes_text, **({"background_color": _DANGER} if danger else {}))
    buttons.add_widget(no_btn)
    buttons.add_widget(yes_btn)
    box.add_widget(buttons)
    dialog = ModalView(size_hint=(0.92, None), height=dp(230), background="", background_color=(0.13, 0.10, 0.09, 1))
    dialog.add_widget(box)
    no_btn.bind(on_press=lambda i: dialog.dismiss())
    yes_btn.bind(on_press=lambda i: (dialog.dismiss(), on_yes()))
    dialog.open()


def choose_open(title, options, on_pick, remember_text="Remember my choice"):
    """A popup with one button per option (``options``: (key, text)) and a tick-box; the chosen
    ``on_pick(key, remember)`` runs after the popup closes."""
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    head = Label(text=title, size_hint_y=None, height=dp(44))
    head.text_size = (content_width() * 0.84, None)
    box.add_widget(head)
    dialog = ModalView(size_hint=(0.92, None), background="", background_color=(0.13, 0.10, 0.09, 1))
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=GAP)
    check = CheckBox(active=False, size_hint_x=None, width=dp(48))
    text = Label(text=remember_text, halign="left", valign="middle")
    text.bind(size=lambda inst, size: setattr(inst, "text_size", size))
    row.add_widget(check)
    row.add_widget(text)
    for key, label in options:
        btn = Button(text=label, size_hint_y=None, height=BTN_H)
        btn.bind(on_press=lambda i, k=key: (dialog.dismiss(), on_pick(k, bool(check.active))))
        box.add_widget(btn)
    box.add_widget(row)
    close = Button(text="Close", size_hint_y=None, height=BTN_H)
    close.bind(on_press=lambda i: dialog.dismiss())
    box.add_widget(close)
    dialog.height = 2 * dp(12) + dp(44) + (len(options) + 1) * (BTN_H + GAP) + dp(48) + GAP
    dialog.add_widget(box)
    dialog.open()
