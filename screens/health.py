"""The Health page (Settings > Health): one coloured card per check - green
ok, orange needs a look, red broken (with what to do), grey just information.
Only builds widgets: the checks are in services/health_service.py.
"""
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common
from screens.common import BTN_H, back_button, wrapped_label_height

# card background by status
_CARD = {
    "ok": (0.10, 0.32, 0.17, 1),
    "warn": (0.45, 0.33, 0.07, 1),
    "fail": (0.50, 0.13, 0.13, 1),
    "info": common.CARD,
}
_MARK = {"ok": "OK", "warn": "CHECK", "fail": "PROBLEM", "info": "INFO"}


def build_loading(nav, back):
    nav.clear()
    nav.add(Label(text="Health", size_hint_y=None, height=44))
    nav.add(Label(text="Checking... (a few seconds)", size_hint_y=None, height=40))
    nav.add(back_button(nav, to=back))


def _card(nav, item):
    width = common.content_width() - dp(24)
    parts = [(f"[{_MARK[item['status']]}]  {item['title']}", dp(34), (1, 1, 1, 1))]
    if item.get("detail"):
        parts.append((item["detail"], None, (0.92, 0.92, 0.95, 1)))
    if item.get("fix"):
        parts.append((f"What to do: {item['fix']}", None, (1, 0.93, 0.6, 1)))
    labels, heights = [], []
    for text, height, color in parts:
        h = height or wrapped_label_height(text, extra_padding=dp(6), width=width)
        label = Label(text=text, size_hint_y=None, height=h, halign="left", valign="middle" if height else "top",
                      color=color)
        label.text_size = (width, None)
        labels.append(label)
        heights.append(h)
    box = common.card_box(heights)
    common.paint_card(box, _CARD.get(item["status"], common.CARD))
    for label in labels:
        box.add_widget(label)
    nav.add(box)


def build(nav, res, on_refresh, back):
    nav.clear()
    nav.add(Label(text="Health", size_hint_y=None, height=44))
    if not res.get("ok"):
        nav.add(common.wrapped_label(res.get("error", "Health check failed.")))
    else:
        items = res["items"]
        problems = sum(1 for i in items if i["status"] == "fail")
        looks = sum(1 for i in items if i["status"] == "warn")
        if problems:
            summary = f"{problems} problem{'s' if problems != 1 else ''} to fix"
        elif looks:
            summary = f"No problems, {looks} thing{'s' if looks != 1 else ''} to look at"
        else:
            summary = "Everything is fine"
        nav.add(Label(text=summary, size_hint_y=None, height=36,
                      color=(1, 0.5, 0.5, 1) if problems else ((1, 0.85, 0.4, 1) if looks else (0.5, 1, 0.6, 1))))
        for item in items:
            _card(nav, item)
    refresh = Button(text="Refresh", size_hint_y=None, height=BTN_H)
    refresh.bind(on_press=lambda i: on_refresh())
    nav.add(refresh)
    nav.add(back_button(nav, to=back))
