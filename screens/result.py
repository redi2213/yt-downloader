from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_downloads, android_open
from screens.common import BTN_H, GAP, wrapped_label, wrapped_label_height
from services import file_download_service

MAX_OPEN_ROWS = 8   # Open / Share rows shown after a many-file download


def _short(name, limit=26):
    name = str(name or "file")
    return name if len(name) <= limit else name[:limit - 3] + "..."


def add_size_label(nav, run_id, all_links):
    """A line with the size of the file(s), filled in a moment later."""
    label = wrapped_label("", height=dp(26), halign="center", valign="middle")
    nav.add(label)

    def done(items):
        text = file_download_service.sizes_text(items)

        def apply(_dt):
            label.text = text
            label.height = wrapped_label_height(text, extra_padding=dp(8)) if text else dp(4)
        Clock.schedule_once(apply)

    file_download_service.start_sizes(run_id, all_links, done)


def add_download_in_app(nav, run_id, all_links, category):
    """"Download in app": every file of this result goes to
    Download/Yt-bridge/<category> (the repo is private, so the app fetches the
    release files itself with its token)."""
    folder = android_downloads.folder_label(category)
    status = wrapped_label("", height=60, halign="center", valign="middle")
    btn = Button(text="Download in app", size_hint_y=None, height=52)
    state = {"busy": False}
    # Open / Share rows of the files saved by this button (filled when it finishes)
    files_box = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=GAP)

    def set_text(text):
        Clock.schedule_once(lambda dt: setattr(status, "text", text))

    def show_problem(problem):
        if problem:
            status.text = problem

    def fill_files(saved_files):
        files_box.clear_widgets()
        shown = [(n, loc) for n, loc in saved_files if loc][:MAX_OPEN_ROWS]
        for name, location in shown:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
            open_btn = Button(text=f"Open: {_short(name)}", size_hint_x=0.7, halign="center", shorten=True)
            open_btn.bind(on_press=lambda i, n=name, l=location: show_problem(android_open.open_file(l, n)))
            share_btn = Button(text="Share", size_hint_x=0.3)
            share_btn.bind(on_press=lambda i, n=name, l=location: show_problem(android_open.share_file(l, n)))
            row.add_widget(open_btn)
            row.add_widget(share_btn)
            files_box.add_widget(row)
        extra = len([1 for _n, loc in saved_files if loc]) - len(shown)
        if extra > 0:
            files_box.add_widget(Label(text=f"+ {extra} more: open them from the Files app", size_hint_y=None, height=BTN_H))
        rows = len(files_box.children)
        files_box.height = rows * BTN_H + max(0, rows - 1) * GAP

    def finished(saved_files=None):
        state["busy"] = False

        def apply(_dt):
            btn.disabled = False
            btn.text = "Download again"
            fill_files(saved_files or [])
        Clock.schedule_once(apply)

    def start(_instance):
        if state["busy"]:
            return
        state["busy"] = True
        btn.disabled = True
        btn.text = "Downloading..."
        status.text = f"Saving to {folder} ..."
        files_box.clear_widgets()
        files_box.height = 0
        file_download_service.start_links_download(run_id, all_links, category, set_text, finished)

    btn.bind(on_press=start)
    nav.add(btn)
    nav.add(status)
    nav.add(files_box)


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
    # file size - only for results that have files (not for error texts)
    downloadable = list(links or ([link] if link else []))
    if downloadable and (run_id or category):
        add_size_label(nav, run_id, downloadable)
    # "Download in app" - only for results that have files (not for error texts)
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
