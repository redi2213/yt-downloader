"""The in-app browser: the address bar (Kivy) over a native WebView, and the list of files found.

While the browser screen is shown the WebView covers the area under the bar; every other screen
hides it (Navigator.clear), so it never stays on top of a menu. The round badge (top right, drawn
natively) shows how many files were found, or "YT" on a YouTube video page; tapping it opens the list.
"""
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from core import android_actions, android_browser, browser_media as bm
from screens.common import (BTN_H, CARD, CARD_ON, GAP, PAD, back_button, card_box, content_width,
                            fa_font_kwargs, fa_text, paint_card, wrapped_label, wrapped_label_height)
from screens import browser_pages
from services import browser_service

START_PAGE = "https://www.google.com"
_KIND = {"video": "Video file", "audio": "Audio file", "hls": "HLS stream", "dash": "DASH stream",
         "archive": "Archive file", "apk": "APK file", "pkg": "Package file", "doc": "Document",
         "custom": "Custom file", "other": "Unknown file"}
_CAT_LABEL = {"video": "Videos", "audio": "Audio", "archive": "Archives", "apk": "APK files",
              "pkg": "Packages", "doc": "Documents", "custom": "Custom", "other": "Other"}
_CUSTOM_ERRORS = {"invalid": "Not a valid extension (letters and digits only, up to 8)",
                  "builtin": "This type is already built in", "duplicate": "Already in the list"}


def build(nav, url=None):
    nav.clear()
    if not android_browser.supported():
        nav.add(wrapped_label("The browser works only on the phone (Android)."))
        nav.add(back_button(nav))
        return
    if nav.browser is None:
        nav.browser = android_browser.Browser()
    br = nav.browser
    state = browser_service.state()         # tabs, history and bookmarks (they stay after the app is closed)
    tab = state.tabs.current()
    tab_id = tab["id"]
    sess = state.tabs.session_for(tab_id)   # the files found in this tab only
    nav.browser_session = sess
    sess.set_rules(browser_service.load_rules())        # the file types chosen in Browser settings
    state.flush()

    bar = BoxLayout(orientation="vertical", size_hint_y=None, height=2 * BTN_H + GAP, spacing=GAP)
    row1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    url_box = TextInput(text=sess.page or tab.get("url") or "", hint_text="Search or type a link", multiline=False, size_hint_x=0.76)
    go_btn = Button(text="Go", size_hint_x=0.24)
    row1.add_widget(url_box)
    row1.add_widget(go_btn)
    row2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    buttons = {}
    for key, text, width in (("back", "<", 0.09), ("forward", ">", 0.09), ("reload", "Reload", 0.19),
                             ("tabs", f"Tabs ({state.tabs.count()})", 0.23), ("menu", "Menu", 0.20),
                             ("close", "Close", 0.20)):
        buttons[key] = Button(text=text, size_hint_x=width)
        row2.add_widget(buttons[key])
    bar.add_widget(row1)
    bar.add_widget(row2)
    nav.add(bar)

    def open_typed(*_args):
        target = bm.normalize_input(url_box.text)
        if target:
            url_box.focus = False
            br.load(target)

    go_btn.bind(on_press=open_typed)
    url_box.bind(on_text_validate=open_typed)
    buttons["back"].bind(on_press=lambda i: br.back())
    buttons["forward"].bind(on_press=lambda i: br.forward())
    buttons["reload"].bind(on_press=lambda i: br.reload())
    buttons["tabs"].bind(on_press=lambda i: browser_pages.open_tabs(nav))
    buttons["menu"].bind(on_press=lambda i: browser_pages.open_menu(nav))
    buttons["close"].bind(on_press=lambda i: (state.flush(), nav.show_home()))

    def place(_dt=None):
        # the WebView starts right under the bar; skip when another screen replaced this one meanwhile
        if bar.parent is None:
            return
        try:
            top = int(max(0, Window.height - bar.to_window(bar.x, bar.y)[1] + GAP / 2))
        except Exception:
            top = int(PAD + bar.height + GAP)
        br.ensure(top)
        br.set_extensions(sess.rules.csv())         # the helper reports the file types switched on
        br.set_top(top)
        br.show(True)

    place()
    Clock.schedule_once(place, 0.2)
    Clock.schedule_once(place, 0.8)
    if br.tab_id != tab_id or not br.started:
        # another tab (or the first start): the helper keeps the page of the tab we leave and shows this one
        br.switch_tab(br.tab_id, tab_id, url or tab.get("url") or START_PAGE)
    elif url:
        br.load(url)
    if sess.needs_rescan and br.started and sess.page:
        sess.needs_rescan = False           # a file type was switched on: look at the page again
        Clock.schedule_once(lambda dt: br.rescan(sess.page), 0.5)

    def on_back():
        if br.can_back():
            br.back()
            return True
        return False

    nav.back_hook = on_back

    def tick():
        if bar.parent is None:
            return
        state.save_if_due()
        data = br.poll()
        if not data:
            return
        sess.merge(data)
        state.page_seen(tab_id, sess.page, sess.title)
        if sess.notice and not data.get("tapped"):
            nav.show_browser_list()         # a download started on the page: its file is in the list now
            return
        page = sess.page
        if page and not url_box.focus and url_box.text != page:
            url_box.text = page
        if bm.is_ytdlp_page(page):
            br.set_badge("YT")
        else:
            br.set_badge(str(sess.count()) if sess.count() else "")
        if data.get("tapped"):
            nav.show_browser_list()

    nav.start_progress_timer(tick, interval=0.5)


