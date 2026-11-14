"""Downloads: one compact list like 1DM+ - tabs (All / Downloading / Finished / Failed), one small
row per file with a "..." menu, tap = select, hold = menu, group delete.

Live part: what "Download in app" is saving now (Pause / Resume / Stop), updated in place once a
second (core/download_manager.py). Finished part: the files saved on the phone (Open / Share /
Delete). Deleting asks first and can remove the real file from the phone or only the list entry.

The "+ Add link" panel takes one or more direct links (one per line); every link goes through the
same download manager (segments, Pause / Resume / Stop).
"""
import re
from urllib.parse import unquote

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.textinput import TextInput

from api import downloads_history
from core import android_downloads, android_open, download_manager as dm, file_types, segmented_download
from core.async_utils import run_in_background
from core.links import split_links
from screens.common import (BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box,
                            content_width, font_px, paint_card, paste_row, wrapped_label_height)
from screens.history import _PressCard

_DANGER = (1.0, 0.55, 0.55, 1)
_FAILED = (0.30, 0.12, 0.12, 1)
_BUSY = (0.45, 0.12, 0.12, 1)
PAGE = 30
ROW_H = dp(62)
TABS = ("All", "Downloading", "Finished", "Failed")
_state = {"kind": "All", "query": "", "shown": PAGE, "link": "", "tab": "All", "link_open": False}

_CD_NAME = re.compile(r"filename\*\s*=\s*[^']*''([^;]+)|filename\s*=\s*\"?([^\";]+)\"?", re.IGNORECASE)


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


