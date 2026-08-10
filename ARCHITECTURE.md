# YT Bridge Git — Architecture (v1.4-refactor)

## Layers

```
screens/          UI (Kivy widgets only: build, show input, bind buttons)
  navigator.py     Application/Controller: screen flow, job manager, app-level state
  common.py        shared widget helpers (labels, back button, "working" screen)
  home.py, download.py, upload.py, playlist.py,
  result.py, job_history.py, history.py,
  actions_status.py, about.py

services/         Business logic (no Kivy import except notify_service->plyer)
  download_service.py    fetch formats, download a single video, pick_format()
  upload_service.py      upload-from-link flow
  playlist_service.py    playlist link listing + parallel playlist download
  history_service.py     live GitHub Releases: list/delete/rename/zip
  actions_service.py     GitHub Actions run list / run detail
  job_service.py         generic cancel (shared by every job kind)
  token_service.py       GitHub token get/save (thin pass-through to api.github.auth)
  notify_service.py      OS notifications

api/github/       All GitHub REST calls, nothing else
  auth.py          token storage + auth headers (JsonStore)
  client.py        HTTP session, retries, error mapping (NetworkError/AuthenticationError)
  workflows.py     dispatch/poll/cancel workflow runs, list recent runs, run steps
  releases.py      release link polling, live history, delete, rename asset
  logs.py          run log fetch + yt-dlp "-F" output parsing

core/             Kivy-independent, GitHub-independent
  config.py        constants (repo, timeouts, app version, ...)
  exceptions.py    AuthenticationError, NetworkError, WorkflowError, DownloadError,
                   UploadError, FormatError, CancellationError, ConfigurationError
  models/job.py    Job dataclass (job_id, type, stage, status, run_id, input,
                   result, error, retry, cancel_requested, extra)
  jobs/job_manager.py  tracks current_job + a short finished-job history
  async_utils.py   run_in_background() - one place that starts daemon threads

main.py           Composition root only: builds the Kivy window/scroll/content
                  container and hands off to Navigator. No business logic.
```

## Flow

```
Kivy screen (button press)
      -> Navigator (screens/navigator.py)
            -> services/*_service.py   (spawns a background thread)
                  -> api/github/*.py   (talks to GitHub)
```

Background threads report progress/results through plain callbacks
(`on_status(text)`, `on_complete(job)`). Screens pass in callbacks that hop
back onto the main thread via `Clock.schedule_once` (done once, centrally,
in `Navigator.set_status` / `Navigator.schedule`). Nothing below the
Navigator ever imports Kivy's Clock.

## Adding a new client (e.g. a Telegram bot)

Everything under `services/` and `api/` is plain Python with no Kivy
dependency. A new client just needs its own thin "screens" layer that
calls the same `services.download_service.start_download(...)`, etc., and
supplies its own `on_status`/`on_complete` callbacks (e.g. editing a
Telegram message instead of a Kivy Label).

## Behavior preserved 1:1 from v1.3

All features work exactly as before: single video download (with HDR/size/codec
shown per quality), audio-only, playlist link listing + bulk playlist download
with quality presets, upload-from-link with optional zip/rename, cancel and
"pick a different quality" mid-job, retry-only-the-broken-step after a network
hiccup, in-memory recent-jobs list (last 5), live GitHub Releases history with
delete/bulk-delete/rename/zip, GitHub Actions status + run step detail, and
GitHub token management. One pre-existing quirk was intentionally *not*
preserved: a successful upload used to jump to the "Ready!" screen even if the
user had already navigated to a different job in the meantime (every other job
kind guards against this); it's now consistent with the rest of the app.

`history_patch.py` at the project root was already a standalone Termux CLI
utility not wired into the Kivy app, so it was left untouched.
