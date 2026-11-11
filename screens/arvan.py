"""Arvan files screens (Release History > Arvan files): every file of the Arvan bucket, with
select / copy link / rename / delete. Only builds widgets: the work is done by
services/arvan_service.py through screens/arvan_controller.py.
"""
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput
from kivy.utils import escape_markup

from core import i18n, storage_format as fmt
from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box, content_width,
    fa_text, paint_card, wrapped_label, wrapped_label_height,
)
from screens.history import _BUSY, _PressCard

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
    """Same handling as the Release History: tap a file = select it, hold it = its menu; the bar
    at the bottom (Select all / Clear / Copy links / Download / Delete) shows while files are
    selected. ``selected`` is the set of selected object keys (kept by the navigator across pages)."""
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

    info = Label(text="", size_hint_y=None, height=dp(34), halign="center", valign="middle", shorten=True)
    info.text_size = (content_width(), None)
    cards, rows = {}, {}
    busy = set()                       # keys being deleted right now
    status = {"text": "", "pending": 0}
    footer_state = {"mode": "nav", "nav": None}

    def update_info():
        info.text = status["text"] or f"Selected: {len(selected)} of {len(objs)}"

    def chosen():
        picked = [o for o in objs if o["key"] in selected and o["key"] not in busy]
        if not picked:
            info.text = "Tap a file to select it first"
        return picked

    def detach(widget):
        if widget.parent is not None:
            widget.parent.remove_widget(widget)

    def row_of(buttons):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP / 2)
        for text, fn in buttons:
            btn = Button(text=text, background_color=_DANGER) if text == "Delete" else Button(text=text)
            btn.bind(on_press=fn)
            row.add_widget(btn)
        return row

    def set_selected(key, value):
        if value:
            selected.add(key)
        else:
            selected.discard(key)
        if key in cards:
            cards[key].rgba = CARD_ON if value else CARD

    def copy_selected(_i):
        picked = chosen()
        if picked:
            Clipboard.copy("\n".join(o["url"] for o in picked))
            info.text = f"Copied {len(picked)} link(s)"

    def download_selected(_i):
        picked = chosen()
        if picked:
            info.text = f"Starting {len(picked)} download(s)..."
            nav.start_history_download(
                [{"title": o["key"].rsplit("/", 1)[-1], "link": o["url"]} for o in picked],
                lambda text: setattr(info, "text", text))

    def start_delete():
        picked = chosen()
        if not picked:
            return
        for o in picked:
            busy.add(o["key"])
            selected.discard(o["key"])
            if o["key"] in cards:
                cards[o["key"]].rgba = _BUSY
        status["pending"] += 1
        status["text"] = f"Deleting {len(picked)} file(s) from Arvan..."
        changed()

        def done(res):
            status["pending"] -= 1
            for o in picked:
                busy.discard(o["key"])
            if res.get("ok"):
                now = {o["key"] for o in objects_of(res["data"])}
                gone = [o for o in picked if o["key"] not in now]
                for o in gone:
                    row = rows.pop(o["key"], None)
                    if row is not None and row.parent is not None:
                        row.parent.remove_widget(row)
                for o in picked:
                    if o["key"] in now and o["key"] in cards:
                        cards[o["key"]].rgba = CARD
                status["text"] = f"Deleted {len(gone)}/{len(picked)} file(s)"
            else:
                for o in picked:
                    if o["key"] in cards:
                        cards[o["key"]].rgba = CARD
                status["text"] = str(res.get("error", "Delete failed"))[:90]
            Clock.schedule_once(lambda dt: end_status(), 5)
            changed()

        nav.start_arvan_inline_delete(picked, done)

    def end_status():
        if not status["pending"]:
            status["text"] = ""
            changed()

    def ask_delete(_i):
        picked = chosen()
        if not picked:
            return
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
        box.add_widget(Label(text=f"Delete {len(picked)} file(s) from Arvan?\nThis cannot be undone."))
        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        no_btn = Button(text="Cancel")
        yes_btn = Button(text=f"Yes, delete {len(picked)}", background_color=_DANGER)
        buttons.add_widget(no_btn)
        buttons.add_widget(yes_btn)
        box.add_widget(buttons)
        dialog = ModalView(size_hint=(0.92, None), height=dp(190), background="",
                           background_color=(0.13, 0.10, 0.09, 1))
        dialog.add_widget(box)
        no_btn.bind(on_press=lambda i: dialog.dismiss())
        yes_btn.bind(on_press=lambda i: (dialog.dismiss(), start_delete()))
        dialog.open()

    def select_page(value):
        for o in (shown if value else objs):
            set_selected(o["key"], value)
        changed()

    def make_sel_footer():
        bar = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP / 2)
        bar.height = dp(34) + 2 * BTN_H + GAP
        detach(info)
        bar.add_widget(info)
        bar.add_widget(row_of([("Select all", lambda i: select_page(True)),
                               ("Clear", lambda i: select_page(False))]))
        bar.add_widget(row_of([("Copy links", copy_selected), ("Download", download_selected),
                               ("Delete", ask_delete)]))
        return bar

    def make_del_footer():
        wrap = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP / 2)
        wrap.height = dp(34) + BTN_H + GAP / 2
        detach(info)
        wrap.add_widget(info)
        detach(footer_state["nav"])
        wrap.add_widget(footer_state["nav"])
        return wrap

    def refresh_footer():
        if selected:
            want = "sel"
        else:
            want = "del" if status["text"] else "nav"
        if want == footer_state["mode"]:
            return
        footer_state["mode"] = want
        if want == "sel":
            bar = make_sel_footer()
        elif want == "del":
            bar = make_del_footer()
        else:
            bar = footer_state["nav"]
            detach(bar)
        nav.set_footer(bar)

    def changed():
        update_info()
        refresh_footer()

    def on_tap(key):
        if key in busy:
            return
        set_selected(key, key not in selected)
        changed()

    def on_hold(obj):
        if obj["key"] not in busy:
            nav.show_arvan_item_menu(obj)

    inner_width = content_width() - 2 * dp(8)
    text_w = (inner_width - dp(16)) * 0.78

    def make_card(obj):
        key = obj["key"]
        meta = f"{_when(obj.get('modified', ''))}  ·  {fmt.fmt_bytes(obj.get('size', 0))}"
        height = max(BTN_H, wrapped_label_height(f"{key}\n{meta}", extra_padding=dp(14), width=text_w))
        # [color]/[size] markup must not go through the Persian layer: shape the pieces here
        key_s = fa_text(key, text_w) if i18n.is_fa() else key
        markup = f"{escape_markup(key_s)}\n[size=13sp][color=999999]{escape_markup(meta)}[/color][/size]"
        row = card_box([height])
        cards[key] = paint_card(row, _BUSY if key in busy else (CARD_ON if key in selected else CARD))
        line = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=dp(4))
        title_btn = _PressCard(on_tap=lambda k=key: on_tap(k), on_hold=lambda o=obj: on_hold(o),
                               text=markup, markup=True, size_hint_x=0.78, halign="left", valign="middle",
                               background_normal="", background_color=(0, 0, 0, 0))
        title_btn._ytb_notr = True
        title_btn.text_size = (text_w, None)
        line.add_widget(title_btn)
        copy_btn = Button(text="Copy", size_hint_x=0.22)

        def do_copy(btn, u=obj["url"]):
            Clipboard.copy(u)
            btn.text = "Copied"

        copy_btn.bind(on_press=do_copy)
        line.add_widget(copy_btn)
        row.add_widget(line)
        return row

    if not objs:
        nav.add(Label(text="The bucket is empty", size_hint_y=None, height=BTN_H))
    else:
        nav.add(wrapped_label("Tap a file to select it  -  hold a file to open its menu", halign="center"))
    for obj in shown:
        rows[obj["key"]] = make_card(obj)
        nav.add(rows[obj["key"]])

    footer = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    footer.add_widget(back_button(nav, to=nav.show_live_history))
    if last_page > 0:
        prev_btn = Button(text=f"< Prev {PAGE_SIZE}", disabled=page == 0)
        prev_btn.bind(on_press=lambda i: nav.show_arvan_page(page - 1))
        next_btn = Button(text=f"Next {PAGE_SIZE} >", disabled=page >= last_page)
        next_btn.bind(on_press=lambda i: nav.show_arvan_page(page + 1))
        footer.add_widget(prev_btn)
        footer.add_widget(next_btn)
    footer_state["nav"] = footer
    nav.set_footer(footer)
    if selected:
        changed()


