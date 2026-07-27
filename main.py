import threading
import time
import re
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# GitHub Actions free tier allows ~20 concurrent jobs; stay under that so
# dispatched runs don't queue behind each other.
MAX_PARALLEL_JOBS = 5

settings_store = JsonStore("ytdl_settings.json")

REQUEST_TIMEOUT = 15  # seconds; avoids requests hanging forever on flaky mobile networks

def _build_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session

http = _build_session()

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


class GitHubAuthError(Exception):
    """Raised when the GitHub token is missing, invalid, or lacks permissions."""
    pass


def _check_response(r):
    if r.status_code in (401, 403):
        raise GitHubAuthError(
            "GitHub token is invalid, expired, or missing required permissions."
        )
    r.raise_for_status()


def dispatch_workflow(workflow_file, inputs):
    """Dispatch a workflow and return the UTC timestamp (ISO, second precision)
    just before dispatch, so the caller can reliably find *this* run afterwards
    instead of guessing "the latest run belongs to me"."""
    dispatch_time = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    r = http.post(url, headers=headers(), json={"ref": "main", "inputs": inputs}, timeout=REQUEST_TIMEOUT)
    _check_response(r)
    return dispatch_time


def get_run_id_after(workflow_file, dispatch_time, attempts=10, delay=1.5):
    """Poll for the run created at/after dispatch_time, instead of blindly
    trusting 'most recent run' (which can grab someone else's run if two
    dispatches happen close together)."""
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=5"
    for _ in range(attempts):
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        _check_response(r)
        runs = r.json().get("workflow_runs", [])
        for run in runs:
            created_at = run.get("created_at", "").rstrip("Z")
            if created_at >= dispatch_time:
                return run["id"]
        time.sleep(delay)
    return None


def wait_for_run(run_id, on_status=None, poll_interval=3, stop_event=None):
    """Polls until the run completes. If stop_event is set while waiting,
    returns "cancelled_locally" without cancelling the run on GitHub itself
    (use cancel_run for that)."""
    url = f"{API_BASE}/actions/runs/{run_id}"
    last_status = None
    while True:
        if stop_event is not None and stop_event.is_set():
            return "cancelled_locally"
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        _check_response(r)
        data = r.json()
        status = data["status"]
        if on_status and status != last_status:
            on_status(status)
            last_status = status
        if status == "completed":
            return data["conclusion"]
        time.sleep(poll_interval)


def cancel_run(run_id):
    """Actually cancels the workflow run on GitHub Actions (not just local polling)."""
    url = f"{API_BASE}/actions/runs/{run_id}/cancel"
    r = http.post(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)


