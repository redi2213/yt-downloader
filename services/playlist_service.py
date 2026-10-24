"""Reading a playlist's video links, and downloading every video in it at a
chosen quality."""
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from api import run_mode_prefs
from api.github import workflows, releases, logs as gh_logs
from core.async_utils import run_in_background
from core.config import MAX_PARALLEL_JOBS, PLAYLIST_POLL_INTERVAL
from core.exceptions import AuthenticationError, NetworkError
from core.jobs.job_manager import JobManager
from core.models.job import Job, JOB_TYPE_PLAYLIST_LINKS, JOB_TYPE_PLAYLIST_DOWNLOAD
from services.download_service import pick_format
from services import phone_youtube_service
from services.notify_service import notify

_YOUTUBE_URL_RE = re.compile(
    r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+"
)
# list-playlist.yml prints one "ITEM|<video id>|<title>" line per video
_ITEM_RE = re.compile(r"ITEM\|([\w-]{11})\|([^\r\n]*)")


def start_playlist_quick(job_manager: JobManager, playlist_url: str, target_height: int, want_hdr: bool,
                          audio_only: bool = False, on_status=None, on_complete=None) -> Job:
    """Combo flow for the "This is a playlist" quick-quality buttons: reads
    the playlist's video links, then immediately starts downloading every
    one of them at the given quality - no intermediate "pick a quality for
    these N videos" screen, since the quality was already chosen up front.

    Returns the JOB_TYPE_PLAYLIST_DOWNLOAD job immediately so the caller can
    show a working screen against it right away; the link-reading step runs
    first in the background and the download step is chained after it."""
    job = create_playlist_download_job(job_manager, urls=[])
    run_in_background(
        _playlist_quick_thread, job_manager, job, playlist_url,
        target_height, want_hdr, audio_only, on_status, on_complete
    )
    return job


def _playlist_quick_thread(job_manager, job, playlist_url, target_height, want_hdr, audio_only,
                            on_status, on_complete):
    try:
        _emit(on_status, "Reading playlist...")
        entries = get_playlist_entries(playlist_url)
        if job.cancel_requested:
            return  # job already marked done by the caller's cancel action
        if not entries:
            job_manager.complete(job, ok=False, error="No videos found in playlist")
            _emit_complete(on_complete, job)
            return
        urls = [e["url"] for e in entries]
        items = _make_items(urls, {e["url"]: e["title"] for e in entries})
        job.extra["urls"] = urls
        job.extra["total"] = len(urls)
        job.extra["items"] = items
        job.extra["run_items"] = items
    except Exception as e:
        job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)
        return

    _playlist_download_thread(job_manager, job, urls, target_height, want_hdr, audio_only, on_status, on_complete)


def create_playlist_links_job(job_manager: JobManager, playlist_url: str, pick: bool = False,
                              where: str = None, sort: str = None, limit: int = None) -> Job:
    """``pick=True``: the result is shown as a list of titles to choose from
    (the "Choose videos" button) instead of going straight to the quality
    picker for the whole playlist."""
    job = Job(job_id=_new_job_id(), type=JOB_TYPE_PLAYLIST_LINKS, input=playlist_url)
    job.extra["pick"] = pick
    job.extra["sort"] = sort
    job.extra["limit"] = limit
    job.extra["where"] = where or run_mode_prefs.get_mode()
    job_manager.start(job)
    return job


def run_playlist_links_job(job_manager: JobManager, job: Job, on_status=None, on_complete=None) -> None:
    run_in_background(_fetch_playlist_thread, job_manager, job, on_status, on_complete)


