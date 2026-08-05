from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock

from screens.base import BaseScreen


class PlaylistScreen(BaseScreen):

    pass

    def show_playlist_quality_picker(self, urls):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=f"{len(urls)} videos found. Choose quality for ALL:",
                size_hint_y=None,
                height=50
            )
        )

        presets = [
            ("480p", 480, False),
            ("720p", 720, False),
            ("1080p", 1080, False),
            ("2160p", 2160, False),
            ("Best", 99999, False),
            ("Best HDR", 99999, True),
        ]

        for name, height, hdr in presets:
            btn = Button(
                text=name,
                size_hint_y=None,
                height=50
            )

            btn.bind(
                on_press=lambda inst, h=height, hd=hdr:
                self.start_playlist_download(urls, h, hd)
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


    def start_playlist_download(self, urls, target_height, want_hdr):

        app = self.app

        app.current_job = {
            "stage": "playlist_download",
            "run_id": None,
            "video_url": None,
            "result": None,
            "last_status": "starting",
            "cancel_requested": False,
            "urls": urls,
            "total": len(urls)
        }

        job = app.current_job

        self.clear()

        self.status_label = Label(
            text=f"Processing 0/{len(urls)}...",
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

        reselect_btn = Button(
            text="Pick a different quality",
            size_hint_y=None,
            height=48
        )

        reselect_btn.bind(
            on_press=lambda i: self.show_playlist_quality_picker(urls)
        )

        self.add(reselect_btn)

        import threading

        threading.Thread(
            target=self.playlist_download_thread,
            args=(urls, target_height, want_hdr, job),
            daemon=True
        ).start()


    def process_one_video(self, url, target_height, want_hdr):
        app = self.app

        try:
            dispatch_time = app.dispatch_workflow(
                "list-formats.yml",
                {"video_url": url}
            )

            run_id = app.get_run_id_after(
                "list-formats.yml",
                dispatch_time
            )

            if run_id is None:
                return url, None, "could not detect list-formats run"

            conclusion = app.wait_for_run(run_id)

            if conclusion != "success":
                return url, None, f"format fetch failed ({conclusion})"

            log_text = app.get_run_log_text(run_id)

            formats = app.parse_formats(log_text)

            if not formats:
                return url, None, "no formats found"

            chosen = None

            for fmt in formats:
                fmt_id, label, size, codec = fmt

                if str(target_height) in label:
                    chosen = fmt_id
                    break

            if chosen is None:
                chosen = formats[0][0]

            dispatch_time = app.dispatch_workflow(
                "download.yml",
                {
                    "video_url": url,
                    "format_id": chosen,
                    "audio_only": "false"
                }
            )

            run_id = app.get_run_id_after(
                "download.yml",
                dispatch_time
            )

            if run_id is None:
                return url, None, "could not detect download run"

            conclusion = app.wait_for_run(run_id)

            if conclusion != "success":
                return url, None, f"download failed ({conclusion})"

            link = app.get_release_link(run_id)

            if not link:
                return url, None, "no release link"

            return url, link, None

        except Exception as e:
            return url, None, str(e)[:80]


    def playlist_download_thread(self, urls, target_height, want_hdr, job):

        app = self.app

        results = []
        errors = []

        total = len(urls)

        for index, url in enumerate(urls, 1):

            if job.get("cancel_requested"):
                break

            self.set_status(
                f"Processing {index}/{total}..."
            )

            item = self.process_one_video(
                url,
                target_height,
                want_hdr
            )

            if item[1]:
                results.append(item)
            else:
                errors.append(item)

        job["stage"] = "done"
        job["kind"] = "playlist_download"

        job["result"] = {
            "ok": True,
            "error": None,
            "formats": None,
            "link": None,
            "retry": None,
            "playlist_results": results,
            "playlist_errors": errors
        }

        app._record_job_history(job)

        Clock.schedule_once(
            lambda dt:
            self.show_playlist_results(results, errors)
            if app.current_job is job else None
        )

