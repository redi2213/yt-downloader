"""Downloading finished files into the phone's Download/Yt-bridge folder, one
subfolder per source (APK, Backup, YouTube, Aparat, ...).

Two entry points:

* ``start_download(job, link, on_update, category)`` - ONE file of a finished
  job (project backup zip, built APK). The state lives in ``job.extra`` so the
  screen can be rebuilt (or reopened from history) and still show where things are:
    - ``dl_state``    - missing (never started) / "running" / "done" / "error"
    - ``dl_text``     - the line the screen shows
    - ``dl_location`` - content uri / path of the saved file (the Install button needs it)
* ``start_links_download(run_id, links, category, on_text, on_finish)`` - every
  file of a result screen ("Download in app" button), one after another.
  ``run_id`` may also be a list of run ids (a finished playlist).

``on_update()`` / ``on_text(text)`` are called from a background thread; the
caller hops onto the Kivy thread.
"""
from api.github import releases
from core import android_downloads
from core.async_utils import run_in_background
from services.notify_service import notify


def _mb(size):
    return f"{size / (1024 * 1024):.1f}"


def _progress_text(prefix, done, total):
    if total:
        return f"{prefix} {done * 100 // total}%  ({_mb(done)} / {_mb(total)} MB)"
    return f"{prefix} {_mb(done)} MB"


def _release_files(run_id):
    """[(name, url, headers)] of the files in release run-<run_id>. The repo
    is private: the plain link gives 404, the API link + token works."""
    if not run_id:
        return []
    try:
        assets = releases.get_release_assets(run_id)
    except Exception:
        assets = []
    if not assets:
        return []
    headers = releases.asset_download_headers()
    return [(a["name"], a["api_url"], headers) for a in assets]


# -- one file of a job ---------------------------------------------------------
def start_download(job, link, on_update, category="Other"):
    if not link or job.extra.get("dl_state") == "running":
        return
    folder = f"Download/{android_downloads.ROOT_FOLDER}/{category}"
    job.extra["dl_state"] = "running"
    job.extra["dl_text"] = f"Downloading to {folder} ... 0%"
    on_update()
    run_in_background(_run_one, job, link, on_update, category)


def _run_one(job, link, on_update, category):
    folder = f"Download/{android_downloads.ROOT_FOLDER}/{category}"

    def progress(done, total):
        job.extra["dl_text"] = _progress_text(f"Downloading to {folder} ...", done, total)
        on_update()

    try:
        url, name, headers = link, None, None
        files = _release_files(job.run_id)
        if files:
            name, url, headers = files[0]
        saved = android_downloads.download_to_downloads(
            url, name=name, on_progress=progress, headers=headers, category=category)
        job.extra["dl_state"] = "done"
        job.extra["dl_location"] = getattr(saved, "location", None)
        job.extra["dl_text"] = f"Saved:\n{saved}"
        notify("YT Bridge", "Saved in Downloads")
    except Exception as e:
        job.extra["dl_state"] = "error"
        job.extra["dl_text"] = f"Download failed: {str(e)[:80]}\nThe link above still works."
    on_update()


# -- every file of a result screen ---------------------------------------------
def start_links_download(run_id, links, category, on_text, on_finish=None):
    run_in_background(_run_many, run_id, list(links or []), category, on_text, on_finish)


def _run_many(run_id, links, category, on_text, on_finish):
    folder = f"Download/{android_downloads.ROOT_FOLDER}/{category}"
    saved_count, errors, last_error = 0, 0, ""
    try:
        on_text("Looking for the files...")
        items = []
        for one in (run_id if isinstance(run_id, (list, tuple)) else [run_id]):
            items.extend(_release_files(one))
        if not items:
            items = [(android_downloads.file_name_from_url(u), u, None) for u in links]
        total = len(items)
        if not total:
            on_text("There is nothing to download here.")
            return
        for index, (name, url, headers) in enumerate(items, 1):
            prefix = f"Downloading {index}/{total} ..."

            def progress(done, size, prefix=prefix):
                on_text(_progress_text(prefix, done, size))

            try:
                android_downloads.download_to_downloads(
                    url, name=name, on_progress=progress, headers=headers, category=category)
                saved_count += 1
            except Exception as e:
                errors += 1
                last_error = str(e)[:60]
        text = f"Saved {saved_count} of {total} file(s) in {folder}"
        if errors:
            text += f"\n{errors} failed ({last_error})"
        on_text(text)
        if saved_count:
            notify("YT Bridge", "Saved in Downloads")
    except Exception as e:
        on_text(f"Download failed: {str(e)[:80]}")
    finally:
        if on_finish:
            on_finish()
