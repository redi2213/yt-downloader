"""Several tabs inside the app. Every tab is a separate copy of the app: its own Navigator (screens, jobs,
back history), its own scroll area and bottom bar. Only the active tab's containers are shown; the other
tabs keep working in the background (their jobs and timers go on).

Shared on purpose: the one native browser view (hidden while another tab is shown; a tab that was on the
browser page gets it back when it is opened), the Downloads manager and the settings.

Rules without Kivy (tab state, percent, which tab to close): core/tab_state.py.
Top bar: main.py (Home button + Tabs button); the Tabs button opens the card list built here."""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.scrollview import ScrollView

from core import tab_state as ts
from services import run_progress_service
from screens import dialogs
from screens.common import BTN_H, GAP, PAD

MAX_TABS = ts.MAX_TABS
_POLL_SECONDS = 15

_COLORS = {ts.RUNNING: (1.0, 0.82, 0.45, 1), ts.DONE: (0.55, 0.9, 0.6, 1), ts.ERROR: (1.0, 0.55, 0.55, 1)}

# the Navigator method that opened an idle tab's screen -> the title shown on its card (existing UI texts)
_SCREEN_TITLES = {
    "show_youtube_download": "YouTube Download",
    "show_dynamic_actions": "Download Anything",
    "show_browser": "مرورگر",
    "show_browser_list": "مرورگر",
    "show_follow_menu": "Auto follow",
    "show_downloads": "Downloads",
    "show_release_history": "Release History",
    "show_actions_status": "Check GitHub Actions status",
    "show_settings": "Settings",
    "show_running_jobs": "Running jobs",
}
_JOB_TITLES = {
    "formats": "Quality list", "download": "Video download", "playlist_links": "Playlist links",
    "playlist_download": "Playlist download", "upload": "File upload",
}


def _tr(text):
    try:
        from core.i18n import tr
        return tr(text)
    except Exception:
        return text


class TabShell:
    """What one tab's Navigator sees as its ``app``: its own content / footer / status label.
    Only the active tab's containers are put on screen (TabManager.activate)."""

    def __init__(self, manager):
        from screens.navigator import Navigator
        self.manager = manager
        self.topbar_mode = "tabs"       # "full" (Home + Tabs), "tabs" (Tabs only), "hidden"
        self.percent = None
        self.ack_job = None             # the finished job the user already saw
        self.browser_was_visible = False
        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", padding=PAD, spacing=GAP, size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.status_label = Label(text="")
        self.footer = BoxLayout(orientation="vertical", size_hint_y=None, height=0, padding=(PAD, dp(6)))
        self.nav = Navigator(self)

    # -- what the Navigator calls (same names as the old App) -----------------
    def clear_content(self):
        self.content.clear_widgets()
        self.footer.clear_widgets()
        self.footer.height = 0

    def set_footer(self, widget):
        self.footer.clear_widgets()
        self.footer.add_widget(widget)
        self.footer.height = widget.height + dp(12)

    def add_widget_to_content(self, widget):
        self.content.add_widget(widget)

    def show_topbar(self, visible):
        """True = Home + Tabs buttons, False = no bar (browser page), "tabs" = Tabs button only (Home screen)."""
        if visible is True:
            visible = "full"
        elif visible is False or visible is None:
            visible = "hidden"
        self.topbar_mode = visible
        self.manager.apply_topbar(self)

    # -- state for the card and the Tabs button ---------------------------------
    def main_job(self):
        jm = self.nav.job_manager
        active = jm.active_jobs
        if not active:
            return None
        cur = jm.current_job
        return cur if any(j is cur for j in active) else active[0]

    def state(self):
        jm = self.nav.job_manager
        cur = jm.current_job
        return ts.tab_state(bool(jm.active_jobs), cur is not None and cur.is_done,
                            getattr(cur, "ok", None), bool(getattr(cur, "cancel_requested", False)),
                            cur is self.ack_job)

    def title(self):
        job = self.main_job()
        if job is not None:
            action = (getattr(job, "extra", None) or {}).get("action") or {}
            name = action.get("title") or action.get("name")
            return str(name) if name else _JOB_TITLES.get(job.type, "Running job")
        if getattr(self.nav, "on_home", False):
            return "Home"
        menu = getattr(self.nav, "_last_menu", None)
        owner = getattr(menu, "__self__", None)
        page = getattr(owner, "title_text", None)       # a Lab / plugin tool page: the tool's own name
        if page:
            return str(page)
        if getattr(menu, "__module__", "") == "screens.lab":    # the Lab tool list
            return "Lab"
        name = getattr(menu, "__name__", "")
        return _SCREEN_TITLES.get(name, "Tab")


