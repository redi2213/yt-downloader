from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import escape_markup

from datetime import datetime

from core import android_actions, timeutil
from kivy.metrics import dp

from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box,
    content_width, paint_card, wrapped_label, wrapped_label_height,
)

_DANGER = (1.0, 0.55, 0.55, 1)   # tint for buttons that delete things


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))
    nav.add(back_button(nav))


def fill_follow_box(box, follows, new, on_open):
    """One compact button per Auto follow channel (their files are no longer behind the
    channel's own screen)."""
    box.clear_widgets()
    if not follows:
        box.height = 0
        return
    for f in follows:
        badge = f"  [NEW {new[f['id']]}]" if new.get(f.get("id")) else ""
        btn = Button(text=f"Auto follow: {f.get('name', '?')}{badge}", size_hint_y=None, height=BTN_H)
        btn.bind(on_press=lambda i, f=f: on_open(f))
        box.add_widget(btn)


def build_bot_error(nav, message, back=None):
    """The Telegram bot's file list could not be read (e.g. the app has no access to its repo)."""
    nav.clear()
    nav.add(Label(text=message, size_hint_y=None, height=dp(110), halign="center"))
    nav.add(back_button(nav, to=back))


_VIDEO = {"mp4", "mkv", "webm", "mov", "avi", "ts", "m4v", "3gp"}
_AUDIO = {"mp3", "m4a", "flac", "opus", "ogg", "wav", "aac", "wma"}
_TYPE_NAMES = ("All", "Video", "Audio", "Other")
_SORT_NAMES = ("Newest", "Biggest", "Expiring soon")


def _kind(item):
    title = str(item.get("title", ""))
    ext = title.rsplit(".", 1)[-1].lower() if "." in title else ""
    return "Video" if ext in _VIDEO else ("Audio" if ext in _AUDIO else "Other")


def _expiry_key(item):
    if item.get("forever") or item.get("days_left") is None:
        return (1, 0)
    return (0, item["days_left"])


def _day_label(item):
    """Group heading of a file: Today / Yesterday / This week / its day (Jalali when set)."""
    dt = timeutil.parse_utc(item.get("sort_ts"))
    if dt is None:
        return ""
    tz = timeutil._local_tz()
    diff = (datetime.now(tz).date() - dt.astimezone(tz).date()).days
    if diff <= 0:
        return "Today"
    if diff == 1:
        return "Yesterday"
    if diff < 7:
        return "This week"
    return timeutil.datetime_to_local(dt, "%Y-%m-%d")


def _deadline_color(item):
    if item.get("forever"):
        return "66dd88"
    days = item.get("days_left")
    if days is None:
        return "aaaaaa"
    return "ff6666" if days <= 3 else ("ffcc55" if days <= 7 else "66dd88")


def _meta_parts(item):
    """(size, date, quality, deadline) pieces of the small grey line under a file's title."""
    size_mb = item.get("size", 0) / (1024 * 1024)
    parts = [f"{size_mb:.1f} MB"] if size_mb else []
    parts.append(str(item["date"]).replace("\n", " "))
    if item.get("quality_label"):
        parts.append(item["quality_label"])
    deadline = item.get("deadline_text") if item.get("asset_id") is not None else ""
    return parts, deadline


def _grid_rows(nav, buttons):
    """Compact buttons, two per row: ``buttons`` = [(text, callback)]."""
    for i in range(0, len(buttons), 2):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        for text, fn in buttons[i:i + 2]:
            btn = Button(text=text)
            btn.bind(on_press=lambda _i, fn=fn: fn())
            row.add_widget(btn)
        if len(buttons[i:i + 2]) == 1:
            row.add_widget(Widget())
        nav.add(row)


