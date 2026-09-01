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

from core.jobs.job_manager import JobManager
from core.models.job import JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS, JOB_TYPE_PLAYLIST_DOWNLOAD
from services import download_service, playlist_service, upload_service, job_service
from services import history_service, actions_service
from services import remote_config_service, generic_action_service


class Navigator:
    def __init__(self, app):
        self.app = app
        self.job_manager = JobManager()
        self.audio_only = False
        self.show_token_field = False

    # -- low level content/status plumbing (delegates to the Kivy App) ----
    def clear(self):
        self.app.clear_content()

    def add(self, widget):
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

    def show_working(self, message, job=None, back_text="Back (job keeps running)", extra_buttons=None):
        from screens import common
        on_cancel = (lambda: self.cancel_job(job)) if job is not None else None
        common.build_working_screen(self, message, back_text=back_text,
                                     on_cancel=on_cancel, extra_buttons=extra_buttons)

    def show_result(self, message, link=None, retry=None, retry_message="Working..."):
        from screens import result
        result.build(self, message, link=link, retry=retry, retry_message=retry_message)

    def show_about(self):
        from screens import about
        about.build(self)

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
            self.show_result(job.error, retry=job.retry,
                              retry_message=job.extra.get("retry_message", "Working..."))
            return
        if job.type == JOB_TYPE_FORMATS:
            self.show_quality_list(job.input, job.result["formats"])
        elif job.type == JOB_TYPE_PLAYLIST_LINKS:
            self.show_playlist_quality_picker(job.result["urls"])
        elif job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            self.show_playlist_results(job.result.get("playlist_results", []),
                                        job.result.get("playlist_errors", []))
        else:  # download, upload
            self.show_result("Ready!", link=job.result.get("link"))

    def _handle_job_complete(self, job):
        # Only navigate if the user is still looking at this job - they may
        # have gone back home and started a different one in the meantime.
        if self.job_manager.current_job is not job:
            return
        self.route_finished_job(job)

    def _status_and_complete_callbacks(self):
        on_status = lambda text: self.set_status(text)
        on_complete = lambda job: self.schedule(lambda: self._handle_job_complete(job))
        return on_status, on_complete

    # -- starting jobs --------------------------------------------------------
    def start_fetch_formats(self, url):
        on_status, on_complete = self._status_and_complete_callbacks()
        job = download_service.create_fetch_formats_job(self.job_manager, url)
        self.show_working("Fetching qualities...", job=job)
        download_service.run_fetch_formats_job(self.job_manager, job, on_status=on_status, on_complete=on_complete)

    def start_download(self, url, format_id, audio_only, formats_for_reselect=None):
        job = download_service.create_download_job(self.job_manager, url, formats_for_reselect=formats_for_reselect)
        extra_buttons = None
        if formats_for_reselect:
            extra_buttons = [(
                "Pick a different quality",
                lambda: self.reselect_quality(job, url, formats_for_reselect),
            )]
        self.show_working("Starting download...", job=job, extra_buttons=extra_buttons)
        on_status, on_complete = self._status_and_complete_callbacks()
        download_service.run_download_job(self.job_manager, job, format_id, audio_only,
                                           on_status=on_status, on_complete=on_complete)

    def handle_fetch_single(self, url, audio_only):
        url = url.strip()
        if not url:
            self.set_status("Enter a YouTube link")
            return
        if audio_only:
            self.start_download(url, "bestaudio", audio_only=True)
        else:
            self.start_fetch_formats(url)

    def start_upload(self, file_url, zip_it, custom_name):
        job = upload_service.create_upload_job(self.job_manager, file_url)
        self.show_working("Starting upload...", job=job)
        on_status, on_complete = self._status_and_complete_callbacks()
        upload_service.run_upload_job(self.job_manager, job, zip_it, custom_name,
                                       on_status=on_status, on_complete=on_complete)

    def handle_start_upload(self, file_url, zip_it, custom_name):
        file_url = file_url.strip()
        if not file_url:
            self.show_upload_screen()
            return
        self.start_upload(file_url, zip_it, custom_name.strip())

    def start_fetch_playlist(self, url):
        job = playlist_service.create_playlist_links_job(self.job_manager, url)
        self.show_working("Reading playlist...", job=job)
        on_status, on_complete = self._status_and_complete_callbacks()
        playlist_service.run_playlist_links_job(self.job_manager, job, on_status=on_status, on_complete=on_complete)

    def handle_fetch_playlist(self, url):
        url = url.strip()
        if not url:
            self.set_status("Enter a playlist link")
            return
        self.start_fetch_playlist(url)

    def start_playlist_download(self, urls, target_height, want_hdr):
        job = playlist_service.create_playlist_download_job(self.job_manager, urls)
        extra_buttons = [("Pick a different quality", lambda: self.show_playlist_quality_picker(urls))]
        self.show_working(f"Processing 0/{len(urls)}...", job=job, extra_buttons=extra_buttons)
        on_status, on_complete = self._status_and_complete_callbacks()
        playlist_service.run_playlist_download_job(self.job_manager, job, urls, target_height, want_hdr,
                                                     on_status=on_status, on_complete=on_complete)

    # -- quality / upload / playlist screens ----------------------------------
    def show_quality_list(self, url, formats):
        from screens import download as download_screen
        download_screen.build_quality_list(self, url, formats)

    def show_upload_screen(self):
        from screens import upload as upload_screen
        upload_screen.build(self)

    # -- dynamic/remote-config actions --------------------------------------
    def show_dynamic_actions(self):
        from screens import actions_dynamic
        actions_dynamic.build_loading(self)
        remote_config_service.start_load_actions(
            on_complete=lambda res: self.schedule(lambda: self._after_load_actions(res)))

    def _after_load_actions(self, res):
        from screens import actions_dynamic
        actions_dynamic.build(self, res.get("actions", []))

    def show_action_input(self, action):
        from screens import actions_dynamic
        actions_dynamic.build_input(self, action)

    def start_dynamic_action(self, action, user_input):
        user_input = user_input.strip()
        if not user_input:
            self.set_status("Enter a link")
            return
        job = generic_action_service.create_action_job(self.job_manager, action, user_input)
        self.show_working("Starting workflow...", job=job)
        on_status, on_complete = self._status_and_complete_callbacks()
        generic_action_service.run_action_job(self.job_manager, job, on_status=on_status, on_complete=on_complete)

    def show_playlist_quality_picker(self, urls):
        from screens import playlist as playlist_screen
        playlist_screen.build_quality_picker(self, urls)

    def show_playlist_results(self, links, errors=None):
        from screens import playlist as playlist_screen
        playlist_screen.build_results(self, links, errors)

    # -- GitHub Actions status -------------------------------------------------
    def show_actions_status(self):
        from screens import actions_status as actions_screen
        actions_screen.build_loading(self)
        actions_service.start_load_recent_runs(
            on_complete=lambda res: self.schedule(lambda: self._after_load_runs(res)))

    def _after_load_runs(self, res):
        if res.get("ok"):
            self.render_actions_status(res["runs"])
        else:
            self.show_result(res["error"])

    def render_actions_status(self, runs):
        from screens import actions_status as actions_screen
        actions_screen.build(self, runs)

    def show_run_detail(self, run):
        from screens import actions_status as actions_screen
        actions_screen.build_run_detail_loading(self, run)
        actions_service.start_load_run_steps(
            run["run_id"],
            on_complete=lambda steps: self.schedule(lambda: self.render_run_detail(run["run_id"], steps)))

    def render_run_detail(self, run_id, steps):
        from screens import actions_status as actions_screen
        actions_screen.build_run_detail(self, run_id, steps)

    # -- job history -------------------------------------------------------
    def show_job_history(self):
        from screens import job_history as job_history_screen
        job_history_screen.build(self)

    # -- live release history + delete/rename/zip -----------------------------
    def show_live_history(self):
        from screens import history as history_screen
        history_screen.build_loading(self)
        history_service.start_load_live_history(
            on_complete=lambda items: self.schedule(lambda: self.render_history(items)))

    def render_history(self, items):
        from screens import history as history_screen
        history_screen.build(self, items)

    def show_delete_confirm(self, item):
        from screens import history as history_screen
        history_screen.build_delete_confirm(self, item)

    def show_bulk_delete_confirm(self, items):
        from screens import history as history_screen
        history_screen.build_bulk_delete_confirm(self, items)

    def show_rename_prompt(self, item):
        from screens import history as history_screen
        history_screen.build_rename_prompt(self, item)

    def do_delete_release(self, item):
        from screens import history as history_screen
        history_screen.build_deleting(self)
        history_service.start_delete_release(
            item, on_complete=lambda res: self.schedule(lambda: self._after_release_action(res)))

    def do_bulk_delete(self, items):
        from screens import history as history_screen
        history_screen.build_bulk_deleting(self, len(items))
        history_service.start_bulk_delete_releases(
            items, on_status=lambda text: self.set_status(text),
            on_complete=lambda res: self.schedule(lambda: self.show_job_history()))

    def do_rename_release(self, item, new_name):
        if not new_name or new_name == item["title"]:
            self.show_job_history()
            return
        from screens import history as history_screen
        history_screen.build_renaming(self)
        history_service.start_rename_release(
            item, new_name, on_complete=lambda res: self.schedule(lambda: self._after_release_action(res)))

    def start_zip_release(self, item):
        self.show_working(f"Zipping:\n{item['title']}...", job=None)
        history_service.start_zip_release(
            item, on_complete=lambda res: self.schedule(lambda: self._after_release_action(res)))

    def _after_release_action(self, res):
        if res.get("ok"):
            self.show_job_history()
        else:
            self.show_result(res.get("error"))

