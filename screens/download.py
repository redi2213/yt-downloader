from kivy.clock import Clock
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.base import BaseScreen


class DownloadScreen(BaseScreen):

    def show_quality_list(self, url, formats):
        self.clear()

        app = self.app

        self.add(
            Label(
                text="Choose quality",
                size_hint_y=None,
                height=40
            )
        )

        for fmt_id, label, size_label, codec_label in formats:
            details = []

            if size_label:
                details.append(f"~{size_label}")

            if codec_label:
                details.append(codec_label)

            btn_text = (
                f"{label} ({', '.join(details)})"
                if details
                else label
            )

            btn = Button(
                text=btn_text,
                size_hint_y=None,
                height=50
            )

            btn.bind(
                on_press=lambda i, fid=fmt_id:
                app.start_download(
                    url,
                    fid,
                    audio_only=False,
                    formats_for_reselect=formats
                )
            )

            self.add(btn)

        back_btn = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda i: app.show_home()
        )

        self.add(back_btn)


    def start_screen(self, job, text="Starting download..."):
        self.clear()

        app = self.app

        self.status_label = Label(
            text=text,
            size_hint_y=None,
            height=60
        )

        self.add(self.status_label)

        back_btn = Button(
            text="Back (job keeps running)",
            size_hint_y=None,
            height=48
        )

        back_btn.bind(
            on_press=lambda i: app.show_home()
        )

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


    def set_status(self, text):
        Clock.schedule_once(
            lambda dt: setattr(
                self.status_label,
                "text",
                text
            )
        )


    def start_download(self, url, format_id, audio_only, formats_for_reselect=None):
        app = self.app

        app.current_job = {
            "stage": "download",
            "run_id": None,
            "video_url": url,
            "result": None,
            "last_status": "starting",
            "formats": formats_for_reselect
        }

        job = app.current_job

        self.start_screen(job, "Starting download...")

        import threading

        threading.Thread(
            target=self.download_thread,
            args=(url, format_id, audio_only, job),
            daemon=True
        ).start()



    def stop_and_reselect(self, job, url, formats):
        app = self.app

        if job.get("run_id"):
            try:
                app.cancel_run(job["run_id"])
            except Exception:
                pass

        job["stage"] = "done"
        job["result"] = {
            "ok": False,
            "error": "Cancelled by user",
            "formats": None,
            "link": None,
            "retry": None
        }

        app._record_job_history(job)

        app.show_quality_list(url, formats)


    def download_thread(self, url, format_id, audio_only, job):
        app = self.app

        try:
            self.set_status("Starting workflow...")

            dispatch_time = app.dispatch_workflow(
                "download.yml",
                {
                    "video_url": url,
                    "format_id": format_id,
                    "audio_only": "true" if audio_only else "false"
                }
            )

            run_id = app.get_run_id_after(
                "download.yml",
                dispatch_time
            )

            job["run_id"] = run_id

            if run_id is None:
                app._complete_job(
                    job,
                    ok=False,
                    kind="download",
                    error="Could not detect workflow run."
                )
                return


            def on_status(s):
                job["last_status"] = s
                self.set_status(f"{s}...")


            conclusion = app.wait_for_run(
                run_id,
                on_status=on_status
            )


            if conclusion != "success":
                app._complete_job(
                    job,
                    ok=False,
                    kind="download",
                    error=f"Download failed ({conclusion})"
                )
                return


            self.finish_download(run_id, job)


        except Exception as e:
            app._complete_job(
                job,
                ok=False,
                kind="download",
                error=f"Error: {str(e)[:60]}"
            )


    def finish_download(self, run_id, job):
        app = self.app

        try:
            link = app.get_release_link(run_id)

        except Exception as e:
            app._complete_job(
                job,
                ok=False,
                kind="download",
                error=f"Network error: {str(e)[:60]}",
                retry=lambda: self.retry_fetch_link(run_id, job)
            )
            return


        if link:
            app.notify(
                "YT Bridge Git",
                "Link ready!"
            )

            app._complete_job(
                job,
                ok=True,
                kind="download",
                link=link
            )

            Clock.schedule_once(
                lambda dt:
                app.show_result(
                    "Ready!",
                    link=link
                )
            )

        else:
            app._complete_job(
                job,
                ok=False,
                kind="download",
                error="Could not get link.",
                retry=lambda:
                self.retry_fetch_link(run_id, job)
            )


    def retry_fetch_link(self, run_id, job):
        self.start_screen(
            job,
            "Fetching link..."
        )

        import threading

        threading.Thread(
            target=self.finish_download,
            args=(run_id, job),
            daemon=True
        ).start()

