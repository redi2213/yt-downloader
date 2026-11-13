from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from api.github import releases
from core import android_downloads, android_install, version_check
from core.async_utils import run_in_background
from core.config import APP_VERSION, ABOUT_TEXT_TEMPLATE
from screens import common


def _size_text(size):
    return f"{size / (1024 * 1024):.1f} MB" if size else ""


def build(nav):
    nav.clear()
    about_text = ABOUT_TEXT_TEMPLATE.format(version=APP_VERSION)
    nav.add(Label(text=about_text, size_hint_y=None, height=220))

    status = Label(text="", size_hint_y=None, height=70, halign="center", valign="middle")
    status.text_size = (common.content_width(), None)

    # the buttons that depend on the check (Download update / Install / Build APK now)
    actions = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6)
    actions.bind(minimum_height=actions.setter("height"))

    def on_screen():
        try:
            return status in nav._content_widgets()
        except Exception:
            return False

    def say(text):
        if on_screen():
            status.text = text

    def add_button(text, handler):
        btn = Button(text=text, size_hint_y=None, height=48)
        btn.bind(on_press=lambda i: handler(btn))
        actions.add_widget(btn)
        return btn

    # -- the update is on GitHub: find its APK ----------------------------------------------------
    def show(res):
        if not on_screen():
            return
        actions.clear_widgets()
        status.text = version_check.describe(res)
        if res.get("ok") and res.get("state") == "newer":
            say(status.text + "\nLooking for the APK...")
            from services import update_check_service
            update_check_service.find_apk(
                res["latest"], lambda found: nav.schedule(lambda: after_find(res, found)))

    def after_find(res, found):
        if not on_screen():
            return
        actions.clear_widgets()
        base = version_check.describe(res)
        if found.get("ok") and found.get("found"):
            size = _size_text(found.get("size"))
            say(base)
            add_button(f"Download update ({size})" if size else "Download update",
                       lambda btn: download(btn, found))
        elif found.get("ok"):
            say(base + "\nThe APK of this version is not ready yet.")
            add_button("Build APK now", lambda btn: nav.start_build_apk())
        else:
            say(base + "\n" + str(found.get("error", "")))

    # -- download, then install -----------------------------------------------------------------
    def download(btn, found):
        btn.disabled = True
        last = [-1]

        def progress(done, total):
            pct = done * 100 // total if total else 0
            if pct != last[0]:
                last[0] = pct
                nav.schedule(lambda: say(f"Downloading the update... {pct}%"))

        def work():
            try:
                saved = android_downloads.download_to_downloads(
                    found["api_url"], name=found["name"], on_progress=progress,
                    headers=releases.asset_download_headers(), category="APK")
                nav.schedule(lambda: downloaded(getattr(saved, "location", None)))
            except Exception as e:
                text = str(e)[:80]
                nav.schedule(lambda: failed(text))

        say("Downloading the update... 0%")
        run_in_background(work)

    def downloaded(location):
        if not on_screen():
            return
        actions.clear_widgets()
        say("The update is downloaded. Press Install.")
        add_button("Install", lambda btn: install(location))

    def failed(text):
        if not on_screen():
            return
        actions.clear_widgets()
        say(f"Download failed: {text}")
        add_button("Check for update", lambda btn: check(None))

    def install(location):
        problem = android_install.open_installer(location)
        if problem:
            say(problem)

    def check(_instance):
        actions.clear_widgets()
        status.text = "Checking..."
        from services import update_check_service
        update_check_service.start_check(lambda res: nav.schedule(lambda: show(res)))

    check_btn = Button(text="Check for update", size_hint_y=None, height=48)
    check_btn.bind(on_press=check)
    nav.add(check_btn)
    nav.add(status)
    nav.add(actions)

    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_settings())
    nav.add(back_btn)
