"""Uploading a file from a direct link (optionally renamed/zipped first)."""
import uuid

from api.github import workflows, releases
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError
from core.jobs.job_manager import JobManager
from core.models.job import Job, JOB_TYPE_UPLOAD
from services.notify_service import notify


def create_upload_job(job_manager: JobManager, file_url: str) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], type=JOB_TYPE_UPLOAD, input=file_url)
    job_manager.start(job)
    return job


def run_upload_job(job_manager: JobManager, job: Job, zip_it: bool, custom_name: str,
                    on_status=None, on_complete=None) -> None:
    run_in_background(_upload_thread, job_manager, job, zip_it, custom_name, on_status, on_complete)


def start_upload(job_manager: JobManager, file_url: str, zip_it: bool, custom_name: str,
                  on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_upload_job(job_manager, file_url)
    run_upload_job(job_manager, job, zip_it, custom_name, on_status=on_status, on_complete=on_complete)
    return job


def _upload_thread(job_manager, job, zip_it, custom_name, on_status, on_complete):
    try:
        _emit(on_status, "Starting workflow...")
        workflows.dispatch_workflow("upload-file.yml", {
            "file_url": job.input,
            "zip_it": "true" if zip_it else "false",
            "custom_name": custom_name,
            "job_id": job.job_id,
        })
        _find_and_track_upload_run(job_manager, job, on_status, on_complete)
    except AuthenticationError:
        job_manager.complete(job, ok=False, error="GitHub token invalid or expired. Update it and retry.")
        _emit_complete(on_complete, job)
    except Exception as e:
        job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def _find_and_track_upload_run(job_manager, job, on_status, on_complete):
    # Large files can take a while for GitHub to register the run under,
    # so search longer, and if we still don't find it, offer a retry
    # instead of a dead end - the workflow may simply still be starting.
    run_id = workflows.get_run_id_by_job_id("upload-file.yml", job.job_id, attempts=40, delay=3)
    job.run_id = run_id
    if job.cancel_requested:
        _safe_cancel(run_id)
        return  # job already marked done by the caller's cancel action

    if run_id is None:
        job.extra["retry_message"] = "Looking for the workflow run..."
        retry = lambda: run_in_background(_find_and_track_upload_run, job_manager, job, on_status, on_complete)
        job_manager.complete(job, ok=False,
                              error="Could not detect the workflow run yet. It may still be starting on GitHub Actions.",
                              retry=retry)
        _emit_complete(on_complete, job)
        return

    _track_upload_run(job_manager, run_id, job, on_status, on_complete)


def _track_upload_run(job_manager, run_id, job, on_status, on_complete):
    try:
        conclusion = workflows.wait_for_run(run_id, on_status=_status_relay(job, on_status))
        if job.is_done:
            return  # cancelled by the user in the meantime
        if conclusion != "success":
            job_manager.complete(job, ok=False, error=f"Upload failed ({conclusion})")
            _emit_complete(on_complete, job)
            return

        tag = f"job-{job.job_id}"
        link = releases.get_release_link(tag=tag)
        if link:
            notify("YT Bridge Git", "Upload link ready!")
            job_manager.complete(job, ok=True, result_data={"link": link})
            _emit_complete(on_complete, job)
        else:
            retry = _make_retry_fetch_upload_link(job_manager, tag, job, on_complete)
            job_manager.complete(job, ok=False,
                                  error="Could not get link (release may not be ready yet).", retry=retry)
            _emit_complete(on_complete, job)
    except AuthenticationError:
        job_manager.complete(job, ok=False, error="GitHub token invalid or expired. Update it and retry.")
        _emit_complete(on_complete, job)
    except Exception as e:
        # The GitHub Actions run itself may have already succeeded even if
        # this network call failed (e.g. mobile connection drop) - offer a
        # retry that just re-fetches the link instead of a dead end.
        tag = f"job-{job.job_id}"
        retry = _make_retry_fetch_upload_link(job_manager, tag, job, on_complete)
        job_manager.complete(job, ok=False, error=f"Network error: {str(e)[:60]}", retry=retry)
        _emit_complete(on_complete, job)


def _make_retry_fetch_upload_link(job_manager, tag, job, on_complete):
    job.extra["retry_message"] = "Fetching link..."

    def _retry():
        run_in_background(_retry_fetch_upload_link_thread, job_manager, tag, job, on_complete)

    return _retry


def _retry_fetch_upload_link_thread(job_manager, tag, job, on_complete):
    link = releases.get_release_link(tag=tag)
    if link:
        job_manager.complete(job, ok=True, result_data={"link": link})
        _emit_complete(on_complete, job)
    else:
        retry = _make_retry_fetch_upload_link(job_manager, tag, job, on_complete)
        job_manager.complete(job, ok=False, error="Still could not get link.", retry=retry)
        _emit_complete(on_complete, job)


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
