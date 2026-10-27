"""Downloads Mornye (lossless) music on the phone itself (see api/mornye.py).

Like filimo_link_service there is no GitHub workflow here: nothing is dispatched
and nothing is polled - api.zarz.moe blocks GitHub's IPs, so the phone's own
network does everything. The only thing that needs the person is the one-time
browser check: the worker thread asks the UI to show it, then waits until the
person pastes the code (submit_grant) or cancels.

After every run the step log (no secrets) is also saved to the repo's config
branch under logs/, so a failure can be read without copying anything.
"""
import json
import queue
import shutil
import tempfile
import threading
import time

import requests

from api import mornye
from core import android_downloads, flac_tags, mornye_download
from core.async_utils import run_in_background

WAIT_SECONDS = 280          # the gateway's challenge lives 5 minutes
CATEGORY = "Mornye"
WORKFLOW = "mornye-from-links.yml"
BATCH_TRACKS = 8            # tracks per workflow run: the links expire, so send them early
BATCH_CHARS = 40000         # a dispatch carries at most 65535 characters of inputs

_grants = queue.Queue()
_cancelled = threading.Event()


def cancel() -> None:
    """Stops the running download (also frees a thread waiting for the code)."""
    _cancelled.set()
    _grants.put(None)


def submit_grant(text: str) -> bool:
    """The text the person pasted from the verification page. False if it does
    not look like a code (nothing is passed on then)."""
    if not mornye.parse_grant(text):
        return False
    _grants.put(text)
    return True


def start_download(url: str, quality: str, providers: str, progress, show_verify,
                   on_done, target: str = "phone") -> None:
    """progress(text), show_verify(challenge_url) and on_done(result) are all
    called from a background thread. target 'phone' saves the files on the phone;
    'github' sends the links to the Mornye From Links workflow, which uploads them
    to a release. on_done gets {'ok': True, 'title', 'saved', 'failed', 'folder',
    'links' (github), 'log', 'log_path'} or {'ok': False, 'error', 'log',
    'log_path'}."""
    _cancelled.clear()
    while not _grants.empty():
        try:
            _grants.get_nowait()
        except queue.Empty:
            break
    run_in_background(_thread, url, quality, providers, progress, show_verify, on_done, target)


def _cover_bytes(url: str, cache: dict) -> bytes:
    """The cover picture (kept per link: an album has one cover for all tracks)."""
    if not url:
        return b""
    if url not in cache:
        try:
            resp = requests.get(url, timeout=20)
            cache[url] = resp.content if resp.status_code == 200 else b""
        except requests.RequestException:
            cache[url] = b""
    return cache[url]


def _unique(stem: str, used: set) -> str:
    """The same artist - title twice in one run must not overwrite the first file."""
    name, n = stem, 1
    while name.lower() in used:
        n += 1
        name = "%s (%d)" % (stem, n)
    used.add(name.lower())
    return name


def _upload_log(text: str) -> str:
    """Saves the log on the config branch; '' when that did not work."""
    try:
        from api.github import repo_files
        path = "logs/mornye-%s.txt" % time.strftime("%Y%m%d-%H%M%S")
        repo_files.replace_file("config", path, text.encode("utf-8"), "log: " + path)
        return path
    except Exception:
        return ""


class _Batcher:
    """Collects tracks for the workflow and dispatches them in small batches."""

    def __init__(self, progress, title_prefix="Mornye"):
        self.items = []
        self.run_ids = []
        self.progress = progress
        self.prefix = title_prefix

    def add(self, entry):
        self.items.append(entry)
        size = len(json.dumps(self.items, ensure_ascii=False, separators=(",", ":")))
        if len(self.items) >= BATCH_TRACKS or size > BATCH_CHARS:
            self.flush()

    def flush(self):
        if not self.items:
            return
        from api.github import workflows
        batch, self.items = self.items, []
        self.progress("Sending %d track(s) to GitHub..." % len(batch))
        inputs = {
            "tracks_json": json.dumps(batch, ensure_ascii=False, separators=(",", ":")),
            "run_title": "%s %d track(s)" % (self.prefix, len(batch)),
        }
        run_id = workflows.dispatch_and_find_run(WORKFLOW, inputs)
        mornye._log("dispatched %s: %d track(s), run %s" % (WORKFLOW, len(batch), run_id))
        self.run_ids.append(run_id)