def build(nav, items, title="Release History", back=None, extra=None, page=0, has_next=False,
          follows=None, new=None, on_follow=None, bot=False, on_bot=None, apk=False, on_apk=None,
          on_deadlines=None):
    """``title`` / ``back``: another title and parent screen when this list shows only
    one Auto follow channel's files. ``extra``: (button text, function) shown at the top.

    Compact list: one small card per file (title, grey size/date line, coloured days left, quick
    Copy). Tap a card = its menu (copy, share, rename, zip, extend, delete). "Select files" turns
    on the selection toolbar (copy/share/delete many); nothing destructive is on screen otherwise."""
    nav.clear()
    paged = back is None or bot or apk   # the normal list and the bot's list are paged; one Auto follow channel is not
    heading = f"{title} - page {page + 1} ({len(items)} files)" if paged else f"{title} ({len(items)} found)"
    nav.add(Label(text=heading, size_hint_y=None, height=BTN_H))

    top = []
    if on_deadlines and not bot and not apk and page == 0:
        top.append(("File deadlines", on_deadlines))
    if on_bot and not bot and page == 0:
        top.append(("Telegram bot", on_bot))
    if on_apk and not bot and not apk and page == 0:
        top.append(("APK and backups", on_apk))
    if paged and not bot and not apk and page == 0 and hasattr(nav, "show_arvan_files"):
        top.append(("Arvan files", nav.show_arvan_files))
    _grid_rows(nav, top)

    follow_box = None
    if paged and not bot and not apk and page == 0:
        follow_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
        follow_box.bind(minimum_height=follow_box.setter("height"))
        nav.add(follow_box)
        if on_follow:
            fill_follow_box(follow_box, follows or [], new or {}, on_follow)
    if extra:
        extra_btn = Button(text=extra[0], size_hint_y=None, height=BTN_H)
        extra_btn.bind(on_press=lambda i: extra[1]())
        nav.add(extra_btn)

    selected = [False] * len(items)
    select_mode = [False]
    cards = {}   # item index -> card colour of the cards on screen
    view = []    # item indices shown now (after search / type filter / sort)
    state = {"type": 0, "sort": 0}
    all_btn_ref = []
    info = Label(text="", size_hint_y=None, height=BTN_H)
    toolbar = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    toolbar.bind(minimum_height=toolbar.setter("height"))
    toolbar.height = 0
    mode_btn = Button(text="Select files", size_hint_y=None, height=BTN_H)
    search = TextInput(hint_text="Search in this page", multiline=False, size_hint_y=None, height=SMALL_BTN_H)
    type_btn = Button(text="Type: All")
    sort_btn = Button(text="Sort: Newest")
    list_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    list_box.bind(minimum_height=list_box.setter("height"))
    inner_width = content_width() - 2 * dp(8)

    def selected_items():
        return [items[i] for i in view if selected[i]]

    def update_info(*_args):
        info.text = f"Selected: {len(selected_items())} of {len(view)}"

    def set_selected(idx, value):
        selected[idx] = value
        if idx in cards:
            cards[idx].rgba = CARD_ON if value else CARD
        update_info()

    def set_all(value):
        for idx in list(view):
            set_selected(idx, value)

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

    def arvan_selected(_inst):
        sel = need_selection()
        if not sel:
            return
        own = [it for it in sel if it.get("asset_id") is not None and not it.get("repo")]
        if own:
            nav.start_arvan_upload(own)
        else:
            info.text = "Select files kept on GitHub (not Arvan or bot files)"

    def fill_toolbar():
        toolbar.clear_widgets()
        all_btn_ref.clear()
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        for text, fn in (("Select all", lambda i: set_all(True)), ("Clear", lambda i: set_all(False))):
            btn = Button(text=text)
            btn.bind(on_press=fn)
            row.add_widget(btn)
        toolbar.add_widget(row)
        update_info()
        toolbar.add_widget(info)
        actions = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        buttons = [("Copy links", copy_selected), ("Share", share_selected)]
        if not bot and not apk and hasattr(nav, "start_arvan_upload"):
            buttons.append(("To Arvan", arvan_selected))
        buttons.append(("Delete", delete_selected))
        for text, fn in buttons:
            btn = Button(text=text, background_color=_DANGER) if text == "Delete" else Button(text=text)
            btn.bind(on_press=fn)
            actions.add_widget(btn)
        toolbar.add_widget(actions)
        all_btn = Button(text=f"Delete all {len(view)} shown", size_hint_y=None, height=BTN_H,
                         background_color=_DANGER)
        all_btn.bind(on_press=lambda i: nav.show_bulk_delete_confirm([items[n] for n in view]))
        all_btn_ref.append(all_btn)
        toolbar.add_widget(all_btn)

    def toggle_mode(_inst):
        select_mode[0] = not select_mode[0]
        if select_mode[0]:
            mode_btn.text = "Done selecting"
            fill_toolbar()
        else:
            set_all(False)
            mode_btn.text = "Select files"
            toolbar.clear_widgets()
            all_btn_ref.clear()
            toolbar.height = 0

    def on_tap(idx, item):
        if select_mode[0]:
            set_selected(idx, not selected[idx])
        else:
            nav.show_item_menu(item)

    def make_card(idx, item):
        parts, deadline = _meta_parts(item)
        meta_plain = "  ·  ".join(parts + ([deadline] if deadline else []))
        plain = f"{item['title']}\n{meta_plain}"
        markup = (f"{escape_markup(item['title'])}\n[size=13sp][color=999999]{escape_markup('  ·  '.join(parts))}[/color]"
                  + (f"  [color={_deadline_color(item)}]{escape_markup(deadline)}[/color]" if deadline else "")
                  + "[/size]")
        text_w = (inner_width - dp(16)) * 0.78
        title_height = max(BTN_H, wrapped_label_height(plain, extra_padding=dp(14), width=text_w))
        row = card_box([title_height])
        cards[idx] = paint_card(row, CARD_ON if selected[idx] else CARD)
        line = BoxLayout(orientation="horizontal", size_hint_y=None, height=title_height, spacing=dp(4))
        title_btn = Button(text=markup, markup=True, size_hint_x=0.78, halign="left", valign="middle",
                           background_normal="", background_color=(0, 0, 0, 0))
        title_btn.text_size = (text_w, None)
        title_btn.bind(on_press=lambda i, n=idx, it=item: on_tap(n, it))
        line.add_widget(title_btn)
        copy_btn = Button(text="Copy", size_hint_x=0.22)

        def do_copy(btn, l=item["link"]):
            Clipboard.copy(l)
            btn.text = "Copied"

        copy_btn.bind(on_press=do_copy)
        line.add_widget(copy_btn)
        row.add_widget(line)
        return row

    def compute_view():
        q = search.text.strip().lower()
        want = _TYPE_NAMES[state["type"]]
        idxs = [i for i, it in enumerate(items)
                if (not q or q in str(it.get("title", "")).lower()) and (want == "All" or _kind(it) == want)]
        if state["sort"] == 1:
            idxs.sort(key=lambda i: -items[i].get("size", 0))
        elif state["sort"] == 2:
            idxs.sort(key=lambda i: _expiry_key(items[i]))
        return idxs

    def render_list(*_args):
        list_box.clear_widgets()
        cards.clear()
        view[:] = compute_view()
        if not view:
            list_box.add_widget(Label(text="No matching files", size_hint_y=None, height=BTN_H))
        last = None
        for idx in view:
            if state["sort"] == 0:
                group = _day_label(items[idx])
                if group and group != last:
                    head = Label(text=group, size_hint_y=None, height=dp(30), halign="left",
                                 color=(0.7, 0.7, 0.7, 1))
                    head.text_size = (inner_width, None)
                    list_box.add_widget(head)
                    last = group
            list_box.add_widget(make_card(idx, items[idx]))
        update_info()
        if all_btn_ref:
            all_btn_ref[0].text = f"Delete all {len(view)} shown"

    def cycle_type(_inst):
        state["type"] = (state["type"] + 1) % len(_TYPE_NAMES)
        type_btn.text = f"Type: {_TYPE_NAMES[state['type']]}"
        render_list()

    def cycle_sort(_inst):
        state["sort"] = (state["sort"] + 1) % len(_SORT_NAMES)
        sort_btn.text = f"Sort: {_SORT_NAMES[state['sort']]}"
        render_list()

    if not items:
        nav.add(Label(text="No files yet" if back else "No downloads yet", size_hint_y=None, height=BTN_H))
    else:
        search.bind(text=render_list)
        nav.add(search)
        type_btn.bind(on_press=cycle_type)
        sort_btn.bind(on_press=cycle_sort)
        filters = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        filters.add_widget(type_btn)
        filters.add_widget(sort_btn)
        nav.add(filters)
        mode_btn.bind(on_press=toggle_mode)
        nav.add(mode_btn)
        nav.add(toolbar)
        render_list()
        nav.add(list_box)

    if paged and (page > 0 or has_next):
        pager = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        prev_btn = Button(text="< Previous 20", disabled=page == 0)
        prev_btn.bind(on_press=lambda i: nav.show_history_page(page - 1))
        next_btn = Button(text="Next 20 >", disabled=not has_next)
        next_btn.bind(on_press=lambda i: nav.show_history_page(page + 1))
        pager.add_widget(prev_btn)
        pager.add_widget(next_btn)
        nav.add(pager)

    nav.add(back_button(nav, to=back))
    return follow_box


