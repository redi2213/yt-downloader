"""Downloading a finished job's file (project backup zip, built APK) into the
phone's Downloads folder. The state lives in ``job.extra`` so the screen can
be rebuilt (or reopened from history) and still show where things are:

* ``dl_state`` - missing (never started) / "running" / "done" / "error"
* ``dl_text``  - the line the screen shows

``on_update()`` is called from a background thread whenever the text changes;
the caller hops onto the Kivy thread.
"""
from core import android_downloads
from core.async_utils import run_in_background
from services.notify_service import notify


def start_download(job, link, on_update):
    if not link or job.extra.get("dl_state") == "running":
        return
    job.extra["dl_state"] = "running"
    job.extra["dl_text"] = "Downloading to the Downloads folder... 0%"
    on_update()
    run_in_background(_run, job, link, on_update)


def _mb(size):
    return f"{size / (1024 * 1024):.1f}"


def _run(job, link, on_update):
    def progress(done, total):
        if total:
            text = f"Downloading to the Downloads folder... {done * 100 // total}%  ({_mb(done)} / {_mb(total)} MB)"
        else:
            text = f"Downloading to the Downloads folder... {_mb(done)} MB"
        job.extra["dl_text"] = text
        on_update()

    try:
        saved = android_downloads.download_to_downloads(link, on_progress=progress)
        job.extra["dl_state"] = "done"
        job.extra["dl_text"] = f"Saved in the Downloads folder:\n{saved}"
        notify("YT Bridge", "Saved in Downloads")
    except Exception as e:
        job.extra["dl_state"] = "error"
        job.extra["dl_text"] = f"Download failed: {str(e)[:80]}\nThe link above still works."
    on_update()
