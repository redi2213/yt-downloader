"""Aparat video picker: the videos of a playlist / channel as tap-to-select
cards (same look as the YouTube playlist picker), with Select all / Clear."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, back_button, card_box, content_width,
    fa_font_kwargs, fa_text, paint_card, wrapped_label_height,
)


def build(nav, entries, action, values, selected, on_go, on_back):
    """``selected``: one bool per entry, edited in place. ``on_go(ids, quality)``
    is called with the chosen video ids (``quality`` is None for "Start with
    selected" = the form's quality, or the value of the quality button that was
    pressed); ``on_back()`` returns to the form."""
    nav.clear()
    total = len(entries)
    nav.add(Label(text=f"Aparat videos ({total})", size_hint_y=None, height=BTN_H))

    cards = []
    info = Label(text="", size_hint_y=None, height=BTN_H)

    def update_info():
        info.text = f"Selected: {sum(selected)} of {total}"

    def set_selected(idx, value):
        selected[idx] = value
        cards[idx].rgba = CARD_ON if value else CARD
        update_info()

    def set_all(value):
        for idx in range(total):
            set_selected(idx, value)

    def go(_inst, quality=None):
        ids = [e["uid"] for e, on in zip(entries, selected) if on]
        if not ids:
            info.text = "Tap the videos you want first"
            return
        on_go(ids, quality)

    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    all_btn = Button(text="Select all")
    all_btn.bind(on_press=lambda i: set_all(True))
    clear_btn = Button(text="Clear")
    clear_btn.bind(on_press=lambda i: set_all(False))
    row.add_widget(all_btn)
    row.add_widget(clear_btn)
    nav.add(row)
    nav.add(info)

    go_btn = Button(text="Start with selected", size_hint_y=None, height=BTN_H)
    go_btn.bind(on_press=go)
    nav.add(go_btn)

    # like the YouTube playlist: a quality button starts the selected videos at once
    quality_field = next((f for f in (action.get("fields") or []) if f.get("key") == "quality"), None)
    choices = (quality_field or {}).get("choices") or []
    if choices:
        nav.add(Label(text="or start with a quality", size_hint_y=None, height=32))
        per_row = 4
        for start in range(0, len(choices), per_row):
            q_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
            for choice in choices[start:start + per_row]:
                q_btn = Button(text=choice.get("label", str(choice["value"])))
                q_btn.bind(on_press=lambda i, v=choice["value"]: go(i, v))
                q_row.add_widget(q_btn)
            nav.add(q_row)

    inner_width = content_width() - 2 * dp(8)
    for idx, entry in enumerate(entries):
        raw_text = f"{idx + 1}. {entry['title']}"
        text = fa_text(raw_text, inner_width - dp(16))
        height = wrapped_label_height(text, extra_padding=dp(14), width=inner_width - dp(16))
        card = card_box([height])
        cards.append(paint_card(card, CARD_ON if selected[idx] else CARD))
        title_btn = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                           background_normal="", background_color=(0, 0, 0, 0),
                           **fa_font_kwargs(raw_text))
        title_btn.text_size = (inner_width - dp(16), None)
        title_btn.bind(on_press=lambda i, n=idx: set_selected(n, not selected[n]))
        card.add_widget(title_btn)
        nav.add(card)

    update_info()
    nav.add(back_button(nav, to=on_back))
