from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_downloads
from screens.common import wrapped_label
from services import file_download_service


def add_download_in_app(nav, run_id, all_links, category):
    """"Download in app": every file of this result goes to
    Download/Yt-bridge/<category> (the repo is private, so the app fetches the
    release files itself with its token)."""
    folder = f"Download/{android_downloads.ROOT_FOLDER}/{category}"
    status = wrapped_label("", height=60, halign="center", valign="middle")
    btn = Button(text="Download in app", size_hint_y=None, height=52)
    state = {"busy": False}

    def set_text(text):
        Clock.schedule_once(lambda dt: setattr(status, "text", text))

    def finished():
        state["busy"] = False
        Clock.schedule_once(lambda dt: (setattr(btn, "disabled", False), setattr(btn, "text", "Download again")))

    def start(_instance):
        if state["busy"]:
            return
        state["busy"] = True
        btn.disabled = True
        btn.text = "Downloading..."
        status.text = f"Saving to {folder} ..."
        file_download_service.start_links_download(run_id, all_links, category, set_text, finished)

    btn.bind(on_press=start)
    nav.add(btn)
    nav.add(status)


def build(nav, message, link=None, retry=None, retry_message="Working...", extra_buttons=None, links=None,
          arvan_links=None, storage_warn=None, run_id=None, category=None):
    nav.clear()
    many = bool(links) and len(links) > 1
    if many:
        message = f"{message} ({len(links)} files)"
    nav.add(Label(text=message, size_hint_y=None, height=60))
    if storage_warn:
        # e.g. "Bucket ... is full" - the file is still safe on GitHub
        nav.add(wrapped_label(f"Storage note: {storage_warn}"))
    if many:
        # several files: every link on its own line, one button copies them all
        all_text = "\n".join(links)
        link_box = TextInput(text=all_text, readonly=True, multiline=True,
                             size_hint_y=None, height=dp(220))
        nav.add(link_box)
        copy_btn = Button(text="Copy all links", size_hint_y=None, height=48)
        copy_btn.bind(on_press=lambda i: Clipboard.copy(all_text))
        nav.add(copy_btn)
        first_btn = Button(text="Copy first link only", size_hint_y=None, height=48)
        first_btn.bind(on_press=lambda i: Clipboard.copy(links[0]))
        nav.add(first_btn)
    elif link:
        link_box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
        nav.add(link_box)
        copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
        copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
        nav.add(copy_btn)
    # "Download in app" - only for results that have files (not for error texts)
    downloadable = list(links or ([link] if link else []))
    if category and downloadable:
        add_download_in_app(nav, run_id, downloadable, category)
    # Links on Arvan Cloud that are not already the main link (GitHub + Arvan mode)
    shown = set(links or ([link] if link else []))
    arvan_only = [u for u in (arvan_links or []) if u not in shown]
    if arvan_only:
        arvan_text = "\n".join(arvan_only)
        nav.add(Label(text="Arvan link (deleted after 7 days)" if len(arvan_only) == 1
                      else f"Arvan links ({len(arvan_only)} files, deleted after 7 days)",
                      size_hint_y=None, height=32))
        nav.add(TextInput(text=arvan_text, readonly=True, multiline=len(arvan_only) > 1,
                          size_hint_y=None, height=dp(48) if len(arvan_only) == 1 else dp(160)))
        arvan_btn = Button(text="Copy Arvan link" if len(arvan_only) == 1 else "Copy all Arvan links",
                           size_hint_y=None, height=48)
        arvan_btn.bind(on_press=lambda i: Clipboard.copy(arvan_text))
        nav.add(arvan_btn)
    # extra_buttons: [(text, callable)] shown under "Copy link"
    for text, callback in (extra_buttons or []):
        extra_btn = Button(text=text, size_hint_y=None, height=48)
        extra_btn.bind(on_press=lambda i, cb=callback: cb())
        nav.add(extra_btn)
    if retry:
        retry_btn = Button(text="Try again", size_hint_y=None, height=48)
        retry_btn.bind(on_press=lambda i: nav.retry_action(retry, retry_message))
        nav.add(retry_btn)
    home_btn = Button(text="Back to home", size_hint_y=None, height=48)
    home_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(home_btn)
