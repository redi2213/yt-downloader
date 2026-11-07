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

## Promote (Lab > "Promote tool to Download Anything")

Does the steps of "Moving a finished tool to Download Anything" for you, with no
APK build, and can undo them. It is itself a Lab plugin (`lab/promote.py` +
`lab/lib/promote_core.py`); the app code on `main` is never touched.

**Promote a tool**

1. Pick a tool from the Lab list. Each one shows *Lab only*, *in Download Anything* or *bundled*.
2. Pre-flight: every file is compiled (a syntax error blocks), `min_host` is checked, and
   warnings are shown for things that change after promotion (`ref="lab"`, `"lab/..."` paths,
   `gh.read_file()` without `ref=`, `dispatch(..., ref=)`). The workflows the plugin starts
   (`.dispatch("x.yml"`, `"workflow": "x.yml"`, `WORKFLOW = "x.yml"`) are found, and so are
   the scripts they run that exist only on `lab` (e.g. `lab_scripts/...`).
3. Settings: button title, action id, group, domains (share-link routing), enabled, the name
   each workflow gets on `main` (a `lab-` prefix is dropped unless that name is already used),
   copy the scripts or not, keep the tool in the Lab list or hide it.
4. Dry run: every file that will be created / overwritten, per branch. Nothing is written
   until you confirm. Overwriting a real workflow or script on `main`, a file another action
   uses, or a workflow that still checks out `lab` asks a second time.
5. Apply, one commit per branch:
   `config`: `plugins/<file>` (+ modules), `config.json` (action added or updated by id,
   `config_version` +1, everything else unchanged), `promotions.json` (the Rollback record);
   `main`: the real workflow(s) (replacing the Lab stub) and the scripts;
   `lab`: `lab/index.json` gets `"promoted": true`.
   Then it re-reads `config.json` and the plugin file to check them.
6. Open Download Anything and use **Reload list**.

Promoting the same tool again updates it (no duplicate action). `build-apk.yml` and any
workflow the plugin does not start are never touched. `version.txt` is never changed.

**Copies made with Copy tools** are marked in the Promote list ("copy of Download Anything: x").
Promoting one asks: *Replace the original* (same action id, same `plugins/x.py`, the button keeps its
title, group and domains) or *Add as a new tool*. For every workflow the tool starts that already
exists on `main` as a real file, it asks: *Replace it on main* (shows what changes, asks again) or
*Add as a new workflow* (a free name such as `x-v2.yml`; the plugin's copy on `config` is changed to
start it and the original workflow stays untouched).

**Rollback**: lists the promotions. It restores the previous action (or removes the new
one), deletes the files the promotion created, puts back the files and workflows it
replaced (a Lab stub comes back as the stub) and clears the `promoted` flag. `config_version`
goes **up** by one, never back, so phones notice the change. If it stops halfway, run
Rollback again: it only redoes what is left.

**Test write access** pushes and deletes a throw-away branch with a workflow file to
check the app's GitHub sign-in may write workflow files (a GitHub App needs the
*Workflows: read and write* permission). Nothing else changes.

If Apply fails after the config step, the screen lists what was done and offers Rollback.

Self-test of the pure logic (config upsert, workflow detection, stub detection ...):
`python lab/lib/promote_core.py` (prints `ok`).

## Add workflow (Lab > "Add workflow (link or paste)")

Brings a workflow made somewhere else into the Lab as a new tool under test.

1. **Source**: any of these
   - **Upload from the phone**: the system file picker, several files at once. Pick the `.yml` and,
     if it runs scripts, the scripts too (`.py`, `.sh`, `requirements.txt`): they are matched by file
     name to what the workflow runs (`python scripts/x.py` <- the picked `x.py`) and put at that path
     on the lab branch; modules a picked script imports are matched too. Files that are not used are
     listed and ignored. Works only inside the app on the phone.
   - a link to a public GitHub file, folder (`.github/workflows`) or repo (the scripts the workflow
     runs are fetched from the same repo);
   - pasted `.yml` text (scripts cannot come with it: the check lists the missing ones).
2. **Check** against what the app needs: `workflow_dispatch`, the `job_id` / `run_title` inputs,
   `run-name` containing `inputs.job_id`, the release tag `run-${{ github.run_id }}`,
   `contents: write` for releases, other triggers (a `push` trigger would run it on every push to
   lab), inputs used but not declared, files it runs, secrets it uses. Problems that can be fixed
   automatically are marked; choose "Apply the suggested fixes" (the default) or "Add exactly as it is".
3. **Add to the Lab**: `lab` gets the workflow (as `lab-<name>.yml`, editable), the scripts, a small
   plugin `lab/wf_<id>.py` and an index entry; `main` gets a registration stub with the same name and
   inputs (GitHub starts a workflow by file name only when it exists on main). Nothing is overwritten:
   a name that exists on main, or a script that exists on lab with different content, is refused.
4. **The new tool** (Lab > its name): a form made from the workflow's inputs, **Run** (waits, shows the
   release files or the failure), **Check workflow** (the same static check, with **Apply fixes** that
   also keeps the stub in step), **Report of the last run**.
   A failed run shows the failed step and the probable causes in plain words (missing Python package,
   missing file, 403, tag already exists ...). **Copy report** puts the causes, the log tail, the checks
   and the workflow file in one text to paste for help.
5. **My imported tools**: update (from the source link, or by uploading / pasting a new version), or remove (deletes the files, the index entry
   and the stub; a workflow already promoted to Download Anything is kept).
6. When it works, use **Promote**.

Self-test of the pure logic: `python lab/lib/wf_core.py` (prints `ok`).

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
