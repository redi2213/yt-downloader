"""Python side of the in-app browser (the WebView itself is java/org/redi2213/ytbridge/BrowserHelper.java).

pyjnius cannot subclass WebViewClient, so a small Java class (added to the APK with
``android.add_src = java`` in buildozer.spec) does that; this module only calls its static methods.
Everything returns quietly on desktop: ``supported()`` is False there.
"""
import json
import time

_CLASS = "org.redi2213.ytbridge.BrowserHelper"
_supported = None


def supported():
    global _supported
    if _supported is None:
        try:
            from jnius import autoclass
            autoclass(_CLASS)
            _supported = True
        except Exception:
            _supported = False
    return _supported


class Browser:
    def __init__(self):
        self._h = None
        self._created = False
        self.started = False        # a first page was already loaded
        self._exts = None           # the extensions the helper was last told to report
        self.tab_id = ""            # the tab whose page the WebView shows now
        self._guard = None          # (epoch, url, until): after a tab switch on an APK without switchTab()
        self._sent = {}             # page-tool values the helper already has (sent again only when they change)
        self._native = None

    def _helper(self):
        if self._h is None:
            from jnius import autoclass
            self._h = autoclass(_CLASS)
        return self._h

    def ensure(self, top_px):
        if self._created:
            return
        from jnius import autoclass
        self._helper().create(autoclass("org.kivy.android.PythonActivity").mActivity, int(top_px))
        self._created = True

    def set_extensions(self, csv):
        """The file extensions the helper reports (core/browser_media.Rules.csv()). An APK built before this
        existed keeps reporting video and audio only."""
        if not self._created or csv == self._exts:
            return
        try:
            self._helper().setExtensions(str(csv or ""))
            self._exts = csv
        except Exception:
            pass

    def set_top(self, top_px):
        if self._created:
            self._helper().setTop(int(top_px))

    def show(self, on=True):
        if self._created:
            self._helper().setVisible(bool(on))

    def hide(self):
        self.show(False)

    def set_badge(self, text):
        if self._created:
            self._helper().setBadge(str(text or ""))

    def load(self, url):
        if self._created:
            self.started = True
            self._helper().load(str(url))

    def back(self):
        if self._created:
            self._helper().goBack()

    def forward(self):
        if self._created:
            self._helper().goForward()

    def reload(self):
        if self._created:
            self._helper().reload()

    def rescan(self, page=""):
        """The list's Refresh: the helper forgets what it saw and the page loads again.
        An APK built before rescan() existed gets the same through about:blank (a new page
        makes the helper forget what it saw)."""
        if not self._created:
            return
        try:
            self._helper().rescan()
            return
        except Exception:
            pass
        try:
            self._helper().load("about:blank")
            if page:
                from kivy.clock import Clock
                Clock.schedule_once(lambda dt: self._helper().load(str(page)), 0.6)
        except Exception:
            pass

    def switch_tab(self, from_id, to_id, url):
        """Shows another tab: the helper keeps the page state (history, scroll) of the tab we leave and
        restores the state of the new one, or loads ``url``. An APK built before switchTab() existed just
        loads ``url`` (the back stack is then shared by the tabs) and ignores what the old page still reports."""
        if not self._created:
            return
        self.started = True
        self.tab_id = str(to_id or "")
        try:
            self._helper().switchTab(str(from_id or ""), str(to_id or ""), str(url or ""))
            self._guard = None
            return
        except Exception:
            pass
        try:
            old = json.loads(str(self._helper().poll()))      # drops what the old page reported
            self._guard = (old.get("epoch"), str(url or ""), time.monotonic() + 4.0)
        except Exception:
            self._guard = None
        self._helper().load(str(url or ""))

    def forget_tab(self, tab_id=None):
        """A tab was closed (all tabs when ``tab_id`` is empty): the helper drops its saved page state."""
        if not tab_id or tab_id == self.tab_id:
            self.tab_id = ""
        if not self._created:
            return
        try:
            self._helper().forgetTab(str(tab_id or ""))
        except Exception:
            pass            # an APK built before tabs existed has nothing saved

    # -- page tools (Desktop view, Dark mode, Find, blocking, cleaning): native, so an APK built before they existed
    #    has none of them; every call then returns False and the screen says a new build is needed.
    def native_ready(self):
        if self._native is None:
            try:
                getattr(self._helper(), "setDark")
                self._native = True
            except Exception:
                self._native = False
        return self._native

    def _call(self, name, *args):
        if not self._created:
            return False
        try:
            getattr(self._helper(), name)(*args)
            return True
        except Exception:
            return False

    def _push(self, key, value, name, *args):
        if self._sent.get(key) == value:
            return True
        ok = self._call(name, *args)
        if ok:
            self._sent[key] = value
        return ok

    def set_desktop(self, on, reload=False):
        """Desktop version of sites (user agent + wide viewport); ``reload`` loads the page again to show it."""
        on = bool(on)
        return self._push("desktop", on, "setDesktop", on, bool(reload))

    def set_dark(self, on):
        on = bool(on)
        return self._push("dark", on, "setDark", on)

    def set_block(self, images, videos):
        """Images / videos are not loaded at all (no network request for them), not only hidden."""
        images, videos = bool(images), bool(videos)
        return self._push("block", (images, videos), "setBlock", images, videos)

    def find(self, text):
        return self._call("find", str(text or ""))

    def find_next(self, forward=True):
        return self._call("findNext", bool(forward))

    def clear_find(self):
        return self._call("clearFind")

    def clear_cache(self):
        return self._call("clearCache")

    def clear_site(self, url):
        """Cookies and saved data of the site of ``url``; the page loads again."""
        return self._call("clearSiteData", str(url or ""))

    def clear_all_site(self):
        return self._call("clearAllSiteData")

    # -- cookie export (screens/browser_cookies.py): native too, an older APK answers "not ready" / None.
    def cookies_ready(self):
        if not self._created:
            return False
        try:
            getattr(self._helper(), "exportCookies")
            return True
        except Exception:
            return False

    def export_cookies(self, urls):
        """What the WebView would send to each address of ``urls``: {ua, page, queries: [{url, cookie}]}, or None
        (not created / an older APK / any failure). The values go to core/browser_cookies.py only."""
        if not self._created:
            return None
        try:
            return json.loads(str(self._helper().exportCookies("\n".join(urls))))
        except Exception:
            return None

    # -- network log (screens/browser_cookies.py, Copy as cURL): native too, an older APK answers "not ready" / None.
    def netlog_ready(self):
        if not self._created:
            return False
        try:
            getattr(self._helper(), "netLog")
            return True
        except Exception:
            return False

    def net_log(self):
        """The Fetch / XHR requests the page made: {page, ua, items: [...]}, or None (not created / an older APK /
        any failure). The requests hold cookie values: they go to core/browser_cookies.py only."""
        if not self._created:
            return None
        try:
            return json.loads(str(self._helper().netLog()))
        except Exception:
            return None

    def clear_net_log(self):
        return self._call("clearNetLog")

    def can_back(self):
        try:
            return bool(self._created and self._helper().canBack())
        except Exception:
            return False

    def poll(self):
        """The helper's news as a dict, or None (not created / any failure)."""
        if not self._created:
            return None
        try:
            data = json.loads(str(self._helper().poll()))
        except Exception:
            return None
        g = self._guard
        if g is not None:
            if data.get("epoch") == g[0] and data.get("page") != g[1] and time.monotonic() < g[2]:
                return None         # still the page of the tab we left
            self._guard = None
        return data
