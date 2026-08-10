"""Reading a playlist's video links, and downloading every video in it at a
chosen quality."""
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from api.github import workflows, releases, logs as gh_logs
from core.async_utils import run_in_background
from core.config import MAX_PARALLEL_JOBS
from core.exceptions import AuthenticationError
from core.jobs.job_manager import JobManager
from core.models.job import Job, JOB_TYPE_PLAYLIST_LINKS, JOB_TYPE_PLAYLIST_DOWNLOAD
from services.download_service import pick_format
from services.notify_service import notify

_YOUTUBE_URL_RE = re.compile(
    r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+"
)


def create_playlist_links_job(job_manager: JobManager, playlist_url: str) -> Job:
    job = Job(job_id=_new_job_id(), type=JOB_TYPE_PLAYLIST_LINKS, input=playlist_url)
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
        urls = get_playlist_links(job.input)
        if job.cancel_requested:
            return  # job already marked done by the caller's cancel action
        if not urls:
            job_manager.complete(job, ok=False, error="No videos found in playlist")
            _emit_complete(on_complete, job)
            return
        job_manager.complete(job, ok=True, result_data={"urls": urls})
        _emit_complete(on_complete, job)
    except Exception as e:
        job_manager.complete(job, ok=False, error=f"Error: {str(e)[:60]}")
        _emit_complete(on_complete, job)


def get_playlist_links(playlist_url: str):
    dispatch_time = workflows.dispatch_workflow("list-playlist.yml", {"playlist_url": playlist_url})
    run_id = workflows.get_run_id_after("list-playlist.yml", dispatch_time)
    if run_id is None:
        return []
    conclusion = workflows.wait_for_run(run_id)
    if conclusion != "success":
        return []
    log_text = gh_logs.get_run_log_text(run_id)
    urls = _YOUTUBE_URL_RE.findall(log_text)
    return list(dict.fromkeys(urls))


def create_playlist_download_job(job_manager: JobManager, urls) -> Job:
    job = Job(job_id=_new_job_id(), type=JOB_TYPE_PLAYLIST_DOWNLOAD, input=None)
    job.extra["urls"] = urls
    job.extra["total"] = len(urls)
    job_manager.start(job)
    return job


def run_playlist_download_job(job_manager: JobManager, job: Job, urls, target_height: int, want_hdr: bool,
                               on_status=None, on_complete=None) -> None:
    run_in_background(_playlist_download_thread, job_manager, job, urls, target_height, want_hdr,
                       on_status, on_complete)


def start_playlist_download(job_manager: JobManager, urls, target_height: int, want_hdr: bool,
                             on_status=None, on_complete=None) -> Job:
    """Convenience wrapper combining create+run. Prefer the split
    create/run functions when the caller needs to build UI for the job
    before the background thread can report any status."""
    job = create_playlist_download_job(job_manager, urls)
    run_playlist_download_job(job_manager, job, urls, target_height, want_hdr,
                               on_status=on_status, on_complete=on_complete)
    return job


def process_one_video(url: str, target_height: int, want_hdr: bool):
    """Runs the full format-pick + download pipeline for a single video.
    Returns (url, link_or_None, error_message_or_None)."""
    try:
        dispatch_time = workflows.dispatch_workflow("list-formats.yml", {"video_url": url})
        run_id = workflows.get_run_id_after("list-formats.yml", dispatch_time)
        if run_id is None:
            return url, None, "could not detect list-formats run"
        if workflows.wait_for_run(run_id) != "success":
            return url, None, "list-formats run failed"
        log_text = gh_logs.get_run_log_text(run_id)
        formats = gh_logs.parse_formats(log_text)
        picked = pick_format(formats, target_height, want_hdr)
        if not picked:
            return url, None, "no matching format"
        fmt_id, _label = picked

        dl_dispatch_time = workflows.dispatch_workflow(
            "download.yml", {"video_url": url, "format_id": fmt_id, "audio_only": "false"}
        )
        dl_run_id = workflows.get_run_id_after("download.yml", dl_dispatch_time)
        if dl_run_id is None:
            return url, None, "could not detect download run"
        conclusion = workflows.wait_for_run(dl_run_id)
        if conclusion != "success":
            return url, None, f"download failed ({conclusion})"
        link = releases.get_release_link(dl_run_id)
        if not link:
            return url, None, "no release link produced"
        return url, link, None
    except AuthenticationError:
        return url, None, "GitHub token invalid or expired"
    except Exception as e:
        return url, None, str(e)[:80]


def _playlist_download_thread(job_manager, job, urls, target_height, want_hdr, on_status, on_complete):
    results = []
    errors = []
    total = len(urls)
    done_count = 0
    lock = threading.Lock()

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
            pool.submit(process_one_video, url, target_height, want_hdr): url
            for url in urls
        }
        for future in as_completed(futures):
            if job.cancel_requested:
                for f in futures:
                    f.cancel()
                return  # job already marked done by the caller's cancel action
            url, link, error = future.result()
            update_progress()
            if link:
                results.append(link)
            else:
                errors.append((url, error))

    if job.cancel_requested:
        return

    if errors:
        notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready, {len(errors)} failed")
    else:
        notify("YT Bridge Git", f"Playlist done: {len(results)}/{total} ready")
    job_manager.complete(job, ok=True, result_data={"playlist_results": results, "playlist_errors": errors})
    _emit_complete(on_complete, job)


def _new_job_id():
    return uuid.uuid4().hex[:12]


def _emit(on_status, text):
    if on_status:
        on_status(text)


def _emit_complete(on_complete, job):
    if on_complete:
        on_complete(job)
