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

from core import android_downloads, links as link_tools, playlist_reports
from core.jobs.job_manager import JobManager
from core.models.job import JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS, JOB_TYPE_PLAYLIST_DOWNLOAD
from services import download_service, playlist_service, upload_service, job_service
from services import history_service, actions_service, run_progress_service
from services import remote_config_service, generic_action_service
from services import error_help_service, follow_service, health_service, ntfy_service
from core import follow as follow_core
from api import run_mode_prefs
from services import auth_service, storage_service, file_download_service, runs_service
from screens import common


# Most links one box may start at once (GitHub allows ~20 runs in parallel).
MAX_LINKS_AT_ONCE = 20

# Jobs whose single output file gets the link + share + download screen.
RELEASE_FILE_KINDS = {"backup_project": "backup", "build_apk": "apk"}


class Navigator:
    def __init__(self, app):
        self.app = app
        self.job_manager = JobManager()
        self.audio_only = False
        self.show_token_field = False
        self.show_filimo_field = False
        # Remote action list loaded for the Share flow (None until loaded).
        self._share_actions = None
        # Timer behind the run progress panel (see start_progress_timer).
        self._progress_event = None
        # True while the home screen is showing (the phone's Back key closes the app there).
        self.on_home = False
        # Rebuilds the last menu-type screen the user was on. A job's "Back"
        # button returns there (see back_from_working).
        self._last_menu = None
        # False while the app is in the background. Kivy's clock is stopped then, so anything that
        # must happen for the user while they are away is started from a worker thread (see
        # _auto_after_finish), never from a scheduled callback.
        self.app_active = True

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

        def _name(b):   # the English text, also when the screen is shown in Persian
            return getattr(b, "_ytb_src", None) or b.text

        back = [b for b in buttons if _name(b).startswith("Back")]
        cancel = [b for b in buttons if _name(b) == "Cancel"]
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

    def remember(self, rebuild):
        """Called by every menu-type screen opener: ``rebuild`` re-opens that
        screen. The working screen's Back button uses it to return to where
        the job was started, instead of always jumping to the home menu."""
        self._last_menu = rebuild

    def back_from_working(self):
        rebuild = self._last_menu
        if rebuild is None:
            self.show_home()
        else:
            rebuild()

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
        self.remember(None)
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

    def show_result(self, message, link=None, retry=None, retry_message="Working...", extra_buttons=None,
                    links=None, arvan_links=None, storage_warn=None, run_id=None, category=None,
                    quality_label: str = "", quality_meta: dict = None, on_redownload=None):
        from screens import result
        result.build(
            self,
            message,
            link=link,
            retry=retry,
            retry_message=retry_message,
            extra_buttons=extra_buttons,
            links=links,
            arvan_links=arvan_links,
            storage_warn=storage_warn,
            run_id=run_id,
            category=category,
            quality_label=quality_label,
            quality_meta=quality_meta,
            on_redownload=on_redownload,
        )

    def show_about(self):
        from screens import about
        about.build(self)

    def show_settings(self):
        from screens import settings
        self.remember(self.show_settings)
        settings.build(self)

    def show_downloads(self):
        """What is saving now (Pause / Resume / Stop) and the saved files."""
        from screens import downloads
        self.remember(self.show_downloads)
        downloads.build(self)

    def cycle_download_segments(self):
        from api import download_manager_prefs
        download_manager_prefs.cycle_segments()
        self.show_settings_section("downloads")

    def cycle_download_parallel(self):
        from api import download_manager_prefs
        download_manager_prefs.cycle_parallel()
        self.show_settings_section("downloads")

    def toggle_download_preallocate(self):
        from api import download_manager_prefs
        download_manager_prefs.toggle_preallocate()
        self.show_settings_section("downloads")

    def show_settings_section(self, section):
        """One group of Settings (downloads, notifications, account, tools)."""
        from screens import settings
        self.remember(lambda: self.show_settings_section(section))
        settings.build_section(self, section)

    # -- Settings > Appearance and language ------------------------------------
    def show_appearance(self):
        from screens import appearance
        self.remember(self.show_appearance)
        appearance.build_menu(self)

    def show_appearance_language(self):
        from screens import appearance
        self.remember(self.show_appearance_language)
        appearance.build_language(self)

    def show_appearance_theme(self):
        from screens import appearance
        self.remember(self.show_appearance_theme)
        appearance.build_theme(self)

    def show_appearance_font(self):
        from screens import appearance
        self.remember(self.show_appearance_font)
        appearance.build_font(self)

    # -- Settings > Downloads: the folder files are saved in --------------------
    def pick_save_folder(self):
        from core import android_files
        from api import download_folder_prefs

        def chosen(uri, label):
            download_folder_prefs.set_tree(uri, label)
            self.show_settings_section("downloads")

        def failed(text):
            self.set_status(text)

        android_files.pick_folder(chosen, failed)

    def reset_save_folder(self):
        from api import download_folder_prefs
        download_folder_prefs.clear()
        self.show_settings_section("downloads")

    def toggle_save_subfolders(self):
        from api import download_folder_prefs
        download_folder_prefs.set_subfolders(not download_folder_prefs.subfolders())
        self.show_settings_section("downloads")

    # -- storage: GitHub / Arvan Cloud ---------------------------------------
    def storage_mode(self):
        return storage_service.get_mode()

    def storage_mode_label(self):
        return storage_service.mode_label()

    def run_mode_label(self):
        return run_mode_prefs.label()

    def run_mode_other_side(self):
        """\"phone\" or \"github\": what the per-tool exception buttons offer."""
        return run_mode_prefs.other_side()

    def cycle_run_mode(self):
        """Settings button: auto -> github -> phone -> auto."""
        run_mode_prefs.set_mode(run_mode_prefs.next_mode())
        self.show_settings_section("downloads")

    def cycle_storage_mode(self):
        """Settings button: github -> arvan -> both -> github."""
        storage_service.cycle_mode()
        self.show_settings_section("downloads")

    def set_storage_mode(self, mode):
        storage_service.set_mode(mode)
        self.show_storage()

    def set_active_bucket(self, bucket_id):
        storage_service.set_active_bucket(bucket_id)
        self.show_storage()

    def show_storage(self):
        from screens import storage
        self.remember(self.show_storage)
        storage.build(self, None)
        storage_service.start_load_buckets(
            on_complete=lambda res: self.schedule(lambda: self._render_storage(res)))

    def _render_storage(self, res):
        from screens import storage
        storage.build(self, res)

    def show_add_bucket(self):
        from screens import storage
        self.remember(self.show_add_bucket)
        storage.build_add(self)

    def start_add_bucket(self, access_key, secret_key, bucket, endpoint, quota_gb):
        self.show_working("Saving the bucket keys...", job=None)
        storage_service.start_add_bucket(
            access_key, secret_key, bucket, endpoint, quota_gb,
            on_complete=lambda res: self.schedule(lambda: self._after_bucket_change(res, "Bucket saved")))

    def show_remove_bucket_confirm(self, bucket):
        from screens import storage
        storage.build_remove_confirm(self, bucket)

    def start_remove_bucket(self, bucket_id):
        self.show_working("Removing the bucket...", job=None)
        storage_service.start_remove_bucket(
            bucket_id,
            on_complete=lambda res: self.schedule(lambda: self._after_bucket_change(res, "Bucket removed")))

    def _after_bucket_change(self, res, ok_text):
        if res.get("ok"):
            self.show_storage()
            self.set_status(ok_text)
        else:
            self.show_result(res.get("error", "Failed"))

    def show_storage_info(self):
        from screens import storage
        self.show_working("Reading the Arvan buckets (about a minute)...", job=None)
        storage_service.start_arvan_info(
            on_status=self.set_status,
            on_complete=lambda res: self.schedule(lambda: self._after_storage_info(res)))

    def _after_storage_info(self, res):
        from screens import storage
        if res.get("ok"):
            storage.build_info(self, res["data"])
        else:
            self.show_result(res.get("error", "Failed"))

    def start_arvan_cleanup(self):
        self.show_working("Deleting expired Arvan files...", job=None)
        storage_service.start_arvan_cleanup(
            on_status=self.set_status,
            on_complete=lambda res: self.schedule(lambda: self._after_arvan_cleanup(res)))

    def _after_arvan_cleanup(self, res):
        if res.get("ok"):
            self.show_result(storage_service.cleanup_summary(res["data"]))
        else:
            self.show_result(res.get("error", "Failed"))

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
        self.remember(self.show_running_jobs)
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
        self.back_from_working()

    def cancel_running_job(self, job):
        """Cancel button of the Running jobs list."""
        job_service.cancel(self.job_manager, job)
        self.show_running_jobs()

    def cancel_run_by_id(self, run_id, origin="status"):
        """Cancel button on a run's page: stops that run on GitHub."""
        self.show_working("Cancelling the run...")

        def done(res):
            def after():
                if not res.get("ok"):
                    self.show_result(res["error"])
                    return
                for j in list(self.job_manager.active_jobs):   # a job of this app: close it too
                    if j.run_id == run_id:
                        self.job_manager.cancel(j)
                self.show_run_detail({"run_id": run_id, "workflow": "", "origin": origin})
            self.schedule(after)

        runs_service.start_cancel_run(run_id, done)

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
        elif job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            self.show_playlist_report(job)
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
            self.show_quality_list(job.input, job.result["formats"],
                                   from_phone=bool(job.extra.get("from_phone")))

        elif job.type == JOB_TYPE_PLAYLIST_LINKS:
            self._remember_playlist_titles(job.result.get("entries"))
            if job.extra.get("pick") and job.result.get("entries"):
                self.show_playlist_pick(job.result["entries"], job.input)
            else:
                self.show_playlist_quality_picker(job.result["urls"])

        elif job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            self.show_playlist_report(job)

        elif RELEASE_FILE_KINDS.get((job.extra.get("action") or {}).get("id")) and job.result.get("link"):
            self.show_release_file(job, RELEASE_FILE_KINDS[job.extra["action"]["id"]])

        else:  # download, upload
            qlabel = job.result.get("quality_label", "")
            qmeta  = job.result.get("quality_meta") or {}
            redownload_cb = self._make_redownload_cb(job) if qlabel else None
            self.show_result(
                "Ready!",
                link=job.result.get("link"),
                links=job.result.get("links"),
                arvan_links=job.result.get("arvan_links"),
                storage_warn=job.result.get("storage_warn"),
                run_id=job.result.get("files_run_id") or job.run_id,
                category=self._download_category(job),
                quality_label=qlabel,
                quality_meta=qmeta,
                on_redownload=redownload_cb,
            )

    def _make_redownload_cb(self, job):
        """Returns a callback that takes the user back to where the quality is chosen, with
        the same link already filled in, so they can get the file again in another quality:
        the form of the same Download Anything tool, or the YouTube Download screen."""
        action = (job.extra or {}).get("action")
        if action:
            values = dict(job.input) if isinstance(job.input, dict) else {}

            def go_tool(_qmeta=None):
                self.show_action_input(action, initial=values)

            return go_tool
        url = job.input if isinstance(job.input, str) else (job.result or {}).get("link", "")

        def go(_qmeta=None):
            # Navigate to YouTube download screen with URL pre-filled;
            # show_quality_list needs formats — re-fetch them first.
            if url:
                self.show_youtube_download(video_url=url)

        return go

    def _download_category(self, job):
        """Subfolder of Download/Yt-bridge for the files of a finished job."""
        action = job.extra.get("action") or {}
        if action.get("workflow"):
            return android_downloads.category_for_workflow(action["workflow"])
        if job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            return "YouTube"
        # plain YouTube download (download.yml) and the "Upload a file" flow
        return "YouTube" if job.type == "download" else "Other"

    def _handle_job_complete(self, job):
        if job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            playlist_reports.save_report(job)  # kept on the phone for later
        # Only navigate if the user is still looking at this job - they may
        # have gone back home and started a different one in the meantime.
        if self.job_manager.current_job is not job:
            return

        self.route_finished_job(job)

    def show_release_file(self, job, kind):
        """Backup zip / built APK: link, Copy, Share and the download to the
        Downloads folder. The small backup zip downloads by itself, once;
        the APK only asks (the screen's button starts it)."""
        from screens import release_file
        release_file.build(self, job, kind)
        if kind == "backup" and not job.extra.get("dl_state"):
            self.start_file_download(job)

    def start_file_download(self, job):
        """Downloads the finished job's file (backup zip / APK) to the Downloads folder. Safe to
        call from a worker thread: the download runs in its own thread and the screen is only
        refreshed through the (coalesced) scheduled callback."""
        kind = RELEASE_FILE_KINDS.get((job.extra.get("action") or {}).get("id"))
        job.extra["install_asked"] = False
        refresh_queued = {"on": False}

        def on_update():
            # Called from the download thread (also while the app is in the background).
            if (job.extra.get("dl_state") == "done" and job.extra.get("auto_install")
                    and not job.extra.get("install_asked")):
                job.extra["install_asked"] = True
                job.extra["install_pending"] = True
                if not self.app_active:
                    from core.i18n import tr
                    from services.notify_service import notify
                    notify("YT Bridge", tr("The APK is downloaded. Open the app to install it."),
                           job_id=job.job_id, run_id=job.run_id)
            if refresh_queued["on"] and job.extra.get("dl_state") == "running":
                return   # progress is frequent; one queued refresh is enough
            refresh_queued["on"] = True

            def run():
                refresh_queued["on"] = False
                self._after_download_update(job)
            self.schedule(run)

        file_download_service.start_download(
            job, (job.result or {}).get("link"),
            on_update=on_update,
            category="APK" if kind == "apk" else "Backup",
        )

    def _after_download_update(self, job):
        """Main thread: redraw the screen, and open the installer once when the APK is saved
        (auto-install). Runs when the app is on screen - right away, or when the user comes back."""
        from screens import release_file
        release_file.refresh(job)
        if job.extra.get("install_pending"):
            job.extra["install_pending"] = False
            from core import android_install
            problem = android_install.open_installer(job.extra.get("dl_location"))
            if problem:
                job.extra["dl_text"] = f"{job.extra.get('dl_text', '')}\n{problem}".strip()
                release_file.refresh(job)

    def _notify_job_finished(self, job):
        """Worker thread, when a job ends (done or failed): a notification, unless the user is
        looking at this very job right now. Tapping it opens the job's result screen
        (open_from_notification), also when the app was in the background."""
        ok = getattr(job, "ok", None)
        if ok is None or getattr(job, "cancel_requested", False):
            return
        if self.app_active and self.job_manager.current_job is job:
            return
        from core.i18n import tr
        from services.notify_service import notify
        kind = RELEASE_FILE_KINDS.get((job.extra.get("action") or {}).get("id"))
        if ok is False:
            text = tr("Job failed") + ": " + str(job.error or "")[:80]
        elif kind == "apk":
            text = tr("APK build finished")
        elif kind == "backup":
            text = tr("Project backup finished")
        elif job.type == "formats":
            text = tr("Qualities are ready")
        elif job.type == JOB_TYPE_PLAYLIST_DOWNLOAD:
            text = tr("Playlist finished")
        else:
            text = tr("Finished - tap to see the result")
        notify("YT Bridge", text, job_id=job.job_id, run_id=job.run_id)

    def open_from_notification(self, job_id, run_id):
        """Main thread: the user tapped one of the app's notifications. Opens that job's screen;
        if the job is no longer in memory (the app was closed meanwhile), the run's result page."""
        job = None
        manager = self.job_manager
        for candidate in [manager.current_job, *manager.active_jobs, *manager.history]:
            if candidate is not None and job_id and candidate.job_id == job_id:
                job = candidate
                break
        if job is not None:
            self.view_job_from_history(job)
        elif str(run_id or "").isdigit():
            self._run_ctx = None
            self.show_run_result(int(run_id))
        else:
            self.show_home()

    def _auto_after_finish(self, job):
        """Worker thread, the moment a job finishes - before (and whether or not) any screen is
        shown. A finished backup zip, or an APK when "Download automatically" is on, is downloaded
        right here. Waiting for the screen would not work: Kivy's clock is stopped while the app is
        in the background, and nothing is shown at all when the user left the job's screen."""
        kind = RELEASE_FILE_KINDS.get((job.extra.get("action") or {}).get("id"))
        if not kind or not getattr(job, "ok", False) or not (job.result or {}).get("link"):
            return
        if kind == "apk" and not job.extra.get("auto_download"):
            return
        if job.extra.get("dl_state") or job.extra.get("dl_location"):
            return
        self.start_file_download(job)

    def _relay_status(self, job, text):
        """Several jobs can run at once. A job's status line may only be
        shown while that job is the one on screen - otherwise its text would
        overwrite another job's screen."""
        if job is not None and self.job_manager.current_job is not job:
            return
        self.set_status(text)

    def _status_and_complete_callbacks(self, job=None, job_ref=None):
        """``job_ref`` is a dict whose ``"job"`` entry is filled in later, for
        flows where the service creates the job itself."""
        def on_status(text):
            target = job_ref.get("job") if job_ref is not None else job
            self._relay_status(target, text)
        def on_complete(job):
            try:
                self._auto_after_finish(job)       # worker thread: does not wait for a screen
            except Exception:
                pass
            try:
                self._notify_job_finished(job)     # worker thread: also works in the background
            except Exception:
                pass
            self.schedule(lambda: self._handle_job_complete(job))
        return on_status, on_complete

    # -- starting jobs --------------------------------------------------------
    def start_fetch_formats(self, url, where=None):
        """``where``: "github" / "phone" / "auto"; None = the Settings default."""
        job = download_service.create_fetch_formats_job(
            self.job_manager,
            url,
            where=where
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
            extra_buttons = [
                ("Pick a different quality",
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

    def youtube_links(self, text):
        """Every link in a (multi-line) box; a lone non-http text counts as one."""
        urls = link_tools.split_links(text)
        if not urls and (text or "").strip():
            urls = [text.strip()]
        return urls

    def start_downloads(self, text, format_id, audio_only):
        """The Quick Download buttons: one link = the usual job screen; several
        links (one per line) = one separate GitHub run each, all started now.
        Their results are in Running jobs / Recent jobs."""
        urls = self.youtube_links(text)
        if not urls:
            self.set_status("Enter a YouTube link")
            return
        if len(urls) == 1:
            self.start_download(urls[0], format_id, audio_only)
            return
        for url in urls[:MAX_LINKS_AT_ONCE]:
            job = download_service.create_download_job(self.job_manager, url)
            download_service.run_download_job(
                self.job_manager, job, format_id, audio_only,
                on_status=lambda text: None, on_complete=lambda job: None
            )
        self.show_running_jobs()

    def handle_fetch_single(self, url, audio_only, where=None):
        urls = self.youtube_links(url)

        if not urls:
            self.set_status("Enter a YouTube link")
            return

        if audio_only:
            self.start_downloads(url, "bestaudio", True)
        else:
            # the quality list is for one video: the first link
            self.start_fetch_formats(urls[0], where=where)

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

    def start_fetch_playlist(self, url, pick=False, where=None, sort=None, limit=None):
        job = playlist_service.create_playlist_links_job(
            self.job_manager,
            url,
            pick=pick,
            where=where,
            sort=sort,
            limit=limit
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

    def handle_pick_channel(self, url, sort, count_text, where=None):
        """\"Choose from latest / most viewed\": reads the newest (or most viewed)
        videos of a channel / page link, then shows them to tick (like a playlist)."""
        url = self.youtube_links(url)[0] if self.youtube_links(url) else ""
        if not url:
            self.set_status("Enter a channel or page link")
            return
        low = url.lower()
        if "youtube.com" not in low and "youtu.be" not in low:
            self.set_status("Only YouTube channel or page links work here")
            return
        if "watch?v=" in low or "youtu.be/" in low or "/shorts/" in low:
            self.set_status("That is ONE video. Paste the channel or page link (youtube.com/@name)")
            return
        text = str(count_text or "").strip()
        if not text.isdigit() or not (1 <= int(text) <= 500):
            self.set_status("Type how many videos: a number from 1 to 500")
            return
        self.start_fetch_playlist(url, pick=True, where=where, sort=sort, limit=int(text))

    def handle_pick_playlist(self, url, where=None):
        """\"Choose videos\" button: reads the playlist, then shows its video
        titles to tick before anything is downloaded. ``where`` overrides the
        Settings default for this one press."""
        url = url.strip()

        if not url:
            self.set_status("Enter a playlist link")
            return

        self.start_fetch_playlist(url, pick=True, where=where)

    def start_playlist_download(self, urls, target_height, want_hdr, audio_only=False, quality_screen=None,
                                titles=None, previous_items=None):
        """``previous_items``: the items of an earlier run when only some of
        its videos are retried (the others keep their state and links)."""
        job = playlist_service.create_playlist_download_job(
            self.job_manager,
            urls,
            titles=titles or getattr(self, "playlist_titles", None),
            previous_items=previous_items
        )
        job.extra["pick_quality"] = quality_screen or (lambda: self.show_playlist_quality_picker(urls))

        self.show_playlist_report(job)

        on_status, on_complete = self._status_and_complete_callbacks(job)

        playlist_service.run_playlist_download_job(
            self.job_manager,
            job,
            urls,
            target_height,
            want_hdr,
            audio_only=audio_only,
            on_status=on_status,
            on_complete=on_complete
        )

    def retry_playlist_videos(self, job, urls):
        """Report screen: run the given videos of a finished playlist job
        again, same quality; every other video keeps its state and link."""
        settings = job.extra.get("settings") or {}
        self.start_playlist_download(
            urls,
            settings.get("height", 99999),
            settings.get("hdr", False),
            audio_only=settings.get("audio_only", False),
            quality_screen=job.extra.get("pick_quality"),
            previous_items=job.extra.get("items"),
        )

    def recheck_playlist(self, job):
        """Report screen: look again for the releases of failed videos."""
        def done(finished):
            self.schedule(lambda: self._reshow_playlist_report(finished))
        playlist_service.recheck_failed(job, on_complete=done)

    def _reshow_playlist_report(self, job):
        if self.job_manager.current_job is job:
            self.show_playlist_report(job)

    def _remember_playlist_titles(self, entries):
        self.playlist_titles = {e["url"]: e["title"] for e in (entries or [])}

    # -- quality / upload / playlist screens ----------------------------------
    def show_quality_list(self, url, formats, from_phone=False):
        from screens import download as download_screen
        self.remember(lambda: self.show_quality_list(url, formats, from_phone))
        download_screen.build_quality_list(
            self,
            url,
            formats,
            from_phone=from_phone,
            on_github=lambda: self.start_fetch_formats(url, where="github"),
        )

    def show_youtube_download(self, video_url="", playlist_url=""):
        from screens import youtube_download
        self.remember(lambda: self.show_youtube_download(video_url, playlist_url))
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

        self.show_playlist_report(job)

    def show_upload_screen(self, url=""):
        from screens import upload as upload_screen
        self.remember(lambda: self.show_upload_screen(url))
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
        self.remember(self.show_dynamic_actions)
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
            res.get("actions", []),
            notice=res.get("notice", ""),
            retry=self.show_dynamic_actions,
        )

    def show_action_group(self, name, actions):
        """One group of Download Anything (e.g. Upload / import files)."""
        from screens import actions_dynamic
        self.remember(lambda: self.show_action_group(name, actions))
        actions_dynamic.build_group(self, name, actions)

    def show_action_input(self, action, prefill=None, share_url=None, initial=None):
        from screens import actions_dynamic
        self.remember(lambda: self.show_action_input(action, prefill, share_url, initial))
        actions_dynamic.build_input(
            self,
            action,
            prefill=prefill,
            share_url=share_url,
            initial=initial
        )

    # -- links shared into the app (Android Share menu) -----------------------
    # -- app update (Settings): update.zip and the APK build -------------------
    def pick_file_for_update(self):
        from core import android_files
        android_files.pick_files(on_files=self.handle_update_files, on_error=self.set_status)

    def handle_shared_file(self, data, name=None):
        """A file shared into the app from another app (zip, .yml, .py, config.json...)."""
        self.handle_update_files([(name or "update.zip", data)])

    def handle_update_files(self, files):
        """files: [(name, bytes)] from the picker or the Share menu.

        * ONE zip with main/ and config/ folders -> the zip confirmation, as before.
        * anything else (one or many files, or a zip without branch folders)
          -> the smart path: find where each file belongs, then ask."""
        from core import zip_tools
        from screens import app_update
        from services import repo_update_service

        def is_zip_name(name, data):
            return name.lower().endswith(".zip") and zip_tools.is_zip(data)

        if (len(files) == 1 and is_zip_name(*files[0])
                and zip_tools.has_branch_folders(files[0][1])):
            app_update.build_zip_confirm(self, files[0][1])
            return

        items, skipped = [], []
        try:
            for name, data in files:
                if is_zip_name(name, data):
                    if zip_tools.has_branch_folders(data):
                        self.show_result("A zip with main/ and config/ folders must be chosen on its own.")
                        return
                    for path, content, mode in zip_tools.read_loose_files(data):
                        items.append((path, content, mode))
                elif zip_tools.is_skipped_path(name):
                    skipped.append(name)
                else:
                    mode = "100755" if name.lower().endswith(".sh") else "100644"
                    items.append((name, data, mode))
        except zip_tools.ZipError as e:
            self.show_result(str(e))
            return
        if not items:
            note = f" (ignored: {', '.join(skipped)})" if skipped else ""
            self.show_result("Nothing to update" + note)
            return

        self.show_working("Reading the repo...", job=None, back_text="Back")
        repo_update_service.start_plan(
            items,
            on_done=lambda res: self.schedule(lambda: self._after_update_plan(res, skipped)),
        )

    def _after_update_plan(self, res, skipped):
        from screens import app_update
        if not res.get("ok"):
            self.show_result(res["message"])
            return
        app_update.build_review(self, res["plan"], res["folders"], skipped)

    def start_apply_update(self, plan):
        from services import repo_update_service
        self.show_working("Updating...", job=None, back_text="Back")
        repo_update_service.start_apply(
            plan,
            on_status=lambda text: self.set_status(text),
            on_done=self._repo_update_finished,
        )

    def start_repo_update(self, data):
        from services import repo_update_service
        self.show_working("Updating...", job=None, back_text="Back")
        repo_update_service.start_repo_update(
            data,
            on_status=lambda text: self.set_status(text),
            on_done=self._repo_update_finished,
        )

    def _repo_update_finished(self, res):
        """Worker thread, when the repo update is done. With "Build automatically after the update"
        the build is started here, not from a screen, so it also starts when the app is in the
        background."""
        auto_job = None
        try:
            from api import auto_build_prefs
            if res.get("ok") and res.get("changed") and auto_build_prefs.build_after_update():
                auto_job = self.start_build_apk(headless=True)
        except Exception:
            auto_job = None
        self.schedule(lambda: self._after_repo_update(res, auto_job))

    def _after_repo_update(self, res, auto_job=None):
        extra = None
        message = res["message"]
        if auto_job is not None:
            message += "\n\nThe build started by itself (about 15-30 minutes). It keeps going if you leave this screen."
            extra = [("Show the build", lambda: self.view_job_from_history(auto_job))]
        elif res.get("ok") and res.get("changed"):
            # "Build now?" - new code only reaches the phone through a new APK
            extra = [("Build APK now", self.start_build_apk)]
        self.show_result(message, extra_buttons=extra)

    def start_build_apk(self, auto_download=None, auto_install=None, headless=False):
        """Starts the APK build. The two flags default to the Settings tick-boxes: download the
        APK when the build is done, and open the installer when it is saved (install implies
        download). ``headless`` = no screen (started from a worker thread); returns the job."""
        from api import auto_build_prefs
        if auto_install is None:
            auto_install = auto_build_prefs.install_after_download()
        if auto_download is None:
            auto_download = auto_build_prefs.download_after_build()
        auto_download = bool(auto_download or auto_install)
        action = {"id": "build_apk", "workflow": "build-apk.yml", "workflow_inputs": {}}
        previous = self.job_manager.current_job
        job = generic_action_service.create_action_job(self.job_manager, action, {"input": "Build APK"})
        job.extra["auto_download"] = auto_download
        job.extra["auto_install"] = bool(auto_install)
        if headless:
            if previous is not None:     # do not take over the screen the user is looking at
                self.job_manager.current_job = previous
        else:
            self.show_working("Starting the build (takes about 15-30 minutes)...", job=job)
        on_status, on_complete = self._status_and_complete_callbacks(job)
        generic_action_service.run_action_job(
            self.job_manager, job, on_status=on_status, on_complete=on_complete
        )
        return job

    def start_project_backup(self):
        """Settings > Backup project: a workflow zips the latest main and
        config branches (folders main-branch/ and config-branch/) and
        uploads the zip to a release; the result screen shows the link."""
        action = {"id": "backup_project", "workflow": "backup-project.yml", "workflow_inputs": {}}
        job = generic_action_service.create_action_job(self.job_manager, action, {"input": "Project backup"})
        self.show_working("Starting the project backup (takes about a minute)...", job=job)
        on_status, on_complete = self._status_and_complete_callbacks(job)
        generic_action_service.run_action_job(
            self.job_manager, job, on_status=on_status, on_complete=on_complete
        )

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

    def start_filimo_phone_link(self, values, message="Getting link from this phone's network..."):
        """Filimo link requested from the phone's own network (not GitHub).
        The result screen offers Copy, Open in downloader and Refresh (the
        link expires, so Refresh asks Filimo for a new one with the same
        link and quality)."""
        from core import android_actions
        from services import filimo_link_service
        self.show_working(message)

        def _done(res):
            def _show():
                if res.get("ok"):
                    link = res["link"]
                    msg = f"{res['title']} - {res['quality']}".strip(" -")
                    self.show_result(
                        msg or "Link ready",
                        link=link,
                        extra_buttons=[
                            ("Open in downloader",
                             lambda: android_actions.share_text(link)),
                            ("Refresh link",
                             lambda: self.start_filimo_phone_link(
                                 values, "Refreshing link...")),
                        ],
                    )
                else:
                    self.show_result(
                        res.get("error", "Failed"),
                        extra_buttons=[
                            ("Try again",
                             lambda: self.start_filimo_phone_link(values)),
                        ],
                    )
            self.schedule(_show)

        filimo_link_service.start_fetch_link(
            values.get("url", ""), values.get("quality", "Best available"), _done)

    # -- Mornye: lossless music downloaded on the phone's own network ------------
    def start_mornye_phone_links(self, values, message="Downloading music on this phone..."):
        """Spotify track / album / playlist -> FLAC files saved in Download/Yt-bridge/
        Mornye. Everything runs on the phone (api.zarz.moe blocks GitHub's IPs): the
        links are made, downloaded and saved straight away because they expire."""
        from kivy.core.clipboard import Clipboard
        from services import mornye_link_service
        self.show_working(message, extra_buttons=[("Cancel", mornye_link_service.cancel)])

        def _done(res):
            def _show():
                buttons = [("Copy log", lambda: Clipboard.copy(res.get("log", "")))]
                note = ""
                if res.get("log_path"):
                    note = "\nLog saved in the repo: " + res["log_path"]
                if not res.get("ok"):
                    buttons.append(("Try again",
                                    lambda: self.start_mornye_phone_links(values)))
                    self.show_result(res.get("error", "Failed") + note,
                                     extra_buttons=buttons)
                    return
                failed = res.get("failed") or []
                saved = res.get("saved") or []
                msg = "%s: %d file(s) saved in %s" % (
                    res.get("title") or "Done", len(saved), res.get("folder", ""))
                if failed:
                    msg += "\n%d failed:\n%s" % (len(failed), "\n".join(failed[:6]))
                    buttons.insert(0, ("Copy failed tracks",
                                       lambda: Clipboard.copy("\n".join(failed))))
                    buttons.append(("Try again",
                                    lambda: self.start_mornye_phone_links(values)))
                self.show_result(msg + note, extra_buttons=buttons)
            self.schedule(_show)

        mornye_link_service.start_download(
            values.get("url", ""), values.get("quality", "LOSSLESS"),
            values.get("providers", "tidal,qobuz"),
            self.set_status,
            lambda link: self.schedule(lambda: self.show_mornye_verify(link)),
            _done)

    def show_mornye_verify(self, link):
        """The one-time browser check: open the page, then wait for the code."""
        from core import android_actions
        from screens import mornye_verify
        from services import mornye_link_service

        def _submit(text):
            if mornye_link_service.submit_grant(text):
                self.show_working("Starting the session...",
                                  extra_buttons=[("Cancel", mornye_link_service.cancel)])
            else:
                self.set_status("That is not the verification code")

        android_actions.open_url(link)
        mornye_verify.build(self, _submit, lambda: android_actions.open_url(link),
                            mornye_link_service.cancel)

    # -- Aparat: choose videos, links on the phone -----------------------------
    def start_aparat_pick(self, action, values):
        """\"Choose videos\": read the playlist / channel on the phone, then
        show the tick list. Quality, output and channel amount stay as set on
        the form and are used when the user starts with the selection."""
        from screens import actions_dynamic
        from scripts import aparat_core
        from services import aparat_service
        link = (values.get("url") or "").strip()
        if not link:
            self.set_status("Enter the Aparat link first")
            return
        kind, _value = aparat_core.parse_link(link)
        if kind == "video":
            self.set_status("Choosing videos works for playlist or channel links")
            return
        if kind == "channel":
            for field in action.get("fields") or []:
                if field.get("custom"):
                    error = actions_dynamic.validate_custom(field, values.get(field["key"]))
                    if error:
                        self.set_status(error)
                        return
        form = dict(values)
        self.show_working("Reading the video list from Aparat...")

        def _done(res):
            def _show():
                if res.get("ok"):
                    self.show_aparat_pick(action, form, res["entries"])
                else:
                    self.show_result(
                        res.get("error", "Failed"),
                        extra_buttons=[("Back to form",
                                        lambda: self.show_action_input(action, initial=form))],
                    )
            self.schedule(_show)

        aparat_service.start_list(link, form.get("channel_limit", "count:5"), _done)

    def show_aparat_pick(self, action, form, entries, selected=None):
        from screens import aparat_pick
        if selected is None or len(selected) != len(entries):
            selected = [False] * len(entries)
        self.remember(lambda: self.show_aparat_pick(action, form, entries, selected))
        aparat_pick.build(
            self, entries, action, form, selected,
            on_go=lambda ids, quality=None: self.start_dynamic_action(
                action, {**form, "quality": quality} if quality else form,
                extra={"video_ids": ",".join(ids)}),
            on_back=lambda: self.show_action_input(action, initial=form),
        )

    def start_aparat_phone_links(self, values, ids=None, message="Getting links from Aparat on this phone..."):
        """Aparat links fetched by the phone itself (not GitHub). The result
        screen offers Copy, Open in downloader, Copy names list and Refresh
        (links expire after a few days)."""
        from kivy.core.clipboard import Clipboard
        from core import android_actions
        from services import aparat_service
        self.show_working(message)

        def _done(res):
            def _show():
                if not res.get("ok"):
                    self.show_result(
                        res.get("error", "Failed"),
                        extra_buttons=[("Try again",
                                        lambda: self.start_aparat_phone_links(values, ids))],
                    )
                    return
                links, names = res["links"], res["names"]
                msg = f"{len(links)} link(s) ready"
                if res.get("nearest"):
                    msg += f" - nearest quality used for {res['nearest']}"
                if res.get("failed"):
                    msg += f", {res['failed']} failed"
                buttons = [
                    ("Open in downloader",
                     lambda: android_actions.share_text("\n".join(links))),
                    ("Copy names list", lambda: Clipboard.copy("\n".join(names))),
                    ("Refresh links",
                     lambda: self.start_aparat_phone_links(values, ids, "Refreshing links...")),
                ]
                if len(links) == 1:
                    self.show_result(msg, link=links[0], extra_buttons=buttons, category="Aparat")
                else:
                    self.show_result(msg, links=links, extra_buttons=buttons, category="Aparat")
            self.schedule(_show)

        aparat_service.start_links(
            values.get("url", ""), values.get("quality", "best"),
            values.get("channel_limit", "count:5"), ids or [], _done)

    # -- Any site: check formats, then download one ----------------------------
    def start_anysite_check(self, action, form):
        """Runs the workflow in "check" mode (nothing is downloaded), then shows
        the offered formats; tapping one downloads it."""
        from services import anysite_service
        self.show_working("Checking the available formats...")

        def _done(res):
            def _show():
                if res.get("ok"):
                    self.show_anysite_formats(action, form, res["links"])
                else:
                    self.show_result(
                        res.get("error", "Failed"),
                        extra_buttons=[("Back to form",
                                        lambda: self.show_action_input(action, initial=form))],
                    )
            self.schedule(_show)

        anysite_service.start_check(action, form.get("urls", ""), self.set_status, _done)

    def show_anysite_formats(self, action, form, links):
        from screens import anysite_formats
        self.remember(lambda: self.show_anysite_formats(action, form, links))
        anysite_formats.build(
            self, links,
            on_pick=lambda url, format_id: self.start_dynamic_action(
                action, {**form, "urls": url},
                extra={"format_id": format_id}),
            on_back=lambda: self.show_action_input(action, initial=form),
        )

    def start_anysite_history_check(self, action, cleaned, extra):
        """Reads the site log; when a link's site failed before and never worked, asks
        yes / no first. Any problem reading the log just lets the run start."""
        from services import site_log_service
        self.show_working("Checking the site history...")

        def _go(force):
            self.start_dynamic_action(action, cleaned, extra={**(extra or {}), "force": force})

        def _done(res):
            def _show():
                warnings = res.get("warnings") or []
                if warnings:
                    self.show_site_warning(action, cleaned, extra, warnings)
                else:
                    _go("no")
            self.schedule(_show)

        site_log_service.start_check_history(cleaned.get("urls", ""), _done)

    def show_site_warning(self, action, cleaned, extra, warnings):
        from screens import site_log as site_log_screen
        self.remember(lambda: self.show_site_warning(action, cleaned, extra, warnings))
        site_log_screen.build_warning(
            self, warnings,
            on_yes=lambda: self.start_dynamic_action(
                action, cleaned, extra={**(extra or {}), "force": "yes"}),
            on_no=lambda: self.show_action_input(action, initial=cleaned),
        )

    def start_dynamic_action(self, action, field_values, extra=None):
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

        # Any site: quality "Check formats" lists what the site offers; the
        # chosen format is then downloaded by a normal run (format_id set).
        if action.get("handler") == "anysite":
            if extra and extra.get("format_id"):
                cleaned["quality"] = "highest"  # ignored by the workflow when format_id is set
            elif cleaned.get("quality") == "check":
                return self.start_anysite_check(action, cleaned)
            # before a download: ask if a link's site failed before and never worked
            if not (extra and "force" in extra):
                return self.start_anysite_history_check(action, cleaned, extra)

        # One Filimo button, two modes: "phone" gets the link from this
        # phone's network; anything else goes through the GitHub workflow.
        if action.get("handler") == "filimo_phone" and cleaned.get("mode") == "phone":
            return self.start_filimo_phone_link(cleaned)

        # Mornye: the links come from this phone's network, never from GitHub.
        if action.get("handler") == "mornye_phone":
            return self.start_mornye_phone_links(cleaned)

        # Aparat: "Links on phone" never goes to GitHub; otherwise the chosen
        # video ids (empty = everything the link gives) travel with the run.
        if action.get("handler") == "aparat":
            ids = (extra or {}).get("video_ids", "")
            if cleaned.get("output") == "links_phone":
                return self.start_aparat_phone_links(cleaned, ids.split(",") if ids else None)
            cleaned["video_ids"] = ids
        elif extra:
            cleaned.update(extra)

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
        self.remember(lambda: self.show_playlist_quality_picker(urls))
        playlist_screen.build_quality_picker(
            self,
            urls
        )

    def show_playlist_pick(self, entries, playlist_url, selected=None):
        """The tick list of a playlist's videos. ``selected`` (one bool per
        video) is kept when the user comes back from the quality screen."""
        from screens import playlist as playlist_screen
        if selected is None or len(selected) != len(entries):
            selected = [False] * len(entries)
        self._remember_playlist_titles(entries)
        self.remember(lambda: self.show_playlist_pick(entries, playlist_url, selected))
        playlist_screen.build_picker(self, entries, playlist_url, selected)

    def show_playlist_selected_quality(self, entries, playlist_url, selected, urls):
        from screens import playlist as playlist_screen
        self.remember(lambda: self.show_playlist_selected_quality(entries, playlist_url, selected, urls))
        playlist_screen.build_selected_quality(
            self, urls,
            back=lambda: self.show_playlist_pick(entries, playlist_url, selected),
        )

    def show_playlist_report(self, job):
        from screens import playlist as playlist_screen
        if job.is_done or not job.extra.get("saved_at_start"):
            job.extra["saved_at_start"] = True
            playlist_reports.save_report(job)
        playlist_screen.build_report(self, job)

    def show_playlist_reports(self):
        """The saved playlist reports (newest first); a tap reopens one."""
        from screens import runs_browser
        self.remember(self.show_playlist_reports)
        runs_browser.build_playlist_reports(
            self, playlist_reports.list_reports(),
            on_open=lambda report: self.show_playlist_report(playlist_reports.to_job(report)),
            back=self.show_actions_status)

    # -- GitHub Actions status -------------------------------------------------
    def show_actions_status(self):
        from screens import actions_status as actions_screen
        self.remember(self.show_actions_status)
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
        if origin == "wf":
            ctx = getattr(self, "_wf_ctx", None)
            if ctx:
                self.show_workflow_runs(ctx["wf"], ctx["page"], ctx["back"])
            else:
                self.show_actions_status()
        elif origin == "running":
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
        self._run_ctx = run

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
        actions_screen.build_step_loading(self, run_id, origin)
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

    # -- browsing runs by workflow / by app menu, running one by hand ----------
    def show_workflows_browser(self):
        from screens import runs_browser
        self.remember(self.show_workflows_browser)
        runs_browser.build_loading(self, "Runs by workflow", self.show_actions_status)

        def done(res):
            def render():
                if not res.get("ok"):
                    self.show_result(res["error"])
                    return
                runs_browser.build_workflows(
                    self, "Runs by workflow", res["workflows"],
                    on_open=lambda wf: self.show_workflow_runs(wf, 1, self.show_workflows_browser),
                    back=self.show_actions_status)
            self.schedule(render)

        runs_service.start_load_workflows(done)

    def show_menu_groups_browser(self):
        from screens import runs_browser
        self.remember(self.show_menu_groups_browser)
        runs_browser.build_loading(self, "Runs by app menu", self.show_actions_status)

        def done(res):
            def render():
                if not res.get("ok"):
                    self.show_result(res["error"])
                    return
                runs_browser.build_groups(
                    self, runs_service.group_workflows(res["workflows"]),
                    on_open=self.open_menu_group, back=self.show_actions_status)
            self.schedule(render)

        runs_service.start_load_workflows(done)

    def open_menu_group(self, title, workflows):
        from screens import runs_browser
        if len(workflows) == 1:
            self.show_workflow_runs(workflows[0], 1, self.show_menu_groups_browser)
            return
        here = lambda: self.open_menu_group(title, workflows)
        self.remember(here)
        runs_browser.build_workflows(
            self, title, workflows,
            on_open=lambda wf: self.show_workflow_runs(wf, 1, here),
            back=self.show_menu_groups_browser)

    def show_workflow_runs(self, wf, page, back):
        """One page of a workflow's runs; ``back`` opens the screen it was reached from."""
        from screens import runs_browser
        self._wf_ctx = {"wf": wf, "page": page, "back": back}
        here = lambda: self.show_workflow_runs(wf, page, back)
        self.remember(here)
        runs_browser.build_loading(self, wf["tool"], back)

        def done(res):
            def render():
                runs_browser.build_runs(
                    self, wf, res, page,
                    on_page=lambda p: self.show_workflow_runs(wf, p, back),
                    on_manual=lambda: self.show_manual_run(wf, here),
                    on_refresh=here, back=back)
            self.schedule(render)

        runs_service.start_load_runs(wf["file"], page, done)

    def show_manual_run(self, wf, back, text="", message=""):
        from screens import runs_browser
        self.remember(lambda: self.show_manual_run(wf, back, text, message))
        runs_browser.build_manual_run(
            self, wf, on_run=lambda value: self.start_manual_run(wf, value, back),
            back=back, text=text, message=message)

    def start_manual_run(self, wf, text, back):
        inputs, error = runs_service.parse_inputs(text)
        if error:
            self.set_status(error)
            return
        self.show_working("Starting the workflow...")

        def done(res):
            def after():
                if res.get("ok") and res.get("run_id"):
                    self._wf_ctx = {"wf": wf, "page": 1, "back": back}
                    self.show_run_detail({"run_id": res["run_id"], "workflow": wf["file"], "origin": "wf"})
                elif res.get("ok"):
                    self.show_result(
                        "Started, but the run did not show up yet. Open the runs list in a few seconds.",
                        extra_buttons=[("Open the runs", lambda: self.show_workflow_runs(wf, 1, back))])
                else:
                    self.show_manual_run(wf, back, text=text, message=res["error"])
            self.schedule(after)

        runs_service.start_manual_run(wf["file"], inputs, done)

    def copy_run_error(self, run_id, jobs, show):
        """Failed run: copies the error text (with the failed step) so it can
        be pasted in the chat. ``show(text)`` updates the line under the buttons."""
        from kivy.core.clipboard import Clipboard
        show("Getting the error text...")

        def done(res):
            def after():
                if res.get("ok"):
                    Clipboard.copy(res["text"])
                    preview = res["text"] if len(res["text"]) <= 500 else res["text"][:500] + "..."
                    show("Copied - paste it in the chat.\n\n" + preview)
                else:
                    show(res["error"])
            self.schedule(after)

        runs_service.start_error_text(run_id, jobs, done)

    def copy_run_log(self, run_id, jobs, show):
        """Any run: copies the (cleaned) log - its last 400 lines."""
        from kivy.core.clipboard import Clipboard
        show("Getting the log...")

        def done(res):
            def after():
                if res.get("ok"):
                    Clipboard.copy(res["text"])
                    show(f"Log copied ({len(res['text'].splitlines())} lines).")
                else:
                    show(res["error"])
            self.schedule(after)

        runs_service.start_log_text(run_id, jobs, done)

    def show_run_result(self, run_id):
        """Result of a run in the runs browser: its release's link(s) with size,
        Copy / Share and Download in app - the same result screen the job showed."""
        run = getattr(self, "_run_ctx", None) or {"run_id": run_id}
        back = lambda: self.show_run_detail(run)
        self.show_working("Reading what this run left...")

        def done(res):
            def after():
                if not res.get("ok"):
                    self.show_result(res["error"], extra_buttons=[("Back to the run", back)])
                    return
                self.show_result(
                    "Result of this run",
                    link=res.get("link"), links=res.get("links"),
                    arvan_links=res.get("arvan_links"), storage_warn=res.get("storage_warn"),
                    run_id=run_id,
                    category=android_downloads.category_for_workflow(run.get("workflow")),
                    extra_buttons=[("Back to the run", back)])
            self.schedule(after)

        runs_service.start_run_result(run_id, done)

    def save_run_log(self, run_id, jobs, show):
        """Failed run: saves the whole job log as a text file in Download/Yt-bridge/Logs."""
        show("Saving the log...")

        def done(res):
            self.schedule(lambda: show("Log saved:\n" + res["saved"]) if res.get("ok") else show(res["error"]))

        runs_service.start_save_log(run_id, jobs, done)

    # -- Run again -----------------------------------------------------------------
    def rerun_run(self, run_id):
        """"Run again" on a run's page: the same workflow with the same inputs
        (read from the run's name). Runs whose inputs cannot be read open the
        manual-run page with the workflow's inputs prefilled instead."""
        run = getattr(self, "_run_ctx", None) or {"run_id": run_id, "origin": "status"}
        back = lambda: self.show_run_detail({**run, "run_id": run_id})
        self.show_working("Reading the run...")

        def planned(res):
            def after():
                if not res.get("ok"):
                    self.show_result(res["error"], extra_buttons=[("Back to the run", back)])
                elif res["exact"]:
                    self._start_rerun(res["workflow"], res["inputs"], run, back)
                else:
                    wf = {"file": res["workflow"], "tool": res["tool"]}
                    self._wf_ctx = {"wf": wf, "page": 1, "back": back}
                    self.show_manual_run(
                        wf, back, text=res["prefill"],
                        message="This run's inputs could not be read. Check them and press Run.")
            self.schedule(after)

        runs_service.start_rerun_plan(run_id, planned)

    def _start_rerun(self, workflow_file, inputs, run, back):
        self.show_working("Starting the run again...")

        def done(res):
            def after():
                if res.get("ok") and res.get("run_id"):
                    self.show_run_detail({"run_id": res["run_id"], "workflow": workflow_file,
                                          "origin": run.get("origin", "status")})
                elif res.get("ok"):
                    self.show_result("Started, but the new run did not show up yet. "
                                     "Open the runs list in a few seconds.",
                                     extra_buttons=[("Back to the run", back)])
                else:
                    self.show_result(res["error"], extra_buttons=[("Back to the run", back)])
            self.schedule(after)

        runs_service.start_rerun_dispatch(workflow_file, inputs, done)

    def load_error_help(self, run_id, jobs, show):
        """Fills the Persian help of a failed run's page. ``show(text)`` hops to
        the UI thread itself; it gets '' when nothing matches."""
        def done(res):
            show(res.get("text", "") if res.get("ok") else "")
        error_help_service.start_error_help(run_id, jobs, done)

    # -- Auto follow ----------------------------------------------------------------------
    def show_follow_menu(self):
        from screens import follow
        self.remember(self.show_follow_menu)
        follow.build_loading(self, self.show_home)

        def done(res):
            def after():
                if res.get("ok"):
                    self._follows, self._follow_state = res["follows"], res["state"]
                    self._follow_new = res.get("new", {})
                follow.build_list(
                    self, res, self.show_home, on_add=self.show_follow_add, on_open=self._open_follow,
                    on_check_all=lambda: self.check_follow_now(None),
                    on_sync=self.sync_follow_schedule)
            self.schedule(after)

        follow_service.start_overview(done)

    def _open_follow(self, f):
        from screens import follow
        self.remember(lambda: self._open_follow(f))
        st = (getattr(self, "_follow_state", {}) or {}).get(f["id"], {})
        follow.build_detail(
            self, f, st, (getattr(self, "_follow_new", {}) or {}).get(f["id"], 0), self.show_follow_menu,
            on_files=lambda: self.show_follow_history(f),
            on_check=lambda: self.check_follow_now(f["id"]),
            on_toggle=lambda: self._save_follows(
                [dict(x, enabled=not x.get("enabled", True)) if x["id"] == f["id"] else x for x in self._follows],
                "Saved."),
            on_edit=lambda: self.show_follow_form(f, False),
            on_delete=lambda: self._save_follows([x for x in self._follows if x["id"] != f["id"]], "Deleted."))

    def show_follow_add(self):
        from screens import follow
        self.remember(self.show_follow_add)
        self._open_url_step(follow)

    def _open_url_step(self, follow):
        """Adding starts with the link only (the rest has sensible defaults)."""
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.textinput import TextInput
        from screens import common
        from screens.common import BTN_H, back_button, paste_row
        self.clear()
        self.add(Label(text="Follow a channel", size_hint_y=None, height=44))
        self.add(Label(text="Paste the YouTube or Aparat channel link", size_hint_y=None, height=34))
        box = TextInput(hint_text="https://youtube.com/@channel", multiline=False, size_hint_y=None, height=48)
        self.add(box)
        self.add(paste_row(box))
        info = Label(text="", size_hint_y=None, height=64, color=(1, 0.6, 0.5, 1))
        info.text_size = (common.content_width(), None)
        go = Button(text="Next", size_hint_y=None, height=BTN_H)

        def next_step(_i):
            url = follow_core.clean_url(box.text)
            if not follow_core.site_of(url):
                info.text = "Only YouTube and Aparat channel links work."
                return
            if follow_core.looks_like_video(box.text):
                info.text = "That is ONE video. Open its channel page and copy that link (youtube.com/@name)."
                return
            self.show_follow_form(follow_core.new_follow(url, getattr(self, "_follows", []) or []), True)
        go.bind(on_press=next_step)
        self.add(info)
        self.add(go)
        self.add(back_button(self, to=self.show_follow_menu))

    def show_follow_form(self, f, is_new):
        from screens import follow
        self.remember(lambda: self.show_follow_form(f, is_new))
        back = self.show_follow_add if is_new else (lambda: self._open_follow(f))

        def save(out):
            items = list(getattr(self, "_follows", []) or [])
            if is_new:
                items.append(out)
            else:
                items = [out if x["id"] == out["id"] else x for x in items]
            self._save_follows(items, "Saved.")

        follow.build_form(self, f, is_new, save, back)

    def _save_follows(self, items, message):
        self.show_working("Saving...")

        def done(res):
            def after():
                if res.get("ok"):
                    self._follows = items
                    self.show_result(f"{message}\n{res.get('schedule', '')}",
                                     extra_buttons=[("Auto follow", self.show_follow_menu)])
                else:
                    self.show_result(res["error"], extra_buttons=[("Auto follow", self.show_follow_menu)])
            self.schedule(after)

        follow_service.start_save(items, done)

    def sync_follow_schedule(self):
        self.show_working("Updating the schedule...")

        def done(res):
            self.schedule(lambda: self.show_result(
                res.get("schedule") if res.get("ok") else res["error"],
                extra_buttons=[("Auto follow", self.show_follow_menu)]))

        follow_service.start_sync(getattr(self, "_follows", []) or [], done)

    def check_follow_now(self, follow_id):
        """Starts the scheduler now (one channel ignoring its window, or all channels)."""
        self.show_working("Starting the check...")

        def done(res):
            def after():
                if res.get("ok") and res.get("run_id"):
                    self.show_run_detail({"run_id": res["run_id"], "workflow": "Auto-Follow.yml", "origin": "status"})
                elif res.get("ok"):
                    self.show_result("Started. Open the runs list in a few seconds.",
                                     extra_buttons=[("Auto follow", self.show_follow_menu)])
                else:
                    self.show_result(res["error"], extra_buttons=[("Auto follow", self.show_follow_menu)])
            self.schedule(after)

        follow_service.start_check_now(follow_id, done)

    def show_follow_files(self, f):
        self.show_working("Loading the files...")

        def done(res):
            def after():
                back = lambda: self._open_follow(f)
                if not res.get("ok"):
                    self.show_result(res["error"], extra_buttons=[("Back", back)])
                    return
                links = res["links"]
                self.show_result(f"{len(links)} file(s) in {res['tag']}", link=links[-1] if links else None,
                                 links=links, run_id=res["tag"], category="Auto",
                                 extra_buttons=[("Back", back)])
            self.schedule(after)

        follow_service.start_files(f, done)

    # -- Health and ntfy notifications ------------------------------------------
    def show_health(self):
        from screens import health
        self.remember(self.show_health)
        health.build_loading(self, lambda: self.show_settings_section("notify"))

        def done(res):
            self.schedule(lambda: health.build(self, res, self.show_health, lambda: self.show_settings_section("notify")))

        health_service.start_health(done)

    # -- Site log (which sites worked) --------------------------------------------
    def show_site_log(self):
        from screens import site_log as site_log_screen
        from services import site_log_service
        self.remember(self.show_site_log)
        back = lambda: self.show_settings_section("notify")  # noqa: E731
        site_log_screen.build_loading(self, back)

        def done(res):
            self.schedule(lambda: site_log_screen.build(self, res, self.show_site_log, back))

        site_log_service.start_load_summary(done)

    def save_ntfy_topic(self, topic, show):
        show("Saving the topic...")

        def done(res):
            if res.get("ok"):
                show("Saved: every workflow now sends to this topic." if res.get("topic")
                     else "Saved: notifications are off.")
            else:
                show(res["error"])

        ntfy_service.start_save(topic, done)

    def test_ntfy(self, topic, show):
        show("Sending...")
        ntfy_service.start_test(
            topic, lambda res: show("Sent: it should arrive in the ntfy app." if res.get("ok") else res["error"]))

    # -- job history ------------------------------------------------------
    def show_job_history(self, origin="status"):
        """Recent jobs. ``origin`` ("status" or "running") is the screen it
        was opened from - Back returns there."""
        from screens import job_history as job_history_screen
        self.remember(lambda: self.show_job_history(origin))
        job_history_screen.build(self, origin)

    # -- live release history + delete/rename/zip -----------------------------
    def show_release_history(self):
        """The normal Release History (from the home menu)."""
        self._history_follow = None
        self._history_bot = False
        self._history_apk = False
        self._history_page = 0
        self.show_live_history()

    def show_apk_history(self):
        """The APKs built by the app (build-apk.yml), kept apart from the downloaded files."""
        self._history_follow = None
        self._history_bot = False
        self._history_apk = True
        self._history_page = 0
        self.show_live_history()

    def show_bot_history(self):
        """The files of the Telegram bot (aparat-bot releases): the same screen and buttons."""
        self._history_follow = None
        self._history_bot = True
        self._history_apk = False
        self._history_page = 0
        self.show_live_history()

    def show_history_page(self, page):
        """Previous / Next of the Release History."""
        self._history_page = max(0, page)
        self.show_live_history()

    def show_follow_history(self, f):
        """The same screen (select, copy, share, rename, zip, delete), but only
        the files of one Auto follow channel's release."""
        self._history_follow = f
        self._history_bot = False
        self._history_apk = False
        self.show_live_history()

    def show_live_history(self):
        from screens import history as history_screen

        self.remember(self.show_live_history)
        history_screen.build_loading(self)
        f = getattr(self, "_history_follow", None)

        history_service.start_load_live_history(
            on_complete=lambda res: self.schedule(
                lambda: self.render_history(res)
            ),
            tag=follow_core.release_tag(f) if f else None,
            page=getattr(self, "_history_page", 0),
            repo="bot" if getattr(self, "_history_bot", False) else None,
            apk=getattr(self, "_history_apk", False),
        )

    def render_history(self, res):
        from screens import history as history_screen
        items = res["items"]
        f = getattr(self, "_history_follow", None)
        if f is None and getattr(self, "_history_bot", False):
            if res.get("error"):
                history_screen.build_bot_error(self, res["error"], back=self.show_release_history)
                return
            self._history_page = res["page"]
            history_screen.build(
                self, items, title="Telegram bot files", back=self.show_release_history,
                page=res["page"], has_next=res["has_next"], bot=True)
            return
        if f is None and getattr(self, "_history_apk", False):
            self._history_page = res["page"]
            history_screen.build(
                self, items, title="APK builds and backups", back=self.show_release_history,
                page=res["page"], has_next=res["has_next"], apk=True)
            return
        if f is None:
            self._history_page = res["page"]   # a page past the end falls back to the last one
            box = history_screen.build(
                self, items, page=res["page"], has_next=res["has_next"],
                follows=getattr(self, "_follows", None) or [], new=getattr(self, "_follow_new", None) or {},
                on_follow=self.show_follow_history, on_bot=self.show_bot_history, on_apk=self.show_apk_history)
            if box is not None:
                self._load_follow_buttons(box)
            return
        history_screen.build(
            self, items, title=f"Auto follow: {f.get('name', '')} (files)", back=self.show_release_history,
            extra=("Download in app / copy all links", lambda: self.show_follow_files(f)))

    def _load_follow_buttons(self, box):
        """Fresh Auto follow channels for the buttons at the top of Release History
        (the screen is already shown with the channels known so far)."""
        from screens import history as history_screen

        def done(res):
            if not res.get("ok"):
                return

            def after():
                self._follows, self._follow_state = res["follows"], res["state"]
                self._follow_new = res.get("new", {})
                if box.parent is not None:    # still on the screen
                    history_screen.fill_follow_box(box, self._follows, self._follow_new, self.show_follow_history)
            self.schedule(after)

        follow_service.start_overview(done)

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
            on_complete=lambda res: self.schedule(self.show_live_history)
        )

    def do_rename_release(self, item, new_name):
        if not new_name or new_name == item["title"]:
            self.show_live_history()
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
            self.show_live_history()
        else:
            self.show_result(
                res.get("error")
        )
