"""Arvan files screens (Release History > Arvan files): every file of the Arvan bucket, with
select / copy link / rename / delete. Only builds widgets: the work is done by
services/arvan_service.py through screens/arvan_controller.py.
"""
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import storage_format as fmt
from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box, content_width,
    paint_card, wrapped_label, wrapped_label_height,
)

PAGE_SIZE = 20
_DANGER = (1.0, 0.55, 0.55, 1)


def _when(iso):
    try:
        from core import timeutil
        return timeutil.utc_iso_to_local(str(iso).replace("+00:00", "Z"))
    except Exception:
        return str(iso)[:16].replace("T", " ")


def objects_of(data):
    return list((data or {}).get("objects") or [])


def build_list(nav, data, page=0, selected=None, note=""):
    """``selected`` is the set of selected object keys (kept by the navigator across pages)."""
    nav.clear()
    selected = selected if selected is not None else set()
    objs = objects_of(data)
    last_page = max(0, (len(objs) - 1) // PAGE_SIZE) if objs else 0
    page = max(0, min(page, last_page))
    shown = objs[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]

    nav.add(Label(text=f"Arvan files - page {page + 1}", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label(f"{len(objs)} files, {fmt.fmt_bytes(data.get('total_size', 0))} in the bucket "
                          f"{data.get('bucket', '')}\nList read: {_when(data.get('generated', ''))}"))
    if note:
        nav.add(wrapped_label(note))

    refresh = Button(text="Refresh the list (about 40 seconds)", size_hint_y=None, height=BTN_H)
    refresh.bind(on_press=lambda i: nav.show_arvan_files(refresh=True))
    nav.add(refresh)

    info = Label(text="", size_hint_y=None, height=BTN_H)
    cards = {}

    def update_info():
        info.text = f"Selected: {len(selected)} of {len(objs)}"

    def set_selected(key, value):
        if value:
            selected.add(key)
        else:
            selected.discard(key)
        if key in cards:
            cards[key].rgba = CARD_ON if value else CARD
        update_info()

    def chosen():
        picked = [o for o in objs if o["key"] in selected]
        if not picked:
            info.text = "Tap a file to select it first"
        return picked

    if not objs:
        nav.add(Label(text="The bucket is empty", size_hint_y=None, height=BTN_H))
    else:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        all_btn = Button(text="Select all on this page")
        all_btn.bind(on_press=lambda i: [set_selected(o["key"], True) for o in shown])
        clear_btn = Button(text="Clear")
        clear_btn.bind(on_press=lambda i: [set_selected(o["key"], False) for o in objs])
        row.add_widget(all_btn)
        row.add_widget(clear_btn)
        nav.add(row)
        update_info()
        nav.add(info)

        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        copy_btn = Button(text="Copy links")

        def copy_selected(_i):
            picked = chosen()
            if picked:
                Clipboard.copy("\n".join(o["url"] for o in picked))
                info.text = f"Copied {len(picked)} link(s)"

        copy_btn.bind(on_press=copy_selected)
        del_btn = Button(text="Delete selected", background_color=_DANGER)

        def delete_selected(_i):
            picked = chosen()
            if picked:
                nav.show_arvan_delete_confirm(picked)

        del_btn.bind(on_press=delete_selected)
        actions.add_widget(copy_btn)
        actions.add_widget(del_btn)
        nav.add(actions)

    inner_width = content_width() - 2 * dp(8)
    for obj in shown:
        key = obj["key"]
        text = f"{_when(obj.get('modified', ''))}\n{key}  ({fmt.fmt_bytes(obj.get('size', 0))})"
        height = wrapped_label_height(text, extra_padding=dp(14), width=inner_width - dp(16))
        row = card_box([height, SMALL_BTN_H, BTN_H])
        cards[key] = paint_card(row, CARD_ON if key in selected else CARD)

        title_btn = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                           background_normal="", background_color=(0, 0, 0, 0))
        title_btn.text_size = (inner_width - dp(16), None)
        title_btn.bind(on_press=lambda i, k=key: set_selected(k, k not in selected))
        row.add_widget(title_btn)
        row.add_widget(TextInput(text=obj["url"], readonly=True, multiline=False,
                                 size_hint_y=None, height=SMALL_BTN_H))

        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        copy = Button(text="Copy")
        copy.bind(on_press=lambda i, u=obj["url"]: Clipboard.copy(u))
        rename = Button(text="Rename")
        rename.bind(on_press=lambda i, o=obj: nav.show_arvan_rename(o))
        delete = Button(text="Delete", background_color=_DANGER)
        delete.bind(on_press=lambda i, o=obj: nav.show_arvan_delete_confirm([o]))
        for b in (copy, rename, delete):
            buttons.add_widget(b)
        row.add_widget(buttons)
        nav.add(row)

    if page > 0 or page < last_page:
        pager = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        prev_btn = Button(text=f"< Previous {PAGE_SIZE}", disabled=page == 0)
        prev_btn.bind(on_press=lambda i: nav.show_arvan_page(page - 1))
        next_btn = Button(text=f"Next {PAGE_SIZE} >", disabled=page >= last_page)
        next_btn.bind(on_press=lambda i: nav.show_arvan_page(page + 1))
        pager.add_widget(prev_btn)
        pager.add_widget(next_btn)
        nav.add(pager)

    nav.add(back_button(nav, to=nav.show_live_history))


def build_delete_confirm(nav, objs):
    nav.clear()
    names = "\n".join(o["key"] for o in objs[:6]) + (f"\n... and {len(objs) - 6} more" if len(objs) > 6 else "")
    nav.add(wrapped_label(f"Delete {len(objs)} file(s) from Arvan?\n{names}\nThis cannot be undone."))
    yes = Button(text=f"Yes, delete {len(objs)}", size_hint_y=None, height=BTN_H, background_color=_DANGER)
    yes.bind(on_press=lambda i: nav.start_arvan_delete(objs))
    nav.add(yes)
    no = Button(text="Cancel", size_hint_y=None, height=BTN_H)
    no.bind(on_press=lambda i: nav.show_arvan_files())
    nav.add(no)


def build_rename(nav, obj):
    nav.clear()
    nav.add(wrapped_label(f"Rename on Arvan:\n{obj['key']}\n(a name without / stays in the same folder; "
                          "the link changes)"))
    box = TextInput(text=obj["key"].rsplit("/", 1)[-1], multiline=False, size_hint_y=None, height=dp(48))
    nav.add(box)
    save = Button(text="Save name", size_hint_y=None, height=BTN_H)
    save.bind(on_press=lambda i: nav.start_arvan_rename(obj, box.text.strip()))
    nav.add(save)
    cancel = Button(text="Cancel", size_hint_y=None, height=BTN_H)
    cancel.bind(on_press=lambda i: nav.show_arvan_files())
    nav.add(cancel)