# -- the list ---------------------------------------------------------------------------------------------------
def _set(widget, text):
    if getattr(widget, "_ytb_src", widget.text) != text:
        widget.text = text


def _sub(e):
    if e["kind"] == "ytdlp":
        bits = [e.get("quality"), e.get("size_label"), e.get("codec"), "via GitHub"]
    else:
        bits = [_KIND.get(e["kind"], "Unknown file"), e.get("quality")]
        if e["kind"] in bm.FILE_KINDS:
            bits.append(bm.fmt_size(e.get("size")) or ("size ?" if e.get("probed") else "..."))
        else:
            bits.append("via GitHub")
    return "  |  ".join(b for b in bits if b)


def _text(e, width):
    return f"{fa_text(e.get('name') or '', width)}\n{_sub(e)}"


def _group_text(u, width, opened):
    """A video in several qualities: its name, how many qualities and which (tap = open / close)."""
    quals = [m.get("quality") for m in u["members"] if m.get("quality")]
    line2 = f"{len(u['members'])} qualities"
    if quals:
        line2 += "  |  " + ", ".join(quals[:5]) + ("..." if len(quals) > 5 else "")
    return f"{'- ' if opened else '+ '}{fa_text(u['name'] or '', width)}\n{line2}"


PAGE = 30           # rows drawn at a time; "Show more" adds the next ones (a long list stays smooth)
CHK_W = dp(52)      # the select box at the start of a row
INDENT = dp(18)     # the qualities of an open group are drawn a little inside
CARD_PART = [0.13, 0.28, 0.20, 1]       # some (not all) qualities of a group are selected
_MARKS = {0: "[   ]", 1: "[ - ]", 2: "[ x ]"}
_SORT_NAMES = {"newest": "Newest", "oldest": "Oldest", "size": "Size", "quality": "Quality",
               "name": "Name", "type": "Type"}
_EMPTY = "No files found yet. Play a video or open a file link on the page, then tap the badge again."


def _sort_text(mode):
    return "Sort: " + _SORT_NAMES.get(mode, "Newest")


def _filter_text(cat):
    return "Type: " + ("All" if cat == "all" else _CAT_LABEL.get(cat, "Other"))


def _info_text(entries, selected):
    count, total, unknown = bm.selection_summary(entries, selected)
    text = f"Selected: {count} of {len(entries)}"
    if total:
        text += f"  |  Total {bm.fmt_size(total)}" + ("+" if unknown else "")
    return text


def _row(widgets, height=BTN_H):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=GAP)
    for w in widgets:
        row.add_widget(w)
    return row


