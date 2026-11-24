"""In-app browser page tools: the "Page tools" part of the Browser menu, the Find bar and the confirm screen for
clearing site data. Written like screens/browser.py: English texts, translated by core/i18n.

No Build needed: the saved choices (api/browser_prefs), Translate (it only opens another address), Reload and
these screens. Build needed (java/.../BrowserHelper.java): Desktop view, Dark mode, Find in page, Images /
Videos disabled, Clear cache, clearing cookies and site data. An older APK answers False to those calls and the
screens say that a new build is needed."""
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import browser_tabs as bt, browser_tools as tools
from screens.common import BTN_H, GAP, content_width, wrapped_label
from services import browser_service

_WARN = (1, 0.75, 0.4, 1)
_NEEDS_UPDATE = "Needs the latest app update"


def _on_off(text, on):
    return f"{text}: " + ("ON" if on else "OFF")


def _title(nav, text):
    nav.add(Label(text=text, size_hint_y=None, height=BTN_H))


def _status():
    label = Label(text="", size_hint_y=None, height=BTN_H, color=_WARN, halign="center")
    label.text_size = (content_width(), None)
    return label


def _set_ads(br, on):
    """Ad / pop-up blocking in the helper; False on an APK built before it existed (also without the method)."""
    fn = getattr(br, "set_adblock", None)
    try:
        return bool(fn and fn(on))
    except Exception:
        return False


_last = {"text": ""}


def _copy_text(text):
    try:
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(text)
        return True
    except Exception:
        return False