def build_item_menu(nav, item, back, allow_arvan=True):
    """Everything you can do with ONE file (the compact list opens this when a card is tapped)."""
    nav.clear()
    parts, deadline = _meta_parts(item)
    nav.add(wrapped_label(f"{item['title']}\n" + "  ·  ".join(parts + ([deadline] if deadline else []))))
    nav.add(TextInput(text=item["link"], readonly=True, multiline=False, size_hint_y=None, height=SMALL_BTN_H))

    def add(text, fn, danger=False):
        btn = Button(text=text, size_hint_y=None, height=BTN_H)
        if danger:
            btn.background_color = _DANGER
        btn.bind(on_press=lambda i: fn(btn))
        nav.add(btn)

    def copy(btn):
        Clipboard.copy(item["link"])
        btn.text = "Copied"

    def share(btn):
        if not android_actions.share_text(item["link"]):
            Clipboard.copy(item["link"])
            btn.text = "Share not available - copied"

    add("Copy link", copy)
    add("Share link", share)
    add("Rename", lambda b: nav.show_rename_prompt(item))
    add("Zip", lambda b: nav.start_zip_release(item))
    if (item.get("days_left") is not None or item.get("forever")) and item.get("asset_id") is not None:
        add("Extend deadline", lambda b: nav.show_extend_prompt([item], nav.show_live_history))
    if allow_arvan and item.get("asset_id") is not None and not item.get("repo") and hasattr(nav, "start_arvan_upload"):
        add("Send to Arvan", lambda b: nav.start_arvan_upload([item]))
    add("Delete", lambda b: nav.show_delete_confirm(item), danger=True)
    nav.add(back_button(nav, to=back))


