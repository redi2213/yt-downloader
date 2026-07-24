import threading
import time
import re
import os
import io
import zipfile
import queue
import requests

from kivy.app import App
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.storage.jsonstore import JsonStore
from kivy.clock import Clock

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
APP_VERSION = "1.1"

settings_store = JsonStore("ytdl_settings.json")
history_store = JsonStore("ytdl_history.json")

try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False

# ---- Background queue worker ----
job_queue = queue.Queue()
history_lock = threading.Lock()
worker_running = True


def notify(title, message):
    if HAS_NOTIFY:
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass


def get_token():
    if settings_store.exists("github"):
        return settings_store.get("github")["token"]
    return ""


def save_token(token):
    settings_store.put("github", token=token)


def headers():
    return {
        "Authorization": f"token {get_token()}",
        "Accept": "application/vnd.github+json",
    }


def dispatch_workflow(workflow_file, inputs):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    r = requests.post(url, headers=headers(), json={"ref": "main", "inputs": inputs})
    r.raise_for_status()


def get_latest_run_id(workflow_file):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=1"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    runs = r.json()["workflow_runs"]
    return runs[0]["id"] if runs else None


def wait_for_run(run_id, on_status=None):
    url = f"{API_BASE}/actions/runs/{run_id}"
    while True:
        r = requests.get(url, headers=headers())
        r.raise_for_status()
        data = r.json()
        status = data["status"]
        if on_status:
            on_status(status)
        if status == "completed":
            return data["conclusion"]
        time.sleep(2)


