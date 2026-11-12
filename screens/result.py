import re

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import android_downloads, android_open
from core.async_utils import run_in_background
from screens.common import BTN_H, GAP, wrapped_label, wrapped_label_height
from services import file_download_service

MAX_OPEN_ROWS = 8   # Open / Share rows shown after a many-file download


TEXT_EXTS = (".txt", ".json", ".csv", ".tsv", ".log", ".md", ".yml", ".yaml", ".xml", ".ini", ".conf", ".list")
MAX_TEXT_BYTES = 200 * 1024   # bigger text files are only downloaded, not shown
MAX_TEXT_FILES = 3
_PROXY_LINE = re.compile(r"^\s*(?:\w+://)?(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b")


def _is_text_name(name):
    return str(name or "").lower().split("?")[0].endswith(TEXT_EXTS)


def _fetch_texts(run_id, links):
    """[(name, text)] of the small text files of this result. Blocking: call from a thread."""
    import requests
    from api.github import releases
    found = []
    for one in (run_id if isinstance(run_id, (list, tuple)) else [run_id]):
        if not one:
            continue
        try:
            assets = releases.get_release_assets(one, attempts=1, delay=0)
        except Exception:
            assets = []
        headers = releases.asset_download_headers() if assets else None
        for a in assets:
            name = a.get("name") or ""
            if not _is_text_name(name) or (a.get("size") or 0) > MAX_TEXT_BYTES:
                continue
            try:
                resp = requests.get(a["api_url"], headers=headers, timeout=20)
                if resp.status_code == 200:
                    found.append((name, resp.content[:MAX_TEXT_BYTES].decode("utf-8", "replace")))
            except Exception:
                pass
            if len(found) >= MAX_TEXT_FILES:
                return found
    if not found:
        for url in list(links or [])[:MAX_TEXT_FILES]:
            if not _is_text_name(url):
                continue
            try:
                resp = requests.get(url, timeout=20)
                if resp.status_code == 200:
                    found.append((android_downloads.file_name_from_url(url),
                                  resp.content[:MAX_TEXT_BYTES].decode("utf-8", "replace")))
            except Exception:
                pass
    return found


def _proxy_only(text):
    """The IP:PORT of every proxy line ('1.2.3.4:80 | ISP' -> '1.2.3.4:80'); '' when it is not a proxy list."""
    rows = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    hits = [m.group(1) for m in (_PROXY_LINE.match(ln) for ln in rows) if m]
    return "\n".join(hits) if rows and len(hits) * 2 >= len(rows) else ""


def add_text_preview(nav, run_id, links):
    """Small text files of the result (txt, json, csv, log ...) shown right here with Copy buttons."""
    if not any(_is_text_name(u) for u in (links or [])):
        return
    box = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=GAP)
    nav.add(box)

    def fill(found):
        box.clear_widgets()
        total = 0
        for name, text in found:
            shown = text if text.strip() else "(the file is empty)"
            lines = len([ln for ln in text.splitlines() if ln.strip()])
            caption = wrapped_label(f"{name} - {lines} line(s)", height=dp(30), halign="center", valign="middle")
            field = TextInput(text=shown, readonly=True, multiline=True, size_hint_y=None, height=dp(260))
            copy_all = Button(text="Copy all", size_hint_y=None, height=48)
            copy_all.bind(on_press=lambda i, t=text: Clipboard.copy(t))
            parts = [caption, field, copy_all]
            only = _proxy_only(text)
            if only:
                only_btn = Button(text="Copy IP:PORT only", size_hint_y=None, height=48)
                only_btn.bind(on_press=lambda i, t=only: Clipboard.copy(t))
                parts.append(only_btn)
            for w in parts:
                box.add_widget(w)
                total += w.height + GAP
        box.height = max(0, total - GAP)

    def work():
        try:
            found = _fetch_texts(run_id, links)
        except Exception:
            found = []
        if found:
            Clock.schedule_once(lambda dt: fill(found))
    run_in_background(work)


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


def add_quality_row(nav, quality_label: str, quality_meta: dict, on_redownload=None):
    """Shows quality info (e.g. '1080p VP9') and optionally a re-download button."""
    if not quality_label:
        return
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(44), spacing=dp(6))
    ql = Label(
        text=f"Quality: {quality_label}",
        size_hint_x=0.55,
        halign="center",
        valign="middle",
    )
    ql.bind(size=ql.setter("text_size"))
    row.add_widget(ql)
    if on_redownload:
        btn = Button(text="Another quality", size_hint_x=0.45, height=dp(44))
        btn.bind(on_press=lambda i: on_redownload(quality_meta or {}))
        row.add_widget(btn)
    nav.add(row)


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

    def say(text):
        status.text = text
        status.height = max(dp(60), wrapped_label_height(text))

    def set_text(text):
        Clock.schedule_once(lambda dt: say(text))

    def show_problem(problem):
        if problem:
            say(problem)

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
        say(f"Saving to {folder} ...")
        files_box.clear_widgets()
        files_box.height = 0
        file_download_service.start_links_download(run_id, all_links, category, set_text, finished)

    btn.bind(on_press=start)
    nav.add(btn)
    nav.add(status)
    nav.add(files_box)


def build(nav, message, link=None, retry=None, retry_message="Working...", extra_buttons=None, links=None,
          arvan_links=None, storage_warn=None, run_id=None, category=None,
          quality_label: str = "", quality_meta: dict = None, on_redownload=None):
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
    # quality info + re-download button
    if quality_label:
        add_quality_row(nav, quality_label, quality_meta, on_redownload=on_redownload)
    # "Download in app" - only for results that have files (not for error texts)
    if category and downloadable:
        add_download_in_app(nav, run_id, downloadable, category)
    # small text files (a proxy list, a json, a log): shown here, with Copy buttons
    if downloadable and (run_id or category):
        add_text_preview(nav, run_id, downloadable)
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
