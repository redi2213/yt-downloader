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

from core import android_browser, browser_media as bm
from screens.common import (BTN_H, CARD, CARD_ON, GAP, PAD, back_button, card_box, content_width,
                            fa_font_kwargs, fa_text, paint_card, wrapped_label, wrapped_label_height)
from services import browser_service

START_PAGE = "https://www.google.com"
_KIND = {"video": "Video file", "audio": "Audio file", "hls": "HLS stream", "dash": "DASH stream"}


def build(nav, url=None):
    nav.clear()
    if not android_browser.supported():
        nav.add(wrapped_label("The browser works only on the phone (Android)."))
        nav.add(back_button(nav))
        return
    if nav.browser is None:
        nav.browser = android_browser.Browser()
    br, sess = nav.browser, nav.browser_session

    bar = BoxLayout(orientation="vertical", size_hint_y=None, height=2 * BTN_H + GAP, spacing=GAP)
    row1 = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    url_box = TextInput(text=sess.page or "", hint_text="Search or type a link", multiline=False, size_hint_x=0.76)
    go_btn = Button(text="Go", size_hint_x=0.24)
    row1.add_widget(url_box)
    row1.add_widget(go_btn)
    row2 = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    buttons = {}
    for key, text in (("back", "<"), ("forward", ">"), ("reload", "Reload"), ("close", "Close")):
        buttons[key] = Button(text=text)
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
    buttons["close"].bind(on_press=lambda i: nav.show_home())

    def place(_dt=None):
        # the WebView starts right under the bar; skip when another screen replaced this one meanwhile
        if bar.parent is None:
            return
        try:
            top = int(max(0, Window.height - bar.to_window(bar.x, bar.y)[1] + GAP / 2))
        except Exception:
            top = int(PAD + bar.height + GAP)
        br.ensure(top)
        br.set_top(top)
        br.show(True)

    place()
    Clock.schedule_once(place, 0.2)
    Clock.schedule_once(place, 0.8)
    if url:
        br.load(url)
    elif not br.started:
        br.load(START_PAGE)

    def on_back():
        if br.can_back():
            br.back()
            return True
        return False

    nav.back_hook = on_back

    def tick():
        if bar.parent is None:
            return
        data = br.poll()
        if not data:
            return
        sess.merge(data)
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
        bits = [_KIND.get(e["kind"], "File"), e.get("quality")]
        if e["kind"] in ("video", "audio"):
            bits.append(bm.fmt_size(e.get("size")) or ("size ?" if e.get("probed") else "..."))
        else:
            bits.append("via GitHub")
    return "  |  ".join(b for b in bits if b)


def _text(e, width):
    return f"{fa_text(e.get('name') or '', width)}\n{_sub(e)}"


PAGE = 30           # rows drawn at a time; "Show more" adds the next ones (a long list stays smooth)
_SORT_NAMES = {"newest": "Newest", "oldest": "Oldest", "size": "Size", "quality": "Quality",
               "name": "Name", "type": "Type"}
_EMPTY = "No video found yet. Start playing the video on the page, then tap the badge again."


def _sort_text(mode):
    return "Sort: " + _SORT_NAMES.get(mode, "Newest")


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
    cards, labels = {}, {}
    inner = content_width() - 2 * dp(8)

    sort_btn = Button(text=_sort_text(state["mode"]), size_hint_x=0.42)
    refresh_btn = Button(text="Refresh", size_hint_x=0.29)
    clear_btn = Button(text="Clear", size_hint_x=0.29)
    nav.add(_row([sort_btn, refresh_btn, clear_btn]))
    all_btn = Button(text="Select all")
    none_btn = Button(text="Deselect all")
    nav.add(_row([all_btn, none_btn]))
    info = Label(text="", size_hint_y=None, height=BTN_H, color=(1, 0.75, 0.4, 1), halign="center")
    info.text_size = (content_width(), None)
    nav.add(info)
    dl_btn = Button(text="Download selected", size_hint_y=None, height=BTN_H)
    nav.add(dl_btn)

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

    def recolor():
        for key, color in cards.items():
            color.rgba = CARD_ON if key in sess.selected else CARD

    def toggle(key):
        sess.selected ^= {key}
        if key in cards:
            cards[key].rgba = CARD_ON if key in sess.selected else CARD
        update_info()

    def select_all(on):
        if on:
            sess.selected |= {e["key"] for e in state["entries"]}
        else:
            sess.selected.clear()
        recolor()
        update_info()

    def make_row(e):
        text = _text(e, inner - dp(16))
        height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(14), width=inner - dp(16)))
        card = card_box([height])
        cards[e["key"]] = paint_card(card, CARD_ON if e["key"] in sess.selected else CARD)
        btn = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                     background_normal="", background_color=(0, 0, 0, 0), **fa_font_kwargs(e.get("name")))
        btn.text_size = (inner - dp(16), None)
        btn.bind(on_press=lambda i, k=e["key"]: toggle(k))
        labels[e["key"]] = btn
        card.add_widget(btn)
        return card

    def show_more(_i=None):
        state["shown"] += PAGE
        render(force=True)

    def render(force=False):
        entries = sess.all_entries()
        sess.selected &= {e["key"] for e in entries}        # a row that is gone cannot stay selected
        state["entries"] = entries
        shown = bm.sort_entries(entries, state["mode"])[:state["shown"]]
        keys = tuple(e["key"] for e in shown)
        if force or keys != state["keys"]:
            state["keys"] = keys
            rows_box.clear_widgets()
            more_box.clear_widgets()
            cards.clear()
            labels.clear()
            if not entries:
                rows_box.add_widget(wrapped_label(_EMPTY))
            for e in shown:
                rows_box.add_widget(make_row(e))
            if len(entries) > len(shown):
                more = Button(text="Show more", size_hint_y=None, height=BTN_H)
                more.bind(on_press=show_more)
                more_box.add_widget(more)
        else:
            for e in shown:         # same rows: only the sizes / qualities that arrived are redrawn
                if e["key"] in labels:
                    _set(labels[e["key"]], _text(e, inner - dp(16)))
        update_info()

    def cycle_sort(_i):
        modes = bm.SORT_MODES
        state["mode"] = modes[(modes.index(state["mode"]) + 1) % len(modes)]
        sort_btn.text = _sort_text(state["mode"])
        browser_service.save_default_sort(state["mode"])
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

    def go(_i):
        chosen = [e for e in sess.all_entries() if e["key"] in sess.selected]
        if not chosen:
            info.text = "Tap the files you want first"
            return
        nav.browser_download(chosen)

    sort_btn.bind(on_press=cycle_sort)
    refresh_btn.bind(on_press=do_refresh)
    clear_btn.bind(on_press=do_clear)
    all_btn.bind(on_press=lambda i: select_all(True))
    none_btn.bind(on_press=lambda i: select_all(False))
    dl_btn.bind(on_press=go)

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


def button_row(nav, text, action):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: action())
    return btn