def get_run_log_text(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    job_id = r.json()["jobs"][0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = requests.get(log_url, headers=headers())
    r.raise_for_status()
    return r.text


def parse_formats(log_text):
    results = []
    for line in log_text.splitlines():
        if "video only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts:
            continue
        fmt_id = parts[0]
        m = re.search(r"(\d+p\d*)( HDR)?", clean)
        if not m:
            continue
        label = m.group(0)
        results.append((fmt_id, label))
    return results


def get_release_link(run_id):
    tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(10):
        r = requests.get(url, headers=headers())
        if r.status_code == 200:
            data = r.json()
            assets = data.get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(3)
    return None


def add_history_entry(entry):
    with history_lock:
        items = history_store.getall() if hasattr(history_store, 'getall') else {}
        entries = list(items.values()) if items else []
        entries.insert(0, entry)
        for i, e in enumerate(entries[:50]):
            history_store.put(f"entry_{i}", **e)


def get_history():
    items = history_store.getall() if hasattr(history_store, 'getall') else {}
    entries = list(items.values()) if items else []
    entries.sort(key=lambda x: x.get("time", ""), reverse=True)
    return entries


def background_worker():
    global worker_running
    while worker_running:
        try:
            job = job_queue.get(timeout=1)
        except queue.Empty:
            continue

        url, target_height, want_hdr = job
        try:
            process_download_job(url, target_height, want_hdr)
        except Exception as e:
            pass
        job_queue.task_done()


def process_download_job(url, target_height, want_hdr):
    try:
        dispatch_workflow("list-formats.yml", {"video_url": url})
        time.sleep(2)
        run_id = get_latest_run_id("list-formats.yml")
        wait_for_run(run_id)
        log_text = get_run_log_text(run_id)
        formats = parse_formats(log_text)
        if not formats:
            return

        picked = pick_format(formats, target_height, want_hdr)
        if not picked:
            return
        fmt_id, label = picked

        dispatch_workflow("download.yml", {
            "video_url": url, "format_id": fmt_id, "audio_only": "false"
        })
        time.sleep(2)
        dl_run_id = get_latest_run_id("download.yml")
        wait_for_run(dl_run_id)

        link = get_release_link(dl_run_id)
        if link:
            title = re.sub(r"_\[[^\]]*\]", "", link.split("/")[-1].rsplit(".", 1)[0])
            add_history_entry({
                "time": time.strftime("%Y-%m-%d %H:%M"),
                "title": title,
                "quality": label,
                "mode": "link",
                "source_url": url,
                "result": link,
            })
            notify("YT Bridge Git", f"Ready: {title}")
    except Exception:
        pass


def pick_format(formats, target_height, want_hdr):
    candidates = []
    for fmt_id, label in formats:
        is_hdr = "HDR" in label
        digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
        if not digits:
            continue
        height = int(digits)
        candidates.append((fmt_id, label, height, is_hdr))

    if not candidates:
        return None

    if want_hdr:
        hdr_candidates = [c for c in candidates if c[3]]
        pool = hdr_candidates if hdr_candidates else candidates
    else:
        pool = [c for c in candidates if not c[3]] or candidates

    if target_height >= 99999:
        best = max(pool, key=lambda c: c[2])
        return best[0], best[1]

    pool_sorted = sorted(pool, key=lambda c: abs(c[2] - target_height))
    best = pool_sorted[0]
    return best[0], best[1]


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"
        self.audio_only = False
        self.quality_presets = {
            "480p": (480, False),
            "720p": (720, False),
            "1080p": (1080, False),
            "2160p": (2160, False),
            "Best": (99999, False),
            "Best HDR": (99999, True),
        }

        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", padding=10, spacing=8, size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)

        self.show_home()
        return self.scroll

    def clear_content(self):
        self.content.clear_widgets()

    def add(self, widget):
        self.content.add_widget(widget)

    def show_home(self):
        self.clear_content()

        self.token_input = TextInput(
            text=get_token(), hint_text="GitHub Token", multiline=False,
            size_hint_y=None, height=48
        )
        self.add(self.token_input)

        self.url_input = TextInput(
            hint_text="YouTube link", multiline=False, size_hint_y=None, height=48
        )
        self.add(self.url_input)

        self.audio_toggle = ToggleButton(
            text="Audio only (MP3): OFF", size_hint_y=None, height=48
        )
        self.audio_toggle.bind(on_press=self.toggle_audio)
        self.add(self.audio_toggle)

        self.fetch_btn = Button(text="Get qualities", size_hint_y=None, height=56)
        self.fetch_btn.bind(on_press=self.on_fetch)
        self.add(self.fetch_btn)

        history_btn = Button(text="Download history", size_hint_y=None, height=48)
        history_btn.bind(on_press=lambda i: self.show_history())
        self.add(history_btn)

        about_btn = Button(text="About", size_hint_y=None, height=48)
        about_btn.bind(on_press=lambda i: self.show_about())
        self.add(about_btn)

        self.status_label = Label(text="", size_hint_y=None, height=40)
        self.add(self.status_label)

    def toggle_audio(self, instance):
        self.audio_only = not self.audio_only
        instance.text = f"Audio only (MP3): {'ON' if self.audio_only else 'OFF'}"

    def show_quality_list(self, url, formats):
        self.clear_content()
        self.add(Label(text="Choose quality", size_hint_y=None, height=40))

        for fmt_id, label in formats:
            btn = Button(text=label, size_hint_y=None, height=50)
            btn.bind(on_press=lambda inst, fid=fmt_id: self.show_mode_choice(url, fid))
            self.add(btn)

        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def show_mode_choice(self, url, format_id):
        self.clear_content()
        self.add(Label(text="Download mode?", size_hint_y=None, height=40))

        b1 = Button(text="Download (background)", size_hint_y=None, height=56)
        b1.bind(on_press=lambda i: self.start_background_download(url, format_id))
        self.add(b1)

        b2 = Button(text="Get direct link", size_hint_y=None, height=56)
        b2.bind(on_press=lambda i: self.start_direct_download(url, format_id))
        self.add(b2)

        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

        self.status_label = Label(text="", size_hint_y=None, height=40)
        self.add(self.status_label)

    def show_result(self, message, link=None):
        self.clear_content()
        self.add(Label(text=message, size_hint_y=None, height=80))

        if link:
            link_box = TextInput(text=link, readonly=True, multiline=False,
                                  size_hint_y=None, height=48)
            self.add(link_box)

            copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
            copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
            self.add(copy_btn)

        home_btn = Button(text="Back to home", size_hint_y=None, height=48)
        home_btn.bind(on_press=lambda i: self.show_home())
        self.add(home_btn)

    def show_history(self):
        self.clear_content()
        self.add(Label(text="Download history", size_hint_y=None, height=40))

        items = get_history()
        if not items:
            self.add(Label(text="No downloads yet", size_hint_y=None, height=40))
        for item in items:
            row = TextInput(
                text=f"{item.get('time','')} | {item.get('quality','')}",
                readonly=True, multiline=False, size_hint_y=None, height=48
            )
            self.add(row)

        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def show_about(self):
        self.clear_content()

        about_text = f"""YT Bridge Git v{APP_VERSION}

دانلود از YouTube و آپلود به GitHub
Download from YouTube to GitHub

سازنده: Mohsen Mah
Developer: Mohsen Mah

تلگرام: t.me/moh3n201
Telegram: t.me/moh3n201

این اپ برای دانلود ویدیوهای 
یوتیوب با کیفیت‌های مختلف 
(از جمله HDR) و آپلود آن‌ها 
به GitHub Releases طراحی شده است.

This app downloads YouTube videos
in various qualities (including HDR)
and uploads them to GitHub Releases."""

        self.add(Label(text=about_text, size_hint_y=None, height=300))

        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", text))

    def on_fetch(self, instance):
        save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Enter a YouTube link")
            return
        if self.audio_only:
            Clock.schedule_once(lambda dt: self.show_mode_choice(url, "audio"))
        else:
            threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        try:
            self.set_status("Fetching qualities...")
            dispatch_workflow("list-formats.yml", {"video_url": url})
            time.sleep(2)
            run_id = get_latest_run_id("list-formats.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"Status: {s}"))
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            if not formats:
                self.set_status("No formats found")
                return
            Clock.schedule_once(lambda dt: self.show_quality_list(url, formats))
        except Exception as e:
            self.set_status(f"Error: {str(e)[:50]}")

    def start_background_download(self, url, format_id):
        save_token(self.token_input.text.strip())
        height, hdr = self.quality_presets.get("1080p", (1080, False))
        job_queue.put((url, height, hdr))
        self.show_result("Added to queue!\nDownloading in background...")

    def start_direct_download(self, url, format_id):
        threading.Thread(
            target=self.direct_download_thread,
            args=(url, format_id),
            daemon=True
        ).start()

    def direct_download_thread(self, url, format_id):
        try:
            self.set_status("Starting download...")
            dispatch_workflow("download.yml", {
                "video_url": url, "format_id": format_id, "audio_only": "false"
            })
            time.sleep(2)
            run_id = get_latest_run_id("download.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"Status: {s}"))

            link = get_release_link(run_id)
            if link:
                notify("YT Bridge Git", "Link ready!")
                Clock.schedule_once(lambda dt: self.show_result("Link ready:", link=link))
            else:
                self.set_status("Could not get link")
        except Exception as e:
            self.set_status(f"Error: {str(e)[:50]}")


if __name__ == "__main__":
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()

    app = YTBridgeApp()
    app.run()
