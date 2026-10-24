"""Site log screens: the "this site failed before" question (yes / no) and the per-site
table (Settings > Notifications and health > Site log). Only builds widgets; the data comes
from services/site_log_service.py."""
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common
from screens.common import BTN_H, back_button, wrapped_label_height

_GREEN = (0.10, 0.32, 0.17, 1)
_ORANGE = (0.45, 0.33, 0.07, 1)
_RED = (0.50, 0.13, 0.13, 1)
_WHITE = (1, 1, 1, 1)
_SOFT = (0.92, 0.92, 0.95, 1)
_YELLOW = (1, 0.93, 0.6, 1)


def _card(nav, parts, color):
    """One coloured card; parts = [(text, text colour)]."""
    width = common.content_width() - dp(24)
    labels, heights = [], []
    for text, tint in parts:
        h = wrapped_label_height(text, extra_padding=dp(6), width=width)
        label = Label(text=text, size_hint_y=None, height=h, halign="left", valign="top", color=tint)
        label.text_size = (width, None)
        labels.append(label)
        heights.append(h)
    box = common.card_box(heights)
    common.paint_card(box, color)
    for label in labels:
        box.add_widget(label)
    nav.add(box)


def build_warning(nav, warnings, on_yes, on_no):
    """Before a run: these sites failed before and never worked - run anyway?"""
    nav.clear()
    nav.add(Label(text="This site failed before", size_hint_y=None, height=44))
    for w in warnings:
        _card(nav, [(w["domain"], _WHITE),
                    (f"Failed {w['bad']} time(s), worked 0 times.", _SOFT),
                    (f"Last problem: {w.get('reason') or 'unknown'}", _YELLOW)], _ORANGE)
    nav.add(Label(text="Run it anyway?", size_hint_y=None, height=BTN_H))
    yes = Button(text="Yes, run anyway", size_hint_y=None, height=BTN_H)
    yes.bind(on_press=lambda i: on_yes())
    nav.add(yes)
    no = Button(text="No, go back", size_hint_y=None, height=BTN_H)
    no.bind(on_press=lambda i: on_no())
    nav.add(no)


def build_loading(nav, back):
    nav.clear()
    nav.add(Label(text="Site log", size_hint_y=None, height=44))
    nav.add(Label(text="Loading the site log...", size_hint_y=None, height=40))
    nav.add(back_button(nav, to=back))


def _status(row):
    n = row["n"]
    bad = n["fail"] + n["small"]
    if n["success"] and not bad:
        return "Works", _GREEN
    if n["success"]:
        return "Sometimes works", _ORANGE
    if bad:
        return "Never worked", _RED
    return "Not sure yet", common.CARD


def build(nav, res, on_refresh, back):
    nav.clear()
    nav.add(Label(text="Site log", size_hint_y=None, height=44))
    if not res.get("ok"):
        nav.add(common.wrapped_label(res.get("error", "Could not read the site log.")))
    elif not res.get("rows"):
        nav.add(common.wrapped_label("No sites recorded yet. Every Any site run adds its link here."))
    else:
        nav.add(common.wrapped_label("Sites that ran through Any site (success = file over 10 MB)."))
        for row in res["rows"]:
            n = row["n"]
            word, color = _status(row)
            parts = [(row["domain"], _WHITE), (word, _YELLOW),
                     (f"worked {n['success']}  ·  under 10 MB {n['small']}  ·  failed {n['fail']}", _SOFT)]
            if n["unknown"]:
                parts.append((f"Unclear: {n['unknown']}", _SOFT))
            if row.get("last"):
                parts.append((f"Last: {row['last']}", _SOFT))
            if row.get("reason") and (n["fail"] or n["small"]):
                parts.append((f"Last problem: {row['reason']}", _YELLOW))
            _card(nav, parts, color)
    refresh = Button(text="Refresh", size_hint_y=None, height=BTN_H)
    refresh.bind(on_press=lambda i: on_refresh())
    nav.add(refresh)
    nav.add(back_button(nav, to=back))