def start_fetch_playlist_links(job_manager: JobManager, playlist_url: str,
                                on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_playlist_links_job(job_manager, playlist_url)
    run_playlist_links_job(job_manager, job, on_status=on_status, on_complete=on_complete)
    return job


def _fetch_playlist_thread(job_manager, job, on_status, on_complete):
    try:
        _emit(on_status, "Reading playlist...")
        entries = get_playlist_entries(job.input, where=job.extra.get("where"), on_status=on_status,
                                       sort=job.extra.get("sort"), limit=job.extra.get("limit"))
        if job.cancel_requested:
            return  # job already marked done by the caller's cancel action
        if not entries:
            job_manager.complete(job, ok=False, error="No videos found in playlist")
            _emit_complete(on_complete, job)
            return
        urls = [e["url"] for e in entries]
        job_manager.complete(job, ok=True, result_data={"urls": urls, "entries": entries})
        _emit_complete(on_complete, job)
    except Exception as e:
        job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def parse_playlist_entries(log_text: str) -> list:
    """[{"url", "title"}] from a list-playlist run's log, in playlist order.
    Falls back to plain links (title = link) if the workflow is the old one
    that printed only links."""
    entries, seen = [], set()
    for video_id, title in _ITEM_RE.findall(log_text):
        if video_id in seen:
            continue
        seen.add(video_id)
        entries.append({
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "title": title.strip() or video_id,
        })
    if entries:
        return entries
    return [{"url": u, "title": u} for u in dict.fromkeys(_YOUTUBE_URL_RE.findall(log_text))]


def get_playlist_entries(playlist_url: str, where: str = None, on_status=None, sort: str = None,
                         limit: int = None) -> list:
    """The playlist's videos. ``where``: "github", "phone" or "auto" (phone
    first, GitHub when it finds nothing); None = the Settings default."""
    where = where or run_mode_prefs.get_mode()
    if where in ("phone", "auto"):
        _emit(on_status, "Reading the playlist on this phone...")
        try:
            entries = phone_youtube_service.list_playlist(playlist_url, sort, limit)
        except Exception:
            entries = []
        if entries or where == "phone":
            return entries[:limit] if limit else entries
        _emit(on_status, "The phone could not do it - using GitHub...")
    inputs = {"playlist_url": playlist_url}
    if sort:
        inputs.update({"sort": sort, "limit": str(limit or 30)})
    run_id = workflows.dispatch_and_find_run("list-playlist.yml", inputs)
    if run_id is None:
        return []
    conclusion = workflows.wait_for_run(run_id)
    if conclusion != "success":
        return []
    found = parse_playlist_entries(gh_logs.get_run_log_text(run_id))
    return found[:limit] if limit else found


def get_playlist_links(playlist_url: str):
    return [e["url"] for e in get_playlist_entries(playlist_url)]


# ---- per-video items -------------------------------------------------------
# A playlist download keeps one small record per video in job.extra["items"]
# (the screen draws them): state is waiting | listing | downloading | done |
# failed. The worker threads update the records as they go.
_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/)([\w-]+)")


def _make_items(urls, titles=None):
    titles = titles or {}
    items = []
    for u in urls:
        m = _VIDEO_ID_RE.search(u)
        items.append({
            "url": u,
            "title": titles.get(u) or (m.group(1) if m else u),
            "state": "waiting",
            "link": None,
            "error": None,
            "run_id": None,        # the download run, once it is dispatched
            "net_error": False,    # failed only because the connection dropped
        })
    return items


def _summarize(items, settings):
    """The job's result payload, rebuilt from the per-video items."""
    return {
        "playlist_results": [i["link"] for i in items if i["state"] == "done"],
        "playlist_errors": [(i["url"], i["error"] or "failed") for i in items if i["state"] == "failed"],
        "playlist_items": items,
        # what "Retry failed" needs to run videos the same way again
        "playlist_settings": settings,
    }


def create_playlist_download_job(job_manager: JobManager, urls, titles=None, previous_items=None) -> Job:
    """``previous_items``: the item list of an earlier run when only some of
    its videos are being retried - the other videos keep their state (and
    links), the ones in ``urls`` start again from "waiting", all in the
    original order."""
    job = Job(job_id=_new_job_id(), type=JOB_TYPE_PLAYLIST_DOWNLOAD, input=None)
    if previous_items:
        redo = set(urls)
        items, run_items = [], []
        for old in previous_items:
            if old["url"] in redo:
                fresh = _make_items([old["url"]], {old["url"]: old["title"]})[0]
                items.append(fresh)
                run_items.append(fresh)
            else:
                items.append(dict(old))
    else:
        run_items = _make_items(urls, titles)
        items = run_items
    job.extra["urls"] = urls
    job.extra["total"] = len(urls)
    job.extra["items"] = items
    job.extra["run_items"] = run_items
    job_manager.start(job)
    return job


def run_playlist_download_job(job_manager: JobManager, job: Job, urls, target_height: int, want_hdr: bool,
                               audio_only: bool = False, on_status=None, on_complete=None) -> None:
    run_in_background(_playlist_download_thread, job_manager, job, urls, target_height, want_hdr,
                       audio_only, on_status, on_complete)


