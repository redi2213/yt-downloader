"""The Navigator is the Application/Controller layer: it sits between the
Kivy screens (UI) and the services (business logic). It owns the pieces of
state that outlive any single screen - the job manager, the "audio only"
toggle, whether the token field is expanded - and it's responsible for
wiring service callbacks (which may fire from a background thread) back
onto the main thread and into the next screen.

Screens call into the Navigator to move around the app and to kick off
work; the Navigator calls into ``services`` to actually do that work.
Nothing here imports the GitHub API layer directly.
"""
from kivy.clock import Clock
from kivy.uix.button import Button

from core.jobs.job_manager import JobManager
from core.models.job import JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS, JOB_TYPE_PLAYLIST_DOWNLOAD
from services import download_service, playlist_service, upload_service, job_service
from services import history_service, actions_service, run_progress_service
from services import remote_config_service, generic_action_service
from services import auth_service
from screens import common


class Navigator:
    def __init__(self, app):
        self.app = app
        self.job_manager = JobManager()
        self.audio_only = False
        self.show_token_field = False
        # Remote action list loaded for the Share flow (None until loaded).
        self._share_actions = None
        # Timer behind the run progress panel (see start_progress_timer).
        self._progress_event = None
        # True while the home screen is showing (the phone's Back key closes the app there).
        self.on_home = False

    # -- low level content/status plumbing (delegates to the Kivy App) ----
    def clear(self):
        self.stop_progress_timer()
        self.on_home = False
        self.app.clear_content()

    # -- the phone's own Back key ---------------------------------------------
    def _content_widgets(self):
        content = self.app.content
        return list(content) if isinstance(content, list) else list(content.children)

    def go_back(self):
        """Android's Back key: does what this screen's own Back button does,
        so every screen returns to its own parent. On a confirmation screen
        that is Cancel (nothing gets deleted). It never presses a job's Cancel:
        a running job keeps running. Returns True when handled; False on the
        home screen, where the app should close."""
        if getattr(self, "on_home", False):
            return False

        def walk(widgets):
            for w in widgets:
                yield w
                yield from walk(list(getattr(w, "children", [])))

        buttons = [w for w in walk(self._content_widgets())
                   if isinstance(w, Button) and isinstance(w.text, str)]
        back = [b for b in buttons if b.text.startswith("Back")]
        cancel = [b for b in buttons if b.text == "Cancel"]
        target = back[-1] if back else (cancel[-1] if cancel else None)
        if target is None:
            self.show_home()
        else:
            target.dispatch("on_press")
        return True

    # -- auto-refresh for the run progress panel ------------------------------
    def start_progress_timer(self, callback, interval=10):
        """Calls ``callback`` now and then every ``interval`` seconds until the
        screen changes (clear() stops it)."""
        self.stop_progress_timer()
        self._progress_event = Clock.schedule_interval(lambda dt: callback(), interval)
        callback()

    def stop_progress_timer(self):
        event = getattr(self, "_progress_event", None)
        if event is not None:
            event.cancel()
            self._progress_event = None

    def load_run_progress(self, run_id, on_complete):
        run_progress_service.start_load_progress(run_id, on_complete=on_complete)

    def add(self, widget):
        common.fit_height(widget)
        self.app.add_widget_to_content(widget)

    def set_status_label(self, label):
        self.app.status_label = label

    def set_status(self, text):
        Clock.schedule_once(lambda dt: setattr(self.app.status_label, "text", text))

    def schedule(self, fn):
        Clock.schedule_once(lambda dt: fn())

    # -- generic screens ----------------------------------------------------
    def show_home(self):
        from screens import home
        home.build(self)
        self.on_home = True

    def show_working(self, message, job=None, back_text="Back (job keeps running)", extra_buttons=None):
        on_cancel = (lambda: self.cancel_job(job)) if job is not None else None
        common.build_working_screen(
            self,
            message,
            back_text=back_text,
            on_cancel=on_cancel,
            extra_buttons=extra_buttons,
            job=job
        )

    def show_result(self, message, link=None, retry=None, retry_message="Working..."):
        from screens import result
        result.build(
            self,
            message,
            link=link,
            retry=retry,
            retry_message=retry_message
        )

    def show_about(self):
        from screens import about
        about.build(self)

    def show_settings(self):
        from screens import settings
        settings.build(self)

    # -- opening runs on GitHub / running jobs ----------------------------------
    def open_run_on_github(self, run_id):
        """Opens the run's GitHub Actions page (live logs) in the browser."""
        from core import android_actions
        from core.config import run_url
        url = run_url(run_id)
        if not android_actions.open_url(url):
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(url)
            self.set_status("Could not open the browser - link copied")

    def open_job_on_github(self, job):
        if not getattr(job, "run_id", None):
            self.set_status("The run has not started yet - try again in a few seconds")
            return
        self.open_run_on_github(job.run_id)

    def show_running_jobs(self):
        from screens import running_jobs
        running_jobs.build(self)

    def show_job_steps(self, job):
        """Step-by-step view of a job's run (the same screen as Check GitHub
        Actions status); Back returns to the running jobs list."""
        if not getattr(job, "run_id", None):
            self.set_status("The run has not started yet - try again in a few seconds")
            return
        self.show_run_detail({"run_id": job.run_id, "workflow": job.type, "origin": "running"})

    # -- job lifecycle -------------------------------------------------------
    def cancel_job(self, job):
        job_service.cancel(self.job_manager, job)
        self.show_home()

    def reselect_quality(self, job, url, formats):
        """Abandons the in-progress download run (if any) and goes straight
        back to the quality list - no need to re-run list-formats since we
        already have it."""
        job_service.cancel(self.job_manager, job, set_cancel_flag=False)
        self.show_quality_list(url, formats)

    def retry_action(self, retry_callable, message="Working..."):
        """Used by the result screen's "Try again" button: shows a working
        screen (no cancel button, matching the original retry flows) and
        then invokes the retry callable the service attached to the job."""
        self.show_working(message, job=None)
        retry_callable()

    def resume_job_screen(self):
        """Called from the home screen's 'check on last job' button."""
        job = self.job_manager.current_job
        if job is None:
            self.show_home()
            return

        if job.is_done:
            self.route_finished_job(job)
        else:
            self.show_working(f"{job.status}...", job=job)

    def view_job_from_history(self, job):
        self.job_manager.view(job)
        self.resume_job_screen()

    def route_finished_job(self, job):
        """Shows the right screen for a job that has already finished,
        whether it just completed live or is being reopened from history."""
        if not job.ok:
            self.show_result(
                job.error,
                retry=job.retry,
                retry_message=job.extra.get("retry_message", "Working...")
            )
            return

        if job.type == JOB_TYPE_FORMATS:
            self.show_quality_list(job.input, job.result["formats"])

        elif job.type == JOB_TYPE_PLAYLIST_LINKS:
            self.show_playlist_quality_picker(job.result["urls"])

        elif job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            self.show_playlist_results(
                job.result.get("playlist_results", []),
                job.result.get("playlist_errors", [])
            )

        else:  # download, upload
            self.show_result(
                "Ready!",
                link=job.result.get("link")
            )

    def _handle_job_complete(self, job):
        # Only navigate if the user is still looking at this job - they may
        # have gone back home and started a different one in the meantime.
        if self.job_manager.current_job is not job:
            return

        self.route_finished_job(job)

    def _relay_status(self, job, text):
        """Several jobs can run at once. A job's status line may only be
        shown while that job is the one on screen - otherwise its text would
        overwrite another job's screen."""
        if job is not None and self.job_manager.current_job is not job:
            return
        self.set_status(text)

    def _status_and_complete_callbacks(self, job=None, job_ref=None):
        """``job_ref`` is a dict whose "job" entry is filled in later, for
        flows where the service creates the job itself."""
        def on_status(text):
            target = job_ref.get("job") if job_ref is not None else job
            self._relay_status(target, text)
        on_complete = lambda job: self.schedule(
            lambda: self._handle_job_complete(job)
        )
        return on_status, on_complete

    # -- starting jobs --------------------------------------------------------
    def start_fetch_formats(self, url):
        job = download_service.create_fetch_formats_job(
            self.job_manager,
            url
        )
        on_status, on_complete = self._status_and_complete_callbacks(job)
        self.show_working("Fetching qualities...", job=job)
        download_service.run_fetch_formats_job(
            self.job_manager,
            job,
            on_status=on_status,
            on_complete=on_complete
        )

    def start_download(self, url, format_id, audio_only, formats_for_reselect=None):
        job = download_service.create_download_job(
            self.job_manager,
            url,
            formats_for_reselect=formats_for_reselect
        )

        extra_buttons = None

        if formats_for_reselect:
            extra_buttons = [(
                "Pick a different quality",
                lambda: self.reselect_quality(
                    job,
                    url,
                    formats_for_reselect
                ),
            )]

        self.show_working(
            "Starting download...",
            job=job,
            extra_buttons=extra_buttons
        )

        on_status, on_complete = self._status_and_complete_callbacks(job)

        download_service.run_download_job(
            self.job_manager,
            job,
            format_id,
            audio_only,
            on_status=on_status,
            on_complete=on_complete
        )

    def handle_fetch_single(self, url, audio_only):
        url = url.strip()

        if not url:
            self.set_status("Enter a YouTube link")
            return

        if audio_only:
            self.start_download(
                url,
                "bestaudio",
                audio_only=True
            )
        else:
            self.start_fetch_formats(url)

    def start_upload(self, file_url, zip_it, custom_name):
        job = upload_service.create_upload_job(
            self.job_manager,
            file_url
        )

        self.show_working(
            "Starting upload...",
            job=job
        )

        on_status, on_complete = self._status_and_complete_callbacks(job)

        upload_service.run_upload_job(
            self.job_manager,
            job,
            zip_it,
            custom_name,
            on_status=on_status,
            on_complete=on_complete
        )

    def handle_start_upload(self, file_url, zip_it, custom_name):
        file_url = file_url.strip()

        if not file_url:
            self.show_upload_screen()
            return

        self.start_upload(
            file_url,
            zip_it,
            custom_name.strip()
        )

    def start_fetch_playlist(self, url):
        job = playlist_service.create_playlist_links_job(
            self.job_manager,
            url
        )

        self.show_working(
            "Reading playlist...",
            job=job
        )

        on_status, on_complete = self._status_and_complete_callbacks(job)

        playlist_service.run_playlist_links_job(
            self.job_manager,
            job,
            on_status=on_status,
            on_complete=on_complete
        )

    def handle_fetch_playlist(self, url):
        url = url.strip()

        if not url:
            self.set_status("Enter a playlist link")
            return

        self.start_fetch_playlist(url)

    def start_playlist_download(self, urls, target_height, want_hdr):
        job = playlist_service.create_playlist_download_job(
            self.job_manager,
            urls
        )

        extra_buttons = [
            (
                "Pick a different quality",
                lambda: self.show_playlist_quality_picker(urls)
            )
        ]

        self.show_working(
            f"Processing 0/{len(urls)}...",
            job=job,
            extra_buttons=extra_buttons
        )

        on_status, on_complete = self._status_and_complete_callbacks(job)

        playlist_service.run_playlist_download_job(
            self.job_manager,
            job,
            urls,
            target_height,
            want_hdr,
            on_status=on_status,
            on_complete=on_complete
        )

    # -- quality / upload / playlist screens ----------------------------------
    def show_quality_list(self, url, formats):
        from screens import download as download_screen
        download_screen.build_quality_list(
            self,
            url,
            formats
        )

    def show_youtube_download(self, video_url="", playlist_url=""):
        from screens import youtube_download
        youtube_download.build(self, video_url=video_url, playlist_url=playlist_url)

    def start_playlist_from_link(self, playlist_url, target_height, want_hdr, audio_only):
        """Used by the "This is a playlist" quick-quality buttons: reads the
        playlist and starts downloading every video at the chosen quality
        in one step, with no intermediate quality-picker screen."""
        job_ref = {}
        on_status, on_complete = self._status_and_complete_callbacks(job_ref=job_ref)

        job = playlist_service.start_playlist_quick(
            self.job_manager,
            playlist_url,
            target_height,
            want_hdr,
            audio_only=audio_only,
            on_status=on_status,
            on_complete=on_complete
        )
        job_ref["job"] = job

        self.show_working(
            "Reading playlist...",
            job=job
        )

    def show_upload_screen(self, url=""):
        from screens import upload as upload_screen
        upload_screen.build(self, url=url)

    def show_quick_download(self):
        from screens import quick_download
        quick_download.build(self)

    # -- GitHub sign-in (device flow) ----------------------------------------
    def show_github_signin(self):
        from screens import github_signin
        github_signin.build_start(self)

    def start_github_signin(self):
        auth_service.start_device_flow(
            on_status=lambda info: self.schedule(
                lambda: self._on_signin_status(info)
            ),
            on_complete=lambda res: self.schedule(
                lambda: self._on_signin_complete(res)
            )
        )

    def _on_signin_status(self, info):
        if info.get("stage") == "code":
            from screens import github_signin
            github_signin.build_waiting(
                self,
                info["user_code"],
                info["verification_uri"]
            )

    def _on_signin_complete(self, res):
        if res.get("ok"):
            self.show_home()
        else:
            self.show_result(
                res.get("error", "Sign-in failed")
            )

    # -- dynamic/remote-config actions --------------------------------------
    def show_dynamic_actions(self):
        from screens import actions_dynamic
        actions_dynamic.build_loading(self)

        remote_config_service.start_load_actions(
            on_complete=lambda res: self.schedule(
                lambda: self._after_load_actions(res)
            )
        )

    def _after_load_actions(self, res):
        from screens import actions_dynamic
        actions_dynamic.build(
            self,
            res.get("actions", [])
        )

    def show_action_input(self, action, prefill=None, share_url=None):
        from screens import actions_dynamic
        actions_dynamic.build_input(
            self,
            action,
            prefill=prefill,
            share_url=share_url
        )

    # -- links shared into the app (Android Share menu) -----------------------
    def handle_shared_text(self, text):
        """Entry point for text/links shared from other apps. YouTube links
        go straight to the YouTube Download screen; links matching an action's
        ``domains`` (remote config.json) open that action; anything else shows
        a chooser. See core/share_routing.py."""
        from core import share_routing
        quick = share_routing.classify_quick(text)
        if quick:
            if quick["kind"] == "youtube_playlist":
                self.show_youtube_download(playlist_url=quick["url"])
            else:
                self.show_youtube_download(video_url=quick["url"])
            return

        from screens import share_chooser
        share_chooser.build_loading(self)
        remote_config_service.start_load_actions(
            on_complete=lambda res: self.schedule(
                lambda: self._after_share_actions(text, res)
            )
        )

    def _after_share_actions(self, text, res):
        from core import share_routing
        from screens import share_chooser
        actions = res.get("actions", [])
        self._share_actions = actions
        decision = share_routing.classify(text, actions)
        if decision["kind"] == "action":
            self.show_action_input(
                decision["action"],
                prefill=decision["url"],
                share_url=decision["url"]
            )
        else:
            share_chooser.build(self, decision["url"], actions)

    def show_share_chooser(self, url):
        """The manual tool picker for a shared link (also reachable from an
        auto-selected tool via its "Choose another tool" button)."""
        from screens import share_chooser
        if self._share_actions is not None:
            share_chooser.build(self, url, self._share_actions)
            return
        self.handle_shared_text(url)

    def start_dynamic_action(self, action, field_values):
        # field_values: dict of {field_key: value}. Text fields need
        # trimming and a non-empty check; choice fields (already a resolved
        # value, e.g. a format_id string) are left as-is.
        fields = action.get("fields") or [{"key": "input", "type": "text"}]
        cleaned = {}
        for field in fields:
            key = field["key"]
            value = field_values.get(key)
            if field.get("type", "text") == "text":
                value = (value or "").strip()
                if not value:
                    label = field.get("label") or "this field"
                    self.set_status(f"Enter {label.lower()}" if field.get("label") else "Enter a link")
                    return
            else:
                from screens import actions_dynamic
                error = actions_dynamic.validate_custom(field, value)
                if error:
                    self.set_status(error)
                    return
            cleaned[key] = value

        job = generic_action_service.create_action_job(
            self.job_manager,
            action,
            cleaned
        )

        self.show_working(
            "Starting workflow...",
            job=job
        )

        on_status, on_complete = self._status_and_complete_callbacks(job)

        generic_action_service.run_action_job(
            self.job_manager,
            job,
            on_status=on_status,
            on_complete=on_complete
        )

    def show_playlist_quality_picker(self, urls):
        from screens import playlist as playlist_screen
        playlist_screen.build_quality_picker(
            self,
            urls
        )

    def show_playlist_results(self, links, errors=None):
        from screens import playlist as playlist_screen
        playlist_screen.build_results(
            self,
            links,
            errors
        )

    # -- GitHub Actions status -------------------------------------------------
    def show_actions_status(self):
        from screens import actions_status as actions_screen
        actions_screen.build_loading(self)

        actions_service.start_load_recent_runs(
            on_complete=lambda res: self.schedule(
                lambda: self._after_load_runs(res)
            )
        )

    def _after_load_runs(self, res):
        if res.get("ok"):
            self.render_actions_status(res["runs"])
        else:
            self.show_result(res["error"])

    def render_actions_status(self, runs):
        from screens import actions_status as actions_screen
        actions_screen.build(
            self,
            runs
        )

    def back_from_run_detail(self, origin="status"):
        if origin == "running":
            self.show_running_jobs()
        elif isinstance(origin, str) and origin.startswith("job:"):
            # opened from a job's progress panel: return to that job's screen
            job_id = origin[4:]
            jm = self.job_manager
            candidates = list(jm._started) + list(jm.history) + ([jm.current_job] if jm.current_job else [])
            job = next((j for j in candidates if j.job_id == job_id), None)
            if job is not None:
                self.view_job_from_history(job)
            else:
                self.show_running_jobs()
        else:
            self.show_actions_status()

    def show_run_detail(self, run):
        from screens import actions_status as actions_screen
        origin = run.get("origin", "status")

        actions_screen.build_run_detail_loading(
            self,
            run
        )

        actions_service.start_load_run_jobs(
            run["run_id"],
            on_complete=lambda jobs: self.schedule(
                lambda: self.render_run_detail(
                    run["run_id"],
                    jobs,
                    origin
                )
            )
        )

    def render_run_detail(self, run_id, jobs, origin="status"):
        from screens import actions_status as actions_screen
        actions_screen.build_run_detail(
            self,
            run_id,
            jobs,
            origin=origin
        )

    def show_step_log(self, run_id, job_id, step_number, origin="status"):
        """The last lines of one step's log. Refresh (at the bottom) reloads
        both the step's status and its log."""
        from screens import actions_status as actions_screen
        actions_screen.build_step_loading(self)
        run_progress_service.start_load_step_view(
            run_id,
            job_id,
            step_number,
            on_complete=lambda res: self.schedule(
                lambda: actions_screen.build_step_log(
                    self, run_id, job_id, step_number, res, origin
                )
            )
        )

    # -- job history -------------------------------------------------------
    def show_job_history(self):
        from screens import job_history as job_history_screen
        job_history_screen.build(self)

    # -- live release history + delete/rename/zip -----------------------------
    def show_live_history(self):
        from screens import history as history_screen

        history_screen.build_loading(self)

        history_service.start_load_live_history(
            on_complete=lambda items: self.schedule(
                lambda: self.render_history(items)
            )
        )

    def render_history(self, items):
        from screens import history as history_screen
        history_screen.build(
            self,
            items
        )

    def show_delete_confirm(self, item):
        from screens import history as history_screen
        history_screen.build_delete_confirm(
            self,
            item
        )

    def show_bulk_delete_confirm(self, items, scope="shown"):
        from screens import history as history_screen
        history_screen.build_bulk_delete_confirm(
            self,
            items,
            scope=scope
        )

    def show_rename_prompt(self, item):
        from screens import history as history_screen
        history_screen.build_rename_prompt(
            self,
            item
        )

    def do_delete_release(self, item):
        from screens import history as history_screen

        history_screen.build_deleting(self)

        history_service.start_delete_release(
            item,
            on_complete=lambda res: self.schedule(
                lambda: self._after_release_action(res)
            )
        )

    def do_bulk_delete(self, items, scope="shown"):
        from screens import history as history_screen

        history_screen.build_bulk_deleting(
            self,
            len(items)
        )

        history_service.start_bulk_delete_releases(
            items,
            on_status=lambda text: self.set_status(text),
            on_complete=lambda res: self.schedule(
                lambda: (self.show_live_history() if scope == "selected"
                         else self.show_job_history())
            )
        )

    def do_rename_release(self, item, new_name):
        if not new_name or new_name == item["title"]:
            self.show_job_history()
            return

        from screens import history as history_screen

        history_screen.build_renaming(self)

        history_service.start_rename_release(
            item,
            new_name,
            on_complete=lambda res: self.schedule(
                lambda: self._after_release_action(res)
            )
        )

    def start_zip_release(self, item):
        self.show_working(
            f"Zipping:\n{item['title']}...",
            job=None
        )

        history_service.start_zip_release(
            item,
            on_complete=lambda res: self.schedule(
                lambda: self._after_release_action(res)
            )
        )

    def _after_release_action(self, res):
        if res.get("ok"):
            self.show_job_history()
        else:
            self.show_result(
                res.get("error")
        )
        