def get_run_log_text(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
    jobs = r.json().get("jobs", [])
    if not jobs:
        return ""
    job_id = jobs[0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = http.get(log_url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
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


def get_release_link(run_id, attempts=10, delay=2):
    tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(attempts):
        r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
        if r.status_code in (401, 403):
            raise GitHubAuthError("GitHub token is invalid or lacks permission to read releases.")
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(delay)
    return None


def get_playlist_links(playlist_url):
    dispatch_time = dispatch_workflow("list-playlist.yml", {"playlist_url": playlist_url})
    run_id = get_run_id_after("list-playlist.yml", dispatch_time)
    if run_id is None:
        return []
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        return []
    log_text = get_run_log_text(run_id)
    urls = re.findall(r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+", log_text)
    return list(dict.fromkeys(urls))


def get_live_history():
    url = f"{API_BASE}/releases?per_page=30"
    r = http.get(url, headers=headers(), timeout=REQUEST_TIMEOUT)
    _check_response(r)
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
        # Tracks the most recent single-video job so the home screen can offer
        # "check status" after navigating away, and so quality can be
        # re-picked without re-running list-formats.
        self.current_job = None  # dict: {stage, run_id, video_url, formats, stop_event}
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

        if self.current_job is not None:
            job = self.current_job
            label = "Check on last job" if job["stage"] != "done" else "View last result"
            check_btn = Button(text=label, size_hint_y=None, height=48)
            check_btn.bind(on_press=lambda i: self.resume_job_screen())
            self.add(check_btn)

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
            self.current_job = {"stage": "formats", "run_id": None, "video_url": url,
                                 "result": None, "last_status": "starting"}
            self.show_working_screen("Fetching qualities...")
            threading.Thread(target=self.fetch_formats_thread, args=(url, self.current_job), daemon=True).start()

    def show_working_screen(self, message):
        """Screen shown while a background job runs. Back just navigates to
        home - the job thread keeps running regardless, and writes its result
        into current_job so 'check on last job' can pick it up later."""
        self.clear_content()
        self.status_label = Label(text=message, size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def resume_job_screen(self):
        """Called from the home screen's 'check on last job' button."""
        job = self.current_job
        if job is None:
            self.show_home()
            return
        if job["stage"] == "done":
            result = job["result"]
            if result["ok"]:
                if job.get("kind") == "formats":
                    self.show_quality_list(job["video_url"], result["formats"])
                else:
                    self.show_result("Ready!", link=result["link"])
            else:
                self.show_result(result["error"], retry=result.get("retry"))
        else:
            # Still running - show current status; the same background
            # thread will update current_job when it finishes.
            self.show_working_screen(f"{job.get('last_status', 'Working')}...")

    def fetch_formats_thread(self, url, job):
        try:
            self.set_status("Fetching qualities...")
            dispatch_time = dispatch_workflow("list-formats.yml", {"video_url": url})
            run_id = get_run_id_after("list-formats.yml", dispatch_time)
            job["run_id"] = run_id
            if run_id is None:
                self._complete_job(job, ok=False, error="Could not detect the workflow run. Try again.", kind="formats")
                return

            def on_status(s):
                job["last_status"] = s
                self.set_status(f"{s}...")
            conclusion = wait_for_run(run_id, on_status=on_status)
            if conclusion != "success":
                self._complete_job(job, ok=False, error=f"Could not fetch qualities ({conclusion})", kind="formats")
                return
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            if not formats:
                self._complete_job(job, ok=False, error="No formats found", kind="formats")
                return
            self._complete_job(job, ok=True, formats=formats, kind="formats")
            Clock.schedule_once(lambda dt: self.show_quality_list(url, formats) if self.current_job is job else None)
        except GitHubAuthError:
            self._complete_job(job, ok=False, error="GitHub token invalid or expired. Update it and retry.", kind="formats")
        except Exception as e:
            self._complete_job(job, ok=False, error=f"Error: {str(e)[:60]}", kind="formats")

    def _complete_job(self, job, ok, kind, error=None, formats=None, link=None, retry=None):
        job["stage"] = "done"
        job["kind"] = kind
        job["result"] = {"ok": ok, "error": error, "formats": formats, "link": link, "retry": retry}
        if not ok:
            # If the user is still sitting on the working screen for this job,
            # update it in place; if they navigated home, current_job now
            # reflects the failure so "check on last job" shows it correctly.
            Clock.schedule_once(lambda dt: self.show_result(error, retry=retry) if self.current_job is job else None)

    def show_quality_list(self, url, formats, reselect_only=False):
        self.clear_content()
        self.add(Label(text="Choose quality", size_hint_y=None, height=40))
        for fmt_id, label in formats:
            btn = Button(text=label, size_hint_y=None, height=50)
            btn.bind(on_press=lambda inst, fid=fmt_id: self.start_download(url, fid, audio_only=False, formats_for_reselect=formats))
            self.add(btn)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def start_download(self, url, format_id, audio_only, formats_for_reselect=None):
        self.current_job = {"stage": "download", "run_id": None, "video_url": url,
                             "result": None, "last_status": "starting",
                             "formats": formats_for_reselect}
        job = self.current_job
        self.clear_content()
        self.status_label = Label(text="Starting download...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        if formats_for_reselect:
            reselect_btn = Button(text="Pick a different quality", size_hint_y=None, height=48)
            reselect_btn.bind(on_press=lambda i: self.stop_and_reselect(job, url, formats_for_reselect))
            self.add(reselect_btn)
        threading.Thread(
            target=self.download_thread, args=(url, format_id, audio_only, job), daemon=True
        ).start()

    def stop_and_reselect(self, job, url, formats):
        """Cancels the in-progress download run on GitHub (if one exists yet)
        and goes straight back to the quality list - no need to re-run
        list-formats since we already have it."""
        if job.get("run_id"):
            try:
                cancel_run(job["run_id"])
            except Exception:
                pass  # best-effort; the old run finishing harmlessly is fine
        job["stage"] = "done"
        job["result"] = {"ok": False, "error": "Cancelled by user"}
        self.show_quality_list(url, formats)

    def download_thread(self, url, format_id, audio_only, job):
        try:
            self.set_status("Starting workflow...")
            dispatch_time = dispatch_workflow("download.yml", {
                "video_url": url, "format_id": format_id,
                "audio_only": "true" if audio_only else "false"
            })
            run_id = get_run_id_after("download.yml", dispatch_time)
            job["run_id"] = run_id
            if run_id is None:
                self._complete_job(job, ok=False, kind="download",
                                    error="Could not detect the workflow run. It may still be running on GitHub Actions.")
                return

            def on_status(s):
                job["last_status"] = s
                self.set_status(f"{s}...")
            conclusion = wait_for_run(run_id, on_status=on_status)
            if job["stage"] == "done":
                return  # was cancelled by stop_and_reselect while we were waiting
            if conclusion != "success":
                self._complete_job(job, ok=False, kind="download", error=f"Download failed ({conclusion})")
                return

            self.finish_download(run_id, job)
        except GitHubAuthError:
            self._complete_job(job, ok=False, kind="download",
                                error="GitHub token invalid or expired. Update it and retry.")
        except Exception as e:
            # The GitHub Actions run itself may have already succeeded even if this
            # network call failed (e.g. mobile connection drop) - let the person
            # retry just the "fetch the link" step instead of starting over.
            run_id_for_retry = job.get("run_id")
            if run_id_for_retry:
                self._complete_job(job, ok=False, kind="download",
                                    error=f"Network error while fetching the link: {str(e)[:60]}",
                                    retry=lambda: self.retry_fetch_link(run_id_for_retry, job))
            else:
                self._complete_job(job, ok=False, kind="download", error=f"Error: {str(e)[:60]}")

    def finish_download(self, run_id, job):
        try:
            link = get_release_link(run_id)
        except Exception as e:
            self._complete_job(job, ok=False, kind="download",
                                error=f"Network error while fetching the link: {str(e)[:60]}",
                                retry=lambda: self.retry_fetch_link(run_id, job))
            return
        if link:
            notify("YT Bridge Git", "Link ready!")
            self._complete_job(job, ok=True, kind="download", link=link)
            Clock.schedule_once(lambda dt: self.show_result("Ready!", link=link) if self.current_job is job else None)
        else:
            self._complete_job(job, ok=False, kind="download",
                                error="Could not get link (release may not be ready yet).",
                                retry=lambda: self.retry_fetch_link(run_id, job))

    def retry_fetch_link(self, run_id, job):
        self.clear_content()
        self.status_label = Label(text="Fetching link...", size_hint_y=None, height=60)
        self.add(self.status_label)
        threading.Thread(target=self.finish_download, args=(run_id, job), daemon=True).start()

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
    def process_one_video(self, url, target_height, want_hdr):
        """Runs the full format-pick + download pipeline for a single video.
        Returns (url, link_or_None, error_message_or_None)."""
        try:
            dispatch_time = dispatch_workflow("list-formats.yml", {"video_url": url})
            run_id = get_run_id_after("list-formats.yml", dispatch_time)
            if run_id is None:
                return url, None, "could not detect list-formats run"
            if wait_for_run(run_id) != "success":
                return url, None, "list-formats run failed"
            log_text = get_run_log_text(run_id)
            formats = parse_formats(log_text)
            picked = self.pick_format(formats, target_height, want_hdr)
            if not picked:
                return url, None, "no matching format"
            fmt_id, _label = picked

            dl_dispatch_time = dispatch_workflow(
                "download.yml", {"video_url": url, "format_id": fmt_id, "audio_only": "false"}
            )
            dl_run_id = get_run_id_after("download.yml", dl_dispatch_time)
            if dl_run_id is None:
                return url, None, "could not detect download run"
            conclusion = wait_for_run(dl_run_id)
            if conclusion != "success":
                return url, None, f"download failed ({conclusion})"
            link = get_release_link(dl_run_id)
            if not link:
                return url, None, "no release link produced"
            return url, link, None
        except GitHubAuthError:
            return url, None, "GitHub token invalid or expired"
        except Exception as e:
            return url, None, str(e)[:80]

    def playlist_download_thread(self, urls, target_height, want_hdr):
        results = []
        errors = []
        total = len(urls)
        done_count = 0
        lock = threading.Lock()

        def update_progress():
            nonlocal done_count
            with lock:
                done_count += 1
                self.set_status(f"Processing {done_count}/{total}...")

        # Process multiple videos concurrently instead of one-at-a-time, since
        # each video's work is a separate GitHub Actions run anyway.
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as pool:
            futures = {
                pool.submit(self.process_one_video, url, target_height, want_hdr): url
                for url in urls
            }
            for future in as_completed(futures):
                url, link, error = future.result()
                update_progress()
                if link:
                    results.append(link)
                else:
                    errors.append((url, error))

        if errors:
            notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready, {len(errors)} failed")
        else:
            notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready")
        Clock.schedule_once(lambda dt: self.show_playlist_results(results, errors))

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

    def show_playlist_results(self, links, errors=None):
        errors = errors or []
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

        if errors:
            self.add(Label(text=f"{len(errors)} failed:", size_hint_y=None, height=40))
            for url, reason in errors:
                short_url = url if len(url) <= 45 else url[:42] + "..."
                self.add(Label(
                    text=f"{short_url}\n{reason}",
                    size_hint_y=None, height=44,
                ))

        home_btn = Button(text="Back to home", size_hint_y=None, height=48)
        home_btn.bind(on_press=lambda i: self.show_home())
        self.add(home_btn)

    def show_result(self, message, link=None, retry=None):
        self.clear_content()
        self.add(Label(text=message, size_hint_y=None, height=60))
        if link:
            link_box = TextInput(text=link, readonly=True, multiline=False, size_hint_y=None, height=48)
            self.add(link_box)
            copy_btn = Button(text="Copy link", size_hint_y=None, height=48)
            copy_btn.bind(on_press=lambda i: Clipboard.copy(link))
            self.add(copy_btn)
        if retry:
            retry_btn = Button(text="Try again", size_hint_y=None, height=48)
            retry_btn.bind(on_press=lambda i: retry())
            self.add(retry_btn)
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
            row = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6, padding=(0, 6))

            title_label = Label(
                text=f"{item['date']}\n{item['title']}",
                size_hint_y=None,
                halign="left",
                valign="top",
            )
            # Wrap text within the row's width and size the label to fit however
            # many lines that takes, instead of a fixed height that clips long titles.
            title_label.bind(
                width=lambda inst, w: setattr(inst, "text_size", (w, None)),
                texture_size=lambda inst, size: setattr(inst, "height", size[1]),
            )
            row.add_widget(title_label)

            link_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
            box = TextInput(text=item["link"], readonly=True, multiline=False, size_hint_x=0.7)
            copy_btn = Button(text="Copy", size_hint_x=0.3)
            copy_btn.bind(on_press=lambda i, l=item["link"]: Clipboard.copy(l))
            link_row.add_widget(box)
            link_row.add_widget(copy_btn)
            row.add_widget(link_row)

            # Row height = title height + link row height + padding/spacing, so rows
            # never overlap regardless of how long the title is.
            def _update_row_height(inst, value, row=row, title_label=title_label, link_row=link_row):
                row.height = title_label.height + link_row.height + row.spacing + row.padding[1] * 2
            title_label.bind(height=_update_row_height)
            _update_row_height(None, None)

            self.add(row)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def show_about(self):
        self.clear_content()
        about_text = f"""YT Bridge Git v{APP_VERSION}

Download from YouTube to GitHub

Developer: Mohsen Mah

Telegram: t.me/moh3n2016

Note: files are auto-deleted after 2 days"""
        self.add(Label(text=about_text, size_hint_y=None, height=220))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)


if __name__ == "__main__":
    YTBridgeApp().run()
