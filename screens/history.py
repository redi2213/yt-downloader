from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_actions
from kivy.metrics import dp

from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box,
    content_width, paint_card, wrapped_label_height,
)

_DANGER = (1.0, 0.55, 0.55, 1)   # tint for buttons that delete things


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))


def build(nav, items):
    nav.clear()
    nav.add(Label(text=f"Release History ({len(items)} found)", size_hint_y=None, height=BTN_H))

    selected = [False] * len(items)
    cards = []   # (card colour, title button) of every item, in display order
    info = Label(text="", size_hint_y=None, height=BTN_H)

    def selected_items():
        return [it for it, on in zip(items, selected) if on]

    def set_selected(idx, value):
        selected[idx] = value
        color, _title = cards[idx]
        color.rgba = CARD_ON if value else CARD
        update_info()

    def update_info(*_args):
        info.text = f"Selected: {len(selected_items())} of {len(items)}"

    def need_selection():
        sel = selected_items()
        if not sel:
            info.text = "Tap a file to select it first"
        return sel

    def copy_selected(_inst):
        sel = need_selection()
        if sel:
            Clipboard.copy("\n".join(it["link"] for it in sel))
            info.text = f"Copied {len(sel)} link(s)"

    def share_selected(_inst):
        sel = need_selection()
        if sel:
            shared = android_actions.share_text("\n".join(it["link"] for it in sel))
            info.text = (f"Sharing {len(sel)} link(s)" if shared
                         else f"Share not available - copied {len(sel)} link(s)")

    def delete_selected(_inst):
        sel = need_selection()
        if sel:
            nav.show_bulk_delete_confirm(sel, scope="selected")

    def set_all(value):
        for idx in range(len(items)):
            set_selected(idx, value)

    if not items:
        nav.add(Label(text="No downloads yet", size_hint_y=None, height=BTN_H))
    else:
        select_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        select_all_btn = Button(text="Select all")
        select_all_btn.bind(on_press=lambda i: set_all(True))
        clear_btn = Button(text="Clear")
        clear_btn.bind(on_press=lambda i: set_all(False))
        select_row.add_widget(select_all_btn)
        select_row.add_widget(clear_btn)
        nav.add(select_row)

        update_info()
        nav.add(info)

        action_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        copy_sel_btn = Button(text="Copy links")
        copy_sel_btn.bind(on_press=copy_selected)
        share_sel_btn = Button(text="Share")
        share_sel_btn.bind(on_press=share_selected)
        delete_sel_btn = Button(text="Delete selected", background_color=_DANGER)
        delete_sel_btn.bind(on_press=delete_selected)
        action_row.add_widget(copy_sel_btn)
        action_row.add_widget(share_sel_btn)
        action_row.add_widget(delete_sel_btn)
        nav.add(action_row)

        bulk_delete_btn = Button(text=f"Delete all {len(items)} shown", size_hint_y=None,
                                 height=BTN_H, background_color=_DANGER)
        bulk_delete_btn.bind(on_press=lambda i: nav.show_bulk_delete_confirm(items))
        nav.add(bulk_delete_btn)

    inner_width = content_width() - 2 * dp(8)
    for idx, item in enumerate(items):
        size_mb = item.get("size", 0) / (1024 * 1024)
        size_text = f" ({size_mb:.1f} MB)" if size_mb else ""
        title_text = f"{item['date']}\n{item['title']}{size_text}"
        title_height = wrapped_label_height(title_text, extra_padding=dp(14), width=inner_width - dp(16))

        # One card per file: tap the file's text to select it - the whole card
        # turns green. Link on its own line, then four evenly spaced buttons.
        row = card_box([title_height, SMALL_BTN_H, BTN_H])
        color = paint_card(row, CARD)

        title_btn = Button(text=title_text, size_hint_y=None, height=title_height, halign="left",
                           valign="middle", background_normal="", background_color=(0, 0, 0, 0))
        title_btn.text_size = (inner_width - dp(16), None)
        title_btn.bind(on_press=lambda i, n=idx: set_selected(n, not selected[n]))
        cards.append((color, title_btn))
        row.add_widget(title_btn)

        row.add_widget(TextInput(text=item["link"], readonly=True, multiline=False,
                                 size_hint_y=None, height=SMALL_BTN_H))

        action_buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        copy_btn = Button(text="Copy")
        copy_btn.bind(on_press=lambda i, l=item["link"]: Clipboard.copy(l))
        rename_btn = Button(text="Rename")
        rename_btn.bind(on_press=lambda i, it=item: nav.show_rename_prompt(it))
        zip_btn = Button(text="Zip")
        zip_btn.bind(on_press=lambda i, it=item: nav.start_zip_release(it))
        delete_btn = Button(text="Delete", background_color=_DANGER)
        delete_btn.bind(on_press=lambda i, it=item: nav.show_delete_confirm(it))
        for btn in (copy_btn, rename_btn, zip_btn, delete_btn):
            action_buttons.add_widget(btn)
        row.add_widget(action_buttons)
        nav.add(row)

    nav.add(back_button(nav))


def build_delete_confirm(nav, item):
    nav.clear()
    nav.add(Label(text=f"Delete this release?\n{item['title']}", size_hint_y=None, height=80))
    confirm_btn = Button(text="Yes, delete", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_delete_release(item))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_job_history())
    nav.add(cancel_btn)


def build_bulk_delete_confirm(nav, items, scope="shown"):
    nav.clear()
    selected = scope == "selected"
    question = (f"Delete the {len(items)} selected release(s)?" if selected
                else f"Delete all {len(items)} releases shown?")
    nav.add(Label(text=f"{question}\nThis cannot be undone.", size_hint_y=None, height=80))
    confirm_text = f"Yes, delete {len(items)}" if selected else f"Yes, delete all {len(items)}"
    confirm_btn = Button(text=confirm_text, size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_bulk_delete(items, scope=scope))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_live_history() if selected else nav.show_job_history())
    nav.add(cancel_btn)


def build_deleting(nav):
    nav.clear()
    nav.add(Label(text="Deleting...", size_hint_y=None, height=60))
    nav.add(back_button(nav))


def build_bulk_deleting(nav, count):
    nav.clear()
    status_label = Label(text=f"Deleting 0/{count}...", size_hint_y=None, height=60)
    nav.add(status_label)
    nav.set_status_label(status_label)
    back_btn = Button(text="Back (keeps deleting)", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build_renaming(nav):
    nav.clear()
    nav.add(Label(text="Renaming...", size_hint_y=None, height=60))
    nav.add(back_button(nav))


def build_rename_prompt(nav, item):
    nav.clear()
    nav.add(Label(text=f"Rename:\n{item['title']}", size_hint_y=None, height=60))
    name_input = TextInput(text=item["title"], multiline=False, size_hint_y=None, height=48)
    nav.add(name_input)
    confirm_btn = Button(text="Save name", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_rename_release(item, name_input.text.strip()))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_job_history())
    nav.add(cancel_btn)