def build_list(nav):
    nav.clear()
    sess = nav.browser_session
    token = object()
    nav.browser_list_token = token
    nav.add(Label(text="Found files", size_hint_y=None, height=BTN_H))
    caught = sess.take_notice()
    if caught:
        nav.add(wrapped_label(f"{len(caught)} download(s) caught from the page - find them below"))

    if bm.is_ytdlp_page(sess.page) and sess.ytdlp_for != sess.page:
        sess.ytdlp_for = sess.page
        nav.add(wrapped_label("Reading the qualities on this phone..."))

        def done(res):
            def apply():
                if res.get("ok"):
                    sess.set_ytdlp(res["formats"])
                else:
                    sess.ytdlp_error = res["error"]
                if nav.browser_list_token is token:
                    nav.show_browser_list()
            nav.schedule(apply)

        browser_service.start_ytdlp(sess.page, done)
        nav.add(button_row(nav, "Back to browser", nav.show_browser))
        return

    if sess.ytdlp_error:
        nav.add(wrapped_label(f"The phone could not read the qualities ({sess.ytdlp_error})."))

    # state of this screen: sort mode (saved as the default), rows drawn, what the last draw showed
    state = {"mode": browser_service.default_sort(), "shown": PAGE, "version": None, "keys": None,
             "entries": [], "scan": 0}
    marks, labels = {}, {}          # row key -> (card colour, select box, entry keys) / its text button
    inner = content_width() - 2 * dp(8)
    base_w = inner - dp(16) - CHK_W - dp(4)

    sort_btn = Button(text=_sort_text(state["mode"]), size_hint_x=0.42)
    refresh_btn = Button(text="Refresh", size_hint_x=0.29)
    clear_btn = Button(text="Clear", size_hint_x=0.29)
    nav.add(_row([sort_btn, refresh_btn, clear_btn]))
    filter_btn = Button(text=_filter_text(sess.type_filter), size_hint_x=0.5)
    settings_btn = Button(text="Browser settings", size_hint_x=0.5)
    nav.add(_row([filter_btn, settings_btn]))
    all_btn = Button(text="Select all")
    none_btn = Button(text="Deselect all")
    nav.add(_row([all_btn, none_btn]))
    info = Label(text="", size_hint_y=None, height=BTN_H, color=(1, 0.75, 0.4, 1), halign="center")
    info.text_size = (content_width(), None)
    nav.add(info)
    dl_btn = Button(text="Download selected")
    act_btn = Button(text="Actions for selected")
    nav.add(_row([dl_btn, act_btn]))

    rows_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    rows_box.bind(minimum_height=rows_box.setter("height"))
    nav.add(rows_box)
    more_box = BoxLayout(orientation="vertical", size_hint_y=None)
    more_box.bind(minimum_height=more_box.setter("height"))
    nav.add(more_box)
    nav.add(button_row(nav, "Try this page on GitHub (Any site)", lambda: nav.browser_send_page(sess.page)))
    nav.add(button_row(nav, "Back to browser", nav.show_browser))

    def update_info():
        entries = state["entries"]
        if state["scan"] > 0 and not entries:
            text = "Scanning the page again..."
        else:
            text = _info_text(entries, sess.selected)
        info.text = text
        info.height = max(BTN_H, wrapped_label_height(text, width=content_width()))

    def mark_of(keys):
        n = sum(1 for k in keys if k in sess.selected)
        return 2 if n and n == len(keys) else (1 if n else 0)

    def refresh_marks():
        for color, chk, keys in marks.values():
            m = mark_of(keys)
            color.rgba = (CARD, CARD_PART, CARD_ON)[m]
            if chk.text != _MARKS[m]:
                chk.text = _MARKS[m]

    def toggle(keys):
        if all(k in sess.selected for k in keys):
            sess.selected -= set(keys)
        else:
            sess.selected |= set(keys)
        refresh_marks()
        update_info()

    def select_all(on):
        if on:
            sess.selected |= {e["key"] for e in state["entries"]}
        else:
            sess.selected -= {e["key"] for e in state["entries"]}
        refresh_marks()
        update_info()

    def toggle_open(gkey):
        sess.open_groups ^= {gkey}
        render(force=True)

    def make_card(key, keys, text, name, on_body, member=False):
        """One row: a select box (selects) and the text (opens the actions menu / opens the group)."""
        width = base_w - (INDENT if member else 0)
        height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(14), width=width))
        card = card_box([height])
        color = paint_card(card, CARD)
        line = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=dp(4))
        chk = Button(text=_MARKS[0], size_hint=(None, None), size=(CHK_W, height),
                     background_normal="", background_color=(0, 0, 0, 0))
        chk.bind(on_press=lambda i: toggle(keys))
        body = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                      background_normal="", background_color=(0, 0, 0, 0), **fa_font_kwargs(name))
        body.text_size = (width, None)
        body.bind(on_press=lambda i: on_body())
        line.add_widget(chk)
        line.add_widget(body)
        card.add_widget(line)
        marks[key] = (color, chk, keys)
        labels[key] = body
        refresh_marks_one(key)
        if not member:
            return card
        wrap = BoxLayout(orientation="horizontal", size_hint_y=None, height=height + 2 * dp(8))
        wrap.add_widget(Widget(size_hint_x=None, width=INDENT))
        wrap.add_widget(card)
        return wrap

    def refresh_marks_one(key):
        color, chk, keys = marks[key]
        m = mark_of(keys)
        color.rgba = (CARD, CARD_PART, CARD_ON)[m]
        chk.text = _MARKS[m]

    def make_row(e, member=False):
        key = e["key"]
        text = _sub(e) if member else _text(e, base_w)
        return make_card(key, [key], text, e.get("name"), lambda k=key: open_actions(nav, [k]), member)

    def make_group(u):
        gkey = u["key"]
        text = _group_text(u, base_w, gkey in sess.open_groups)
        return make_card(gkey, [m["key"] for m in u["members"]], text, u["name"], lambda k=gkey: toggle_open(k))

    def show_more(_i=None):
        state["shown"] += PAGE
        render(force=True)

    def render(force=False):
        every = sess.all_entries()
        sess.selected &= {e["key"] for e in every}          # a row that is gone cannot stay selected
        if sess.type_filter != "all" and not any(bm.category_of(e) == sess.type_filter for e in every):
            sess.type_filter = "all"                        # nothing of that type is left
        entries = bm.filter_entries(every, sess.type_filter)
        state["entries"] = entries
        filter_btn.text = _filter_text(sess.type_filter)
        units = bm.sort_units(bm.group_units(entries), state["mode"])
        shown = units[:state["shown"]]
        layout = tuple((u["key"], u["key"] in sess.open_groups,
                        tuple(m["key"] for m in u["members"]) if u["members"] else ()) for u in shown)
        if force or layout != state["keys"]:
            state["keys"] = layout
            rows_box.clear_widgets()
            more_box.clear_widgets()
            marks.clear()
            labels.clear()
            if not entries:
                rows_box.add_widget(wrapped_label(_EMPTY))
            for u in shown:
                if u["members"] is None:
                    rows_box.add_widget(make_row(u["entry"]))
                    continue
                rows_box.add_widget(make_group(u))
                if u["key"] in sess.open_groups:
                    for m in u["members"]:
                        rows_box.add_widget(make_row(m, member=True))
            if len(units) > len(shown):
                more = Button(text="Show more", size_hint_y=None, height=BTN_H)
                more.bind(on_press=show_more)
                more_box.add_widget(more)
        else:
            for u in shown:         # same rows: only the sizes / qualities that arrived are redrawn
                if u["members"] is None:
                    if u["key"] in labels:
                        _set(labels[u["key"]], _text(u["entry"], base_w))
                    continue
                opened = u["key"] in sess.open_groups
                if u["key"] in labels:
                    _set(labels[u["key"]], _group_text(u, base_w, opened))
                if opened:
                    for m in u["members"]:
                        if m["key"] in labels:
                            _set(labels[m["key"]], _sub(m))
        update_info()

    def cycle_sort(_i):
        modes = bm.SORT_MODES
        state["mode"] = modes[(modes.index(state["mode"]) + 1) % len(modes)]
        sort_btn.text = _sort_text(state["mode"])
        browser_service.save_default_sort(state["mode"])
        state["shown"] = PAGE
        render(force=True)

    def cycle_filter(_i):
        have = bm.count_by_category(sess.all_entries())
        modes = ["all"] + [c for c in bm.CATEGORIES + ("other",) if have.get(c)]
        cur = sess.type_filter if sess.type_filter in modes else "all"
        sess.type_filter = modes[(modes.index(cur) + 1) % len(modes)]
        state["shown"] = PAGE
        render(force=True)

    def do_clear(_i):
        sess.clear()
        state["shown"] = PAGE
        state["scan"] = 0
        render(force=True)

    def do_refresh(_i):
        sess.restart_scan()
        if nav.browser is not None:
            nav.browser.rescan(sess.page)
        state["shown"] = PAGE
        if bm.is_ytdlp_page(sess.page):
            nav.show_browser_list()         # reads the qualities of the page again
            return
        state["scan"] = 8
        render(force=True)

    def chosen_keys():
        return [e["key"] for e in state["entries"] if e["key"] in sess.selected]

    def go(_i):
        keys = set(chosen_keys())
        if not keys:
            info.text = "Tap the files you want first"
            return
        nav.browser_download([e for e in state["entries"] if e["key"] in keys])

    def actions(_i):
        keys = chosen_keys()
        if not keys:
            info.text = "Tap the files you want first"
            return
        open_actions(nav, keys)

    sort_btn.bind(on_press=cycle_sort)
    filter_btn.bind(on_press=cycle_filter)
    settings_btn.bind(on_press=lambda i: open_settings(nav, nav.show_browser_list, "Back to the list"))
    refresh_btn.bind(on_press=do_refresh)
    clear_btn.bind(on_press=do_clear)
    all_btn.bind(on_press=lambda i: select_all(True))
    none_btn.bind(on_press=lambda i: select_all(False))
    dl_btn.bind(on_press=go)
    act_btn.bind(on_press=actions)

    def tick():
        if nav.browser_list_token is not token:
            return
        if nav.browser is not None:
            data = nav.browser.poll()       # files that arrive while the list is open (Refresh) join the list
            if data:
                sess.merge(data)
        browser_service.start_probe(sess)
        if state["scan"] > 0:
            state["scan"] -= 1
        if sess.version != state["version"]:
            state["version"] = sess.version
            render()
        elif state["scan"] >= 0:
            update_info()

    nav.start_progress_timer(tick, interval=1.0)


