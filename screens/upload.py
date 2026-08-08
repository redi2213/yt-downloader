import threading
import uuid

from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from screens.base import BaseScreen

from backend.github_api import (
    GitHubAuthError,
    dispatch_workflow,
    get_run_id_by_job_id,
    cancel_run,
    wait_for_run,
    get_release_link,
    notify,
)


class UploadScreen(BaseScreen):

    def show_upload_screen(self):
        self.clear()

        self.add(
            Label(
                text="Upload a file from a link",
                size_hint_y=None,
                height=40
            )
        )

        self.upload_url_input = TextInput(
            hint_text="Direct file link",
            multiline=False,
            size_hint_y=None,
            height=48
        )
        self.add(self.upload_url_input)

        self.upload_rename_input = TextInput(
            hint_text="New name (optional, leave blank to keep original)",
            multiline=False,
            size_hint_y=None,
            height=48
        )
        self.add(self.upload_rename_input)

        self.upload_zip_toggle = ToggleButton(
            text="Zip before upload: OFF",
            size_hint_y=None,
            height=48
        )
        self.upload_zip_toggle.bind(on_press=self._toggle_upload_zip)
        self.add(self.upload_zip_toggle)

        start_btn = Button(
            text="Upload",
            size_hint_y=None,
            height=56
        )
        start_btn.bind(on_press=self.on_start_upload)
        self.add(start_btn)

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )
        back_btn.bind(on_press=lambda i: self.app.show_home())
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
        app = self.app

        job_id = uuid.uuid4().hex[:12]

        app.current_job = {
            "stage": "upload",
            "run_id": None,
            "video_url": file_url,
            "result": None,
            "last_status": "starting",
            "job_id": job_id,
            "cancel_requested": False,
        }

        job = app.current_job

        self.clear()

        self.status_label = Label(
            text="Starting upload...",
            size_hint_y=None,
            height=60
        )
        self.add(self.status_label)

        back_btn = Button(
            text="Back (job keeps running)",
            size_hint_y=None,
            height=48
        )
        back_btn.bind(on_press=lambda i: app.show_home())
        self.add(back_btn)

        cancel_btn = Button(
            text="Cancel",
            size_hint_y=None,
            height=48
        )
        cancel_btn.bind(
            on_press=lambda i: app.cancel_job_in_progress(job)
        )
        self.add(cancel_btn)

        threading.Thread(
            target=self.upload_file_thread,
            args=(file_url, zip_it, custom_name, job),
            daemon=True
        ).start()

    def upload_file_thread(self, file_url, zip_it, custom_name, job):
        app = self.app

        try:
            app.set_status("Starting workflow...")

            dispatch_workflow(
                "upload-file.yml",
                {
                    "file_url": file_url,
                    "zip_it": "true" if zip_it else "false",
                    "custom_name": custom_name,
                    "job_id": job["job_id"],
                }
            )

            self._find_and_track_upload_run(job)

        except GitHubAuthError:
            app._complete_job(
                job,
                ok=False,
                kind="upload",
                error="GitHub token invalid or expired. Update it and retry."
            )

        except Exception as e:
            app._complete_job(
                job,
                ok=False,
                kind="upload",
                error=f"Error: {str(e)[:60]}"
            )

    def _find_and_track_upload_run(self, job):
        app = self.app

        run_id = get_run_id_by_job_id(
            "upload-file.yml",
            job["job_id"],
            attempts=40,
            delay=3
        )

        job["run_id"] = run_id

        if job.get("cancel_requested"):
            if run_id:
                try:
                    cancel_run(run_id)
                except Exception:
                    pass
            return

        if run_id is None:
            app._complete_job(
                job,
                ok=False,
                kind="upload",
                error=(
                    "Could not detect the workflow run yet. "
                    "It may still be starting on GitHub Actions."
                ),
                retry=lambda: self._retry_find_upload_run(job)
            )
            return

        self._track_upload_run(run_id, job)

    def _retry_find_upload_run(self, job):
        app = self.app

        self.clear()

        self.status_label = Label(
            text="Looking for the workflow run...",
            size_hint_y=None,
            height=60
        )
        self.add(self.status_label)

        back_btn = Button(
            text="Back (job keeps running)",
            size_hint_y=None,
            height=48
        )
        back_btn.bind(on_press=lambda i: app.show_home())
        self.add(back_btn)

        threading.Thread(
            target=self._find_and_track_upload_run,
            args=(job,),
            daemon=True
        ).start()

    def _track_upload_run(self, run_id, job):
        app = self.app

        try:

            def on_status(s):
                job["last_status"] = s
                app.set_status(f"{s}...")

            conclusion = wait_for_run(
                run_id,
                on_status=on_status
            )

            if job["stage"] == "done":
                return

            if conclusion != "success":
                app._complete_job(
                    job,
                    ok=False,
                    kind="upload",
                    error=f"Upload failed ({conclusion})"
                )
                return

            tag = f"job-{job['job_id']}"

            link = get_release_link(tag=tag)

            if link:
                notify(
                    "YT Bridge Git",
                    "Upload link ready!"
                )

                job["stage"] = "done"
                job["kind"] = "upload"
                job["result"] = {
                    "ok": True,
                    "error": None,
                    "formats": None,
                    "link": link,
                    "retry": None
                }

                app._record_job_history(job)

                Clock.schedule_once(
                    lambda dt: app.show_result(
                        "Ready!",
                        link=link
                    )
                )

            else:
                app._complete_job(
                    job,
                    ok=False,
                    kind="upload",
                    error=(
                        "Could not get link "
                        "(release may not be ready yet)."
                    ),
                    retry=lambda: self.retry_fetch_upload_link(
                        tag,
                        job
                    )
                )

        except GitHubAuthError:
            app._complete_job(
                job,
                ok=False,
                kind="upload",
                error="GitHub token invalid or expired. Update it and retry."
            )

        except Exception as e:
            tag = f"job-{job['job_id']}"

            app._complete_job(
                job,
                ok=False,
                kind="upload",
                error=f"Network error: {str(e)[:60]}",
                retry=lambda: self.retry_fetch_upload_link(
                    tag,
                    job
                )
            )

    def retry_fetch_upload_link(self, tag, job):
        app = self.app

        self.clear()

        self.status_label = Label(
            text="Fetching link...",
            size_hint_y=None,
            height=60
        )
        self.add(self.status_label)

        back_btn = Button(
            text="Back (job keeps running)",
            size_hint_y=None,
            height=48
        )
        back_btn.bind(on_press=lambda i: app.show_home())
        self.add(back_btn)

        def _retry():
            link = get_release_link(tag=tag)

            if link:
                app._complete_job(
                    job,
                    ok=True,
                    kind="upload",
                    link=link
                )

                Clock.schedule_once(
                    lambda dt: (
                        app.show_result("Ready!", link=link)
                        if app.current_job is job
                        else None
                    )
                )

            else:
                app._complete_job(
                    job,
                    ok=False,
                    kind="upload",
                    error="Still could not get link.",
                    retry=lambda: self.retry_fetch_upload_link(
                        tag,
                        job
                    )
                )

        threading.Thread(
            target=_retry,
            daemon=True
        ).start()
