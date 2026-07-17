import threading
import time
import re
import os
import io
import zipfile
import requests

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.storage.jsonstore import JsonStore
from kivy.clock import Clock

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

store = JsonStore("ytdl_settings.json")


def get_token():
    if store.exists("github"):
        return store.get("github")["token"]
    return ""


def save_token(token):
    store.put("github", token=token)


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
        time.sleep(4)


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


def get_artifact_and_download(run_id, dest_dir):
    url = f"{API_BASE}/actions/runs/{run_id}/artifacts"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    artifacts = r.json()["artifacts"]
    if not artifacts:
        return None
    download_url = artifacts[0]["archive_download_url"]
    r = requests.get(download_url, headers=headers())
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    z.extractall(dest_dir)
    for name in z.namelist():
        if name.endswith(".mkv"):
            return os.path.join(dest_dir, name)
    return None


class YTDLApp(App):
    def build(self):
        self.root_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self.token_input = TextInput(
            text=get_token(), hint_text="GitHub Token", multiline=False, size_hint_y=None, height=48
        )
        self.root_layout.add_widget(self.token_input)

        self.url_input = TextInput(
            hint_text="لینک یوتیوب", multiline=False, size_hint_y=None, height=48
        )
        self.root_layout.add_widget(self.url_input)

        self.fetch_btn = Button(text="دریافت کیفیت‌ها", size_hint_y=None, height=56)
        self.fetch_btn.bind(on_press=self.on_fetch)
        self.root_layout.add_widget(self.fetch_btn)

        self.status_label = Label(text="", size_hint_y=None, height=40)
        self.root_layout.add_widget(self.status_label)

        self.scroll = ScrollView()
        self.grid = GridLayout(cols=1, size_hint_y=None, spacing=5)
        self.grid.bind(minimum_height=self.grid.setter("height"))
        self.scroll.add_widget(self.grid)
        self.root_layout.add_widget(self.scroll)

        return self.root_layout

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", text))

    def on_fetch(self, instance):
        save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("لینک را وارد کن")
            return
        threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        try:
            self.set_status("در حال اجرای ورک‌فلو...")
            dispatch_workflow("list-formats.yml", {"video_url": url})
            time.sleep(5)
            run_id = get_latest_run_id("list-formats.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"وضعیت: {s}"))
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            Clock.schedule_once(lambda dt: self.show_formats(url, formats))
            self.set_status("آماده - کیفیت را انتخاب کن")
        except Exception as e:
            self.set_status(f"خطا: {e}")

    def show_formats(self, url, formats):
        self.grid.clear_widgets()
        for fmt_id, label in formats:
            btn = Button(text=label, size_hint_y=None, height=50)
            btn.bind(on_press=lambda inst, fid=fmt_id, lb=label: self.on_choose(url, fid, lb))
            self.grid.add_widget(btn)

    def on_choose(self, url, fmt_id, label):
        threading.Thread(target=self.download_thread, args=(url, fmt_id, label), daemon=True).start()

    def download_thread(self, url, fmt_id, label):
        try:
            self.set_status(f"در حال دانلود {label}...")
            dispatch_workflow("download.yml", {"video_url": url, "format_id": fmt_id})
            time.sleep(5)
            run_id = get_latest_run_id("download.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"وضعیت دانلود: {s}"))
            dest_dir = self.user_data_dir
            path = get_artifact_and_download(run_id, dest_dir)
            if path:
                self.set_status(f"آماده شد: {path}")
            else:
                self.set_status("فایل نهایی پیدا نشد")
        except Exception as e:
            self.set_status(f"خطا: {e}")


if __name__ == "__main__":
    YTDLApp().run()