# -- the actions menu of a file (or of the selected files) --------------------------------------------------------
def open_actions(nav, keys):
    nav.remember(lambda: open_actions(nav, keys))
    build_actions(nav, keys)


def open_details(nav, key):
    nav.remember(lambda: open_details(nav, key))
    build_details(nav, key)


def _copy(text):
    try:
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(text)
    except Exception:
        pass


def build_actions(nav, keys):
    sess = nav.browser_session
    wanted = set(keys)
    all_rows = sess.all_entries()
    entries = [e for e in all_rows if e["key"] in wanted]
    nav.clear()
    if not entries:
        nav.show_browser_list()
        return
    many = len(entries) > 1
    nav.add(Label(text="What to do with it", size_hint_y=None, height=BTN_H))
    title = wrapped_label(_info_text(all_rows, wanted) if many else _text(entries[0], content_width()))
    if not many:
        kw = fa_font_kwargs(entries[0].get("name"))
        if kw:
            title.font_name = kw["font_name"]
    nav.add(title)
    status = Label(text="", size_hint_y=None, height=BTN_H, color=(1, 0.75, 0.4, 1), halign="center")
    status.text_size = (content_width(), None)
    nav.add(status)

    urls = list(dict.fromkeys(e["url"] for e in entries))
    plural = len(urls) > 1
    page_only = all(e["kind"] == "ytdlp" for e in entries)      # a YouTube quality has the page link only

    def copy_links():
        _copy("\n".join(urls))
        status.text = f"{len(urls)} links copied" if plural else "Link copied"

    def share_apps():
        if not android_actions.share_text("\n".join(urls)):
            status.text = "Share is not available - copied to the clipboard"

    copy_text = ("Copy page links" if plural else "Copy page link") if page_only else \
        ("Copy direct links" if plural else "Copy direct link")
    items = [
        ("Download in the app", lambda: nav.browser_download(entries)),
        (copy_text, copy_links),
        ("Upload to GitHub with these links" if plural else "Upload to GitHub with this link",
         lambda: nav.browser_upload(entries)),
        ("Send to workflows", lambda: nav.show_share_chooser("\n".join(urls))),
        ("Share with other apps", share_apps),
    ]
    if not many:
        items.append(("File details", lambda: open_details(nav, entries[0]["key"])))
    for text, fn in items:
        nav.add(button_row(nav, text, fn))
    nav.add(button_row(nav, "Back to the list", nav.show_browser_list))


