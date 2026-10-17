from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

import re

from screens.common import (
    BTN_H, CARD, CARD_ON, GAP, SMALL_BTN_H, back_button, card_box, content_width,
    fa_font_kwargs, fa_text, line_height, paint_card, wrapped_label_height,
)

_QUALITY_PRESETS = [
    ("480p", 480, False), ("720p", 720, False), ("1080p", 1080, False),
    ("2160p", 2160, False), ("Best", 99999, False), ("Best HDR", 99999, True),
]


def build_quality_picker(nav, urls):
    nav.clear()
    nav.add(Label(text=f"{len(urls)} videos found. Choose quality for ALL:", size_hint_y=None, height=50))
    for name, target_height, want_hdr in _QUALITY_PRESETS:
        btn = Button(text=name, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, h=target_height, hd=want_hdr: nav.start_playlist_download(urls, h, hd))
        nav.add(btn)
    nav.add(back_button(nav, to=nav.show_youtube_download))


# (label, target_height, want_hdr) for the quality of the chosen videos
_SELECTED_QUALITIES = [
    ("360p", 360, False), ("480p", 480, False), ("720p", 720, False),
    ("1080p", 1080, False), ("Best", 99999, False),
]


def build_picker(nav, entries, playlist_url, selected):
    """The playlist's videos as tap-to-select cards (like Release History):
    Select all / Clear, then "Download selected". ``selected`` is a list of
    bools, one per entry, edited in place."""
    nav.clear()
    total = len(entries)
    nav.add(Label(text=f"Playlist ({total} videos)", size_hint_y=None, height=BTN_H))

    cards = []   # card colour of every video, in display order
    info = Label(text="", size_hint_y=None, height=BTN_H)

    def update_info():
        info.text = f"Selected: {sum(selected)} of {total}"

    def set_selected(idx, value):
        selected[idx] = value
        cards[idx].rgba = CARD_ON if value else CARD
        update_info()

    def set_all(value):
        for idx in range(total):
            set_selected(idx, value)

    def download_selected(_inst):
        urls = [e["url"] for e, on in zip(entries, selected) if on]
        if not urls:
            info.text = "Tap the videos you want first"
            return
        nav.show_playlist_selected_quality(entries, playlist_url, selected, urls)

    select_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    select_all_btn = Button(text="Select all")
    select_all_btn.bind(on_press=lambda i: set_all(True))
    clear_btn = Button(text="Clear")
    clear_btn.bind(on_press=lambda i: set_all(False))
    select_row.add_widget(select_all_btn)
    select_row.add_widget(clear_btn)
    nav.add(select_row)
    nav.add(info)

    go_btn = Button(text="Download selected", size_hint_y=None, height=BTN_H)
    go_btn.bind(on_press=download_selected)
    nav.add(go_btn)

    inner_width = content_width() - 2 * dp(8)
    for idx, entry in enumerate(entries):
        raw_text = f"{idx + 1}. {entry['title']}"
        text = fa_text(raw_text, inner_width - dp(16))
        height = wrapped_label_height(text, extra_padding=dp(14), width=inner_width - dp(16))
        row = card_box([height])
        cards.append(paint_card(row, CARD_ON if selected[idx] else CARD))
        title_btn = Button(text=text, size_hint_y=None, height=height, halign="left", valign="middle",
                           background_normal="", background_color=(0, 0, 0, 0),
                           **fa_font_kwargs(raw_text))
        title_btn.text_size = (inner_width - dp(16), None)
        title_btn.bind(on_press=lambda i, n=idx: set_selected(n, not selected[n]))
        row.add_widget(title_btn)
        nav.add(row)

    update_info()
    nav.add(back_button(nav, to=lambda: nav.show_youtube_download(playlist_url=playlist_url)))


def build_selected_quality(nav, urls, back):
    """Quality for the chosen videos only; audio-only (MP3) is offered too."""
    nav.clear()
    nav.add(Label(text=f"{len(urls)} selected video(s). Choose quality:", size_hint_y=None, height=50))

    def again():
        build_selected_quality(nav, urls, back)

    for name, target_height, want_hdr in _SELECTED_QUALITIES:
        btn = Button(text=name, size_hint_y=None, height=50)
        btn.bind(on_press=lambda inst, h=target_height, hd=want_hdr:
                 nav.start_playlist_download(urls, h, hd, quality_screen=again))
        nav.add(btn)
    audio_btn = Button(text="Audio only (MP3)", size_hint_y=None, height=50)
    audio_btn.bind(on_press=lambda inst: nav.start_playlist_download(
        urls, 0, False, audio_only=True, quality_screen=again))
    nav.add(audio_btn)
    nav.add(back_button(nav, to=back))


_CARD_WORK = (0.30, 0.25, 0.08, 1)    # a video being processed
_CARD_FAIL = (0.42, 0.12, 0.12, 1)    # a failed video
_STATE_TEXT = {
    "waiting": "Waiting",
    "listing": "Checking qualities...",
    "downloading": "Downloading...",
    "done": "Ready",
}
_ID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]+)")


def _short_id(url):
    m = _ID_RE.search(url)
    return m.group(1) if m else url


def _counts(items):
    counts = {"waiting": 0, "listing": 0, "downloading": 0, "done": 0, "failed": 0}
    for item in items:
        counts[item["state"]] = counts.get(item["state"], 0) + 1
    return counts


