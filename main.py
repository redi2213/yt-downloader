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

from backend.github_api import (
    APP_VERSION,
    get_token, save_token, notify,
    GitHubAuthError,
    dispatch_workflow, get_run_id_after, get_run_id_by_job_id,
    wait_for_run, cancel_run, get_run_log_text, parse_formats,
    get_release_link,
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
        if self.audio_only:
            Clock.schedule_once(lambda dt: self.start_download(url, "bestaudio", audio_only=True))
        else:
            self.current_job = {"stage": "formats", "run_id": None, "video_url": url,
                                 "result": None, "last_status": "starting", "cancel_requested": False}
            self.show_working_screen("Fetching qualities...", job=self.current_job)
            threading.Thread(target=self.fetch_formats_thread, args=(url, self.current_job), daemon=True).start()

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
                    self.show_quality_list(job["video_url"], result["formats"])
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

    def fetch_formats_thread(self, url, job):
        try:
            self.set_status("Fetching qualities...")
            dispatch_time = dispatch_workflow("list-formats.yml", {"video_url": url})
            run_id = get_run_id_after("list-formats.yml", dispatch_time)
            job["run_id"] = run_id
            if job.get("cancel_requested"):
                if run_id:
                    try:
                        cancel_run(run_id)
                    except Exception:
                        pass
                return  # job already marked done by cancel_job_in_progress
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

    def show_quality_list(self, url, formats):
        self.download_screen = DownloadScreen(self)
        self.download_screen.show_quality_list(url, formats)

    def show_playlist_quality_picker(self, urls):
        self.playlist_screen = PlaylistScreen(self)
        self.playlist_screen.show_playlist_quality_picker(urls)

    def show_playlist_results(self, links, errors=None):
        self.playlist_screen = PlaylistScreen(self)
        self.playlist_screen.show_playlist_results(links, errors)

    def show_upload_screen(self):
        self.clear_content()
        self.add(Label(text="Upload a file from a link", size_hint_y=None, height=40))

        self.upload_url_input = TextInput(
            hint_text="Direct file link", multiline=False, size_hint_y=None, height=48
        )
        self.add(self.upload_url_input)

        self.upload_rename_input = TextInput(
            hint_text="New name (optional, leave blank to keep original)",
            multiline=False, size_hint_y=None, height=48
        )
        self.add(self.upload_rename_input)

        self.upload_zip_toggle = ToggleButton(text="Zip before upload: OFF", size_hint_y=None, height=48)
        self.upload_zip_toggle.bind(on_press=self._toggle_upload_zip)
        self.add(self.upload_zip_toggle)

        start_btn = Button(text="Upload", size_hint_y=None, height=56)
        start_btn.bind(on_press=self.on_start_upload)
        self.add(start_btn)

        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def _toggle_upload_zip(self, instance):
        is_on = instance.state == "down"
        instance.text = f"Zip before upload: {'ON' if is_on else 'OFF'}"

    def on_start_upload(self, instance):
        file_url = self.upload_url_input.text.strip()
        if not file_url:
            self.show_upload_screen()
            return
        custom_name = self.upload_rename_input.text.strip()
        zip_it = self.upload_zip_toggle.state == "down"
        self.start_upload(file_url, zip_it, custom_name)

    def start_upload(self, file_url, zip_it, custom_name):
        job_id = uuid.uuid4().hex[:12]
        self.current_job = {"stage": "upload", "run_id": None, "video_url": file_url,
                             "result": None, "last_status": "starting", "job_id": job_id,
                             "cancel_requested": False}
        job = self.current_job
        self.clear_content()
        self.status_label = Label(text="Starting upload...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.cancel_job_in_progress(job))
        self.add(cancel_btn)
        threading.Thread(
            target=self.upload_file_thread, args=(file_url, zip_it, custom_name, job), daemon=True
        ).start()

    def upload_file_thread(self, file_url, zip_it, custom_name, job):
        try:
            self.set_status("Starting workflow...")
            dispatch_workflow("upload-file.yml", {
                "file_url": file_url,
                "zip_it": "true" if zip_it else "false",
                "custom_name": custom_name,
                "job_id": job["job_id"],
            })
            self._find_and_track_upload_run(job)
        except GitHubAuthError:
            self._complete_job(job, ok=False, kind="upload",
                                error="GitHub token invalid or expired. Update it and retry.")
        except Exception as e:
            self._complete_job(job, ok=False, kind="upload", error=f"Error: {str(e)[:60]}")

    def _find_and_track_upload_run(self, job):
        # Large files can take a while for GitHub to register the run under,
        # so search longer, and if we still don't find it, offer a retry
        # instead of a dead end - the workflow may simply still be starting.
        run_id = get_run_id_by_job_id("upload-file.yml", job["job_id"], attempts=40, delay=3)
        job["run_id"] = run_id
        if job.get("cancel_requested"):
            if run_id:
                try:
                    cancel_run(run_id)
                except Exception:
                    pass
            return  # job already marked done by cancel_job_in_progress
        if run_id is None:
            self._complete_job(job, ok=False, kind="upload",
                                error="Could not detect the workflow run yet. It may still be starting on GitHub Actions.",
                                retry=lambda: self._retry_find_upload_run(job))
            return
        self._track_upload_run(run_id, job)

    def _retry_find_upload_run(self, job):
        self.clear_content()
        self.status_label = Label(text="Looking for the workflow run...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        threading.Thread(target=self._find_and_track_upload_run, args=(job,), daemon=True).start()

    def _track_upload_run(self, run_id, job):
        try:
            def on_status(s):
                job["last_status"] = s
                self.set_status(f"{s}...")
            conclusion = wait_for_run(run_id, on_status=on_status)
            if job["stage"] == "done":
                return  # cancelled by the user in the meantime
            if conclusion != "success":
                self._complete_job(job, ok=False, kind="upload", error=f"Upload failed ({conclusion})")
                return

            tag = f"job-{job['job_id']}"
            link = get_release_link(tag=tag)
            if link:
                notify("YT Bridge Git", "Upload link ready!")
                job["stage"] = "done"
                job["kind"] = "upload"
                job["result"] = {"ok": True, "error": None, "formats": None, "link": link, "retry": None}
                self._record_job_history(job)
                Clock.schedule_once(lambda dt: self.show_result("Ready!", link=link))
            else:
                self._complete_job(job, ok=False, kind="upload",
                                    error="Could not get link (release may not be ready yet).",
                                    retry=lambda: self.retry_fetch_upload_link(tag, job))
        except GitHubAuthError:
            self._complete_job(job, ok=False, kind="upload",
                                error="GitHub token invalid or expired. Update it and retry.")
        except Exception as e:
            # The GitHub Actions run itself may have already succeeded even if
            # this network call failed (e.g. mobile connection drop) - offer a
            # retry that just re-fetches the link instead of a dead end.
            tag = f"job-{job['job_id']}"
            self._complete_job(job, ok=False, kind="upload",
                                error=f"Network error: {str(e)[:60]}",
                                retry=lambda: self.retry_fetch_upload_link(tag, job))

    def retry_fetch_upload_link(self, tag, job):
        self.clear_content()
        self.status_label = Label(text="Fetching link...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

        def _retry():
            link = get_release_link(tag=tag)
            if link:
                self._complete_job(job, ok=True, kind="upload", link=link)
                Clock.schedule_once(lambda dt: self.show_result("Ready!", link=link) if self.current_job is job else None)
            else:
                self._complete_job(job, ok=False, kind="upload",
                                    error="Still could not get link.",
                                    retry=lambda: self.retry_fetch_upload_link(tag, job))
        threading.Thread(target=_retry, daemon=True).start()

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
