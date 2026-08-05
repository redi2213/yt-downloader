import threading
import uuid
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
from kivy.clock import Clock
from screens.home import HomeScreen
from screens.about import AboutScreen

from backend.github_api import (
    APP_VERSION, MAX_PARALLEL_JOBS,
    get_token, save_token, notify,
    GitHubAuthError,
    dispatch_workflow, get_run_id_after, get_run_id_by_job_id,
    wait_for_run, cancel_run, get_run_log_text, parse_formats,
    get_release_link, get_recent_runs, get_run_steps, get_playlist_links,
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
        about_btn.bind(on_press=lambda i: self.show_about())
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

    def show_quality_list(self, url, formats, reselect_only=False):
        self.clear_content()
        self.add(Label(text="Choose quality", size_hint_y=None, height=40))
        for fmt_id, label, size_label, codec_label in formats:
            details = []
            if size_label:
                details.append(f"~{size_label}")
            if codec_label:
                details.append(codec_label)
            btn_text = f"{label} ({', '.join(details)})" if details else label
            btn = Button(text=btn_text, size_hint_y=None, height=50)
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
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.cancel_job_in_progress(job))
        self.add(cancel_btn)
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
        job["result"] = {"ok": False, "error": "Cancelled by user", "formats": None, "link": None, "retry": None}
        self._record_job_history(job)
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
            if job.get("cancel_requested"):
                if run_id:
                    try:
                        cancel_run(run_id)
                    except Exception:
                        pass
                return  # job already marked done by cancel_job_in_progress
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
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        threading.Thread(target=self.finish_download, args=(run_id, job), daemon=True).start()

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
        threading.Thread(target=self.fetch_playlist_thread, args=(url, job), daemon=True).start()

    def fetch_playlist_thread(self, playlist_url, job):
        try:
            self.set_status("Reading playlist...")
            urls = get_playlist_links(playlist_url)
            if job.get("cancel_requested"):
                return  # already marked done by cancel_job_in_progress
            if not urls:
                self._complete_job(job, ok=False, kind="playlist_links", error="No videos found in playlist")
                return
            self._complete_job(job, ok=True, kind="playlist_links", formats=urls)
            Clock.schedule_once(lambda dt: self.show_playlist_quality_picker(urls) if self.current_job is job else None)
        except Exception as e:
            self._complete_job(job, ok=False, kind="playlist_links", error=f"Error: {str(e)[:60]}")

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
        self.current_job = {"stage": "playlist_download", "run_id": None, "video_url": None,
                             "result": None, "last_status": "starting", "cancel_requested": False,
                             "urls": urls, "total": len(urls)}
        job = self.current_job
        self.clear_content()
        self.status_label = Label(text=f"Processing 0/{len(urls)}...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.cancel_job_in_progress(job))
        self.add(cancel_btn)
        reselect_btn = Button(text="Pick a different quality", size_hint_y=None, height=48)
        reselect_btn.bind(on_press=lambda i: self.show_playlist_quality_picker(urls))
        self.add(reselect_btn)
        threading.Thread(
            target=self.playlist_download_thread, args=(urls, target_height, want_hdr, job), daemon=True
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

    def playlist_download_thread(self, urls, target_height, want_hdr, job):
        results = []
        errors = []
        total = len(urls)
        done_count = 0
        lock = threading.Lock()

        def update_progress():
            nonlocal done_count
            with lock:
                done_count += 1
                job["last_status"] = f"Processing {done_count}/{total}"
                self.set_status(f"Processing {done_count}/{total}...")

        # Process multiple videos concurrently instead of one-at-a-time, since
        # each video's work is a separate GitHub Actions run anyway.
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as pool:
            futures = {
                pool.submit(self.process_one_video, url, target_height, want_hdr): url
                for url in urls
            }
            for future in as_completed(futures):
                if job.get("cancel_requested"):
                    for f in futures:
                        f.cancel()
                    return  # already marked done by cancel_job_in_progress
                url, link, error = future.result()
                update_progress()
                if link:
                    results.append(link)
                else:
                    errors.append((url, error))

        if job.get("cancel_requested"):
            return

        if errors:
            notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready, {len(errors)} failed")
        else:
            notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready")
        job["stage"] = "done"
        job["kind"] = "playlist_download"
        job["result"] = {"ok": True, "error": None, "formats": None, "link": None,
                          "retry": None, "playlist_results": results, "playlist_errors": errors}
        self._record_job_history(job)
        Clock.schedule_once(lambda dt: self.show_playlist_results(results, errors) if self.current_job is job else None)

    def pick_format(self, formats, target_height, want_hdr):
        candidates = []
        for fmt_id, label, _size, _codec in formats:
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

    def show_actions_status(self):
        self.clear_content()
        self.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
        self.add(Label(text="Loading...", size_hint_y=None, height=40))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        threading.Thread(target=self.load_actions_status_thread, daemon=True).start()

    def load_actions_status_thread(self):
        try:
            runs = get_recent_runs()
            Clock.schedule_once(lambda dt: self.render_actions_status(runs))
        except GitHubAuthError:
            Clock.schedule_once(lambda dt: self.show_result(
                "GitHub token invalid or expired. Update it and retry."))
        except Exception as e:
            Clock.schedule_once(lambda dt: self.show_result(f"Could not fetch status: {str(e)[:60]}"))

    def render_actions_status(self, runs):
        self.clear_content()
        self.add(Label(text="Recent GitHub Actions runs", size_hint_y=None, height=40))
        if not runs:
            self.add(Label(text="No runs found", size_hint_y=None, height=40))
        content_width = Window.width - 20
        chars_per_line = max(10, int(content_width / 15))
        for run in runs:
            status = run["status"]
            if status == "completed":
                status_text = run["conclusion"] or "unknown"
            else:
                status_text = status
            row_text = f"{run['created_at']}  [{run['workflow']}]\n{status_text}"
            explicit_lines = row_text.count("\n") + 1
            wrapped_lines = sum(
                max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                for line in row_text.split("\n")
            )
            row_height = max(explicit_lines, wrapped_lines) * 40 + 20
            row_btn = Button(
                text=row_text, size_hint_y=None, height=row_height,
                halign="left", valign="top",
            )
            row_btn.text_size = (content_width, None)
            row_btn.bind(on_press=lambda inst, r=run: self.show_run_detail(r))
            self.add(row_btn)
        refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
        refresh_btn.bind(on_press=lambda i: self.show_actions_status())
        self.add(refresh_btn)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def show_run_detail(self, run):
        self.clear_content()
        self.add(Label(text=f"[{run['workflow']}]\nrun #{run['run_id']}", size_hint_y=None, height=60))
        self.add(Label(text="Loading steps...", size_hint_y=None, height=40))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_actions_status())
        self.add(back_btn)
        threading.Thread(target=self._load_run_detail_thread, args=(run["run_id"],), daemon=True).start()

    def _load_run_detail_thread(self, run_id):
        try:
            steps = get_run_steps(run_id)
        except Exception:
            steps = None
        Clock.schedule_once(lambda dt: self.render_run_detail(run_id, steps))

    def render_run_detail(self, run_id, steps):
        self.clear_content()
        self.add(Label(text=f"Run #{run_id}", size_hint_y=None, height=40))
        content_width = Window.width - 20
        chars_per_line = max(10, int(content_width / 15))
        if not steps:
            self.add(Label(text="Could not load steps", size_hint_y=None, height=40))
        else:
            for step in steps:
                name = step.get("name", "?")
                status = step.get("status", "?")
                conclusion = step.get("conclusion") or status
                text = f"{name}\n{conclusion}"
                explicit_lines = text.count("\n") + 1
                wrapped_lines = sum(
                    max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                    for line in text.split("\n")
                )
                h = max(explicit_lines, wrapped_lines) * 40 + 20
                lbl = Label(text=text, size_hint_y=None, height=h, halign="left", valign="top")
                lbl.text_size = (content_width, None)
                self.add(lbl)
        refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
        refresh_btn.bind(on_press=lambda i: self.show_run_detail({"run_id": run_id, "workflow": ""}))
        self.add(refresh_btn)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_actions_status())
        self.add(back_btn)

    def show_job_history(self):
        self.clear_content()
        self.add(Label(text=f"Recent jobs ({len(self.job_history)})", size_hint_y=None, height=40))
        if not self.job_history:
            self.add(Label(text="No jobs yet", size_hint_y=None, height=40))
        for job in self.job_history:
            kind = job.get("kind", "?")
            result = job.get("result") or {}
            if result.get("ok"):
                if kind == "playlist_download":
                    n_ok = len(result.get("playlist_results") or [])
                    n_err = len(result.get("playlist_errors") or [])
                    outcome = f"{n_ok} ready, {n_err} failed"
                elif kind == "formats" or kind == "playlist_links":
                    outcome = "Ready to pick quality"
                else:
                    outcome = "Ready"
            else:
                outcome = result.get("error", "Unknown error")
            label_text = job.get("video_url") or "(upload)"
            if len(label_text) > 45:
                label_text = label_text[:42] + "..."
            content_width = Window.width - 20
            chars_per_line = max(10, int(content_width / 15))
            kind_text = f"[{kind}] {label_text}"
            kind_lines = max(1, (len(kind_text) + chars_per_line - 1) // chars_per_line)
            kind_height = kind_lines * 40 + 12
            outcome_lines = max(1, (len(outcome) + chars_per_line - 1) // chars_per_line)
            outcome_height = outcome_lines * 40 + 12
            row_height = kind_height + outcome_height + 40 + 6
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=row_height, spacing=2, padding=(0, 4))
            kind_label = Label(text=kind_text, size_hint_y=None, height=kind_height,
                                halign="left", valign="top", text_size=(content_width, None))
            outcome_label = Label(text=outcome, size_hint_y=None, height=outcome_height,
                                   halign="left", valign="top", text_size=(content_width, None))
            row.add_widget(kind_label)
            row.add_widget(outcome_label)
            view_btn = Button(text="View", size_hint_y=None, height=40)
            view_btn.bind(on_press=lambda i, j=job: self.view_job_from_history(j))
            row.add_widget(view_btn)
            self.add(row)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def view_job_from_history(self, job):
        self.current_job = job
        self.resume_job_screen()
    def show_live_history(self):
        self.clear_content()
        self.add(Label(text="Loading...", size_hint_y=None, height=40))
        threading.Thread(target=self._load_live_history_thread, daemon=True).start()

    def _load_live_history_thread(self):
        try:
            items = get_live_history()
        except Exception as e:
            items = []
        Clock.schedule_once(lambda dt: self.render_history(items))

    def render_history(self, items):
        self.clear_content()
        self.add(Label(text=f"Download history ({len(items)} found)", size_hint_y=None, height=40))
        if not items:
            self.add(Label(text="No downloads yet", size_hint_y=None, height=40))
        else:
            bulk_delete_btn = Button(text=f"Delete all {len(items)} shown", size_hint_y=None, height=48)
            bulk_delete_btn.bind(on_press=lambda i: self.show_bulk_delete_confirm(items))
            self.add(bulk_delete_btn)
        # The app is portrait-locked and content width is always the window
        # width minus the outer padding (10px each side, set in build()).
        content_width = Window.width - 20
        for item in items:
            size_mb = item.get("size", 0) / (1024 * 1024)
            size_text = f" ({size_mb:.1f} MB)" if size_mb else ""
            title_text = f"{item['date']}\n{item['title']}{size_text}"

            # Estimate wrapped line count up front instead of binding to
            # texture_size - avoids any live layout feedback loop entirely.
            # ~15px average character width at the default font size.
            chars_per_line = max(10, int(content_width / 15))
            explicit_lines = title_text.count("\n") + 1
            wrapped_lines = sum(
                max(1, (len(line) + chars_per_line - 1) // chars_per_line)
                for line in title_text.split("\n")
            )
            title_height = max(explicit_lines, wrapped_lines) * 40 + 12

            row_height = title_height + 44 + 6 + 12  # title + link_row + spacing + padding
            row = BoxLayout(orientation="vertical", size_hint_y=None, height=row_height, spacing=6, padding=(0, 6))

            title_label = Label(
                text=title_text,
                size_hint_y=None,
                height=title_height,
                halign="left",
                valign="top",
                text_size=(content_width, None),
            )
            row.add_widget(title_label)

            link_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
            box = TextInput(text=item["link"], readonly=True, multiline=False, size_hint_x=0.55)
            copy_btn = Button(text="Copy", size_hint_x=0.15)
            copy_btn.bind(on_press=lambda i, l=item["link"]: Clipboard.copy(l))
            rename_btn = Button(text="Rename", size_hint_x=0.15)
            rename_btn.bind(on_press=lambda i, it=item: self.show_rename_prompt(it))
            zip_btn = Button(text="Zip", size_hint_x=0.15)
            zip_btn.bind(on_press=lambda i, it=item: self.start_zip_release(it))
            delete_btn = Button(text="Delete", size_hint_x=0.15)
            delete_btn.bind(on_press=lambda i, it=item: self.show_delete_confirm(it))
            link_row.add_widget(box)
            link_row.add_widget(copy_btn)
            link_row.add_widget(rename_btn)
            link_row.add_widget(zip_btn)
            link_row.add_widget(delete_btn)
            row.add_widget(link_row)

            self.add(row)
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

    def show_delete_confirm(self, item):
        self.clear_content()
        self.add(Label(text=f"Delete this release?\n{item['title']}", size_hint_y=None, height=80))
        confirm_btn = Button(text="Yes, delete", size_hint_y=None, height=48)
        confirm_btn.bind(on_press=lambda i: self.do_delete_release(item))
        self.add(confirm_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.show_job_history())
        self.add(cancel_btn)
    def show_bulk_delete_confirm(self, items):
        self.clear_content()
        self.add(Label(text=f"Delete all {len(items)} releases shown?\nThis cannot be undone.",
                        size_hint_y=None, height=80))
        confirm_btn = Button(text=f"Yes, delete all {len(items)}", size_hint_y=None, height=48)
        confirm_btn.bind(on_press=lambda i: self.do_bulk_delete(items))
        self.add(confirm_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.show_job_history())
        self.add(cancel_btn)

    def do_bulk_delete(self, items):
        self.clear_content()
        self.status_label = Label(text=f"Deleting 0/{len(items)}...", size_hint_y=None, height=60)
        self.add(self.status_label)
        back_btn = Button(text="Back (keeps deleting)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

        def _bulk_delete():
            done = 0
            failed = 0
            for item in items:
                try:
                    delete_release(item["release_id"], item["tag_name"])
                except Exception:
                    failed += 1
                done += 1
                self.set_status(f"Deleting {done}/{len(items)}...")
            notify("YT Bridge Git", f"Deleted {done - failed}/{len(items)} releases")
            Clock.schedule_once(lambda dt: self.show_job_history())
        threading.Thread(target=_bulk_delete, daemon=True).start()

    def do_delete_release(self, item):
        self.clear_content()
        self.add(Label(text="Deleting...", size_hint_y=None, height=60))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

        def _delete():
            try:
                delete_release(item["release_id"], item["tag_name"])
                Clock.schedule_once(lambda dt: self.show_job_history())
            except GitHubAuthError:
                Clock.schedule_once(lambda dt: self.show_result(
                    "GitHub token invalid or expired. Update it and retry."))
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_result(f"Delete failed: {str(e)[:60]}"))
        threading.Thread(target=_delete, daemon=True).start()

    def show_rename_prompt(self, item):
        self.clear_content()
        self.add(Label(text=f"Rename:\n{item['title']}", size_hint_y=None, height=60))
        name_input = TextInput(text=item["title"], multiline=False, size_hint_y=None, height=48)
        self.add(name_input)
        confirm_btn = Button(text="Save name", size_hint_y=None, height=48)
        confirm_btn.bind(on_press=lambda i: self.do_rename_release(item, name_input.text.strip()))
        self.add(confirm_btn)
        cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
        cancel_btn.bind(on_press=lambda i: self.show_job_history())
        self.add(cancel_btn)

    def do_rename_release(self, item, new_name):
        if not new_name or new_name == item["title"]:
            self.show_job_history()
            return
        self.clear_content()
        self.add(Label(text="Renaming...", size_hint_y=None, height=60))
        back_btn = Button(text="Back", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)

        def _rename():
            try:
                rename_release_asset(item["release_id"], item["asset_id"], new_name)
                Clock.schedule_once(lambda dt: self.show_job_history())
            except GitHubAuthError:
                Clock.schedule_once(lambda dt: self.show_result(
                    "GitHub token invalid or expired. Update it and retry."))
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_result(f"Rename failed: {str(e)[:60]}"))
        threading.Thread(target=_rename, daemon=True).start()

    def start_zip_release(self, item):
        self.clear_content()
        self.add(Label(text=f"Zipping:\n{item['title']}...", size_hint_y=None, height=60))
        back_btn = Button(text="Back (job keeps running)", size_hint_y=None, height=48)
        back_btn.bind(on_press=lambda i: self.show_home())
        self.add(back_btn)
        job_id = uuid.uuid4().hex[:12]

        def _zip():
            try:
                dispatch_workflow("zip-release.yml", {
                    "asset_url": item["link"],
                    "asset_name": item["title"],
                    "release_id": str(item["release_id"]),
                    "job_id": job_id,
                })
                run_id = get_run_id_by_job_id("zip-release.yml", job_id)
                if run_id is None:
                    Clock.schedule_once(lambda dt: self.show_result(
                        "Could not detect the zip workflow run. It may still be running."))
                    return
                conclusion = wait_for_run(run_id)
                if conclusion != "success":
                    Clock.schedule_once(lambda dt: self.show_result(f"Zip failed ({conclusion})"))
                    return
                Clock.schedule_once(lambda dt: self.show_job_history())
            except GitHubAuthError:
                Clock.schedule_once(lambda dt: self.show_result(
                    "GitHub token invalid or expired. Update it and retry."))
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_result(f"Zip failed: {str(e)[:60]}"))
        threading.Thread(target=_zip, daemon=True).start()

    def show_about(self):
        self.about_screen = AboutScreen(self)
        self.about_screen.show()

if __name__ == "__main__":
    YTBridgeApp().run()
