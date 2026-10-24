"""Result screen for jobs whose output is ONE file the user wants on the
phone: the project backup zip and the built APK.

* link box + Copy link + Share link (Android Share sheet)
* ``backup`` - the zip is small, so the download to the Downloads folder
  starts by itself (see Navigator.show_release_file); a button repeats it.
* ``apk``    - bigger, so the screen only ASKS: "Download to Downloads"
  button; nothing is downloaded until it is pressed. When it is saved an
  "Install" button opens Android's installer for the saved file.
* both    - once saved, "Open file" (Android's Open with... chooser) and
  "Share file" (the file itself in the Share sheet) become available.

Files go to Download/Yt-bridge/APK and Download/Yt-bridge/Backup.

The download state is kept in job.extra by services/file_download_service.py;
``refresh(job)`` redraws the status line and button from it.
"""
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_actions, android_install, android_open
from services import file_download_service
from screens import common

_TITLES = {"backup": "Project backup is ready", "apk": "APK is ready"}
_ASK = {"backup": "Download again", "apk": "Download in app"}
_ASK_TEXT = {
    "backup": "",
    "apk": "Download the APK to your save folder (APK), then install it from here?",
}

# job_id -> (status label, download button, kind, install button or None,
#            (Open file, Share file buttons)) of the screen being shown
_active = {}


def build(nav, job, kind):
    nav.clear()
    link = (job.result or {}).get("link") or ""

    nav.add(Label(text=_TITLES[kind], size_hint_y=None, height=44))
    box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
    nav.add(box)

    copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
    copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
    nav.add(copy_btn)

    status = common.wrapped_label("", height=common.line_height(3) + 12, halign="center", valign="middle")

    def share(_instance):
        if not android_actions.share_text(link):
            status.text = "Share is not available here - the link was copied instead."

    share_btn = Button(text="Share link", size_hint_y=None, height=48)
    share_btn.bind(on_press=share)
    nav.add(share_btn)

    size_label = common.wrapped_label("", height=dp(26), halign="center", valign="middle")
    nav.add(size_label)
    file_download_service.start_sizes(
        job.run_id, [link],
        lambda items: Clock.schedule_once(
            lambda _dt: setattr(size_label, "text", file_download_service.sizes_text(items))))

    nav.add(status)
    download_btn = Button(text=_ASK[kind], size_hint_y=None, height=52)
    download_btn.bind(on_press=lambda i: nav.start_file_download(job))
    nav.add(download_btn)

    install_btn = None
    if kind == "apk":
        install_btn = Button(text="Install", size_hint_y=None, height=52)

        def install(_instance):
            problem = android_install.open_installer(job.extra.get("dl_location"))
            if problem:
                status.text = problem

        install_btn.bind(on_press=install)
        nav.add(install_btn)

    def open_saved(_instance):
        problem = android_open.open_file(job.extra.get("dl_location"), job.extra.get("dl_name", ""))
        if problem:
            status.text = problem

    def share_saved(_instance):
        problem = android_open.share_file(job.extra.get("dl_location"), job.extra.get("dl_name", ""))
        if problem:
            status.text = problem

    open_btn = Button(text="Open file", size_hint_y=None, height=52)
    open_btn.bind(on_press=open_saved)
    nav.add(open_btn)
    share_file_btn = Button(text="Share file", size_hint_y=None, height=52)
    share_file_btn.bind(on_press=share_saved)
    nav.add(share_file_btn)

    home_btn = Button(text="Back to home", size_hint_y=None, height=48)
    home_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(home_btn)

    _active[job.job_id] = (status, download_btn, kind, install_btn, (open_btn, share_file_btn))
    refresh(job)


def refresh(job):
    """Redraws the status line and the download button for ``job`` (no-op
    when its screen is not the one on display)."""
    entry = _active.get(job.job_id)
    if entry is None:
        return
    status, button, kind, install_btn, file_buttons = entry
    state = job.extra.get("dl_state")
    for file_btn in file_buttons:
        file_btn.disabled = state != "done" or not job.extra.get("dl_location")
    if install_btn is not None:
        install_btn.disabled = state != "done" or not job.extra.get("dl_location")
    if state:
        status.text = job.extra.get("dl_text", "")
    else:
        status.text = _ASK_TEXT[kind]
    button.disabled = state == "running"
    if state == "running":
        button.text = "Downloading..."
    elif state in ("done", "error"):
        button.text = "Download again"
    else:
        button.text = _ASK[kind]
