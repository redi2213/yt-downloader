# Lab and plugins

A **plugin** is a normal Python file with a `build(host)` function. The app
downloads it from GitHub when you open it, so changing a menu, a button, a
sub-menu or the logic behind it needs **no APK build**: edit the file on the
`lab` branch and open the tool again.

Nothing runs at app start. A plugin only runs when you open it, so a broken
plugin cannot stop the app from opening. Errors show a screen with the
traceback and a **Copy error** button.

## Where files live

Everything that belongs to the Lab is on the **`lab` branch**. Nothing of it
is on `main` or `config`, except one small registration file per workflow
(see "Workflows" below).

```
branch lab:
  lab/index.json         tools being tried out (listed under the Lab button)
  lab/<file>.py          their code
  lab/lib/<file>.py      optional helper modules  ->  `from labx import <file>`
  lab_scripts/           scripts their workflows run
  .github/workflows/     their workflows (the real definitions)
  logs/                  logs the tools write
branch config:
  plugins/<file>.py      finished tools, shown in Download Anything
```

## Workflows

GitHub only lets a workflow be started by its file name when a file with that
name exists on the default branch (`main`). So each Lab workflow has a tiny
**registration stub** on `main` (same file name, no real steps). When a Lab
tool calls `host.gh.dispatch("x.yml", {...})` the app starts it with
`ref=lab`, and GitHub runs the **real file from the `lab` branch**. To add a
new Lab workflow: commit the real file on `lab`, and a stub with the same name
on `main` once (or reuse `lab-run.yml`, which takes `tool` and `payload`).

`lab/index.json`:

```json
{"plugins": [
  {"id": "hello", "title": "Hello Lab", "file": "hello.py",
   "modules": ["lib/helper.py"], "description": "shown under the button",
   "min_host": 1, "enabled": true}
]}
```

## Writing a plugin

```python
def build(host):
    host.title("My tool")
    url = host.input("Link")
    mode = host.choice(["Fast", "Slow"])
    host.button("Go", lambda: host.show(result, url.text, mode.value))
    host.status()
    host.back_button("Back")          # leaves the plugin

def result(host, url, mode):
    host.title("Working")
    host.status()
    host.background(lambda: host.get_json(url), done=lambda data, err: host.set_status(err or data))
    host.back_button()
```

Rules: screens are functions `fn(host, *args)`. Button callbacks take no
arguments. Keep the Back button text starting with `Back` (the phone's Back
key presses it). Never touch widgets from a background thread: use
`host.background(..., done=...)` or `host.set_status`.

A plugin may import anything inside the APK: `kivy`, `requests`, `yt_dlp`,
`plyer`, `jnius` ...

## Host API (version 1)

| Area | Methods |
|---|---|
| Screens | `show(fn,*a)` `replace(fn,*a)` `back()` `home()` `exit()` |
| Widgets | `title` `text` `button` `row` `input` `choice` `status` `set_status` `back_button` `working` `result` `add` |
| Work | `background(fn,*a,done=)` `every(s,fn)` `after(s,fn)` `run_action(action, values)` |
| Network | `get` `post` `http` `get_json` (never send the GitHub token) |
| GitHub | `gh.dispatch` (Lab tools: runs the file from the `lab` branch; `ref=` overrides) `gh.read_file` (Lab tools read the `lab` branch) `gh.wait` `gh.cancel` `gh.release_links` `gh.release_result` `gh.request` `gh.read_file` (with the token, this repo only; blocking, use inside `background`) |
| Data | `store.get/set/delete/all` (saved per plugin), `log(...)` `show_log()` |
| Phone | `copy` `paste` `open_url` `share_text` `notify` `android()` |
| Info | `id` `source` `origin` `prefill` `app_version` `data_dir` |

`run_action` runs a workflow exactly like a Download Anything button
(progress screen, Running jobs, notification, result screen):
`host.run_action({"workflow": "x.yml", "workflow_inputs": {...}}, {...})`.

Method names never change inside one `api_version`. If one has to change, the
version goes up and a plugin can require it with `"min_host"`.

## Moving a finished tool to Download Anything

The plugin file stays the same. Only its place changes:

1. Move `lab/<file>.py` from the `lab` branch to `plugins/<file>.py` on the `config` branch. If it dispatches a workflow, that workflow must then live on `main` (a plugin from `config` runs workflows on the app's own branch).
2. Add an action to `config.json`:
   `{"id": "x", "title": "X", "plugin": "x", "file": "x.py", "source": "config", "group": "..."}`
   (`file` defaults to `<id>.py`; optional `modules`, `min_host`).

The button appears in Download Anything without a build.

## Final build

1. Copy each finished plugin into the repo as `plugins_bundled/<file>.py`
   (and helpers next to it).
2. Change its action to `"source": "bundled"`: the code now ships inside the
   APK and nothing is downloaded or executed from the internet.
3. Delete `screens/lab.py`: the Lab button disappears from the home screen
   (home.py imports it with a try/except).
4. Build.

To drop plugin loading completely, turn each plugin into a normal screen and
delete `core/plugin_loader.py`, `screens/plugin_host.py` and
`screens/plugin_runner.py`.

## Limits (these still need a build)

Android permissions, `intent_filters.xml`, `buildozer.spec`, native libraries
that are not in the APK, and changes to the Host itself.