def _deliver(text, say):
    _last["text"] = text
    ok = _copy_text(text)
    size = max(1, len(text) // 1000)
    say((f"Copied ({size} KB): paste it in the chat" if ok else "Could not copy: use Share last result")
        + ". A very long text is cut.")


def _inspect(br, kind, say):
    """Reads the shown page (HTML or links) through the helper and copies it. Needs the latest build."""
    start = getattr(br, "inspect", None)
    if start is None or not start(kind):
        say(_NEEDS_UPDATE)
        return
    say("Reading the page...")
    tries = {"n": 0}

    def poll(_dt):
        tries["n"] += 1
        out = br.inspect_result()
        if out is None:
            if tries["n"] >= 25:
                say("The page did not answer")
                return False
            return True
        if not out:
            say("Nothing was read: open a page first")
        else:
            _deliver(out, say)
        return False

    Clock.schedule_interval(poll, 0.3)


def apply_saved(br, state, tab_id):
    """Gives the helper the saved choices (dark mode, blocking, desktop view of this tab). Called each time the
    browser screen is built, so a tab switch also switches the user agent before the page loads."""
    flags = browser_service.load_tools()
    br.set_dark(flags["dark"])
    br.set_block(flags["no_images"], flags["no_videos"])
    _set_ads(br, not flags.get("ads_off"))
    br.set_desktop(state.tabs.is_desktop(tab_id))


# -- the Browser menu ----------------------------------------------------------------------------------------------
def add_menu(nav, status):
    """Adds the page-tool buttons to the Browser menu (``status`` is the menu's message line)."""
    br = nav.browser
    st = browser_service.state()
    tab = st.tabs.current()
    tab_id = tab["id"]
    sess = st.tabs.session_for(tab_id)
    page = sess.page if bt.is_web(sess.page) else tab.get("url")
    flags = browser_service.load_tools()

    def button(text, action):
        btn = Button(text=text, size_hint_y=None, height=BTN_H)
        btn.bind(on_press=lambda i: action(btn))
        nav.add(btn)
        return btn

    def say(text):
        status.text = text

    _title(nav, "Page tools")
    if br is None or not br.native_ready():
        nav.add(wrapped_label("Some page tools need the latest app update (a new build)."))

    def desktop(btn):
        on = not st.tabs.is_desktop(tab_id)
        st.tabs.set_desktop(tab_id, on)
        st.flush()
        btn.text = _on_off("Desktop view", on)
        if br.set_desktop(on, reload=True):
            say("Desktop view on for this tab" if on else "Desktop view off for this tab")
        else:
            say(_NEEDS_UPDATE)

    def dark(btn):
        on = not flags["dark"]
        flags["dark"] = on
        browser_service.save_tool("dark", on)
        btn.text = _on_off("Dark mode", on)
        say(("Dark mode on" if on else "Dark mode off") if br.set_dark(on) else _NEEDS_UPDATE)

    def translate(_btn):
        if not bt.is_web(page):
            say("Open a page first")
            return
        target = tools.original_url(page) if tools.is_translated(page) else tools.translate_url(page, "fa")
        if not target:
            say("This page cannot be translated")
            return
        br.load(target)
        nav.show_browser()

    def find(_btn):
        nav.browser_find = {"on": True, "q": ""}
        nav.show_browser()

    def reload_page(_btn):
        br.reload()
        nav.show_browser()

    button(_on_off("Desktop view", st.tabs.is_desktop(tab_id)), desktop)
    button(_on_off("Dark mode", flags["dark"]), dark)
    button("Show original page" if tools.is_translated(page) else "Translate page (Persian)", translate)
    nav.add(wrapped_label("Translate opens the page through Google Translate: it needs Google to be reachable, "
                          "and pages that need a sign-in may not work."))
    button("Find in page", find)
    button("Reload", reload_page)

    _title(nav, "Ads and pop-ups")

    def ads(btn):
        off = not flags["ads_off"]
        flags["ads_off"] = off
        browser_service.save_tool("ads_off", off)
        btn.text = _on_off("Block ads and pop-ups", not off)
        if _set_ads(br, not off):
            br.reload()
            say("Ads and pop-ups are allowed now; the page reloads" if off
                else "Ads and pop-ups are blocked now; the page reloads")
        else:
            say(_NEEDS_UPDATE)

    button(_on_off("Block ads and pop-ups", not flags["ads_off"]), ads)
    nav.add(wrapped_label("Stops pop-up windows, jumps to ad sites and invisible click-catchers. "
                          "If a site stops working, switch this off."))

    _title(nav, "Data saving")

    def block(key, title, msg_on, msg_off):
        def run(btn):
            on = not flags[key]
            flags[key] = on
            browser_service.save_tool(key, on)
            btn.text = _on_off(title, on)
            if br.set_block(flags["no_images"], flags["no_videos"]):
                br.reload()
                say(msg_on if on else msg_off)
            else:
                say(_NEEDS_UPDATE)
        return run

    button(_on_off("Images disabled", flags["no_images"]),
           block("no_images", "Images disabled", "Images are blocked now; the page reloads",
                 "Images are loaded again; the page reloads"))
    button(_on_off("Videos disabled", flags["no_videos"]),
           block("no_videos", "Videos disabled", "Videos are blocked now; the page reloads",
                 "Videos are loaded again; the page reloads"))

    _title(nav, "Clean up")
    button("Clear cache", lambda b: say("Cache cleared" if br.clear_cache() else _NEEDS_UPDATE))
    button("Clear this site's data", lambda b: open_confirm(nav, "site"))
    button("Clear data of all sites", lambda b: open_confirm(nav, "all"))

    _title(nav, "Cookies and headers")
    button("Export cookies", lambda b: _open_cookies(nav))

    _title(nav, "Inspect page (to share)")

    def nav_log(_btn):
        getter = getattr(br, "nav_log", None)
        text = getter() if getter else None
        if text is None:
            say(_NEEDS_UPDATE)
        elif not text.strip():
            say("The navigation log is empty")
        else:
            _deliver(text, say)

    def clear_log(_btn):
        fn = getattr(br, "clear_nav_log", None)
        say("Navigation log cleared" if fn and fn() else _NEEDS_UPDATE)

    def share_last(_btn):
        text = _last["text"]
        if not text:
            say("Nothing to share yet")
            return
        try:
            from core import android_actions
            if android_actions.share_text(text):
                return
        except Exception:
            pass
        say("Share is not available" + (" - the text is on the clipboard" if _copy_text(text) else ""))

    button("Copy page HTML", lambda b: _inspect(br, "html", say))
    button("Copy page links", lambda b: _inspect(br, "links", say))
    button("Copy navigation log", nav_log)
    button("Clear navigation log", clear_log)
    button("Share last result", share_last)
    nav.add(wrapped_label("Open the page first, do what you want to show (tap the link), then come back here. "
                          "The page HTML can hold personal data: look before you share."))


def _open_cookies(nav):
    from screens import browser_cookies         # a screen of its own (it imports this module)
    browser_cookies.open_export(nav)


# -- confirm before clearing cookies and site data --------------------------------------------------------------------
def open_confirm(nav, scope):
    nav.remember(lambda: open_confirm(nav, scope))
    build_confirm(nav, scope)


def build_confirm(nav, scope):
    from screens import browser_pages
    br = nav.browser
    st = browser_service.state()
    tab = st.tabs.current()
    sess = st.tabs.session_for(tab["id"])
    page = sess.page if bt.is_web(sess.page) else tab.get("url")
    site = tools.original_url(page) if bt.is_web(page) else ""
    nav.clear()
    if scope == "site":
        _title(nav, "Clear this site's data")
        nav.add(wrapped_label(f"Site: {tools.host_of(site) or '-'}"))
        nav.add(wrapped_label("Cookies and saved data (sign-in, preferences) of this site are deleted. "
                              "You will be signed out of it."))
    else:
        _title(nav, "Clear data of all sites")
        nav.add(wrapped_label("Cookies and saved data of ALL sites are deleted. You will be signed out of every site."))
    status = _status()
    nav.add(status)
    yes = Button(text="Yes, clear", size_hint_y=None, height=BTN_H)

    def run(_i):
        if scope == "site" and not site:
            status.text = "Open a page first"
            return
        ok = br.clear_site(site) if scope == "site" else br.clear_all_site()
        status.text = "Done. The page reloads." if ok else _NEEDS_UPDATE
        yes.disabled = bool(ok)

    yes.bind(on_press=run)
    nav.add(yes)
    cancel = Button(text="Cancel", size_hint_y=None, height=BTN_H)
    cancel.bind(on_press=lambda i: browser_pages.open_menu(nav))
    nav.add(cancel)
    back = Button(text="Back to browser", size_hint_y=None, height=BTN_H)
    back.bind(on_press=lambda i: nav.show_browser())
    nav.add(back)


# -- the Find bar: a third row of the browser bar -------------------------------------------------------------------
class FindBar:
    """Search box, result counter (3/12), previous / next and Done. The row is added to the bar only while it is
    in use (``relayout(True/False)`` does that and puts the WebView under the taller bar)."""

    def __init__(self, nav, br, relayout):
        self.nav, self.br, self.relayout = nav, br, relayout
        self._ev = None
        self._mute = False
        self.row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        self.box = TextInput(hint_text="Find in page", multiline=False, size_hint_x=0.4)
        self.count = Label(text="", size_hint_x=0.16)
        prev_btn = Button(text="<", size_hint_x=0.1)
        next_btn = Button(text=">", size_hint_x=0.1)
        done_btn = Button(text="Done", size_hint_x=0.24)
        for w in (self.box, self.count, prev_btn, next_btn, done_btn):
            self.row.add_widget(w)
        self.box.bind(text=self._typed)
        self.box.bind(on_text_validate=lambda *_a: self.br.find_next(True))
        prev_btn.bind(on_press=lambda i: self.br.find_next(False))
        next_btn.bind(on_press=lambda i: self.br.find_next(True))
        done_btn.bind(on_press=lambda i: self.hide())

    def show(self, text=""):
        self.nav.browser_find = {"on": True, "q": text}
        self.relayout(True)
        self._mute = True
        self.box.text = text
        self._mute = False
        if text:
            self._schedule(text, 0.6)           # the page is shown again: look for the text again
        else:
            Clock.schedule_once(lambda dt: setattr(self.box, "focus", True), 0.3)

    def hide(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        self.br.clear_find()
        self.nav.browser_find = {"on": False, "q": ""}
        self._mute = True
        self.box.focus = False
        self.box.text = ""
        self._mute = False
        self.count.text = ""
        self.relayout(False)

    def _schedule(self, text, delay):
        if self._ev is not None:
            self._ev.cancel()
        self._ev = Clock.schedule_once(lambda dt: self._run(text), delay)

    def _typed(self, _inst, value):
        if not self._mute:
            self._schedule(value, 0.4)

    def _run(self, text):
        self._ev = None
        query = str(text or "").strip()
        self.nav.browser_find = {"on": True, "q": query}
        if query:
            self.br.find(query)
        else:
            self.br.clear_find()
            self.count.text = ""

    def update(self, data):
        """The counter from the helper's news (poll)."""
        if self.row.parent is None:
            return
        try:
            n, i = int(data.get("find_n") or 0), int(data.get("find_idx") or 0)
        except (TypeError, ValueError):
            return
        self.count.text = f"{i}/{n}" if n else ("0" if self.box.text.strip() else "")
