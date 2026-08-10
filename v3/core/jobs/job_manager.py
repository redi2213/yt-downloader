"""JobManager keeps track of the currently running job and a short history
of finished jobs.

It has no idea Kivy exists - it is plain Python state plus a couple of
helper methods, so it can be reused unchanged by any future client
(Telegram bot, REST API, CLI, ...).
"""
from typing import List, Optional

from core.config import MAX_JOB_HISTORY
from core.models.job import Job, STAGE_DONE


class JobManager:
    def __init__(self, max_history: int = MAX_JOB_HISTORY):
        self.current_job: Optional[Job] = None
        self.history: List[Job] = []
        self._max_history = max_history

    def start(self, job: Job) -> Job:
        """Registers a newly created job as the current job."""
        self.current_job = job
        return job

    def complete(self, job: Job, ok: bool, error: Optional[str] = None,
                 result_data: Optional[dict] = None, retry=None) -> Job:
        """Marks a job as finished (successfully or not) and records it in
        history. ``result_data`` holds kind-specific payload, e.g.
        {"formats": [...]} or {"link": "..."}."""
        job.stage = STAGE_DONE
        job.error = error
        job.retry = retry
        job.result = {"ok": ok, "error": error, **(result_data or {})}
        job.touch()
        self._record_history(job)
        return job

    def cancel(self, job: Job, message: str = "Cancelled by user") -> Job:
        job.cancel_requested = True
        job.stage = STAGE_DONE
        job.error = message
        job.result = {"ok": False, "error": message}
        job.touch()
        self._record_history(job)
        return job

    def view(self, job: Job):
        """Makes ``job`` (typically one picked from history) the current job."""
        self.current_job = job
        return job

    def _record_history(self, job: Job):
        # Avoid double-recording the same job object if it's already there.
        self.history = [j for j in self.history if j is not job]
        self.history.insert(0, job)
        self.history = self.history[: self._max_history]