def build_details(nav, key):
    sess = nav.browser_session
    e = next((x for x in sess.all_entries() if x["key"] == key), None)
    nav.clear()
    if e is None:
        nav.show_browser_list()
        return
    nav.add(Label(text="File details", size_hint_y=None, height=BTN_H))
    if e["kind"] == "ytdlp":
        kind = "Video page (via GitHub)"
        size = e.get("size_label") or "Not known"
    else:
        kind = _KIND.get(e["kind"], "File")
        size = bm.fmt_size(e.get("size")) or "Not known"
    rows = [("File name", e.get("name") or ""), ("File type", kind), ("Video quality", e.get("quality") or ""),
            ("File size", size), ("Codec", e.get("codec") or ""),
            ("Page link" if e["kind"] == "ytdlp" else "Direct link", e.get("url") or ""),
            ("Found on page", e.get("found_on") or ""),
            ("Sent with the request", ", ".join(e.get("headers") or {}))]      # the names only, never the values
    kw = fa_font_kwargs(e.get("name"))
    for caption, value in rows:
        if not value:
            continue
        cap = Label(text=caption, size_hint_y=None, height=dp(26), halign="left", color=(0.7, 0.7, 0.75, 1))
        cap.text_size = (content_width(), None)
        nav.add(cap)
        val = wrapped_label(value)
        if caption == "File name" and kw:
            val.font_name = kw["font_name"]
        nav.add(val)

    def copy_link():
        _copy(e.get("url") or "")

    nav.add(button_row(nav, "Copy page link" if e["kind"] == "ytdlp" else "Copy direct link", copy_link))
    nav.add(button_row(nav, "Back to the actions", lambda: open_actions(nav, [key])))


