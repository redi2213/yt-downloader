"""Python side of the in-app browser (the WebView itself is java/org/redi2213/ytbridge/BrowserHelper.java).

pyjnius cannot subclass WebViewClient, so a small Java class (added to the APK with
``android.add_src = java`` in buildozer.spec) does that; this module only calls its static methods.
Everything returns quietly on desktop: ``supported()`` is False there.
"""
import json

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
            return json.loads(str(self._helper().poll()))
        except Exception:
            return None
