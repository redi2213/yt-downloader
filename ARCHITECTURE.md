# YT Bridge - Architecture

The app is a thin Kivy client. GitHub Actions is the backend: the app dispatches a workflow, polls
the run, and shows the release link. Nothing runs on a server of ours.

## Branches

| Branch | Holds |
|---|---|
| `main` | the app and all workflows (the default branch: scheduled workflows only run from here) |
| `config` | data shared by every build: `config.json` (Download Anything buttons, error help), `ntfy.json`, `follows.json` + `follow-state.json` (Auto follow), `site-log.jsonl` |
| `backup` | dated zips of `main` made by the in-app updater (last 5) |

A build made from a branch other than `main` is a DEV build: other package name, version `X.Y-dev.N`,
`version.txt` untouched, and every workflow it dispatches runs on that same branch.

## Layers (UI -> services -> api; core knows nothing about Kivy or GitHub)

```
main.py            window + scroll view, hands over to the Navigator
screens/           Kivy widgets only; navigator.py is the controller (screen flow, job manager)
  style.py         theme, fonts, sizes and Persian text applied to every widget
services/          business logic, runs in background threads, reports through callbacks
api/github/        every GitHub REST call (auth, client, workflows, releases, logs, secrets, repo files)
api/*_prefs.py     small settings kept on the phone
core/              pure helpers: models, job manager, i18n, zip/file routing, run-again packing,
                   download manager (segmented downloads), follow rules, version check, sealed box
scripts/           run on GitHub runners (and some on the phone): publish, quality probe, auto follow,
                   cleanup, Aparat, site log
tests/             pytest for core/ and scripts/ (no Kivy needed); CI runs them on pull requests
```

## Main flows

- **Run a tool**: screen -> Navigator -> `services/*` -> `api/github/workflows.dispatch_and_find_run`
  (adds `job_id` / `run_title` / `rerun` inputs so the exact run is found and can be repeated) ->
  `wait_for_run` -> release link -> result screen.
- **Run again**: the inputs are packed into the run name (`core/rerun.py`) and read back later.
- **Files**: `storage_publish.py` puts them in a GitHub release `run-<id>`; the app downloads them with the
  download manager into `Download/Yt-bridge/<category>`.
- **Auto follow**: `Auto-Follow.yml` wakes on a cron the app keeps short, reads `follows.json`, and starts
  the normal download workflows with `release_tag=auto-<slug>`.
- **Notifications**: the last step of every workflow posts to the ntfy topic stored in `ntfy.json`.
- **Cleanup**: `cleanup-releases.yml` deletes `run-*` video releases after 7 days; APK builds and backups stay.

## Rules that keep it working

- New workflow inputs need a default, and the app retries without optional inputs on HTTP 422.
- Texts: English in code; Persian lives in `core/fa_strings*.py` (`tests/test_i18n.py` checks the tables).
- Anything that writes to `main` or `config` from the app (Update project, Auto follow, ntfy) needs a token
  with write access; use it carefully from a DEV build.