def start_playlist_download(job_manager: JobManager, urls, target_height: int, want_hdr: bool,
                             audio_only: bool = False, on_status=None, on_complete=None,
                             titles=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_playlist_download_job(job_manager, urls, titles=titles)
    run_playlist_download_job(job_manager, job, urls, target_height, want_hdr,
                               audio_only=audio_only, on_status=on_status, on_complete=on_complete)
    return job


def _net_retry(fn, *args, tries: int = 6, delay: float = 8, **kwargs):
    """Calls fn, trying again when the connection to GitHub drops."""
    for attempt in range(tries):
        try:
            return fn(*args, **kwargs)
        except NetworkError:
            if attempt == tries - 1:
                raise
            time.sleep(delay)


def _mark(item, **fields):
    if item is not None:
        item.update(fields)


def process_one_video(url: str, target_height: int, want_hdr: bool, audio_only: bool = False, item=None):
    """Runs the full format-pick + download pipeline for a single video.
    Returns (url, link_or_None, error_message_or_None). ``item`` (optional)
    is the video's record, kept up to date for the progress screen."""
    try:
        if audio_only:
            fmt_id = "bestaudio"
        else:
            _mark(item, state="listing")
            run_id = workflows.dispatch_and_find_run("list-formats.yml", {"video_url": url})
            if run_id is None:
                return url, None, "could not detect list-formats run"
            if workflows.wait_for_run(run_id, poll_interval=PLAYLIST_POLL_INTERVAL) != "success":
                return url, None, "list-formats run failed"
            log_text = _net_retry(gh_logs.get_run_log_text, run_id)
            formats = gh_logs.parse_formats(log_text)
            picked = pick_format(formats, target_height, want_hdr)
            if not picked:
                return url, None, "no matching format"
            fmt_id, _label = picked

        _mark(item, state="downloading")
        dl_run_id = workflows.dispatch_and_find_run(
            "download.yml", {"video_url": url, "format_id": fmt_id, "audio_only": "true" if audio_only else "false"}
        )
        if dl_run_id is None:
            return url, None, "could not detect download run"
        _mark(item, run_id=dl_run_id)
        conclusion = workflows.wait_for_run(dl_run_id, poll_interval=PLAYLIST_POLL_INTERVAL)
        if conclusion != "success":
            return url, None, f"download failed ({conclusion})"
        link = releases.get_release_link(dl_run_id, attempts=30)
        if not link:
            return url, None, "no release link produced"
        return url, link, None
    except AuthenticationError:
        return url, None, "GitHub token invalid or expired"
    except NetworkError:
        _mark(item, net_error=True)
        if item is not None and item.get("run_id"):
            return url, None, "connection lost - it may have finished, tap Recheck failed"
        return url, None, "connection lost - tap Retry"
    except Exception as e:
        return url, None, str(e)[:80]


def _run_item(item, target_height, want_hdr, audio_only):
    _url, link, error = process_one_video(item["url"], target_height, want_hdr, audio_only, item=item)
    if link:
        item.update(state="done", link=link, error=None)
    else:
        item.update(state="failed", error=error or "failed")


def _try_recover(item, attempts: int = 3) -> bool:
    """A video that "failed" because the connection dropped after its
    download run started may well have finished: look for its release."""
    try:
        link = releases.get_release_link(item["run_id"], attempts=attempts, delay=2)
    except Exception:
        return False
    if link:
        item.update(state="done", link=link, error=None, net_error=False)
        return True
    return False


def recheck_failed(job: Job, on_complete=None) -> None:
    """Looks again, in the background, for the releases of failed videos
    whose download run is known (e.g. after a network drop)."""
    run_in_background(_recheck_thread, job, on_complete)


def _recheck_thread(job, on_complete):
    items = job.extra.get("items") or []
    for item in items:
        if item["state"] == "failed" and item.get("run_id"):
            _try_recover(item)
    if job.result is not None:
        job.result.update(_summarize(items, job.extra.get("settings")))
    if on_complete:
        on_complete(job)


def _playlist_download_thread(job_manager, job, urls, target_height, want_hdr, audio_only, on_status, on_complete):
    run_items = job.extra.get("run_items") or []
    total = len(run_items)
    done_count = 0
    lock = threading.Lock()
    settings = {"height": target_height, "hdr": want_hdr, "audio_only": audio_only}
    job.extra["settings"] = settings

    def update_progress():
        nonlocal done_count
        with lock:
            done_count += 1
            job.status = f"Processing {done_count}/{total}"
            _emit(on_status, f"Processing {done_count}/{total}...")

    # Process multiple videos concurrently instead of one-at-a-time, since
    # each video's work is a separate GitHub Actions run anyway.
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS) as pool:
        futures = {
            pool.submit(_run_item, item, target_height, want_hdr, audio_only): item
            for item in run_items
        }
        for future in as_completed(futures):
            if job.cancel_requested:
                for f in futures:
                    f.cancel()
                return  # job already marked done by the caller's cancel action
            future.result()
            update_progress()

    if job.cancel_requested:
        return

    # Videos lost to a dropped connection after their run started: look once
    # for the release before calling them failed.
    for item in run_items:
        if item["state"] == "failed" and item.get("net_error") and item.get("run_id"):
            _try_recover(item)

    ok = sum(1 for i in run_items if i["state"] == "done")
    bad = total - ok
    if bad:
        notify("YT Bridge Git", f"Playlist done: {ok}/{total} ready, {bad} failed")
    else:
        notify("YT Bridge Git", f"Playlist done: {ok}/{total} ready")
    job_manager.complete(job, ok=True, result_data=_summarize(job.extra["items"], settings))
    _emit_complete(on_complete, job)


def _new_job_id():
    return uuid.uuid4().hex[:12]


def _emit(on_status, text):
    if on_status:
        on_status(text)


def _emit_complete(on_complete, job):
    if on_complete:
        on_complete(job)
