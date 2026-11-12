"""Downloading finished files into the phone's Download/Yt-bridge folder, one
subfolder per source (APK, Backup, YouTube, Aparat, ...).

Two entry points:

* ``start_download(job, link, on_update, category)`` - ONE file of a finished
  job (project backup zip, built APK). The state lives in ``job.extra`` so the
  screen can be rebuilt (or reopened from history) and still show where things are:
    - ``dl_state``    - missing (never started) / "running" / "done" / "error"
    - ``dl_text``     - the line the screen shows
    - ``dl_location`` - content uri / path of the saved file (Install / Open / Share need it)
    - ``dl_name``     - its file name (Open needs it to pick the right kind of app)
* ``start_links_download(run_id, links, category, on_text, on_finish)`` - every
  file of a result screen ("Download in app" button), one after another.
  ``on_finish([(name, location)])`` gets the saved files (Open / Share buttons).
  ``run_id`` may also be a list of run ids (a finished playlist).

``on_update()`` / ``on_text(text)`` are called from a background thread; the
caller hops onto the Kivy thread.
"""
import threading

from api.github import releases
from core import android_downloads, segmented_download
from core.config import API_BASE
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
    folder = android_downloads.folder_label(category)
    job.extra["dl_state"] = "running"
    job.extra["dl_text"] = f"Downloading to {folder} ... 0%"
    on_update()
    run_in_background(_run_one, job, link, on_update, category)


def _run_one(job, link, on_update, category):
    folder = android_downloads.folder_label(category)

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
        job.extra["dl_name"] = name or android_downloads.file_name_from_url(url)
        job.extra["dl_text"] = f"Saved:\n{saved}"
        notify("YT Bridge", "Saved in Downloads", job_id=job.job_id, run_id=job.run_id)
    except segmented_download.Cancelled:
        job.extra["dl_state"] = "error"
        job.extra["dl_text"] = "Stopped. Press Download to start again."
    except Exception as e:
        job.extra["dl_state"] = "error"
        job.extra["dl_text"] = f"Download failed: {str(e)[:80]}\nThe link above still works."
    on_update()


# -- every file of a result screen ---------------------------------------------
def start_links_download(run_id, links, category, on_text, on_finish=None):
    run_in_background(_run_many, run_id, list(links or []), category, on_text, on_finish)


def _run_many(run_id, links, category, on_text, on_finish, prepared=None):
    folder = android_downloads.folder_label(category)
    saved_count, errors, last_error = 0, 0, ""
    saved_files = []   # [(file name, content uri / path)] for the Open / Share buttons
    try:
        on_text("Looking for the files...")
        if prepared is not None:
            items = list(prepared)
        else:
            items = []
            for one in (run_id if isinstance(run_id, (list, tuple)) else [run_id]):
                items.extend(_release_files(one))
            if not items:
                items = [(android_downloads.file_name_from_url(u), u, None) for u in links]
        total = len(items)
        if not total:
            on_text("There is nothing to download here.")
            return
        # The manager keeps at most "Simultaneous downloads" (Settings) running; the others wait.
        lock = threading.Lock()
        progress_of = {}          # index -> (done, size) of the files that are running
        stopped = [0]

        def work(index, name, url, headers):
            nonlocal saved_count, errors, last_error

            def progress(done, size):
                with lock:
                    progress_of[index] = (done, size)
                    running = len(progress_of)
                    d = sum(x[0] for x in progress_of.values())
                    s = sum(x[1] for x in progress_of.values())
                on_text(_progress_text(f"Downloading {saved_count + errors + stopped[0] + running}/{total} ...", d, s))

            try:
                saved = android_downloads.download_to_downloads(
                    url, name=name, on_progress=progress, headers=headers, category=category)
                with lock:
                    saved_files.append((name or android_downloads.file_name_from_url(url),
                                        getattr(saved, "location", None)))
                    saved_count += 1
            except segmented_download.Cancelled:
                with lock:
                    stopped[0] += 1
            except Exception as e:
                with lock:
                    errors += 1
                    last_error = str(e)[:60]
            finally:
                with lock:
                    progress_of.pop(index, None)

        workers = []
        for index, (name, url, headers) in enumerate(items, 1):
            t = threading.Thread(target=work, args=(index, name, url, headers), daemon=True)
            t.start()
            workers.append(t)
        for t in workers:
            t.join()
        text = f"Saved {saved_count} of {total} file(s) in {folder}"
        if errors:
            text += f"\n{errors} failed ({last_error})"
        if stopped[0]:
            text += f"\n{stopped[0]} stopped"
        on_text(text)
        if saved_count:
            one_run = run_id if isinstance(run_id, int) else (
                run_id[0] if isinstance(run_id, (list, tuple)) and run_id else None)
            notify("YT Bridge", "Saved in Downloads", run_id=one_run)
    except Exception as e:
        on_text(f"Download failed: {str(e)[:80]}")
    finally:
        if on_finish:
            on_finish(saved_files)


