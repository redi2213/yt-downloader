from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_actions
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
    """One button per Auto follow channel (their files are no longer behind the channel's own
    screen). The title names the channel, so it is clear which one it is."""
    box.clear_widgets()
    if not follows:
        box.height = 0
        return
    box.add_widget(Label(text="Auto follow channels", size_hint_y=None, height=32))
    for f in follows:
        badge = f"  [NEW {new[f['id']]}]" if new.get(f.get("id")) else ""
        btn = Button(text=f"Auto follow channel: {f.get('name', '?')}{badge}\nfiles of this channel",
                     size_hint_y=None, height=dp(64), halign="center")
        btn.bind(on_press=lambda i, f=f: on_open(f))
        box.add_widget(btn)


def build_bot_error(nav, message, back=None):
    """The Telegram bot's file list could not be read (e.g. the app has no access to its repo)."""
    nav.clear()
    nav.add(Label(text=message, size_hint_y=None, height=dp(110), halign="center"))
    nav.add(back_button(nav, to=back))


def build(nav, items, title="Release History", back=None, extra=None, page=0, has_next=False,
          follows=None, new=None, on_follow=None, bot=False, on_bot=None, apk=False, on_apk=None,
          on_deadlines=None):
    """``title`` / ``back``: another title and parent screen when this list shows only
    one Auto follow channel's files. ``extra``: (button text, function) shown at the top."""
    nav.clear()
    paged = back is None or bot or apk   # the normal list and the bot's list are paged; one Auto follow channel is not
    heading = f"{title} - page {page + 1} ({len(items)} files)" if paged else f"{title} ({len(items)} found)"
    nav.add(Label(text=heading, size_hint_y=None, height=BTN_H))

    if on_deadlines and not bot and not apk and page == 0:
        dl_btn = Button(text="File deadlines\nwhen each file is deleted", size_hint_y=None,
                        height=dp(64), halign="center")
        dl_btn.bind(on_press=lambda i: on_deadlines())
        nav.add(dl_btn)

    if on_bot and not bot and page == 0:
        bot_btn = Button(text="Telegram bot files\noutputs of the Telegram bot", size_hint_y=None,
                         height=dp(64), halign="center")
        bot_btn.bind(on_press=lambda i: on_bot())
        nav.add(bot_btn)

    if on_apk and not bot and not apk and page == 0:
        apk_btn = Button(text="APK builds and backups", size_hint_y=None, height=BTN_H)
        apk_btn.bind(on_press=lambda i: on_apk())
        nav.add(apk_btn)

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
        nav.add(Label(text="No files yet" if back else "No downloads yet", size_hint_y=None, height=BTN_H))
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
        qlabel = item.get("quality_label", "")
        quality_text = f"  - {qlabel}" if qlabel else ""
        title_text = f"{item['date']}\n{item['title']}{size_text}{quality_text}"
        title_height = wrapped_label_height(title_text, extra_padding=dp(14), width=inner_width - dp(16))

        # One card per file: tap the file's text to select it - the whole card
        # turns green. Link on its own line, then four evenly spaced buttons.
        has_deadline = bool(item.get("deadline_text")) and item.get("asset_id") is not None
        row = card_box([title_height, SMALL_BTN_H, BTN_H] + ([BTN_H] if has_deadline else []))
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
        if has_deadline:
            row.add_widget(_deadline_button(nav, item, nav.show_live_history))
        nav.add(row)

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
