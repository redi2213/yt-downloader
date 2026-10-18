"""Playlist download reports kept on the phone.

The coloured per-video report of a playlist download lives in the app's memory
and was gone after closing the app. Every finished (or started) playlist job is
saved here, so "was the whole list downloaded?" can be answered later: the
runs screen has a "Playlist reports" list that reopens the same coloured cards.

A plain JSON file next to the app's settings; the newest ``MAX_REPORTS`` are
kept. No Kivy.
"""
import json
import os
from datetime import datetime, timezone

from core.config import SETTINGS_STORE_FILE
from core.models.job import Job, JOB_TYPE_PLAYLIST_DOWNLOAD, STAGE_DONE

MAX_REPORTS = 30
_FILE = os.path.join(os.path.dirname(SETTINGS_STORE_FILE) or ".", "playlist_reports.json")


def _load():
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _store(reports):
    tmp = _FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(reports, f, ensure_ascii=False, default=str)
        os.replace(tmp, _FILE)
    except OSError:
        pass  # a report that cannot be saved must never break the screen


def save_report(job):
    """Saves (or updates) the report of a playlist download job."""
    items = job.extra.get("items") or []
    if not items:
        return
    report = {
        "id": job.job_id,
        "created": job.created_at.astimezone(timezone.utc).isoformat() if job.created_at else "",
        "finished": bool(job.is_done),
        "settings": job.extra.get("settings") or {},
        "items": [dict(i) for i in items],
    }
    reports = [r for r in _load() if r.get("id") != report["id"]]
    reports.insert(0, report)
    _store(reports[:MAX_REPORTS])


def list_reports():
    """Saved reports, newest first."""
    return sorted(_load(), key=lambda r: r.get("created", ""), reverse=True)


def counts(report):
    items = report.get("items") or []
    return (sum(1 for i in items if i.get("state") == "done"),
            sum(1 for i in items if i.get("state") == "failed"),
            len(items))


def to_job(report):
    """A finished Job holding the saved items, so the normal report screen
    (with Copy / Retry buttons) can show it. A report saved while videos were
    still running shows them as they were, nothing more happens."""
    items = [dict(i) for i in report.get("items") or []]
    for item in items:
        if item.get("state") in ("waiting", "listing", "downloading"):
            item["state"] = "failed"
            item["error"] = "the app was closed before this video finished"
    job = Job(job_id=report.get("id") or "saved", type=JOB_TYPE_PLAYLIST_DOWNLOAD,
              input=[i.get("url") for i in items], stage=STAGE_DONE, status="Saved report")
    try:
        job.created_at = datetime.fromisoformat(report.get("created"))
    except (TypeError, ValueError):
        pass
    job.extra["items"] = items
    job.extra["run_items"] = items
    job.extra["settings"] = report.get("settings") or {}
    return job
