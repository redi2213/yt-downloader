"""The Job model: a plain data object describing one background operation
(fetching formats, downloading a video, uploading a file, processing a
playlist, ...).

This module has no dependency on Kivy or on the GitHub API - a Job is just
a record of what's happening, so any client (Kivy UI, a future Telegram
bot, a REST API, ...) can inspect and react to the same shape of object.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional


# Job types (the ``type`` field). Kept as plain strings rather than an Enum
# to keep this easy to extend from services without touching this file.
JOB_TYPE_FORMATS = "formats"
JOB_TYPE_DOWNLOAD = "download"
JOB_TYPE_PLAYLIST_LINKS = "playlist_links"
JOB_TYPE_PLAYLIST_DOWNLOAD = "playlist_download"
JOB_TYPE_UPLOAD = "upload"

STAGE_DONE = "done"


@dataclass
class Job:
    job_id: str
    type: str
    stage: str = ""
    status: str = "starting"
    run_id: Optional[int] = None
    # The value the job was started with: a video/playlist URL, a file URL, etc.
    input: Any = None
    result: Optional[dict] = None
    error: Optional[str] = None
    # Optional zero-arg-friendly callable a UI can invoke to retry the failed
    # step. Set by the service layer; never touches UI code directly.
    retry: Optional[Callable[..., None]] = None
    cancel_requested: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # Kind-specific extra data that doesn't deserve its own column, e.g. the
    # list of formats to allow "pick a different quality" without re-fetching,
    # or the list of playlist URLs and running total for progress display.
    extra: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.stage:
            self.stage = self.type

    def touch(self):
        self.updated_at = datetime.now(timezone.utc)

    @property
    def is_done(self) -> bool:
        return self.stage == STAGE_DONE

    @property
    def ok(self) -> Optional[bool]:
        """True/False once finished, None while still running."""
        if not self.result:
            return None
        return bool(self.result.get("ok"))