class TabManager:
    def __init__(self, app):
        self.app = app
        self.tabs = []
        self.active = None
        self.body = BoxLayout(orientation="vertical")   # holds the active tab's scroll area + footer
        self._overlay = None
        self._btn_bg = None
        self._btn_text = None
        self._patch_browser()
        Clock.schedule_interval(lambda dt: self.refresh_button(), 1.0)

    # -- the native browser view is one for the whole app -----------------------
    @staticmethod
    def _patch_browser():
        """Browser.show() remembers whether the view is on screen (``visible``)."""
        try:
            from core import android_browser
            cls = android_browser.Browser
            if getattr(cls, "_tabs_patched", False):
                return
            original = cls.show

            def show(self, on=True):
                self.visible = bool(on)
                return original(self, on)

            cls.show = show
            cls._tabs_patched = True
        except Exception:
            pass

    def _sync_browser(self):
        shared = next((t.nav.browser for t in self.tabs if getattr(t.nav, "browser", None) is not None), None)
        if shared is not None:
            for t in self.tabs:
                t.nav.browser = shared

    # -- opening, switching, closing ---------------------------------------------
    def new_tab(self, start=None):
        """A new tab, shown at once. ``start(nav)`` builds its first screen (default: Home)."""
        if len(self.tabs) >= MAX_TABS:
            return None
        shell = TabShell(self)
        self.tabs.append(shell)
        self.activate(shell)
        if start is None:
            shell.nav.show_home()
        else:
            start(shell.nav)
        self.refresh_button()
        return shell

    def activate(self, shell):
        prev = self.active
        if prev is shell or shell not in self.tabs:
            return
        self._sync_browser()
        if prev is not None:
            self._leave(prev)
        self.active = shell
        for t in self.tabs:
            t.nav.tab_visible = (t is shell)
        self.body.clear_widgets()
        self.body.add_widget(shell.scroll)
        self.body.add_widget(shell.footer)
        self.app.set_topbar_mode(shell.topbar_mode)
        self._ack(shell)
        if shell.browser_was_visible:
            shell.browser_was_visible = False
            Clock.schedule_once(lambda dt: self._restore_browser(shell), 0.05)
        self.refresh_button()

    def _leave(self, shell):
        browser = getattr(shell.nav, "browser", None)
        shell.browser_was_visible = bool(browser is not None and getattr(browser, "visible", False))
        if browser is not None:
            browser.hide()
        self._ack(shell)

    def _restore_browser(self, shell):
        if self.active is shell:
            shell.nav.show_browser()        # rebuilds the browser page and puts the native view back

    @staticmethod
    def _ack(shell):
        cur = shell.nav.job_manager.current_job
        if cur is not None and cur.is_done:
            shell.ack_job = cur

    def apply_topbar(self, shell):
        if shell is self.active:
            self.app.set_topbar_mode(shell.topbar_mode)

    def close_tab(self, shell):
        """Closing a tab that runs a job asks first (the job itself keeps running on GitHub)."""
        if len(self.tabs) < 2 or shell not in self.tabs:
            return
        if shell.state() == ts.RUNNING:
            dialogs.confirm(
                "This tab is running a job. Close it anyway? The job keeps running on GitHub, "
                "but you will not see it here.",
                "Close the tab", lambda: self._do_close(shell))
            return
        self._do_close(shell)

    def _do_close(self, shell):
        if len(self.tabs) < 2 or shell not in self.tabs:
            return
        index = self.tabs.index(shell)
        if shell is self.active:
            self.activate(self.tabs[index - 1] if index > 0 else self.tabs[1])
        self.tabs.remove(shell)
        try:
            shell.nav.stop_progress_timer()
            shell.nav.back_hook = None
        except Exception:
            pass
        shell.nav.tab_visible = False
        shell.content.clear_widgets()
        shell.footer.clear_widgets()
        self.refresh_button()
        self._render()

    # -- things that arrive from outside the app --------------------------------
    def handle_shared_text(self, text):
        self.open_external(lambda nav: nav.handle_shared_text(text))

    def handle_shared_file(self, *args, **kwargs):
        self.open_external(lambda nav: nav.handle_shared_file(*args, **kwargs))

    def open_external(self, start):
        """A link or file from another app always opens in a NEW tab. All tabs used: the oldest idle tab is
        closed; if every tab is running the user chooses which one to close."""
        if len(self.tabs) < MAX_TABS:
            self.new_tab(start)
            return
        index = ts.pick_to_replace([t.state() for t in self.tabs])
        if index is not None:
            self._do_close(self.tabs[index])
            self.new_tab(start)
            return
        buttons = [(f"Close tab {i}: {_tr(t.title())}", (lambda t=t: self._replace(t, start)), True)
                   for i, t in enumerate(self.tabs, 1)]
        dialogs.menu("All tabs are busy. Which one should be closed to make room for the new link?", buttons)

    def _replace(self, shell, start):
        self._do_close(shell)
        self.new_tab(start)

    def open_from_notification(self, job_id, run_id):
        """The user tapped a notification: open the tab that owns that job (else the tab on screen)."""
        target = None
        for t in self.tabs:
            jm = t.nav.job_manager
            for job in [jm.current_job, *jm.active_jobs, *jm.history]:
                if job is not None and job_id and job.job_id == job_id:
                    target = t
                    break
            if target is not None:
                break
        shell = target or self.active
        self.activate(shell)
        shell.nav.open_from_notification(job_id, run_id)

    # -- the Tabs button -----------------------------------------------------------
    def refresh_button(self):
        btn = getattr(self.app, "tabs_btn", None)
        if btn is None or self.active is None or self.active not in self.tabs:
            return
        if self._btn_bg is None:
            self._btn_bg = tuple(btn.background_color)
        badge = ts.badge_state([t.state() for t in self.tabs], self.tabs.index(self.active))
        text = f"Tabs ({len(self.tabs)})" + ts.badge_suffix(badge)
        if text != self._btn_text:
            btn.text = text
            self._btn_text = text
        color = _COLORS.get(badge, self._btn_bg)
        if tuple(btn.background_color) != tuple(color):
            btn.background_color = color
        if self._overlay is not None:
            self._refresh_rows()

    # -- the card list ---------------------------------------------------------------
    def open_overlay(self):
        if self._overlay is not None:
            return
        dlg = ModalView(size_hint=(0.94, 0.86), background="", background_color=(0.13, 0.10, 0.09, 1))
        box = BoxLayout(orientation="vertical", padding=dp(12), spacing=GAP)
        box.add_widget(Label(text="Tabs", size_hint_y=None, height=dp(40)))
        scroll = ScrollView()
        lst = BoxLayout(orientation="vertical", spacing=GAP, size_hint_y=None)
        lst.bind(minimum_height=lst.setter("height"))
        scroll.add_widget(lst)
        box.add_widget(scroll)
        note = Label(text="", size_hint_y=None, height=dp(24))
        box.add_widget(note)
        new_btn = Button(text="New tab", size_hint_y=None, height=BTN_H)
        close_btn = Button(text="Close", size_hint_y=None, height=BTN_H)
        box.add_widget(new_btn)
        box.add_widget(close_btn)
        dlg.add_widget(box)
        self._overlay = {"dlg": dlg, "lst": lst, "note": note, "new": new_btn, "rows": [], "poll": None}
        new_btn.bind(on_press=lambda b: self._new_from_overlay())
        close_btn.bind(on_press=lambda b: dlg.dismiss())
        dlg.bind(on_dismiss=lambda d: self._overlay_closed())
        self._render()
        dlg.open()
        self._poll_percent()
        self._overlay["poll"] = Clock.schedule_interval(lambda dt: self._poll_percent(), _POLL_SECONDS)

    def _overlay_closed(self):
        overlay, self._overlay = self._overlay, None
        if overlay and overlay.get("poll") is not None:
            overlay["poll"].cancel()

    def _new_from_overlay(self):
        self._overlay["dlg"].dismiss()
        Clock.schedule_once(lambda dt: self.new_tab(), 0.05)

    def _open_tab(self, shell):
        if self._overlay is not None:
            self._overlay["dlg"].dismiss()
        Clock.schedule_once(lambda dt: self.activate(shell), 0.05)

    def _render(self):
        overlay = self._overlay
        if overlay is None:
            return
        overlay["lst"].clear_widgets()
        overlay["rows"] = []
        for shell in self.tabs:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(80), spacing=GAP)
            info = BoxLayout(orientation="vertical", spacing=dp(4))
            title_btn = Button(text="", size_hint_y=None, height=BTN_H)
            status = Label(text="", size_hint_y=None, height=dp(26))
            title_btn.bind(on_press=lambda b, s=shell: self._open_tab(s))
            info.add_widget(title_btn)
            info.add_widget(status)
            row.add_widget(info)
            if len(self.tabs) > 1:
                close = Button(text="Close tab", size_hint_x=0.3)
                close.bind(on_press=lambda b, s=shell: self.close_tab(s))
                row.add_widget(close)
            overlay["lst"].add_widget(row)
            overlay["rows"].append({"shell": shell, "btn": title_btn, "status": status, "bg": None})
        full = len(self.tabs) >= MAX_TABS
        overlay["new"].disabled = full
        overlay["note"].text = f"Up to {MAX_TABS} tabs are open" if full else ""
        self._refresh_rows()

    def _refresh_rows(self):
        overlay = self._overlay
        if overlay is None:
            return
        for number, row in enumerate(overlay["rows"], 1):
            shell, btn = row["shell"], row["btn"]
            if row["bg"] is None:
                row["bg"] = tuple(btn.background_color)
            state = shell.state()
            mark = "> " if shell is self.active else ""
            text = f"{mark}{number} - {_tr(shell.title())}"
            if btn.text != text:
                btn.text = text
            color = _COLORS.get(state, row["bg"])
            if tuple(btn.background_color) != tuple(color):
                btn.background_color = color
            label = ts.status_text(state, shell.percent if state == ts.RUNNING else None)
            if row["status"].text != label:
                row["status"].text = label

    def _poll_percent(self):
        for shell in self.tabs:
            job = shell.main_job()
            run_id = getattr(job, "run_id", None) if job is not None else None
            if not run_id:
                shell.percent = None
                continue

            def done(payload, shell=shell):
                if payload.get("ok"):
                    shell.percent = ts.job_percent(payload.get("job"))
                    Clock.schedule_once(lambda dt: self._refresh_rows())

            run_progress_service.start_load_progress(run_id, on_complete=done)
        self._refresh_rows()
