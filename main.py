import threading
import time
import re
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
from kivy.storage.jsonstore import JsonStore
from kivy.clock import Clock

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
APP_VERSION = "1.2"

settings_store = JsonStore("ytdl_settings.json")

try:
    from plyer import notification
    HAS_NOTIFY = True
except Exception:
    HAS_NOTIFY = False


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
    return {"Authorization": f"token {get_token()}", "Accept": "application/vnd.github+json"}


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
        results.append((fmt_id, m.group(0)))
    return results


def get_release_link(run_id):
    tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(10):
        r = requests.get(url, headers=headers())
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(3)
    return None


def get_playlist_links(playlist_url):
    dispatch_workflow("list-playlist.yml", {"playlist_url": playlist_url})
    time.sleep(2)
    run_id = get_latest_run_id("list-playlist.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        return []
    log_text = get_run_log_text(run_id)
    urls = re.findall(r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+", log_text)
    return list(dict.fromkeys(urls))


def get_live_history():
    url = f"{API_BASE}/releases?per_page=30"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    releases = r.json()
    items = []
    for rel in releases:
        if not rel.get("tag_name", "").startswith("run-"):
            continue
        assets = rel.get("assets", [])
        if not assets:
            continue
        items.append({
            "title": assets[0]["name"],
            "link": assets[0]["browser_download_url"],
            "date": rel.get("created_at", "")[:16].replace("T", " "),
        })
    return items


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"
        self.audio_only = False
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
            hint_text="YouTube video or playlist link", multiline=False,
            size_hint_y=None, height=48
        )
        self.add(self.url_input)

        self.audio_toggle = ToggleButton(text="Audio only (MP3): OFF", size_hint_y=None, height=48)
        self.audio_toggle.bind(on_press=self.toggle_audio)
        self.add(self.audio_toggle)

        fetch_btn = Button(text="Get qualities (single video)", size_hint_y=None, height=56)
        fetch_btn.bind(on_press=self.on_fetch_single)
        self.add(fetch_btn)

        playlist_btn = Button(text="This is a playlist", size_hint_y=None, height=48)
        playlist_btn.bind(on_press=self.on_fetch_playlist)
        self.add(playlist_btn)

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

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", text))

    def on_fetch_single(self, instance):
        save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Enter a YouTube link")
            return
        if self.audio_only:
            Clock.schedule_once(lambda dt: self.start_download(url, "bestaudio", audio_only=True))
        else:
            threading.Thread(target=self.fetch_formats_thread, args=(url,), daemon=True).start()

    def fetch_formats_thread(self, url):
        try:
            self.set_status("Fetching qualities...")
            dispatch_workflow("list-formats.yml", {"video_url": url})
            time.sleep(2)
            run_id = get_latest_run_id("list-formats.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"{s}..."))
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            if not formats:
                self.set_status("No formats found")
                return
            Clock.schedule_once(lambda dt: self.show_quality_list(url, formats))
        except Exception as e:
            self.set_status(f"Error: {str(e)[:60]}")

    def show_quality_list(self, url, formats):
        self.clear_content()
        self.add(Label(text="Choose quality", size_hint_y=None, height=40))
        for fmt_id, label in formats:
            btn = Button(text=label, size_hint_y=None, height=50)
            btn.bind(on_press=lambda inst, fid=fmt_id: self.start_download(url, fid, audio_only=False))
            self.add(btn)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def start_download(self, url, format_id, audio_only):
        self.clear_content()
        self.status_label = Label(text="Starting download...", size_hint_y=None, height=60)
        self.add(self.status_label)
        threading.Thread(
            target=self.download_thread, args=(url, format_id, audio_only), daemon=True
        ).start()

    def download_thread(self, url, format_id, audio_only):
        try:
            dispatch_workflow("download.yml", {
                "video_url": url, "format_id": format_id,
                "audio_only": "true" if audio_only else "false"
            })
            time.sleep(2)
            run_id = get_latest_run_id("download.yml")
            wait_for_run(run_id, on_status=lambda s: self.set_status(f"{s}..."))

            link = get_release_link(run_id)
            if link:
                notify("YT Bridge Git", "Link ready!")
                Clock.schedule_once(lambda dt: self.show_result("Ready!", link=link))
            else:
                self.set_status("Could not get link")
        except Exception as e:
            self.set_status(f"Error: {str(e)[:60]}")

    def on_fetch_playlist(self, instance):
        save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Enter a playlist link")
            return
        threading.Thread(target=self.fetch_playlist_thread, args=(url,), daemon=True).start()

    def fetch_playlist_thread(self, playlist_url):
        try:
            self.set_status("Reading playlist...")
            urls = get_playlist_links(playlist_url)
            if not urls:
                self.set_status("No videos found in playlist")
                return
            Clock.schedule_once(lambda dt: self.show_playlist_quality_picker(urls))
        except Exception as e:
            self.set_status(f"Error: {str(e)[:60]}")

    def show_playlist_quality_picker(self, urls):
        self.clear_content()
        self.add(Label(text=f"{len(urls)} videos found. Choose quality for ALL:", size_hint_y=None, height=50))
        presets = [
            ("480p", 480, False), ("720p", 720, False), ("1080p", 1080, False),
            ("2160p", 2160, False), ("Best", 99999, False), ("Best HDR", 99999, True),
        ]
        for name, height, hdr in presets:
            btn = Button(text=name, size_hint_y=None, height=50)
            btn.bind(on_press=lambda inst, h=height, hd=hdr: self.start_playlist_download(urls, h, hd))
            self.add(btn)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def start_playlist_download(self, urls, target_height, want_hdr):
        self.clear_content()
        self.status_label = Label(text=f"Processing 0/{len(urls)}...", size_hint_y=None, height=60)
        self.add(self.status_label)
        threading.Thread(
            target=self.playlist_download_thread, args=(urls, target_height, want_hdr), daemon=True
        ).start()

    def playlist_download_thread(self, urls, target_height, want_hdr):
        results = []
        for i, url in enumerate(urls, 1):
            self.set_status(f"Processing {i}/{len(urls)}: fetching qualities...")
            try:
                dispatch_workflow("list-formats.yml", {"video_url": url})
                time.sleep(2)
                run_id = get_latest_run_id("list-formats.yml")
                if wait_for_run(run_id) != "success":
                    continue
                log_text = get_run_log_text(run_id)
                formats = parse_formats(log_text)
                picked = self.pick_format(formats, target_height, want_hdr)
                if not picked:
                    continue
                fmt_id, label = picked

                self.set_status(f"Processing {i}/{len(urls)}: downloading...")
                dispatch_workflow("download.yml", {"video_url": url, "format_id": fmt_id, "audio_only": "false"})
                time.sleep(2)
                dl_run_id = get_latest_run_id("download.yml")
                if wait_for_run(dl_run_id) != "success":
                    continue
                link = get_release_link(dl_run_id)
                if link:
                    results.append(link)
            except Exception:
                continue

        notify("YT Bridge Git", f"Playlist done: {len(results)}/{len(urls)} ready")
        Clock.schedule_once(lambda dt: self.show_playlist_results(results))

    def pick_format(self, formats, target_height, want_hdr):
        candidates = []
        for fmt_id, label in formats:
            is_hdr = "HDR" in label
            digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
            if not digits:
                continue
            candidates.append((fmt_id, label, int(digits), is_hdr))
        if not candidates:
            return None
        if want_hdr:
            pool = [c for c in candidates if c[3]] or candidates
        else:
            pool = [c for c in candidates if not c[3]] or candidates
        if target_height >= 99999:
            best = max(pool, key=lambda c: c[2])
        else:
            best = sorted(pool, key=lambda c: abs(c[2] - target_height))[0]
        return best[0], best[1]

    def show_playlist_results(self, links):
        self.clear_content()
        self.add(Label(text=f"{len(links)} links ready:", size_hint_y=None, height=40))
        for link in links:
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
            box = TextInput(text=link, readonly=True, multiline=False, size_hint_x=0.7)
            copy_btn = Button(text="Copy", size_hint_x=0.3)
            copy_btn.bind(on_press=lambda i, l=link: Clipboard.copy(l))
            row.add_widget(box)
            row.add_widget(copy_btn)
            self.add(row)
        home_btn = Button(text="Back to home", size_hint_y=None, height=48)
        home_btn.bind(on_press=lambda i: self.show_home())
        self.add(home_btn)

    def show_result(self, message, link=None):
        self.clear_content()
        self.add(Label(text=message, size_hint_y=None, height=60))
        if link:
            link_box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
            self.add(link_box)
            copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
            copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
            self.add(copy_btn)
        home_btn = Button(text="Back to home", size_hint_y=None, height=48)
        home_btn.bind(on_press=lambda i: self.show_home())
        self.add(home_btn)

    def show_history(self):
        self.clear_content()
        self.add(Label(text="Download history (live from GitHub)", size_hint_y=None, height=40))
        threading.Thread(target=self.load_history_thread, daemon=True).start()
        self.add(Label(text="Loading...", size_hint_y=None, height=40))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def load_history_thread(self):
        try:
            items = get_live_history()
            Clock.schedule_once(lambda dt: self.render_history(items))
        except Exception:
            Clock.schedule_once(lambda dt: self.render_history([]))

    def render_history(self, items):
        self.clear_content()
        self.add(Label(text=f"Download history ({len(items)} found)", size_hint_y=None, height=40))
        if not items:
            self.add(Label(text="No downloads yet", size_hint_y=None, height=40))
        for item in items:
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=90, spacing=2)
            title_label = Label(text=f"{item['date']}\n{item['title'][:45]}", size_hint_y=None, height=45)
            row.add_widget(title_label)
            link_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
            box = TextInput(text=item["link"], readonly=True, multiline=False, size_hint_x=0.7)
            copy_btn = Button(text="Copy", size_hint_x=0.3)
            copy_btn.bind(on_press=lambda i, l=item["link"]: Clipboard.copy(l))
            link_row.add_widget(box)
            link_row.add_widget(copy_btn)
            row.add_widget(link_row)
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

نکته: فایل‌ها پس از ۲ روز خودکار پاک می‌شوند
Note: files are auto-deleted after 2 days"""
        self.add(Label(text=about_text, size_hint_y=None, height=280))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)


if __name__ == "__main__":
    YTBridgeApp().run()
