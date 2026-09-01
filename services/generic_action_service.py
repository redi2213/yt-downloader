"""Running a remote-config-defined action (e.g. 'download from Mediafire').

Unlike download_service/upload_service which each hardcode one specific
workflow + input shape, this dispatches whatever workflow + inputs the
config.json entry for the chosen action describes. Result-link retrieval
follows download.yml's convention (tag "run-{run_id}"), which is what
download-anything.yml also uses - NOT upload-file.yml's job_id-tag
convention, since download-anything.yml has no job_id input.
"""
import uuid

from api.github import workflows, releases
from core.async_utils import run_in_background
from core.exceptions import AuthenticationError
from core.jobs.job_manager import JobManager
from core.models.job import Job, JOB_TYPE_DOWNLOAD
from services.notify_service import notify


def create_action_job(job_manager: JobManager, action: dict, user_input: str) -> Job:
    job = Job(job_id=uuid.uuid4().hex[:12], type=JOB_TYPE_DOWNLOAD, input=user_input)
    job.extra["action"] = action
    job_manager.start(job)
    return job


def run_action_job(job_manager: JobManager, job: Job, on_status=None, on_complete=None) -> None:
    run_in_background(_action_thread, job_manager, job, on_status, on_complete)


def start_action(job_manager: JobManager, action: dict, user_input: str,
                  on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_action_job(job_manager, action, user_input)
    run_action_job(job_manager, job, on_status=on_status, on_complete=on_complete)
    return job


def _resolve_inputs(action: dict, user_input: str) -> dict:
    """Substitutes the {input} placeholder in every workflow_inputs value
    with what the user actually typed."""
    template = action.get("workflow_inputs", {})
    return {key: (value.replace("{input}", user_input) if isinstance(value, str) else value)
            for key, value in template.items()}


def _action_thread(job_manager, job, on_status, on_complete):
    action = job.extra["action"]
    workflow_file = action["workflow"]
    try:
        _emit(on_status, "Starting workflow...")
        inputs = _resolve_inputs(action, job.input)
        dispatch_time = workflows.dispatch_workflow(workflow_file, inputs)
        run_id = workflows.get_run_id_after(workflow_file, dispatch_time)
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
            return  # cancelled while waiting
        if conclusion != "success":
            job_manager.complete(job, ok=False, error=f"Action failed ({conclusion})")
            _emit_complete(on_complete, job)
            return

        _finish_action(job_manager, run_id, job, on_complete)
    except AuthenticationError:
        job_manager.complete(job, ok=False, error="GitHub token invalid or expired. Update it and retry.")
        _emit_complete(on_complete, job)
    except Exception as e:
        run_id_for_retry = job.run_id
        if run_id_for_retry:
            retry = _make_retry_fetch_link(job_manager, run_id_for_retry, job, on_complete)
            job_manager.complete(job, ok=False,
                                  error=f"Network error while fetching the link: {str(e)[:60]}", retry=retry)
        else:
            job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def _finish_action(job_manager, run_id, job, on_complete):
    try:
        link = releases.get_release_link(run_id)
    except Exception as e:
        retry = _make_retry_fetch_link(job_manager, run_id, job, on_complete)
        job_manager.complete(job, ok=False,
                              error=f"Network error while fetching the link: {str(e)[:60]}", retry=retry)
        _emit_complete(on_complete, job)
        return
    if link:
        notify("YT Bridge", "Link ready!")
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
        run_in_background(_finish_action, job_manager, run_id, job, on_complete)

    return _retry


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
