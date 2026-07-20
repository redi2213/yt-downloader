import threading
import time
import re
import os
import io
import zipfile
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

settings_store = JsonStore("ytdl_settings.json")
history_store = JsonStore("ytdl_history.json")

try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False


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
        return os.path.join(dest_dir, name)
    return None


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


def add_history(entry):
    key = str(int(time.time() * 1000))
    history_store.put(key, **entry)


def get_history():
    items = []
    for key in history_store.keys():
        items.append(history_store.get(key))
    items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return items


def notify(title, message):
    if HAS_NOTIFY:
        try:
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass


class YTDLApp(App):
    def build(self):
        Window.softinput_mode = "below_target"

        self.audio_only = False

        self.scroll = ScrollView()
        self.content = BoxLayout(
            orientation="vertical", padding=10, spacing=8,
            size_hint_y=None
        )
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
        self.add(Label(text="How do you want the file?", size_hint_y=None, height=40))

        b1 = Button(text="Download in app", size_hint_y=None, height=56)
        b1.bind(on_press=lambda i: self.start_download(url, format_id, mode="app"))
        self.add(b1)

        b2 = Button(text="Get direct link", size_hint_y=None, height=56)
        b2.bind(on_press=lambda i: self.start_download(url, format_id, mode="link"))
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
                text=f"{item.get('time','')} | {item.get('mode','')} | {item.get('result','')}",
                readonly=True, multiline=False, size_hint_y=None, height=48
            )
            self.add(row)

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
            self.set_status("Requesting qualities...")
            dispatch_workflow("list-formats.yml", {"video_url": url})
            time.sleep(5)
            run_id = get_latest_run_id("list-formats.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"Status: {s}"))
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            if not formats:
                self.set_status("No qualities found. Check the video link or cookies.")
                return
            Clock.schedule_once(lambda dt: self.show_quality_list(url, formats))
        except Exception as e:
            self.set_status(f"Error: {e}")

    def start_download(self, url, format_id, mode):
        threading.Thread(target=self.download_thread, args=(url, format_id, mode), daemon=True).start()

    def download_thread(self, url, format_id, mode):
        try:
            self.set_status("Starting download on GitHub...")
            inputs = {"video_url": url, "format_id": format_id if format_id != "audio" else "bestaudio"}
            inputs["audio_only"] = "true" if format_id == "audio" else "false"
            dispatch_workflow("download.yml", inputs)
            time.sleep(5)
            run_id = get_latest_run_id("download.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"Download status: {s}"))

            if mode == "app":
                dest_dir = self.get_save_dir()
                path = get_artifact_and_download(run_id, dest_dir)
                if path:
                    notify("YT Downloader", "Download complete")
                    add_history({
                        "time": time.strftime("%Y-%m-%d %H:%M"),
                        "mode": "app",
                        "result": path,
                    })
                    Clock.schedule_once(lambda dt: self.show_result(f"Saved to:\n{path}"))
                else:
                    self.set_status("Could not find the final file")
            else:
                link = get_release_link(run_id)
                if link:
                    notify("YT Downloader", "Direct link is ready")
                    add_history({
                        "time": time.strftime("%Y-%m-%d %H:%M"),
                        "mode": "link",
                        "result": link,
                    })
                    Clock.schedule_once(lambda dt: self.show_result("Link ready:", link=link))
                else:
                    self.set_status("Could not get the direct link")
        except Exception as e:
            self.set_status(f"Error: {e}")

    def get_save_dir(self):
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            ext_dir = context.getExternalFilesDir(None)
            return ext_dir.getAbsolutePath()
        except Exception:
            return self.user_data_dir


if __name__ == "__main__":
    YTDLApp().run()