# -- Browser settings: which file types the browser looks for ---------------------------------------------------
def open_settings(nav, back, back_text):
    nav.remember(lambda: open_settings(nav, back, back_text))
    build_settings(nav, back, back_text)


def _use_rules(nav, rules):
    """New rules take effect now and stay after the app is closed."""
    nav.browser_session.set_rules(rules)
    browser_service.save_rules(rules)


def build_settings(nav, back, back_text):
    sess = nav.browser_session
    nav.clear()
    nav.add(Label(text="Browser settings", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("File types the browser looks for. Turn a type off to hide it from the results."))
    status = Label(text="", size_hint_y=None, height=BTN_H, color=(1, 0.75, 0.4, 1), halign="center")
    status.text_size = (content_width(), None)
    toggles = {}

    def refresh():
        for cat, btn in toggles.items():
            btn.text = f"{_CAT_LABEL[cat]}: " + ("ON" if cat in sess.rules.enabled else "OFF")

    def flip(cat):
        _use_rules(nav, sess.rules.with_enabled(set(sess.rules.enabled) ^ {cat}))
        refresh()

    for cat in bm.CATEGORIES:
        btn = Button(text="", size_hint_y=None, height=BTN_H)
        btn.bind(on_press=lambda i, c=cat: flip(c))
        toggles[cat] = btn
        nav.add(btn)
        if cat != "custom":
            nav.add(wrapped_label(", ".join(x.lstrip(".") for x in sorted(bm.CATEGORY_EXT[cat]))))
    refresh()

    nav.add(wrapped_label("Custom extensions"))
    box = TextInput(hint_text="Extension, e.g. torrent", multiline=False, size_hint_x=0.7)
    add_btn = Button(text="Add", size_hint_x=0.3)
    nav.add(_row([box, add_btn]))
    nav.add(status)
    custom_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    custom_box.bind(minimum_height=custom_box.setter("height"))
    nav.add(custom_box)

    def draw_custom():
        custom_box.clear_widgets()
        if not sess.rules.custom:
            custom_box.add_widget(wrapped_label("No custom extensions yet."))
        for ext in sess.rules.custom:
            btn = Button(text=f"Remove: {ext.lstrip('.')}", size_hint_y=None, height=BTN_H)
            btn.bind(on_press=lambda i, x=ext: drop(x))
            custom_box.add_widget(btn)

    def add(_i=None):
        ext, err = bm.check_custom(box.text)
        if not err and ext in sess.rules.custom:
            err = "duplicate"
        if err:
            status.text = _CUSTOM_ERRORS[err]
            return
        rules = sess.rules.with_custom(list(sess.rules.custom) + [ext])
        _use_rules(nav, rules.with_enabled(set(rules.enabled) | {"custom"}))
        box.text = ""
        status.text = f"Added: {ext.lstrip('.')}"
        refresh()
        draw_custom()

    def drop(ext):
        _use_rules(nav, sess.rules.with_custom([x for x in sess.rules.custom if x != ext]))
        status.text = f"Removed: {ext.lstrip('.')}"
        draw_custom()

    add_btn.bind(on_press=add)
    box.bind(on_text_validate=add)
    draw_custom()
    nav.add(wrapped_label("A type you turn on is looked for when you go back (the page loads again). "
                          "These choices stay after the app is closed."))
    nav.add(button_row(nav, back_text, back))


def button_row(nav, text, action):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: action())
    return btn
