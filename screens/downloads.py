"""Downloads: what "Download in app" is saving now (Pause / Resume / Stop) and the files that
are saved on the phone (Open / Share / Delete), with a search box and a type filter.

The live part is updated in place once a second (core/download_manager.py), so a button is never
rebuilt under the finger.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from api import downloads_history
from core import android_open, download_manager as dm, file_types
from screens.common import (BTN_H, CARD, GAP, SMALL_BTN_H, back_button, card_box, content_width,
                            paint_card, wrapped_label_height)

_DANGER = (1.0, 0.55, 0.55, 1)
PAGE = 30
_state = {"kind": "All", "query": "", "shown": PAGE}


def _set(widget, text):
    """Sets a text only when it changed (in Persian ``widget.text`` is the translated one, the
    English text the code wrote is kept in ``_ytb_src``)."""
    if getattr(widget, "_ytb_src", widget.text) != text:
        widget.text = text


def _size_text(size):
    if not size:
        return "?"
    mib = size / (1024 * 1024)
    return f"{mib / 1024:.2f} GB" if mib >= 1024 else (f"{mib:.1f} MB" if mib >= 1 else f"{size / 1024:.0f} KB")


def _matches(name):
    kind, query = _state["kind"], _state["query"].strip().lower()
    return (kind == "All" or file_types.kind_of(name) == kind) and (not query or query in str(name).lower())


def _task_text(t):
    if t.state == dm.QUEUED:
        line = "Waiting for a free slot"
    elif t.state == dm.PAUSED:
        line = f"Paused  {_size_text(t.done)} / {_size_text(t.total)}" if t.total else "Paused"
    elif t.state == dm.SAVING:
        line = "Saving..."
    elif t.state == dm.FAILED:
        line = f"Failed: {t.error}"
    elif t.state == dm.CANCELLED:
        line = "Stopped"
    elif t.total:
        line = f"{t.done * 100 // t.total}%   {_size_text(t.done)} / {_size_text(t.total)}   {_size_text(t.speed)}/s"
    else:
        line = f"{_size_text(t.done)}   {_size_text(t.speed)}/s"
    return f"{t.name}\n{line}"


def build(nav):
    nav.clear()
    nav.add(Label(text="Downloads", size_hint_y=None, height=44))
    info = Label(text="", size_hint_y=None, height=32, color=(1, 0.75, 0.4, 1))

    search = TextInput(text=_state["query"], hint_text="Search downloads", multiline=False,
                       size_hint_y=None, height=BTN_H)
    nav.add(search)

    filter_buttons = {}
    for start in (0, 3):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        for kind in file_types.KINDS[start:start + 3]:
            btn = Button(text=("\u25cf " if kind == _state["kind"] else "") + kind)
            btn.bind(on_press=lambda i, k=kind: set_kind(k))
            filter_buttons[kind] = btn
            row.add_widget(btn)
        nav.add(row)

    active_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    active_box.bind(minimum_height=active_box.setter("height"))
    nav.add(active_box)
    nav.add(info)
    finished_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    finished_box.bind(minimum_height=finished_box.setter("height"))
    nav.add(finished_box)

    clear_btn = Button(text="Clear list (files stay)", size_hint_y=None, height=BTN_H)
    clear_btn.bind(on_press=lambda i: clear_list())
    nav.add(clear_btn)
    nav.add(back_button(nav))

    cards = {}           # task id -> (card, label, pause button, stop button)
    seen_done = set()

    def say(text):
        info.text = text or ""
        info.height = max(dp(32), wrapped_label_height(text or ""))
        info.text_size = (content_width(), None)

    def set_kind(kind):
        _state["kind"], _state["shown"] = kind, PAGE
        nav.show_downloads()

    def on_query(_i, value):
        _state["query"], _state["shown"] = value, PAGE
        refresh_active()
        build_finished()

    search.bind(text=on_query)

    def clear_list():
        downloads_history.clear()
        dm.clear_finished()
        build_finished()
        refresh_active()

    # -- live downloads ------------------------------------------------------------------------
    def make_card(t):
        inner = content_width() - 2 * dp(8)
        card = card_box([dp(56), BTN_H])
        paint_card(card, CARD)
        label = Label(text=_task_text(t), size_hint_y=None, height=dp(56), halign="left", valign="middle")
        label.text_size = (inner - dp(16), None)
        card.add_widget(label)
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        pause_btn = Button(text="Pause")
        pause_btn.bind(on_press=lambda i, tid=t.id: toggle_pause(tid))
        stop_btn = Button(text="Stop", background_color=_DANGER)
        stop_btn.bind(on_press=lambda i, tid=t.id: stop_or_remove(tid))
        row.add_widget(pause_btn)
        row.add_widget(stop_btn)
        card.add_widget(row)
        return card, label, pause_btn, stop_btn

    def toggle_pause(task_id):
        t = dm.get(task_id)
        if t is None:
            return
        if t.state == dm.PAUSED:
            dm.resume(task_id)
        else:
            dm.pause(task_id)
        refresh_active()

    def stop_or_remove(task_id):
        t = dm.get(task_id)
        if t is None:
            return
        if t.active:
            dm.cancel(task_id)
        else:
            dm.forget(task_id)
        refresh_active()

    def refresh_active():
        shown = [t for t in dm.snapshot() if t.state != dm.DONE and _matches(t.name)]
        wanted = {t.id for t in shown}
        for tid in [k for k in cards if k not in wanted]:
            active_box.remove_widget(cards.pop(tid)[0])
        for t in reversed(shown):                    # oldest first
            if t.id not in cards:
                cards[t.id] = make_card(t)
                active_box.add_widget(cards[t.id][0])
        for t in shown:
            _card, label, pause_btn, stop_btn = cards[t.id]
            _set(label, _task_text(t))
            _set(pause_btn, "Resume" if t.state == dm.PAUSED else "Pause")
            pause_btn.disabled = t.state in (dm.SAVING, dm.FAILED, dm.CANCELLED)
            _set(stop_btn, "Stop" if t.active else "Remove")
            stop_btn.disabled = t.state == dm.SAVING
        if not shown:
            active_box.height = 0
        done_now = {t.id for t in dm.snapshot() if t.state == dm.DONE}
        if done_now - seen_done:
            seen_done.update(done_now)
            build_finished()

    # -- saved files ---------------------------------------------------------------------------
    def build_finished():
        finished_box.clear_widgets()
        entries = [e for e in downloads_history.load() if _matches(e.get("name", ""))]
        if not entries:
            finished_box.add_widget(Label(text="No downloads yet", size_hint_y=None, height=BTN_H))
            return
        inner = content_width() - 2 * dp(8)
        for entry in entries[:_state["shown"]]:
            head = f"{entry.get('time', '')}   {_size_text(entry.get('size'))}   [{entry.get('category', '')}]\n{entry.get('name', '')}"
            card = card_box([dp(56), BTN_H])
            paint_card(card, CARD)
            label = Label(text=head, size_hint_y=None, height=dp(56), halign="left", valign="middle")
            label.text_size = (inner - dp(16), None)
            card.add_widget(label)
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
            open_btn = Button(text="Open")
            open_btn.bind(on_press=lambda i, e=entry: say(android_open.open_file(e.get("location"), e.get("name", ""))))
            share_btn = Button(text="Share")
            share_btn.bind(on_press=lambda i, e=entry: say(android_open.share_file(e.get("location"), e.get("name", ""))))
            delete_btn = Button(text="Delete", background_color=_DANGER)
            delete_btn.bind(on_press=lambda i, e=entry, b=delete_btn: delete_entry(e, b))
            for b in (open_btn, share_btn, delete_btn):
                row.add_widget(b)
            card.add_widget(row)
            finished_box.add_widget(card)
        if len(entries) > _state["shown"]:
            more = Button(text="Show more", size_hint_y=None, height=BTN_H)
            more.bind(on_press=lambda i: show_more())
            finished_box.add_widget(more)

    def show_more():
        _state["shown"] += PAGE
        build_finished()

    def delete_entry(entry, button):
        if not getattr(button, "_armed", False):
            button._armed = True
            button.text = "Press again to delete the file"
            return
        android_open.delete_file(entry.get("location"))     # False = already gone; the entry goes either way
        downloads_history.remove(entry.get("id"))
        build_finished()

    seen_done.update(t.id for t in dm.snapshot() if t.state == dm.DONE)
    build_finished()
    nav.start_progress_timer(refresh_active, interval=1.0)
