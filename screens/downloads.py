"""Downloads: one compact list like 1DM+ - tabs (All / Downloading / Adding / Finished / Error / Scheduler), one small
row per file with a "..." menu, tap = select, hold = menu, group delete.

Live part: what "Download in app" is saving now (Pause / Resume / Stop), updated in place once a
second (core/download_manager.py). Finished part: the files saved on the phone (Open / Share /
Delete). Deleting asks first and can remove the real file from the phone or only the list entry.

Files can also be only added (Adding tab: tap to select, then Start now / Add to scheduler) or scheduled
(Scheduler tab: a daily start / stop time by the phone's clock, core/download_manager.py).

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

from api import download_queue_prefs, downloads_history, release_delete_prefs
from core import (android_downloads, android_open, download_manager as dm, download_schedule, file_types, phone_files,
                  release_links, segmented_download)
from core.async_utils import run_in_background
from core.links import split_links
from screens.common import (BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box,
                            content_width, font_px, paint_card, paste_row, wrapped_label_height)
from screens import dialogs
from screens.history import _PressCard

_DANGER = (1.0, 0.55, 0.55, 1)
_FAILED = (0.30, 0.12, 0.12, 1)
_BUSY = (0.45, 0.12, 0.12, 1)
PAGE = 30
ROW_H = dp(62)
TABS = ("All", "Downloading", "Adding", "Finished", "Error", "Scheduler")
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
    if tab == "Error":
        return _is_failed(t)
    if tab == "Adding":
        return t.state == dm.ADDED
    if tab == "Scheduler":
        return t.scheduled and not _is_failed(t)
    if tab == "Downloading":
        return t.state in (dm.QUEUED, dm.RUNNING, dm.PAUSED, dm.SAVING)
    return True


def _schedule_hint():
    cfg = download_queue_prefs.schedule()
    if not cfg["enabled"]:
        return "Scheduled - the scheduler is OFF"
    return f"Scheduled - starts at {cfg['start']}"


def _task_meta(t):
    if t.state == dm.ADDED:
        return "Added - waiting for you to start it"
    if t.state == dm.SCHEDULED:
        return _schedule_hint()
    if t.state == dm.PAUSED and t.sched_paused:
        return "Paused until the next start time"
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


def _probe(url):
    """(file name, size in bytes or 0) of a direct link."""
    name, size = _name_for(url), 0
    try:
        import requests
        r = requests.head(url, allow_redirects=True, timeout=10)
        size = int(r.headers.get("Content-Length") or 0)
    except Exception:
        pass
    return name, size


def _save_link(url, name):
    """Runs in a background thread. The task shows up in the live list; a failure stays there
    with its message, so nothing more is needed here."""
    try:
        android_downloads.download_to_downloads(url, name=name, category="Other")
    except segmented_download.Cancelled:
        pass
    except Exception:
        pass


def _download_link(url):
    name, size = _probe(url)
    if size and phone_files.index().has(name, size):      # same name + size is already on the phone
        Clock.schedule_once(lambda dt: dialogs.menu(
            f"Already on the phone: {name}",
            [("Download again", lambda: run_in_background(_save_link, url, name), False)]), 0)
        return
    _save_link(url, name)


def _time_dialog(title, current, on_save, allow_off=False):
    """A small popup to type an hour and minutes (the phone's clock). ``on_save("HH:MM")``; with
    ``allow_off`` a third button calls ``on_save("")`` (no time)."""
    hm = download_schedule.parse_hm(current) or (0, 0)
    box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
    box.add_widget(Label(text=title, size_hint_y=None, height=dp(40)))
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    hour = TextInput(text=f"{hm[0]:02d}", multiline=False, input_filter="int", halign="center", hint_text="HH")
    mins = TextInput(text=f"{hm[1]:02d}", multiline=False, input_filter="int", halign="center", hint_text="MM")
    row.add_widget(hour)
    row.add_widget(Label(text=":", size_hint_x=None, width=dp(16)))
    row.add_widget(mins)
    box.add_widget(row)
    msg = Label(text="", size_hint_y=None, height=dp(30), color=_DANGER)
    box.add_widget(msg)
    dialog = ModalView(size_hint=(0.92, None), height=dp(190) + (2 if allow_off else 1) * (BTN_H + GAP),
                       background="", background_color=(0.13, 0.10, 0.09, 1))

    def save(_i):
        try:
            h, m = int(hour.text), int(mins.text)
        except ValueError:
            msg.text = "Type the hour and the minutes"
            return
        if not (0 <= h <= 23 and 0 <= m <= 59):
            msg.text = "Hour 0-23, minutes 0-59"
            return
        dialog.dismiss()
        on_save(f"{h:02d}:{m:02d}")

    buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    cancel_btn, save_btn = Button(text="Cancel"), Button(text="Save")
    cancel_btn.bind(on_press=lambda i: dialog.dismiss())
    save_btn.bind(on_press=save)
    buttons.add_widget(cancel_btn)
    buttons.add_widget(save_btn)
    box.add_widget(buttons)
    if allow_off:
        off_btn = Button(text="No stop time", size_hint_y=None, height=BTN_H)
        off_btn.bind(on_press=lambda i: (dialog.dismiss(), on_save("")))
        box.add_widget(off_btn)
    dialog.add_widget(box)
    dialog.open()


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
    switch = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=dp(4))
    here_btn = Button(text="\u25cf Phone")
    there_btn = Button(text="Release")
    there_btn.bind(on_press=lambda i: nav.show_release_history())
    switch.add_widget(here_btn)
    switch.add_widget(there_btn)
    nav.add(switch)
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

    # -- scheduler panel (Scheduler tab only) ---------------------------------------------------------
    sched_w = {}

    def sched_status_text():
        cfg = download_queue_prefs.schedule()
        if not cfg["enabled"]:
            return "Scheduler is off"
        inside = download_schedule.in_window(download_schedule.parse_hm(cfg["start"]),
                                             download_schedule.parse_hm(cfg["stop"]))
        return ("Inside the time window - scheduled files run" if inside
                else "Outside the time window - waiting for the start time")

    def make_scheduler_panel():
        box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
        box.bind(minimum_height=box.setter("height"))
        clock = Label(text="", size_hint_y=None, height=dp(30), color=(1, 0.75, 0.4, 1))
        status_lbl = Label(text="", size_hint_y=None, height=dp(44), halign="center", valign="middle")
        status_lbl.text_size = (content_width(), None)
        sched_w["clock"], sched_w["status"] = clock, status_lbl
        on_btn = Button(text="", size_hint_y=None, height=BTN_H)
        time_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP / 2)
        start_btn, stop_btn = Button(text=""), Button(text="")
        time_row.add_widget(start_btn)
        time_row.add_widget(stop_btn)
        go_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP / 2)
        go_btn, halt_btn = Button(text="Start now"), Button(text="Stop now")
        go_row.add_widget(go_btn)
        go_row.add_widget(halt_btn)
        hint = Label(text="The time is the phone's clock. Scheduled files run between the start and stop time "
                          "every day, while the app is open.", size_hint_y=None, halign="center", valign="middle")
        hint.text_size = (content_width(), None)
        hint.height = max(dp(44), wrapped_label_height(hint.text))

        def paint():
            cfg = download_queue_prefs.schedule()
            on_btn.text = "Scheduler: ON" if cfg["enabled"] else "Scheduler: OFF"
            start_btn.text = f"Start time: {cfg['start']}"
            stop_btn.text = f"Stop time: {cfg['stop']}" if cfg["stop"] else "Stop time: not set"
            _set(status_lbl, sched_status_text())

        def kick():
            paint()
            dm.ensure_scheduler()
            run_in_background(dm.scheduler_tick)

        def toggle(_i):
            download_queue_prefs.set_schedule(enabled=not download_queue_prefs.schedule()["enabled"])
            kick()

        def pick_start(_i):
            _time_dialog("Start time", download_queue_prefs.schedule()["start"],
                         lambda v: (download_queue_prefs.set_schedule(start=v), kick()))

        def pick_stop(_i):
            _time_dialog("Stop time", download_queue_prefs.schedule()["stop"] or "06:00",
                         lambda v: (download_queue_prefs.set_schedule(stop=v), kick()), allow_off=True)

        on_btn.bind(on_press=toggle)
        start_btn.bind(on_press=pick_start)
        stop_btn.bind(on_press=pick_stop)
        go_btn.bind(on_press=lambda i: (dm.scheduler_start_now(), say("Scheduled files started")))
        halt_btn.bind(on_press=lambda i: (dm.scheduler_stop_now(), say("Scheduled downloads paused")))
        for w in (clock, status_lbl, on_btn, time_row, go_row, hint):
            box.add_widget(w)
        paint()
        return box

    # -- tabs ------------------------------------------------------------------------------------
    tab_buttons = {}
    for group in (TABS[:3], TABS[3:]):
        tab_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=dp(4))
        for tab in group:
            btn = Button(text=tab)
            btn.bind(on_press=lambda i, t=tab: set_tab(t))
            tab_buttons[tab] = btn
            tab_row.add_widget(btn)
        nav.add(tab_row)
    if _state["tab"] == "Scheduler":
        nav.add(make_scheduler_panel())

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
    sel_tasks = set()     # ids of selected waiting files (Adding / Scheduler tabs)
    pending_ids = []      # ids of the waiting files shown now (what "Select all" selects)
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

    def make_task_footer():
        bar = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP / 2)
        bar.height = dp(34) + 2 * BTN_H + GAP
        tsel_info.parent.remove_widget(tsel_info) if tsel_info.parent is not None else None
        bar.add_widget(tsel_info)
        bar.add_widget(row_of([("Select all", lambda i: select_all_tasks(True)),
                               ("Clear", lambda i: select_all_tasks(False))]))
        if _state["tab"] == "Scheduler":
            second = ("Back to Adding", lambda i: schedule_selected(False))
        else:
            second = ("Add to scheduler", lambda i: schedule_selected(True))
        bar.add_widget(row_of([("Start now", lambda i: start_selected()), second,
                               ("Remove from list", lambda i: remove_selected())]))
        return bar

    tsel_info = Label(text="", size_hint_y=None, height=dp(34), halign="center", valign="middle")
    tsel_info.text_size = (content_width(), None)

    def refresh_footer():
        want = "tsel" if sel_tasks else ("sel" if selected else "nav")
        sel_info.text = f"Selected: {len(selected)} of {len(shown_ids)}"
        tsel_info.text = f"Selected: {len(sel_tasks)} of {len(pending_ids)}"
        if want == footer_state["mode"]:
            return
        footer_state["mode"] = want
        if want == "tsel":
            nav.set_footer(make_task_footer())
        elif want == "sel":
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
        main = _PressCard(on_tap=lambda tid=t.id: task_tap(tid), on_hold=lambda tid=t.id: task_menu(tid),
                          text="", size_hint_x=0.80, halign="left", valign="middle",
                          background_normal="", background_color=(0, 0, 0, 0))
        main.text_size = (row_w, None)
        more = Button(text="\u2022\u2022\u2022", size_hint_x=0.20)
        more.bind(on_press=lambda i, tid=t.id: task_menu(tid))
        line.add_widget(main)
        line.add_widget(more)
        row.add_widget(line)
        return row, main, more, color

    def task_tap(task_id):
        t = dm.get(task_id)
        if t is None:
            return
        if t.pending:                       # a waiting file: tap = select
            (sel_tasks.discard if task_id in sel_tasks else sel_tasks.add)(task_id)
            if task_id in cards:
                cards[task_id][3].rgba = CARD_ON if task_id in sel_tasks else CARD
            refresh_footer()
        else:
            task_menu(task_id)

    def select_all_tasks(value):
        for tid in list(pending_ids):
            (sel_tasks.add if value else sel_tasks.discard)(tid)
            if tid in cards:
                cards[tid][3].rgba = CARD_ON if value else CARD
        refresh_footer()

    def selected_pending():
        return [t.id for t in (dm.get(i) for i in list(sel_tasks)) if t is not None and t.pending]

    def finish_selection(text):
        sel_tasks.clear()
        say(text)
        refresh_active()
        refresh_footer()

    def start_selected():
        n = sum(1 for tid in selected_pending() if dm.start_task(tid))
        finish_selection(f"Started {n} file(s)")

    def schedule_selected(on):
        n = dm.set_scheduled(selected_pending(), on)
        finish_selection(f"Added {n} file(s) to the scheduler" if on else f"Moved {n} file(s) back to Adding")

    def remove_selected():
        finish_selection(f"Removed {dm.remove_pending(selected_pending())} waiting file(s)")

    def task_menu(task_id):
        t = dm.get(task_id)
        if t is None:
            return
        if t.pending:
            def one(fn, text):
                return lambda: (fn(), say(text), refresh_active())
            move = (("Back to Adding", one(lambda: dm.set_scheduled([task_id], False), "Moved 1 file(s) back to Adding"))
                    if t.state == dm.SCHEDULED else
                    ("Add to scheduler", one(lambda: dm.set_scheduled([task_id], True), "Added 1 file(s) to the scheduler")))
            _menu(t.name, [("Start now", one(lambda: dm.start_task(task_id), "Started 1 file(s)"), False),
                           (move[0], move[1], False),
                           ("Remove from list", one(lambda: dm.remove_pending([task_id]), "Removed 1 waiting file(s)"), True)])
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
        n_down = sum(1 for t in live if t.state in (dm.QUEUED, dm.RUNNING, dm.PAUSED, dm.SAVING))
        n_add = sum(1 for t in live if t.state == dm.ADDED)
        n_sch = sum(1 for t in live if t.scheduled and not _is_failed(t))
        n_done = len(downloads_history.load()) if not hasattr(refresh_tabs, "n") else refresh_tabs.n
        counts = {"All": len(live) + n_done, "Downloading": n_down, "Adding": n_add, "Finished": n_done,
                  "Error": n_fail, "Scheduler": n_sch}
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
        pending_ids[:] = [t.id for t in shown if t.pending]
        sel_tasks.intersection_update(pending_ids)
        for t in shown:
            _row, main, _more, color = cards[t.id]
            _set(main, f"{_short(t.name, row_w)}\n{_task_meta(t)}")
            color.rgba = _FAILED if _is_failed(t) else (CARD_ON if t.id in sel_tasks else CARD)
        if sched_w:
            _set(sched_w["clock"], f"Phone time: {download_schedule.phone_time_text()}")
            _set(sched_w["status"], sched_status_text())
        refresh_footer()
        if not shown:
            active_box.height = 0
        done_now = {t.id for t in all_tasks if t.state == dm.DONE}
        if done_now - seen_done:
            seen_done.update(done_now)
            build_finished()
            Clock.schedule_once(lambda dt: check_release_prompts(), 0.8)
        refresh_tabs(all_tasks)

    # -- saved files ---------------------------------------------------------------------------
    def build_finished():
        finished_box.clear_widgets()
        entry_color.clear()
        entry_row.clear()
        shown_ids[:] = []
        all_entries = downloads_history.load()
        refresh_tabs.n = len(all_entries)
        if _state["tab"] in ("Downloading", "Adding", "Error", "Scheduler"):
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
        buttons = [
            ("Open", lambda: say(android_open.open_file(loc, name)), False),
            ("Share", lambda: say(android_open.share_file(loc, name)), False),
            ("Delete file", lambda: ask_delete([entry]), True),
        ]
        rec = release_links.get(name, entry.get("size"))
        if rec:
            buttons.append(("Delete from release", lambda: dialogs.confirm(
                "Delete this file from the release?", "Yes, delete from release",
                lambda: release_delete([rec["item"]])), True))
        buttons.append(("Remove from list only", lambda: remove_from_list([entry]), False))
        _menu(name, buttons)

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

    # -- files that came from a release: offer to delete them there too ------------------------------
    def release_delete(items):
        if not items:
            return
        total, ok_count = len(items), [0]
        say(f"Deleting {total} from the release...")

        def on_item(item, ok):
            if ok:
                ok_count[0] += 1
                release_links.forget_item(item)

        def on_done(_res):
            say(f"Deleted {ok_count[0]} of {total} from the release")

        nav.start_inline_delete(items, on_item, on_done)

    def check_release_prompts():
        found, seen = [], set()
        for entry in downloads_history.load():
            rec = release_links.get(entry.get("name"), entry.get("size"))
            if rec and not rec.get("asked") and rec["key"] not in seen:
                seen.add(rec["key"])
                found.append(rec)
        if not found:
            return
        release_links.mark_asked([r["key"] for r in found])
        items = [r["item"] for r in found]
        mode = release_delete_prefs.mode()
        if mode == "never":
            return
        if mode == "always":
            release_delete(items)
            return
        dialogs.confirm(f"{len(items)} file(s) you downloaded from the release are on the phone now.\n"
                        "Delete them from the release too?", "Delete from release",
                        lambda: release_delete(items), "Keep in release")

    seen_done.update(t.id for t in dm.snapshot() if t.state == dm.DONE)
    build_finished()
    nav.set_footer(back_row)
    Clock.schedule_once(lambda dt: check_release_prompts(), 0.6)
    nav.start_progress_timer(refresh_active, interval=1.0)
