"""In-app browser: the Tabs, History and Bookmarks screens (the data is core/browser_tabs.py, kept by
services/browser_service.state()). Written like screens/browser.py: English texts, translated by core/i18n."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import browser_tabs as bt
from screens.common import (BTN_H, CARD, CARD_ON, GAP, card_box, content_width, fa_font_kwargs, fa_text,
                            paint_card, wrapped_label, wrapped_label_height)
from api import browser_prefs
from services import browser_service

PAGE = 30               # rows drawn at a time; "Show more" adds the next ones
SIDE_W = dp(72)         # the small button at the end of a row (Close / Delete / Edit)
_WARN = (1, 0.75, 0.4, 1)
_KINDS = {
    "history": {"title": "History", "hint": "Search history", "empty": "No history yet.", "one": "page",
                "many": "pages", "side": "Delete"},
    "bookmarks": {"title": "Bookmarks", "hint": "Search bookmarks", "empty": "No bookmarks yet.", "one": "bookmark",
                  "many": "bookmarks", "side": "Edit"},
}


# -- small helpers -------------------------------------------------------------------------------------------------
def _status():
    label = Label(text="", size_hint_y=None, height=BTN_H, color=_WARN, halign="center")
    label.text_size = (content_width(), None)
    return label


def _button(text, action):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: action())
    return btn


def _row(widgets):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for w in widgets:
        row.add_widget(w)
    return row


def _list_box():
    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(4))
    box.bind(minimum_height=box.setter("height"))
    return box


def _card(title, sub, on_body, on_side, side_text, active=False):
    """One row: the text (tap = open) and a small button at its end."""
    width = content_width() - 2 * dp(8) - dp(16) - SIDE_W - dp(4)
    text = f"{fa_text(title, width)}\n{sub}" if sub else fa_text(title, width)
    height = max(BTN_H, wrapped_label_height(text, extra_padding=dp(14), width=width))
    card = card_box([height])
    paint_card(card, CARD_ON if active else CARD)
    line = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=dp(4))
    body = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                  background_normal="", background_color=(0, 0, 0, 0), **fa_font_kwargs(title))
    body.text_size = (width, None)
    body.bind(on_press=lambda i: on_body())
    side = Button(text=side_text, size_hint=(None, None), size=(SIDE_W, height),
                  background_normal="", background_color=(0, 0, 0, 0))
    side.bind(on_press=lambda i: on_side())
    line.add_widget(body)
    line.add_widget(side)
    card.add_widget(line)
    return card


def _title_of(item):
    return item.get("title") or bt.short_url(item.get("url")) or "New tab"


def _sub_of(item, *extra):
    bits = [bt.short_url(item.get("url")) if item.get("title") else ""] + list(extra)
    return "  |  ".join(b for b in bits if b)


# -- the menu ------------------------------------------------------------------------------------------------------
def open_menu(nav):
    nav.remember(lambda: open_menu(nav))
    build_menu(nav)


def build_menu(nav):
    from screens import browser, browser_tools
    nav.clear()
    try:
        nav.app.show_topbar(False)      # this menu has its own Home button (below)
    except Exception:
        pass
    st = browser_service.state()
    tab = st.tabs.current()
    sess = st.tabs.session_for(tab["id"])
    page = sess.page if bt.is_web(sess.page) else tab.get("url")
    title = sess.title or tab.get("title") or ""
    try:
        from screens import home_menu
        home_btn = Button(text="Home", size_hint_y=None, height=BTN_H)
        home_btn.bind(on_release=lambda b: home_menu.open(nav, b))
        nav.add(home_btn)
    except Exception:
        pass            # an older app without the Home drop-down
    nav.add(Label(text="Browser menu", size_hint_y=None, height=BTN_H))
    status = _status()
    nav.add(status)

    def new_tab():
        _new_tab(nav, status)

    mark = Button(text="", size_hint_y=None, height=BTN_H)

    def draw_mark():
        mark.text = "Remove bookmark" if st.bookmarks.has(page) else "Add bookmark"

    def toggle_mark(_i):
        if not bt.is_web(page):
            status.text = "Open a page first"
            return
        if st.bookmarks.has(page):
            st.bookmarks.remove(page)
            status.text = "Bookmark removed"
        else:
            st.bookmarks.put(page, title, bump=False)
            status.text = "Bookmark added"
        st.flush()
        draw_mark()

    mark.bind(on_press=toggle_mark)
    draw_mark()
    nav.add(Label(text="Tabs and bookmarks", size_hint_y=None, height=BTN_H))
    nav.add(_button("New tab", new_tab))
    nav.add(_button("Speed dial", lambda: open_speed_dial(nav)))
    nav.add(_button(f"Tabs ({st.tabs.count()})", lambda: open_tabs(nav)))
    nav.add(mark)
    nav.add(_button("Bookmarks", lambda: open_bookmarks(nav)))
    nav.add(_button("History", lambda: open_history(nav)))
    nav.add(Label(text="Tools", size_hint_y=None, height=BTN_H))
    browser_tools.add_menu(nav, status)         # one button per category: Page tools, Ads and pop-ups, Clean up, Inspect
    nav.add(_button("Browser settings", lambda: browser.open_settings(nav, nav.show_browser, "Back to browser")))
    nav.add(_button("Back to browser", nav.show_browser))


# -- a link pressed and held in the page ----------------------------------------------------------------------------
def open_link_menu(nav, url, text=""):
    nav.remember(lambda: open_link_menu(nav, url, text))
    build_link_menu(nav, url, text)


def build_link_menu(nav, url, text=""):
    from screens import browser
    from core import android_actions
    nav.clear()
    try:
        nav.app.show_topbar(False)
    except Exception:
        pass
    st = browser_service.state()
    sess = nav.browser_session
    web = bt.is_web(url)
    nav.add(Label(text="Link", size_hint_y=None, height=BTN_H))
    if text:
        head = wrapped_label(text)
        kw = fa_font_kwargs(text)
        if kw:
            head.font_name = kw["font_name"]
        nav.add(head)
    nav.add(wrapped_label(url))
    status = _status()
    nav.add(status)

    def bg_tab():
        if st.tabs.new(url, activate=False) is None:
            status.text = f"Tab limit reached ({bt.MAX_TABS})"
            return
        st.flush()
        status.text = "Opened in a background tab"

    def editor():
        try:
            from core import share_routing
            if share_routing.classify_quick(url):       # a YouTube link goes to its own screen
                nav.handle_shared_text(url)
                return
        except Exception:
            pass
        browser.open_actions(nav, [sess.add_link(url, text)])

    def add_to_list():
        key = sess.add_link(url, text)
        browser._add_waiting([e for e in sess.all_entries() if e["key"] == key], status, False)

    def copy_text():
        if text:
            browser._copy(text)
            status.text = "Link text copied"
        else:
            browser._copy(url)
            status.text = "This link has no text - the link was copied"

    def copy_link():
        browser._copy(url)
        status.text = "Link copied"

    def share_link():
        if not android_actions.share_text(url):
            browser._copy(url)
            status.text = "Share is not available - copied to the clipboard"

    items = []
    if web:
        items += [("Open in a background tab", bg_tab), ("Open in the download editor", editor)]
    items += [("Copy link text", copy_text), ("Copy link", copy_link), ("Share link", share_link)]
    if web:
        items += [("Add to the list (don't start)", add_to_list),
                  ("Send to workflows", lambda: nav.show_share_chooser(url))]
    for label, fn in items:
        nav.add(_button(label, fn))
    nav.add(_button("Back to the page", nav.show_browser))


def _new_tab(nav, status, url=""):
    st = browser_service.state()
    if st.tabs.new(url) is None:
        status.text = f"Tab limit reached ({bt.MAX_TABS})"
        return
    st.flush()
    if not url and browser_prefs.get_flag("newtab_speed"):
        open_speed_dial(nav)            # the setting asks for the Speed dial in a blank new tab
        return
    nav.show_browser()


# -- speed dial: the bookmarks as big buttons ------------------------------------------------------------------
SPEED_DIAL_MAX = 12


def open_speed_dial(nav):
    nav.remember(lambda: open_speed_dial(nav))
    build_speed_dial(nav)


def build_speed_dial(nav):
    from kivy.uix.gridlayout import GridLayout
    nav.clear()
    try:
        nav.app.show_topbar(False)
    except Exception:
        pass
    st = browser_service.state()
    nav.add(Label(text="Speed dial", size_hint_y=None, height=BTN_H))
    items = st.bookmarks.items[:SPEED_DIAL_MAX]
    if not items:
        nav.add(wrapped_label("No bookmarks yet. Add some from the Browser menu (Add bookmark)."))
    else:
        gap = dp(6)
        width = (content_width() - gap) / 2
        grid = GridLayout(cols=2, size_hint_y=None, spacing=gap)
        grid.bind(minimum_height=grid.setter("height"))
        for item in items:
            title = _title_of(item)
            tile = Button(text=fa_text(title, width - dp(12)), size_hint_y=None, height=BTN_H * 2,
                          halign="center", valign="middle", **fa_font_kwargs(title))
            tile.text_size = (width - dp(12), None)
            tile.bind(on_press=lambda i, u=item["url"]: nav.show_browser(u))
            grid.add_widget(tile)
        nav.add(grid)
    nav.add(_button("Bookmarks", lambda: open_bookmarks(nav)))
    nav.add(_button("Back to browser", nav.show_browser))


# -- tabs ----------------------------------------------------------------------------------------------------------
def open_tabs(nav):
    nav.remember(lambda: open_tabs(nav))
    build_tabs(nav)


def build_tabs(nav):
    nav.clear()
    st = browser_service.state()
    ts = st.tabs
    nav.add(Label(text="Tabs", size_hint_y=None, height=BTN_H))
    info = _status()
    nav.add(info)
    new_btn = Button(text="New tab", size_hint_x=0.5)
    all_btn = Button(text="Close all", size_hint_x=0.5)
    nav.add(_row([new_btn, all_btn]))
    box = _list_box()
    nav.add(box)
    nav.add(_button("Back to browser", nav.show_browser))
    armed = {"all": False}

    def switch(tab_id):
        ts.activate(tab_id)
        st.flush()
        nav.show_browser()

    def close(tab_id):
        ts.close(tab_id)
        if nav.browser is not None:
            nav.browser.forget_tab(tab_id)
        st.flush()
        draw()

    def draw():
        armed["all"] = False
        all_btn.text = "Close all"
        info.text = f"Open tabs: {ts.count()} of {bt.MAX_TABS}"
        box.clear_widgets()
        for tab in list(ts.tabs):
            on = tab["id"] == ts.active
            box.add_widget(_card(("* " if on else "") + _title_of(tab), _sub_of(tab),
                                 lambda i=tab["id"]: switch(i), lambda i=tab["id"]: close(i), "Close", on))

    def new(_i):
        _new_tab(nav, info)

    def close_all(_i):
        if ts.count() > 1 and not armed["all"]:
            armed["all"] = True
            all_btn.text = "Tap again to close all"
            return
        ts.close_all()
        if nav.browser is not None:
            nav.browser.forget_tab()
        st.flush()
        nav.show_browser()

    new_btn.bind(on_press=new)
    all_btn.bind(on_press=close_all)
    draw()


# -- history and bookmarks -----------------------------------------------------------------------------------------
def open_history(nav):
    nav.remember(lambda: open_history(nav))
    _build_links(nav, "history")


def open_bookmarks(nav):
    nav.remember(lambda: open_bookmarks(nav))
    _build_links(nav, "bookmarks")


def _build_links(nav, kind):
    nav.clear()
    st = browser_service.state()
    spec = _KINDS[kind]
    store = st.history if kind == "history" else st.bookmarks
    nav.add(Label(text=spec["title"], size_hint_y=None, height=BTN_H))
    search = TextInput(hint_text=spec["hint"], multiline=False, size_hint_y=None, height=BTN_H)
    nav.add(search)
    info = _status()
    nav.add(info)
    clear_btn = Button(text="Clear all", size_hint_y=None, height=BTN_H)
    nav.add(clear_btn)
    rows_box = _list_box()
    nav.add(rows_box)
    more_box = BoxLayout(orientation="vertical", size_hint_y=None)
    more_box.bind(minimum_height=more_box.setter("height"))
    nav.add(more_box)
    nav.add(_button("Back to the menu", lambda: open_menu(nav)))
    state = {"shown": PAGE, "armed": False}

    def open_item(item):
        nav.show_browser(item["url"])

    def side(item):
        if kind == "bookmarks":
            open_bookmark(nav, item["url"])
            return
        store.remove(item["url"])
        st.flush()
        draw()

    def show_more(_i=None):
        state["shown"] += PAGE
        draw()

    def draw(reset=False):
        if reset:
            state["shown"] = PAGE
        state["armed"] = False
        clear_btn.text = "Clear all"
        found = store.search(search.text)
        total = len(store.items)
        noun = spec["one"] if len(found) == 1 else spec["many"]
        info.text = f"{len(found)} of {total} {noun}" if len(found) != total else f"{total} {noun}"
        rows_box.clear_widgets()
        more_box.clear_widgets()
        if not found:
            rows_box.add_widget(wrapped_label(spec["empty"] if not total else "Nothing matches your search."))
        for item in found[:state["shown"]]:
            when = bt.when(item["ts"]) if kind == "history" else ""
            rows_box.add_widget(_card(_title_of(item), _sub_of(item, when),
                                      lambda it=item: open_item(it), lambda it=item: side(it), spec["side"]))
        if len(found) > state["shown"]:
            more = Button(text="Show more", size_hint_y=None, height=BTN_H)
            more.bind(on_press=show_more)
            more_box.add_widget(more)

    def clear_all(_i):
        if not store.items:
            return
        if not state["armed"]:
            state["armed"] = True
            clear_btn.text = "Tap again to clear all"
            return
        store.clear()
        st.flush()
        draw(True)

    search.bind(text=lambda i, v: draw(True))
    clear_btn.bind(on_press=clear_all)
    draw()


def open_bookmark(nav, url):
    nav.remember(lambda: open_bookmark(nav, url))
    build_bookmark(nav, url)


def build_bookmark(nav, url):
    from screens import browser
    nav.clear()
    st = browser_service.state()
    item = st.bookmarks.get(url)
    if item is None:
        open_bookmarks(nav)
        return
    nav.add(Label(text="Bookmark", size_hint_y=None, height=BTN_H))
    name = wrapped_label(fa_text(_title_of(item)))
    kw = fa_font_kwargs(item.get("title"))
    if kw:
        name.font_name = kw["font_name"]
    nav.add(name)
    nav.add(wrapped_label(item["url"]))
    status = _status()
    nav.add(status)
    title_box = TextInput(text=item.get("title") or "", hint_text="Title", multiline=False, size_hint_x=0.7)
    save_btn = Button(text="Save", size_hint_x=0.3)

    def rename(_i=None):
        if not title_box.text.strip():
            status.text = "Title can't be empty"
            return
        st.bookmarks.retitle(item["url"], title_box.text)
        st.flush()
        status.text = "Renamed"

    def copy():
        browser._copy(item["url"])
        status.text = "Link copied"

    def remove():
        st.bookmarks.remove(item["url"])
        st.flush()
        open_bookmarks(nav)

    save_btn.bind(on_press=rename)
    title_box.bind(on_text_validate=rename)
    nav.add(_button("Open", lambda: nav.show_browser(item["url"])))
    nav.add(_button("Open in new tab", lambda: _new_tab(nav, status, item["url"])))
    nav.add(_button("Copy link", copy))
    nav.add(_row([title_box, save_btn]))
    nav.add(_button("Remove bookmark", remove))
    nav.add(_button("Back to bookmarks", lambda: open_bookmarks(nav)))