def _summary_text(items, final):
    if not items:
        return "Reading playlist..."
    c = _counts(items)
    total = len(items)
    if final:
        text = f"Finished: {c['done']} of {total} ready"
        if c["failed"]:
            text += f", {c['failed']} failed"
        return text
    busy = c["listing"] + c["downloading"]
    text = f"{c['done']} of {total} ready - {busy} working, {c['waiting']} waiting"
    if c["failed"]:
        text += f", {c['failed']} failed"
    return text


def _item_card(nav, job, idx, item, final):
    """One video: a coloured card with its title and state; Copy (and Retry
    for a failed one) once it has finished."""
    state = item["state"]
    if state == "done":
        color, status = CARD_ON, "Ready"
    elif state == "failed":
        color = _CARD_FAIL
        status = f"Failed ({_short_id(item['url'])}): {item.get('error') or 'unknown error'}"
    elif state in ("listing", "downloading"):
        color, status = _CARD_WORK, _STATE_TEXT[state]
    else:
        color, status = CARD, _STATE_TEXT["waiting"]

    inner = content_width() - 2 * dp(8) - dp(16)
    title_line = f"{idx + 1}. {item['title']}"
    text = f"{fa_text(title_line, inner)}\n{status}"
    label_h = wrapped_label_height(text, extra_padding=dp(10), width=inner)
    has_buttons = state in ("done", "failed")
    row = card_box([label_h] + ([SMALL_BTN_H] if has_buttons else []))
    paint_card(row, color)

    label = Label(text=text, size_hint_y=None, height=label_h, halign="left", valign="middle",
                  **fa_font_kwargs(title_line))
    label.text_size = (inner, None)
    row.add_widget(label)

    if has_buttons:
        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=SMALL_BTN_H, spacing=GAP)
        if state == "done":
            copy_btn = Button(text="Copy link")
            copy_btn.bind(on_press=lambda i, v=item["link"]: Clipboard.copy(v or ""))
            buttons.add_widget(copy_btn)
        else:
            copy_btn = Button(text="Copy video link")
            copy_btn.bind(on_press=lambda i, v=item["url"]: Clipboard.copy(v))
            buttons.add_widget(copy_btn)
            if final:
                retry_btn = Button(text="Retry")
                retry_btn.bind(on_press=lambda i, u=item["url"]: nav.retry_playlist_videos(job, [u]))
                buttons.add_widget(retry_btn)
        row.add_widget(buttons)
    return row


def build_report(nav, job):
    """The playlist download's report: every video as a coloured card
    (grey waiting, yellow working, green ready, red failed). While the job
    runs it redraws itself every few seconds from the records the worker
    threads keep up to date; once finished it is the final report with Copy
    / Retry / Recheck buttons."""
    nav.clear()
    final = job.is_done
    # worker status lines have nowhere visible to go here; the summary below
    # already says it all
    nav.set_status_label(Label())

    summary = Label(text="", size_hint_y=None, height=line_height(2) + 12, halign="center", valign="middle")
    summary.text_size = (content_width(), None)
    nav.add(summary)

    items = job.extra.get("items") or []
    failed = [i for i in items if i["state"] == "failed"]
    done = [i for i in items if i["state"] == "done"]

    if final:
        if done:
            all_btn = Button(text=f"Copy all links ({len(done)})", size_hint_y=None, height=BTN_H)
            all_btn.bind(on_press=lambda i: Clipboard.copy("\n".join(x["link"] for x in done if x["link"])))
            nav.add(all_btn)
        if failed:
            retry_btn = Button(text=f"Retry failed ({len(failed)})", size_hint_y=None, height=BTN_H)
            retry_btn.bind(on_press=lambda i: nav.retry_playlist_videos(job, [x["url"] for x in failed]))
            nav.add(retry_btn)
            if any(x.get("run_id") for x in failed):
                recheck_btn = Button(text="Recheck failed", size_hint_y=None, height=BTN_H)

                def recheck(inst):
                    inst.text = "Checking releases..."
                    nav.recheck_playlist(job)

                recheck_btn.bind(on_press=recheck)
                nav.add(recheck_btn)
    else:
        pick_quality = job.extra.get("pick_quality")
        if pick_quality:
            quality_btn = Button(text="Pick a different quality", size_hint_y=None, height=BTN_H)
            quality_btn.bind(on_press=lambda i: pick_quality())
            nav.add(quality_btn)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=BTN_H)
        back_btn.bind(on_press=lambda i: nav.back_from_working())
        nav.add(back_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=BTN_H)
        cancel_btn.bind(on_press=lambda i: nav.cancel_job(job))
        nav.add(cancel_btn)

    rows_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    rows_box.height = 0
    rows_box.bind(minimum_height=rows_box.setter("height"))
    nav.add(rows_box)

    if final:
        home_btn = Button(text="Back to home", size_hint_y=None, height=BTN_H)
        home_btn.bind(on_press=lambda i: nav.show_home())
        nav.add(home_btn)

    last = {"sig": None}

    def refresh(*_args):
        current = job.extra.get("items") or []
        summary.text = _summary_text(current, final)
        sig = tuple((i["state"], i.get("error")) for i in current)
        if sig == last["sig"]:
            return
        last["sig"] = sig
        rows_box.clear_widgets()
        for idx, item in enumerate(current):
            rows_box.add_widget(_item_card(nav, job, idx, item, final))

    if final:
        refresh()
    else:
        nav.start_progress_timer(refresh, interval=3)
