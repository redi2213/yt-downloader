"""The in-app browser: the address bar (Kivy) over a native WebView, and the list of videos found.

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


def build_list(nav):
    nav.clear()
    sess = nav.browser_session
    token = object()
    nav.browser_list_token = token
    nav.add(Label(text="Videos on this page", size_hint_y=None, height=BTN_H))
    info = Label(text="", size_hint_y=None, height=BTN_H, color=(1, 0.75, 0.4, 1))

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

    entries = sess.all_entries()
    keys = tuple(e["key"] for e in entries)
    cards, labels = {}, {}
    inner = content_width() - 2 * dp(8)

    def update_info():
        info.text = f"Selected: {len(sess.selected & set(keys))} of {len(keys)}"

    def toggle(key):
        sess.selected ^= {key}
        cards[key].rgba = CARD_ON if key in sess.selected else CARD
        update_info()

    def select_all(on):
        for key in keys:
            if (key in sess.selected) != on:
                toggle(key)

    if not entries:
        nav.add(wrapped_label("No video found yet. Start playing the video on the page, then tap the badge again."))
    else:
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        all_btn = Button(text="Select all")
        all_btn.bind(on_press=lambda i: select_all(True))
        clear_btn = Button(text="Clear")
        clear_btn.bind(on_press=lambda i: select_all(False))
        row.add_widget(all_btn)
        row.add_widget(clear_btn)
        nav.add(row)
        nav.add(info)

        def go(_i):
            chosen = [e for e in sess.all_entries() if e["key"] in sess.selected]
            if not chosen:
                info.text = "Tap the files you want first"
                return
            nav.browser_download(chosen)

        dl_btn = Button(text="Download selected", size_hint_y=None, height=BTN_H)
        dl_btn.bind(on_press=go)
        nav.add(dl_btn)

        for e in entries:
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
            nav.add(card)
        update_info()

    nav.add(button_row(nav, "Try this page on GitHub (Any site)", lambda: nav.browser_send_page(sess.page)))
    nav.add(button_row(nav, "Back to browser", nav.show_browser))

    def refresh():
        browser_service.start_probe(sess)
        now = sess.all_entries()
        if tuple(e["key"] for e in now) != keys:
            if nav.browser_list_token is token:
                nav.show_browser_list()
            return
        for e in now:
            if e["key"] in labels:
                _set(labels[e["key"]], _text(e, inner - dp(16)))

    nav.start_progress_timer(refresh, interval=1.0)


def button_row(nav, text, action):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: action())
    return btn
