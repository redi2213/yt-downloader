"""Fetching available qualities and downloading a single video.

Every public function here returns immediately (spawning a background
thread), and reports progress/results through the ``on_status``/
``on_complete`` callbacks. Those callbacks may be invoked from the
background thread - it's the caller's (UI's) job to marshal them back onto
whatever thread it needs.
"""
import uuid

from api.github import workflows, releases, logs as gh_logs
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError
from core.jobs.job_manager import JobManager
from core.models.job import Job, JOB_TYPE_FORMATS, JOB_TYPE_DOWNLOAD
from services.notify_service import notify


def create_fetch_formats_job(job_manager: JobManager, url: str) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], type=JOB_TYPE_FORMATS, input=url)
    job_manager.start(job)
    return job


def run_fetch_formats_job(job_manager: JobManager, job: Job, on_status=None, on_complete=None) -> None:
    run_in_background(_fetch_formats_thread, job_manager, job, on_status, on_complete)


def start_fetch_formats(job_manager: JobManager, url: str, on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_fetch_formats_job(job_manager, url)
    run_fetch_formats_job(job_manager, job, on_status=on_status, on_complete=on_complete)
    return job


def _fetch_formats_thread(job_manager, job, on_status, on_complete):
    try:
        _emit(on_status, "Fetching qualities...")
        dispatch_time = workflows.dispatch_workflow("list-formats.yml", {"video_url": job.input})
        run_id = workflows.get_run_id_after("list-formats.yml", dispatch_time)
        job.run_id = run_id
        if job.cancel_requested:
            _safe_cancel(run_id)
            return  # job already marked done by the caller's cancel action

        if run_id is None:
            job_manager.complete(job, ok=False, error="Could not detect the workflow run. Try again.")
            _emit_complete(on_complete, job)
            return

        conclusion = workflows.wait_for_run(run_id, on_status=_status_relay(job, on_status))
        if conclusion != "success":
            job_manager.complete(job, ok=False, error=f"Could not fetch qualities ({conclusion})")
            _emit_complete(on_complete, job)
            return

        log_text = gh_logs.get_run_log_text(run_id)
        formats = gh_logs.parse_formats(log_text)
        if not formats:
            job_manager.complete(job, ok=False, error="No formats found")
            _emit_complete(on_complete, job)
            return

        job_manager.complete(job, ok=True, result_data={"formats": formats})
        _emit_complete(on_complete, job)
    except AuthenticationError:
        job_manager.complete(job, ok=False, error="GitHub token invalid or expired. Update it and retry.")
        _emit_complete(on_complete, job)
    except Exception as e:
        job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def create_download_job(job_manager: JobManager, url: str, formats_for_reselect=None) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], type=JOB_TYPE_DOWNLOAD, input=url)
    job.extra["formats"] = formats_for_reselect
    job_manager.start(job)
    return job


def run_download_job(job_manager: JobManager, job: Job, format_id: str, audio_only: bool,
                      on_status=None, on_complete=None) -> None:
    run_in_background(_download_thread, job_manager, job, format_id, audio_only, on_status, on_complete)


def start_download(job_manager: JobManager, url: str, format_id: str, audio_only: bool,
                    formats_for_reselect=None, on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_download_job(job_manager, url, formats_for_reselect=formats_for_reselect)
    run_download_job(job_manager, job, format_id, audio_only, on_status=on_status, on_complete=on_complete)
    return job


def _download_thread(job_manager, job, format_id, audio_only, on_status, on_complete):
    try:
        _emit(on_status, "Starting workflow...")
        dispatch_time = workflows.dispatch_workflow("download.yml", {
            "video_url": job.input, "format_id": format_id,
            "audio_only": "true" if audio_only else "false",
        })
        run_id = workflows.get_run_id_after("download.yml", dispatch_time)
        job.run_id = run_id
        if job.cancel_requested:
            _safe_cancel(run_id)
            return  # job already marked done by the caller's cancel action

        if run_id is None:
            job_manager.complete(job, ok=False,
                                  error="Could not detect the workflow run. It may still be running on GitHub Actions.")
            _emit_complete(on_complete, job)
            return

        conclusion = workflows.wait_for_run(run_id, on_status=_status_relay(job, on_status))
        if job.is_done:
            return  # cancelled, or the user chose to reselect a quality, while waiting
        if conclusion != "success":
            job_manager.complete(job, ok=False, error=f"Download failed ({conclusion})")
            _emit_complete(on_complete, job)
            return

        _finish_download(job_manager, run_id, job, on_complete)
    except AuthenticationError:
        job_manager.complete(job, ok=False, error="GitHub token invalid or expired. Update it and retry.")
        _emit_complete(on_complete, job)
    except Exception as e:
        # The GitHub Actions run itself may have already succeeded even if this
        # network call failed (e.g. mobile connection drop) - let the person
        # retry just the "fetch the link" step instead of starting over.
        run_id_for_retry = job.run_id
        if run_id_for_retry:
            retry = _make_retry_fetch_link(job_manager, run_id_for_retry, job, on_complete)
            job_manager.complete(job, ok=False,
                                  error=f"Network error while fetching the link: {str(e)[:60]}", retry=retry)
        else:
            job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def _finish_download(job_manager, run_id, job, on_complete):
    try:
        link = releases.get_release_link(run_id)
    except Exception as e:
        retry = _make_retry_fetch_link(job_manager, run_id, job, on_complete)
        job_manager.complete(job, ok=False,
                              error=f"Network error while fetching the link: {str(e)[:60]}", retry=retry)
        _emit_complete(on_complete, job)
        return
    if link:
        notify("YT Bridge Git", "Link ready!")
        job_manager.complete(job, ok=True, result_data={"link": link})
        _emit_complete(on_complete, job)
    else:
        retry = _make_retry_fetch_link(job_manager, run_id, job, on_complete)
        job_manager.complete(job, ok=False,
                              error="Could not get link (release may not be ready yet).", retry=retry)
        _emit_complete(on_complete, job)


def _make_retry_fetch_link(job_manager, run_id, job, on_complete):
    job.extra["retry_message"] = "Fetching link..."

    def _retry():
        run_in_background(_finish_download, job_manager, run_id, job, on_complete)

    return _retry


def pick_format(formats, target_height, want_hdr):
    """Chooses the format closest to ``target_height`` (or the highest
    available if target_height is very large, meaning "Best"), preferring
    HDR or non-HDR formats to match ``want_hdr``."""
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


def _status_relay(job, on_status):
    def _on_status(s):
        job.status = s
        _emit(on_status, f"{s}...")
    return _on_status


def _emit(on_status, text):
    if on_status:
        on_status(text)


def _emit_complete(on_complete, job):
    if on_complete:
        on_complete(job)


def _safe_cancel(run_id):
    if not run_id:
        return
    try:
        workflows.cancel_run(run_id)
    except Exception:
        pass