def build_item_menu(nav, obj):
    """Everything you can do with ONE Arvan file (opened by holding its card)."""
    nav.clear()
    nav.add(wrapped_label(f"{obj['key']}\n{_when(obj.get('modified', ''))}  ·  {fmt.fmt_bytes(obj.get('size', 0))}"))
    nav.add(TextInput(text=obj["url"], readonly=True, multiline=False, size_hint_y=None, height=SMALL_BTN_H))
    status = Label(text="", size_hint_y=None, height=0, halign="center", valign="middle")
    status.text_size = (content_width(), None)

    def say(text):
        status.text = text
        status.height = dp(60)

    def add(text, fn, danger=False):
        btn = Button(text=text, size_hint_y=None, height=BTN_H)
        if danger:
            btn.background_color = _DANGER
        btn.bind(on_press=lambda i: fn(btn))
        nav.add(btn)

    def copy(btn):
        Clipboard.copy(obj["url"])
        btn.text = "Copied"

    def download(btn):
        say("Starting the download...")
        nav.start_history_download([{"title": obj["key"].rsplit("/", 1)[-1], "link": obj["url"]}], say)

    add("Copy link", copy)
    add("Download in app", download)
    nav.add(status)
    add("Rename", lambda b: nav.show_arvan_rename(obj))
    add("Delete", lambda b: nav.show_arvan_delete_confirm([obj]), danger=True)
    nav.add(back_button(nav, to=nav.show_arvan_files))


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
