# YT Bridge — Architecture

## Layers

```
screens/          UI (Kivy widgets only: build, show input, bind buttons)
  navigator.py     Application/Controller: screen flow, job manager, app-level state
                   (Navigator(ArvanController): arvan_controller.py is a mixin)
  common.py        shared widget helpers (labels, back button, "working" screen)
  style.py         theme / font / size / Persian (RTL) applied to every widget
  home, youtube_download, download, upload, playlist, result, history, arvan,
  downloads, follow, settings, appearance, health, site_log, runs_browser,
  actions_status, proxy_settings, mornye_*, release_file, ...
  lab.py, plugin_host.py, plugin_runner.py   Lab + plugins (see below)

services/         Business logic (no Kivy import except notify_service -> plyer)
  download_service, playlist_service, upload_service, generic_action_service
  history_service (Releases), arvan_service, storage_service (old storage mode)
  actions_service, runs_service, run_progress_service, job_service
  follow_service, health_service, site_log_service, ntfy_service
  repo_update_service, update_check_service, remote_config_service
  proxy_secret_service (V2RAY_CONFIG secret)
  Run on the PHONE (no GitHub run): phone_youtube_service, anysite_phone_service,
  aparat_service, filimo_link_service, mornye_link_service

api/              GitHub REST calls + external services + on-device settings
  github/          auth, client (session, retries, error mapping), workflows,
                   releases, logs, repo_files, secrets, remote_config, device_auth
  mornye.py, filimo.py     services reached from the phone's own network
  *_prefs.py       small settings kept on the phone (JsonStore)

core/             Kivy-independent, GitHub-independent (pure Python)
  config.py, exceptions.py, models/job.py, jobs/job_manager.py, async_utils.py
  download_manager.py, segmented_download.py   chunked download with Pause/Resume
  plugin_loader.py   loads Lab / Download Anything plugin code
  i18n.py, fa_strings*.py, appearance.py       language and themes
  retention.py, rerun.py, follow.py, links.py, youtube_links.py, share_routing.py ...
  android_*.py     pyjnius helpers (share, open, install, notify, files)
  fmp4_flac.py, flac_tags.py, mornye_download.py   lossless music on the phone

scripts/          Run INSIDE workflows (never imported by the app, except aparat_core)
  storage_publish, storage_core, quality_probe, retention_core, cleanup_releases
  auto_follow, aparat_*, batch_download, arvan_tool, arvan_maintenance
  xray_setup, find_proxies, xh_*, mornye_fetch, site_log, finglish_name

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
Navigator imports Kivy's Clock. While the app is in the background Kivy's
clock stops, so work that must continue (downloads, auto build/install)
is started from worker threads, not from scheduled callbacks.

## How a workflow run is found and shown

1. `api/github/workflows.dispatch_and_find_run` sends the inputs plus a unique
   `job_id` (and `run_title`, `rerun`); the workflow puts them in its `run-name`,
   so the app finds exactly its own run.
2. The workflow publishes to release `run-<run_id>`; hidden blocks in the
   description (`ytb-quality`, `ytb-storage`, `ytb-keep`) carry quality, Arvan
   links and retention dates.
3. `rerun` packs the inputs into the run name, so "Run again" can repeat a run.

## Remote config and plugins (no rebuild needed)

- Branch `config`: `config.json` (Download Anything buttons, error help),
  `follows.json` / `follow-state.json`, `ntfy.json`, `site-log.jsonl`, `plugins/`.
- Branch `lab`: tools being tried out (`lab/index.json`).
- A plugin is a Python file with `build(host)`. `core/plugin_loader.py` fetches it
  (source: lab / config / bundled), `screens/plugin_host.py` gives it the `host`
  object. Plugin code runs only when the user opens it, never at app start.

## Adding a new client (e.g. a Telegram bot)

Everything under `services/` and `api/` is plain Python with no Kivy
dependency. A new client just needs its own thin "screens" layer that
calls the same `services.download_service.start_download(...)`, etc., and
supplies its own `on_status`/`on_complete` callbacks.
