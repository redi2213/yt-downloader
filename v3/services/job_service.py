"""Job lifecycle actions that are the same regardless of job kind
(download, upload, playlist, ...): cancelling, and giving up on the
current run to reselect a different quality.
"""
from api.github import workflows
from core.jobs.job_manager import JobManager
from core.models.job import Job


def cancel(job_manager: JobManager, job: Job, message: str = "Cancelled by user",
           set_cancel_flag: bool = True) -> Job:
    """Stops a job in progress. If ``set_cancel_flag`` is True (the normal
    "Cancel" button case) the background thread is told to stop as soon as
    it next checks; if False (used when the user just wants to abandon the
    current run and reselect a different quality) only the run itself is
    cancelled on GitHub and the job is marked done, letting the background
    thread notice via its own "did stage become done" check."""
    if set_cancel_flag:
        job.cancel_requested = True
    if job.run_id:
        try:
            workflows.cancel_run(job.run_id)
        except Exception:
            pass  # best-effort; the run finishing harmlessly is fine
    return job_manager.cancel(job, message=message)
