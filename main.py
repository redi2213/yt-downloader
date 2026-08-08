import threading
import uuid

from kivy.app import App
from kivy.core.window import Window
from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from screens.home import HomeScreen
from screens.result import ResultScreen
from screens.actions import ActionsScreen
from screens.history import HistoryScreen
from screens.about import AboutScreen
from screens.download import DownloadScreen
from screens.playlist import PlaylistScreen
from screens.upload import UploadScreen

from backend.github_api import (
    APP_VERSION,
    get_token, save_token,
    cancel_run,
    get_live_history, delete_release, rename_release_asset,
)


class YTBridgeApp(App):
    def build(self):
        Window.softinput_mode = "below_target"
        self.audio_only = False
        # Tracks the most recent single-video job so the home screen can offer
        # "check status" after navigating away, and so quality can be
        # re-picked without re-running list-formats.
        self.current_job = None  # dict: {stage, run_id, video_url, formats, stop_event}
        self.job_history = []  # list of finished job dicts, most recent first, capped below
        self.scroll = ScrollView()
        self.content = BoxLayout(orientation="vertical", padding=10, spacing=8, size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.scroll.add_widget(self.content)
        self.home_screen = HomeScreen(self)
        self.home_screen.show()
        return self.scroll

    def clear_content(self):
        self.content.clear_widgets()

    def add(self, widget):
        self.content.add_widget(widget)

    def show_home(self):
        self.clear_content()

        saved_token = get_token()
        if saved_token and not getattr(self, "_show_token_field", False):
            self.token_input = None
            update_token_btn = Button(text="Update GitHub token", size_hint_y=None, height=44)
            update_token_btn.bind(on_press=lambda i: self._reveal_token_field())
            self.add(update_token_btn)
        else:
            self.token_input = TextInput(
                text=saved_token, hint_text="GitHub Token", multiline=False,
                size_hint_y=None, height=48
            )
            self.add(self.token_input)
            save_token_btn = Button(text="Save token", size_hint_y=None, height=40)
            save_token_btn.bind(on_press=lambda i: self._save_token_and_refresh())
            self.add(save_token_btn)

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

        upload_btn = Button(text="Upload a file (any link)", size_hint_y=None, height=48)
        upload_btn.bind(on_press=lambda i: self.show_upload_screen())
        self.add(upload_btn)

        history_btn = Button(text="Download history", size_hint_y=None, height=48)
        history_btn.bind(on_press=lambda i: self.show_live_history())
        self.add(history_btn)

        about_btn = Button(text="About", size_hint_y=None, height=48)
        about_btn.bind(on_press=lambda i: AboutScreen(self).show())
        self.add(about_btn)

        if self.current_job is not None:
            job = self.current_job
            label = "Check on last job" if job["stage"] != "done" else "View last result"
            check_btn = Button(text=label, size_hint_y=None, height=48)
            check_btn.bind(on_press=lambda i: self.resume_job_screen())
            self.add(check_btn)

        status_btn = Button(text="Check GitHub Actions status", size_hint_y=None, height=48)
        status_btn.bind(on_press=lambda i: self.show_actions_status())
        self.add(status_btn)

        if self.job_history:
            recent_btn = Button(text=f"Recent jobs ({len(self.job_history)})", size_hint_y=None, height=48)
            recent_btn.bind(on_press=lambda i: self.show_job_history())
            self.add(recent_btn)

        self.status_label = Label(text="", size_hint_y=None, height=40)
        self.add(self.status_label)

    def _reveal_token_field(self):
        self._show_token_field = True
        self.show_home()

    def _save_token_and_refresh(self):
        if self.token_input is not None:
            save_token(self.token_input.text.strip())
        self._show_token_field = False
        self.show_home()

    def toggle_audio(self, instance):
        self.audio_only = not self.audio_only
        instance.text = f"Audio only (MP3): {'ON' if self.audio_only else 'OFF'}"

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.status_label, "text", text))

    def on_fetch_single(self, instance):
        if self.token_input is not None:
            save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Enter a YouTube link")
            return
        self.download_screen = DownloadScreen(self)

        if self.audio_only:
            Clock.schedule_once(
                lambda dt: self.download_screen.start_download(
                    url,
                    "bestaudio",
                    audio_only=True
                )
            )
        else:
            self.current_job = {
                "stage": "formats",
                "run_id": None,
                "video_url": url,
                "result": None,
                "last_status": "starting",
                "cancel_requested": False
            }

            self.download_screen.start_screen(
                self.current_job,
                "Fetching qualities..."
            )

            threading.Thread(
                target=self.download_screen.fetch_formats_thread,
                args=(url, self.current_job),
                daemon=True
            ).start()

    def show_working_screen(self, message, job=None):
        """Screen shown while a background job runs. Back just navigates to
        home - the job thread keeps running regardless, and writes its result
        into current_job so 'check on last job' can pick it up later.
        If job is given, a Cancel button is also shown that stops the
        underlying GitHub Actions run (immediately if we already know its
        run_id, or as soon as it becomes known otherwise)."""
        self.clear_content()
        self.status_label = Label(text=message, size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        if job is not None:
            cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
            cancel_btn.bind(on_press=lambda i: self.cancel_job_in_progress(job))
            self.add(cancel_btn)

    def cancel_job_in_progress(self, job):
        job["cancel_requested"] = True
        if job.get("run_id"):
            try:
                cancel_run(job["run_id"])
            except Exception:
                pass  # best-effort; the run finishing harmlessly is fine
        job["stage"] = "done"
        job["result"] = {"ok": False, "error": "Cancelled by user", "formats": None, "link": None, "retry": None}
        self._record_job_history(job)
        self.show_home()

    def resume_job_screen(self):
        """Called from the home screen's 'check on last job' button."""
        job = self.current_job
        if job is None:
            self.show_home()
            return
        if job["stage"] == "done":
            result = job["result"]
            if result["ok"]:
                kind = job.get("kind")
                if kind == "formats":
                    self.download_screen = DownloadScreen(self)
                    self.download_screen.show_quality_list(
                        job["video_url"],
                        result["formats"]
                    )
                elif kind == "playlist_links":
                    self.show_playlist_quality_picker(result["formats"])
                elif kind == "playlist_download":
                    self.show_playlist_results(result["playlist_results"], result["playlist_errors"])
                else:
                    self.show_result("Ready!", link=result["link"])
            else:
                self.show_result(result["error"], retry=result.get("retry"))
        else:
            # Still running - show current status; the same background
            # thread will update current_job when it finishes.
            self.show_working_screen(f"{job.get('last_status', 'Working')}...", job=job)

    def _complete_job(self, job, ok, kind, error=None, formats=None, link=None, retry=None):
        job["stage"] = "done"
        job["kind"] = kind
        job["result"] = {"ok": ok, "error": error, "formats": formats, "link": link, "retry": retry}
        self._record_job_history(job)
        if not ok:
            # If the user is still sitting on the working screen for this job,
            # update it in place; if they navigated home, current_job now
            # reflects the failure so "check on last job" shows it correctly.
            Clock.schedule_once(lambda dt: self.show_result(error, retry=retry) if self.current_job is job else None)

    def _record_job_history(self, job):
        """Keeps the last few finished jobs (not just the single most recent
        one) so the user can look back at more than one job's outcome."""
        MAX_JOB_HISTORY = 5
        # Avoid double-recording the same job dict if it's already there.
        self.job_history = [j for j in self.job_history if j is not job]
        self.job_history.insert(0, job)
        self.job_history = self.job_history[:MAX_JOB_HISTORY]

    def show_playlist_quality_picker(self, urls):
        self.playlist_screen = PlaylistScreen(self)
        self.playlist_screen.show_playlist_quality_picker(urls)

    def show_playlist_results(self, links, errors=None):
        self.playlist_screen = PlaylistScreen(self)
        self.playlist_screen.show_playlist_results(links, errors)

    def show_upload_screen(self):
        self.upload_screen = UploadScreen(self)
        self.upload_screen.show_upload_screen()

    def on_fetch_playlist(self, instance):
        if self.token_input is not None:
            save_token(self.token_input.text.strip())
        url = self.url_input.text.strip()
        if not url:
            self.set_status("Enter a playlist link")
            return
        self.current_job = {"stage": "playlist_links", "run_id": None, "video_url": url,
                             "result": None, "last_status": "starting", "cancel_requested": False}
        job = self.current_job
        self.show_working_screen("Reading playlist...", job=job)
        self.playlist_screen = PlaylistScreen(self)
        threading.Thread(target=self.playlist_screen.fetch_playlist_thread, args=(url, job), daemon=True).start()

    def show_live_history(self):
        self.history_screen = HistoryScreen(self)
        self.history_screen.show_live()

    def show_about(self):
        self.about_screen = AboutScreen(self)
        self.about_screen.show()

if __name__ == "__main__":
    YTBridgeApp().run()