def _wait_for_uploads(batcher, progress):
    """Waits for the dispatched runs; returns (links, problems)."""
    from api.github import releases, workflows
    links, problems = [], []
    total = len(batcher.run_ids)
    for n, run_id in enumerate(batcher.run_ids, 1):
        if run_id is None:
            problems.append("a GitHub run could not be found")
            continue
        conclusion = workflows.wait_for_run(
            run_id, on_status=lambda s, n=n: progress("GitHub %d/%d: %s" % (n, total, s)),
            stop_event=_cancelled)
        mornye._log("run %s: %s" % (run_id, conclusion))
        if conclusion == "cancelled_locally":
            raise mornye.Cancelled("Cancelled")
        if conclusion != "success":
            problems.append("run %s ended: %s" % (run_id, conclusion))
            continue
        try:
            links += releases.get_release_links(run_id, attempts=4, delay=2)
        except Exception as e:
            problems.append("run %s: could not read the release (%s)" % (run_id, str(e)[:60]))
    return links, problems


def _thread(url, quality, providers, progress, show_verify, on_done, target="phone"):
    def ask(challenge_url):
        show_verify(challenge_url)
        try:
            item = _grants.get(timeout=WAIT_SECONDS)
        except queue.Empty:
            raise mornye.MornyeError("The browser check was not finished in time")
        if item is None:
            raise mornye.Cancelled("Cancelled")
        return item

    used_names, covers = set(), {}

    def handle(pos, total, track, item, numbered):
        label = " - ".join(p for p in (track["artist"], track["title"]) if p) or "track"
        work = tempfile.mkdtemp(prefix="mornye_")
        try:
            def status(text):
                progress("%d/%d %s - %s" % (pos, total, label[:40], text))
            try:
                path, ext = mornye_download.fetch(item, work, status, _cancelled.is_set)
            except mornye_download.DownloadCancelled:
                raise mornye.Cancelled("Cancelled")
            if ext == ".flac":
                meta = item.get("meta") or {}
                try:
                    flac_tags.tag_file(path, meta.get("tags"),
                                       _cover_bytes(meta.get("cover_url"), covers) or None)
                except Exception as e:      # an untagged file is still a good file
                    mornye._log("tagging failed: %s" % str(e)[:120])
            stem = _unique(mornye.file_name(pos, total, track, "", numbered), used_names)
            name = stem + ext
            android_downloads._save_in_downloads(path, name, CATEGORY)
            mornye._log("saved %s (%s, %s)" % (name, item.get("provider"), item.get("kind")))
            return name
        finally:
            shutil.rmtree(work, ignore_errors=True)

    batcher = _Batcher(progress)

    def queue_for_github(pos, total, track, item, numbered):
        stem = _unique(mornye.file_name(pos, total, track, "", numbered), used_names)
        if item.get("kind") == "dash":
            entry = {"stem": stem, "kind": "dash", **item["template"]}
        else:
            entry = {"stem": stem, "kind": "direct", "url": item["url"],
                     "ext": item.get("ext") or ".flac"}
        meta = item.get("meta") or {}
        if meta.get("tags"):
            entry["tags"] = meta["tags"]
        if meta.get("cover_url"):
            entry["cover"] = meta["cover_url"]
        batcher.add(entry)
        mornye._log("queued %s (%s, %s)" % (stem, item.get("provider"), item.get("kind")))
        return stem

    order = [p.strip() for p in str(providers or "").split(",") if p.strip()]
    github = target == "github"
    result = {}
    try:
        res = mornye.run_tracks(url, quality, order, progress, ask, _cancelled.is_set,
                                queue_for_github if github else handle)
        if github:
            batcher.flush()
            links, problems = _wait_for_uploads(batcher, progress)
            res["failed"] = list(res.get("failed") or []) + problems
            if not links:
                raise mornye.MornyeError("GitHub made no files. " + "; ".join(problems[:2]))
            res["links"] = links
            result = {"ok": True, **res, "folder": "GitHub release"}
        else:
            result = {"ok": True, **res, "folder": android_downloads.folder_label(CATEGORY)}
    except mornye.MornyeError as e:
        result = {"ok": False, "error": str(e)}
    except Exception as e:
        mornye._log("unexpected %s: %s" % (type(e).__name__, str(e)[:200]))
        result = {"ok": False, "error": "Error: %s" % str(e)[:80]}
    kind, sid = mornye.parse_spotify(url)
    header = "Mornye log %s | %s %s | providers %s | target %s | %s\n" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), kind or "?", sid or "?", providers, target,
        "OK" if result.get("ok") else "FAILED: " + str(result.get("error")))
    result["log"] = header + mornye.get_log()
    result["log_path"] = _upload_log(result["log"])
    on_done(result)