# -- files picked in Release History -------------------------------------------
def start_items_download(items, on_text, on_finish=None, category="Other"):
    """Downloads the given Release History items (one or many) into the phone, with the same
    progress / Downloads manager as every other in-app download."""
    run_in_background(_run_many, None, [], category, on_text, on_finish, _history_files(items))


def _history_files(items):
    """[(name, url, headers)] of Release History items. A file of the app's own (private) repo
    needs the API link + token; Arvan and Telegram bot files have a ready public / signed link."""
    headers = None
    out = []
    for it in items:
        if it.get("asset_id") is not None and not it.get("repo"):
            if headers is None:
                headers = releases.asset_download_headers()
            out.append((it["title"], f"{API_BASE}/releases/assets/{it['asset_id']}", headers))
        else:
            out.append((it["title"], it["link"], None))
    return out


# -- sizes -------------------------------------------------------------------
def format_size(size):
    """33554432 -> '32.0 MB'; None/0 -> '?'."""
    if not size:
        return "?"
    if size < 1024:
        return f"{size} B"
    mib = size / (1024 * 1024)
    if mib >= 1024:
        return f"{mib / 1024:.2f} GB"
    if mib >= 1:
        return f"{mib:.1f} MB"
    return f"{size / 1024:.1f} KB" if size < 10 * 1024 else f"{size / 1024:.0f} KB"


def _head_size(url):
    import requests
    try:
        r = requests.head(url, allow_redirects=True, timeout=8)
        value = int(r.headers.get("Content-Length") or 0)
        return value or None
    except Exception:
        return None


def start_sizes(run_id, links, on_done):
    """``on_done([(name, size_bytes or None)])`` from a background thread: the
    sizes of the files behind a result - from the release (one request) when the
    run has one, otherwise a HEAD request per link."""
    run_in_background(_sizes_thread, run_id, list(links or []), on_done)


def _sizes_thread(run_id, links, on_done):
    items = []
    try:
        for one in (run_id if isinstance(run_id, (list, tuple)) else [run_id]):
            if one:
                items.extend((a["name"], a.get("size")) for a in releases.get_release_assets(one, attempts=1, delay=0))
        if not items:
            items = [(android_downloads.file_name_from_url(u), _head_size(u)) for u in links[:12]]
    except Exception:
        items = []
    on_done(items)


def sizes_text(items):
    """One short text for the result screen: 'Size: 32.0 MB' or the files with their sizes."""
    items = [i for i in items if i]
    if not items:
        return ""
    known = [s for _n, s in items if s]
    if len(items) == 1:
        return f"Size: {format_size(items[0][1])}"
    lines = [f"{len(items)} files" + (f", total {format_size(sum(known))}" if known else "")]
    lines += [f"{n} - {format_size(s)}" for n, s in items[:12]]
    if len(items) > 12:
        lines.append("...")
    return "\n".join(lines)