def _deadline_button(nav, item, back):
    """Shows the days left of a file; tapping it opens the Extend screen. A file that never expires
    (Upload File releases) has the text only."""
    text = item["deadline_text"]
    if item.get("days_left") is None and not item.get("forever"):
        return Button(text=text, size_hint_y=None, height=BTN_H, disabled=True)
    btn = Button(text=f"{text}  -  Extend", size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i, it=item: nav.show_extend_prompt([it], back))
    return btn


def build_deadlines(nav, res, back):
    """File deadlines: every file with its days left, per group (Release History, each Auto follow
    channel, the Telegram bot), soonest first, with Extend per file and Extend all per group."""
    nav.clear()
    if not res.get("ok"):
        nav.add(Label(text=res.get("error", "Could not load the deadlines"), size_hint_y=None, height=dp(80)))
        nav.add(back_button(nav, to=back))
        return
    groups = res.get("groups") or []
    total = sum(len(g["items"]) for g in groups)
    nav.add(Label(text=f"File deadlines ({total} files)", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("Files are deleted by a daily cleanup. Extend adds days to a file's deletion date "
                          "(or keeps it forever)."))
    for message in res.get("errors") or []:
        nav.add(wrapped_label(message))
    if not groups:
        nav.add(Label(text="No files yet", size_hint_y=None, height=BTN_H))
    inner_width = content_width() - 2 * dp(8)
    for group in groups:
        items = group["items"]
        nav.add(Label(text=group["title"], size_hint_y=None, height=BTN_H))
        extendable = [it for it in items if it.get("days_left") is not None]
        if extendable:
            all_btn = Button(text=f"Extend all {len(extendable)} files", size_hint_y=None, height=BTN_H)
            all_btn.bind(on_press=lambda i, its=extendable: nav.show_extend_prompt(its, nav.show_deadlines))
            nav.add(all_btn)
        for item in items:
            size_mb = item.get("size", 0) / (1024 * 1024)
            size_text = f" ({size_mb:.1f} MB)" if size_mb else ""
            text = f"{item['title']}{size_text}\n{item['date']}  -  {item['deadline_text']}"
            text_height = wrapped_label_height(text, extra_padding=dp(14), width=inner_width - dp(16))
            has_button = item.get("days_left") is not None or item.get("forever")
            row = card_box([text_height] + ([BTN_H] if has_button else []))
            paint_card(row, CARD)
            label = Label(text=text, size_hint_y=None, height=text_height, halign="left", valign="middle")
            label.text_size = (inner_width - dp(16), None)
            row.add_widget(label)
            if has_button:
                btn = Button(text="Extend", size_hint_y=None, height=BTN_H)
                btn.bind(on_press=lambda i, it=item: nav.show_extend_prompt([it], nav.show_deadlines))
                row.add_widget(btn)
            nav.add(row)
    nav.add(back_button(nav, to=back))


def build_extend_prompt(nav, items, back):
    """Pick how many days to add to the deletion date of ``items``, or keep them forever."""
    from core import retention
    nav.clear()
    count = len(items)
    nav.add(Label(text=f"Extend {count} file{'s' if count != 1 else ''}", size_hint_y=None, height=BTN_H))
    if count == 1:
        nav.add(wrapped_label(f"{items[0]['title']}\n{items[0].get('deadline_text', '')}"))
    nav.add(Label(text="Add days to the deletion date", size_hint_y=None, height=BTN_H))
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for days in retention.EXTEND_PRESETS:
        btn = Button(text=f"+{days} days")
        btn.bind(on_press=lambda i, d=days: nav.do_extend(items, days=d, back=back))
        row.add_widget(btn)
    nav.add(row)
    custom = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    days_input = TextInput(hint_text="Number of days", multiline=False, input_filter="int", size_hint_x=0.6)
    add_btn = Button(text="Add days", size_hint_x=0.4)

    def add_custom(_inst):
        try:
            days = int(days_input.text.strip())
        except ValueError:
            return
        if 0 < days <= 3650:
            nav.do_extend(items, days=days, back=back)

    add_btn.bind(on_press=add_custom)
    custom.add_widget(days_input)
    custom.add_widget(add_btn)
    nav.add(custom)
    forever_btn = Button(text="Keep forever", size_hint_y=None, height=BTN_H)
    forever_btn.bind(on_press=lambda i: nav.do_extend(items, forever=True, back=back))
    nav.add(forever_btn)
    nav.add(back_button(nav, to=back))


def build_extending(nav, back):
    nav.clear()
    nav.add(Label(text="Extending...", size_hint_y=None, height=60))
    nav.add(back_button(nav, to=back))


def build_delete_confirm(nav, item):
    nav.clear()
    nav.add(Label(text=f"Delete this release?\n{item['title']}", size_hint_y=None, height=80))
    confirm_btn = Button(text="Yes, delete", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_delete_release(item))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_live_history())
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
    cancel_btn.bind(on_press=lambda i: nav.show_live_history())
    nav.add(cancel_btn)


def build_deleting(nav):
    nav.clear()
    nav.add(Label(text="Deleting...", size_hint_y=None, height=60))
    nav.add(back_button(nav, to=nav.show_live_history))


def build_bulk_deleting(nav, count):
    nav.clear()
    status_label = Label(text=f"Deleting 0/{count}...", size_hint_y=None, height=60)
    nav.add(status_label)
    nav.set_status_label(status_label)
    back_btn = Button(text="Back (keeps deleting)", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_live_history())
    nav.add(back_btn)


def build_renaming(nav):
    nav.clear()
    nav.add(Label(text="Renaming...", size_hint_y=None, height=60))
    nav.add(back_button(nav, to=nav.show_live_history))


def build_rename_prompt(nav, item):
    nav.clear()
    nav.add(Label(text=f"Rename:\n{item['title']}", size_hint_y=None, height=60))
    name_input = TextInput(text=item["title"], multiline=False, size_hint_y=None, height=48)
    nav.add(name_input)
    confirm_btn = Button(text="Save name", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_rename_release(item, name_input.text.strip()))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_live_history())
    nav.add(cancel_btn)