def _short(name, width):
    """The name cut in the middle (the extension stays visible) so it fits one line."""
    name = str(name)
    limit = max(12, int(width / (font_px() * 0.6)))
    if len(name) <= limit:
        return name
    keep = limit - 1
    return name[:keep - keep // 2] + "\u2026" + name[-(keep // 2):]


def _is_failed(t):
    return t.state in (dm.FAILED, dm.CANCELLED)


def _task_in_tab(t):
    tab = _state["tab"]
    if tab == "Finished":
        return False
    if tab == "Failed":
        return _is_failed(t)
    if tab == "Downloading":
        return not _is_failed(t)
    return True


def _task_meta(t):
    if t.state == dm.QUEUED:
        return "Waiting for a free slot"
    if t.state == dm.PAUSED:
        return f"Paused  {_size_text(t.done)} / {_size_text(t.total)}" if t.total else "Paused"
    if t.state == dm.SAVING:
        return "Saving..."
    if t.state == dm.FAILED:
        return f"Failed: {t.error}"
    if t.state == dm.CANCELLED:
        return "Stopped"
    if t.total:
        return f"{t.done * 100 // t.total}%   {_size_text(t.done)} / {_size_text(t.total)}   {_size_text(t.speed)}/s"
    return f"{_size_text(t.done)}   {_size_text(t.speed)}/s"


def _name_for(url):
    """File name for a direct link: a ``#name=`` in the link, else the server's Content-Disposition,
    else the last part of the path."""
    if "#name=" in url or "&name=" in url.split("#", 1)[-1]:
        return android_downloads.file_name_from_url(url)
    try:
        import requests
        r = requests.head(url, allow_redirects=True, timeout=10)
        m = _CD_NAME.search(r.headers.get("Content-Disposition", ""))
        if m:
            wanted = unquote((m.group(1) or m.group(2) or "").strip())
            if wanted:
                return android_downloads.safe_file_name(wanted)
    except Exception:
        pass
    return android_downloads.file_name_from_url(url)


def _download_link(url):
    """Runs in a background thread. The task shows up in the live list; a failure stays there
    with its message, so nothing more is needed here."""
    try:
        android_downloads.download_to_downloads(url, name=_name_for(url), category="Other")
    except segmented_download.Cancelled:
        pass
    except Exception:
        pass


def _menu(title, buttons):
    """A small popup with one button per action (``buttons``: (text, function, danger))."""
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    head = Label(text=title, size_hint_y=None, height=dp(44), shorten=True, shorten_from="right")
    head.text_size = (content_width() * 0.84, None)
    box.add_widget(head)
    dialog = ModalView(size_hint=(0.92, None), background="", background_color=(0.13, 0.10, 0.09, 1))
    for text, fn, danger in buttons + [("Close", None, False)]:
        btn = Button(text=text, size_hint_y=None, height=BTN_H, **({"background_color": _DANGER} if danger else {}))
        btn.bind(on_press=lambda i, f=fn: (dialog.dismiss(), f() if f else None))
        box.add_widget(btn)
    dialog.height = 2 * dp(12) + dp(44) + (len(buttons) + 1) * (BTN_H + GAP)
    dialog.add_widget(box)
    dialog.open()


def build(nav):
    nav.clear()
    nav.add(Label(text="Downloads", size_hint_y=None, height=44))
    info = Label(text="", size_hint_y=None, height=dp(32), color=(1, 0.75, 0.4, 1))
    row_w = (content_width() - 2 * dp(8)) * 0.80 - dp(16)

    # -- top row: add link / clear list ----------------------------------------------------------
    top = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    add_btn = Button(text="+ Add link")
    clear_btn = Button(text="Clear list (files stay)")
    top.add_widget(add_btn)
    top.add_widget(clear_btn)
    nav.add(top)

    link_holder = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    link_holder.bind(minimum_height=link_holder.setter("height"))
    link_holder.height = 0
    nav.add(link_holder)
    link_panel = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    link_panel.bind(minimum_height=link_panel.setter("height"))
    link_input = TextInput(text=_state["link"], hint_text="Direct link (one per line)", multiline=True,
                           size_hint_y=None, height=BTN_H * 1.6)
    link_panel.add_widget(link_input)
    link_panel.add_widget(paste_row(link_input, append=True))
    link_btn = Button(text="Download link", size_hint_y=None, height=BTN_H)
    link_panel.add_widget(link_btn)

    def toggle_link(_i=None):
        _state["link_open"] = not _state["link_open"]
        show_link_panel()

    def show_link_panel():
        link_holder.clear_widgets()
        if _state["link_open"]:
            link_holder.add_widget(link_panel)
        else:
            link_holder.height = 0

    link_input.bind(text=lambda _i, v: _state.update(link=v))

    def start_links(_i):
        links = split_links(link_input.text)
        if not links:
            say("Paste a link that starts with http:// or https://")
            return
        for url in links:
            run_in_background(_download_link, url)
        link_input.text = ""
        _state["link"] = ""
        _state["link_open"] = False
        show_link_panel()
        say("Download started")

    link_btn.bind(on_press=start_links)
    add_btn.bind(on_press=toggle_link)
    if _state["link"].strip():
        _state["link_open"] = True
    show_link_panel()

    # -- tabs ------------------------------------------------------------------------------------
    tab_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=dp(4))
    tab_buttons = {}
    for tab in TABS:
        btn = Button(text=tab)
        btn.bind(on_press=lambda i, t=tab: set_tab(t))
        tab_buttons[tab] = btn
        tab_row.add_widget(btn)
    nav.add(tab_row)

    # -- search + type -----------------------------------------------------------------------------
    sr = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=GAP)
    search = TextInput(text=_state["query"], hint_text="Search downloads", multiline=False)
    kinds = file_types.KINDS
    type_btn = Button(text=_state["kind"], size_hint_x=0.34)
    sr.add_widget(search)
    sr.add_widget(type_btn)
    nav.add(sr)

    active_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    active_box.bind(minimum_height=active_box.setter("height"))
    nav.add(active_box)
    nav.add(info)
    finished_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    finished_box.bind(minimum_height=finished_box.setter("height"))
    nav.add(finished_box)

    cards = {}            # task id -> (row, label, menu button, color)
    seen_done = set()
    selected = set()      # finished entry ids
    entry_color = {}      # entry id -> Color
    entry_row = {}        # entry id -> row widget
    busy = set()          # entry ids being deleted
    shown_ids = []        # entry ids matching the search / type (what "Select all" selects)
    footer_state = {"mode": "nav"}
    back_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    back_row.add_widget(back_button(nav))

    def say(text):
        info.text = text or ""
        info.height = max(dp(32), wrapped_label_height(text or ""))
        info.text_size = (content_width(), None)

    def set_tab(tab):
        _state["tab"], _state["shown"] = tab, PAGE
        nav.show_downloads()

    def cycle_type(_i):
        order = list(kinds)
        nxt = order[(order.index(_state["kind"]) + 1) % len(order)] if _state["kind"] in order else order[0]
        _state["kind"], _state["shown"] = nxt, PAGE
        nav.show_downloads()

    type_btn.bind(on_press=cycle_type)

    def on_query(_i, value):
        _state["query"], _state["shown"] = value, PAGE
        refresh_active()
        build_finished()

    search.bind(text=on_query)

    def clear_list():
        downloads_history.clear()
        dm.clear_finished()
        selected.clear()
        build_finished()
        refresh_active()

    clear_btn.bind(on_press=lambda i: clear_list())

    # -- footer: Back, or the selection bar ---------------------------------------------------------
    def row_of(buttons):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP / 2)
        for text, fn in buttons:
            btn = Button(text=text, **({"background_color": _DANGER} if text.startswith("Delete") else {}))
            btn.bind(on_press=fn)
            row.add_widget(btn)
        return row

    def make_sel_footer():
        bar = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP / 2)
        bar.height = dp(34) + 2 * BTN_H + GAP
        sel_info.parent.remove_widget(sel_info) if sel_info.parent is not None else None
        bar.add_widget(sel_info)
        bar.add_widget(row_of([("Select all", lambda i: select_all(True)), ("Clear", lambda i: select_all(False))]))
        bar.add_widget(row_of([("Delete files", lambda i: ask_delete(selected_entries())),
                               ("Remove from list", lambda i: remove_from_list(selected_entries()))]))
        return bar

    sel_info = Label(text="", size_hint_y=None, height=dp(34), halign="center", valign="middle")
    sel_info.text_size = (content_width(), None)

    def refresh_footer():
        want = "sel" if selected else "nav"
        sel_info.text = f"Selected: {len(selected)} of {len(shown_ids)}"
        if want == footer_state["mode"]:
            return
        footer_state["mode"] = want
        if want == "sel":
            nav.set_footer(make_sel_footer())
        else:
            if back_row.parent is not None:
                back_row.parent.remove_widget(back_row)
            nav.set_footer(back_row)

    def selected_entries():
        return [e for e in downloads_history.load() if e.get("id") in selected]

    def set_selected(eid, value):
        (selected.add if value else selected.discard)(eid)
        if eid in entry_color:
            entry_color[eid].rgba = CARD_ON if value else CARD
        refresh_footer()

    def select_all(value):
        for eid in list(shown_ids):
            if eid in busy:
                continue
            (selected.add if value else selected.discard)(eid)
            if eid in entry_color:
                entry_color[eid].rgba = CARD_ON if value else CARD
        refresh_footer()

    # -- live downloads ------------------------------------------------------------------------
    def make_card(t):
        row = card_box([ROW_H], padding=dp(4), spacing=0)
        color = paint_card(row, CARD)
        line = BoxLayout(orientation="horizontal", size_hint_y=None, height=ROW_H, spacing=dp(4))
        main = Button(text="", size_hint_x=0.80, halign="left", valign="middle",
                      background_normal="", background_color=(0, 0, 0, 0))
        main.text_size = (row_w, None)
        main.bind(on_press=lambda i, tid=t.id: task_menu(tid))
        more = Button(text="\u2022\u2022\u2022", size_hint_x=0.20)
        more.bind(on_press=lambda i, tid=t.id: task_menu(tid))
        line.add_widget(main)
        line.add_widget(more)
        row.add_widget(line)
        return row, main, more, color

    def task_menu(task_id):
        t = dm.get(task_id)
        if t is None:
            return
        buttons = []
        if t.active and t.state not in (dm.SAVING,):
            buttons.append(("Resume" if t.state == dm.PAUSED else "Pause", lambda: toggle_pause(task_id), False))
        if t.state != dm.SAVING:
            buttons.append(("Stop" if t.active else "Remove", lambda: stop_or_remove(task_id), True))
        _menu(t.name, buttons)

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

    def refresh_tabs(all_tasks):
        live = [t for t in all_tasks if t.state != dm.DONE]
        n_fail = sum(1 for t in live if _is_failed(t))
        n_down = len(live) - n_fail
        n_done = len(downloads_history.load()) if not hasattr(refresh_tabs, "n") else refresh_tabs.n
        counts = {"All": len(live) + n_done, "Downloading": n_down, "Finished": n_done, "Failed": n_fail}
        for tab, btn in tab_buttons.items():
            _set(btn, ("\u25cf " if tab == _state["tab"] else "") + (f"{tab} ({counts[tab]})" if counts[tab] else tab))

    def refresh_active():
        all_tasks = dm.snapshot()
        shown = [t for t in all_tasks if t.state != dm.DONE and _matches(t.name) and _task_in_tab(t)]
        wanted = {t.id for t in shown}
        for tid in [k for k in cards if k not in wanted]:
            active_box.remove_widget(cards.pop(tid)[0])
        for t in reversed(shown):                    # oldest first
            if t.id not in cards:
                cards[t.id] = make_card(t)
                active_box.add_widget(cards[t.id][0])
        for t in shown:
            _row, main, _more, color = cards[t.id]
            _set(main, f"{_short(t.name, row_w)}\n{_task_meta(t)}")
            color.rgba = _FAILED if _is_failed(t) else CARD
        if not shown:
            active_box.height = 0
        done_now = {t.id for t in all_tasks if t.state == dm.DONE}
        if done_now - seen_done:
            seen_done.update(done_now)
            build_finished()
        refresh_tabs(all_tasks)

    # -- saved files ---------------------------------------------------------------------------
    def build_finished():
        finished_box.clear_widgets()
        entry_color.clear()
        entry_row.clear()
        shown_ids[:] = []
        all_entries = downloads_history.load()
        refresh_tabs.n = len(all_entries)
        if _state["tab"] in ("Downloading", "Failed"):
            finished_box.height = 0
            return
        entries = [e for e in all_entries if _matches(e.get("name", ""))]
        selected.intersection_update({e.get("id") for e in entries})
        shown_ids.extend(e.get("id") for e in entries)
        if not entries:
            finished_box.add_widget(Label(text="No downloads yet", size_hint_y=None, height=BTN_H))
            refresh_footer()
            return
        for entry in entries[:_state["shown"]]:
            finished_box.add_widget(make_entry_row(entry))
        if len(entries) > _state["shown"]:
            more = Button(text="Show more", size_hint_y=None, height=BTN_H)
            more.bind(on_press=lambda i: show_more())
            finished_box.add_widget(more)
        refresh_footer()

    def make_entry_row(entry):
        eid = entry.get("id")
        row = card_box([ROW_H], padding=dp(4), spacing=0)
        entry_color[eid] = paint_card(row, CARD_ON if eid in selected else CARD)
        entry_row[eid] = row
        line = BoxLayout(orientation="horizontal", size_hint_y=None, height=ROW_H, spacing=dp(4))
        meta = f"{entry.get('time', '')}   {_size_text(entry.get('size'))}   [{entry.get('category', '')}]"
        main = _PressCard(on_tap=lambda e=eid: on_tap(e), on_hold=lambda en=entry: entry_menu(en),
                          text=f"{_short(entry.get('name', ''), row_w)}\n{meta}", size_hint_x=0.80,
                          halign="left", valign="middle", background_normal="", background_color=(0, 0, 0, 0))
        main.text_size = (row_w, None)
        more = Button(text="\u2022\u2022\u2022", size_hint_x=0.20)
        more.bind(on_press=lambda i, en=entry: entry_menu(en))
        line.add_widget(main)
        line.add_widget(more)
        row.add_widget(line)
        return row

    def on_tap(eid):
        if eid in busy:
            return
        set_selected(eid, eid not in selected)

    def entry_menu(entry):
        eid = entry.get("id")
        if eid in busy:
            return
        loc, name = entry.get("location"), entry.get("name", "")
        _menu(name, [
            ("Open", lambda: say(android_open.open_file(loc, name)), False),
            ("Share", lambda: say(android_open.share_file(loc, name)), False),
            ("Delete file", lambda: ask_delete([entry]), True),
            ("Remove from list only", lambda: remove_from_list([entry]), False),
        ])

    def show_more():
        _state["shown"] += PAGE
        build_finished()

    # -- deleting ------------------------------------------------------------------------------
    def drop_rows(ids):
        for eid in ids:
            selected.discard(eid)
            busy.discard(eid)
            if eid in shown_ids:
                shown_ids.remove(eid)
            row = entry_row.pop(eid, None)
            entry_color.pop(eid, None)
            if row is not None and row.parent is not None:
                row.parent.remove_widget(row)
        refresh_tabs.n = max(0, getattr(refresh_tabs, "n", 0) - len(ids))
        if not shown_ids and not busy:
            finished_box.add_widget(Label(text="No downloads yet", size_hint_y=None, height=BTN_H))
        refresh_footer()

    def remove_from_list(entries):
        if not entries:
            return
        ids = [e.get("id") for e in entries]
        downloads_history.remove_many(ids)
        drop_rows(ids)
        say(f"Removed {len(ids)} from the list (files stay)")

    def ask_delete(entries):
        if not entries:
            say("Tap a file to select it first")
            return
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
        count = len(entries)
        text = (f"Delete this file from the phone?\n{_short(entries[0].get('name', ''), content_width() * 0.7)}"
                if count == 1 else f"Delete the {count} selected files from the phone?")
        box.add_widget(Label(text=text + "\nThis cannot be undone.", halign="center"))
        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        no_btn = Button(text="Cancel")
        yes_btn = Button(text="Yes, delete", background_color=_DANGER)
        buttons.add_widget(no_btn)
        buttons.add_widget(yes_btn)
        box.add_widget(buttons)
        dialog = ModalView(size_hint=(0.92, None), height=dp(210), background="",
                           background_color=(0.13, 0.10, 0.09, 1))
        dialog.add_widget(box)
        no_btn.bind(on_press=lambda i: dialog.dismiss())
        yes_btn.bind(on_press=lambda i: (dialog.dismiss(), start_delete(entries)))
        dialog.open()

    def start_delete(entries):
        entries = [e for e in entries if e.get("id") not in busy]
        if not entries:
            return
        for e in entries:
            eid = e.get("id")
            selected.discard(eid)
            busy.add(eid)
            if eid in entry_color:
                entry_color[eid].rgba = _BUSY
        refresh_footer()
        say(f"Deleting {len(entries)} file(s)...")

        def worker():
            gone = 0
            for e in entries:
                try:
                    if android_open.delete_file(e.get("location")):
                        gone += 1
                except Exception:
                    pass
            Clock.schedule_once(lambda dt: finish(entries, gone), 0)

        def finish(done_entries, gone):
            ids = [e.get("id") for e in done_entries]
            downloads_history.remove_many(ids)
            drop_rows(ids)
            missing = len(ids) - gone
            say(f"Deleted {gone} file(s)" + (f", {missing} already gone" if missing else ""))

        run_in_background(worker)

    seen_done.update(t.id for t in dm.snapshot() if t.state == dm.DONE)
    build_finished()
    nav.set_footer(back_row)
    nav.start_progress_timer(refresh_active, interval=1.0)
