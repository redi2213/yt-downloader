"""Lab: Copy tools.

Makes a safe copy of a main workflow or a finished plugin on the `lab` branch, so it
can be edited and tried without touching the original.

* workflow  .github/workflows/<name>.yml (main)  ->  same path on the lab branch,
  together with the repo files it runs (e.g. scripts/). The app starts it with
  ref=lab, so GitHub runs the lab copy; every normal button still runs main's file.
* plugin    plugins/<name>.py (config)  ->  lab/<name>_copy.py + an entry in lab/index.json,
  so it shows up in the Lab list.

Nothing here changes main or config. "Discard" deletes the copy from lab.
"""
import base64
import json
import re
import threading
import time

WF_DIR = ".github/workflows"
SKIP_INPUTS = ("job_id", "rerun", "run_title")      # set by the app itself
MAX_FILE = 300000
_STATUS_TEXT = {"queued": "Queued on GitHub", "in_progress": "Running", "completed": "Finishing"}


# ---------------------------------------------------------------- GitHub helpers
def _req(host, method, path, **kw):
    last = None
    for attempt in range(3):
        try:
            return host.gh.request(method, path, **kw)
        except Exception as e:           # 409 right after another commit on the branch
            last = e
            if attempt < 2 and ("409" in str(e) or "422" in str(e)):
                time.sleep(1.5)
                continue
            raise
    raise last


def _tree(host, ref):
    r = _req(host, "GET", "/git/trees/%s" % ref, params={"recursive": "1"}).json()
    return {t["path"]: t for t in r.get("tree", []) if t.get("type") == "blob"}


def _sha(host, path, ref="lab"):
    try:
        return _req(host, "GET", "/contents/" + path, params={"ref": ref}).json().get("sha")
    except Exception:
        return None


def _write_lab(host, path, text, message):
    body = {"message": message, "branch": "lab",
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    sha = _sha(host, path)
    if sha:
        body["sha"] = sha
    _req(host, "PUT", "/contents/" + path, json=body)


def _delete_lab(host, path, message):
    sha = _sha(host, path)
    if sha:
        _req(host, "DELETE", "/contents/" + path, json={"message": message, "sha": sha, "branch": "lab"})


def _index(host):
    text = host.gh.read_file("lab/index.json", ref="lab")
    data = json.loads(text)
    return data if isinstance(data, dict) else {"plugins": data}


def _save_index(host, data, message):
    _write_lab(host, "lab/index.json", json.dumps(data, indent=2, ensure_ascii=False) + "\n", message)


# ---------------------------------------------------------------- workflow inputs
def parse_inputs(text):
    """{name: {description, required, default, type, options}} of workflow_dispatch."""
    lines = text.splitlines()
    out, i, n = {}, 0, len(lines)

    def indent(s):
        return len(s) - len(s.lstrip(" "))

    while i < n and not re.match(r"^\s*workflow_dispatch:\s*$", lines[i]):
        i += 1
    i += 1
    while i < n and not re.match(r"^\s*inputs:\s*$", lines[i]):
        if lines[i].strip() and not lines[i].lstrip().startswith("#") and indent(lines[i]) == 0:
            return out
        i += 1
    if i >= n:
        return out
    base = indent(lines[i])
    i += 1
    head_indent, cur = None, None
    while i < n:
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        ind = indent(line)
        if ind <= base:
            break
        if head_indent is None:
            head_indent = ind
        s = line.strip()
        if ind == head_indent:
            m = re.match(r"^([\w\-]+):\s*$", s)
            if not m:
                continue
            cur = {"description": "", "required": False, "default": "", "type": "string", "options": []}
            out[m.group(1)] = cur
            continue
        if cur is None:
            continue
        if s.startswith("- "):
            cur["options"].append(_unq(s[2:]))
            continue
        m = re.match(r"^([\w\-]+):\s*(.*)$", s)
        if not m:
            continue
        key, val = m.group(1), _unq(m.group(2))
        if key == "required":
            cur["required"] = val.lower() == "true"
        elif key in ("description", "default", "type"):
            cur[key] = val
    return out


def _unq(v):
    v = v.strip()
    if " #" in v and not v.startswith(("'", '"')):
        v = v.split(" #", 1)[0].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


# ---------------------------------------------------------------- main screen
def build(host):
    host.title("Copy tools")
    host.text("Make a copy on the lab branch, edit it there and try it. The originals "
              "(main, config) are never touched.")
    host.button("Copy a workflow (from main)", lambda: host.show(_pick, "workflow"))
    host.button("Copy a plugin (from config)", lambda: host.show(_pick, "plugin"))
    host.button("My copies: run / discard", lambda: host.show(_copies))
    host.status()
    host.back_button("Back")


# ---------------------------------------------------------------- pick + copy
def _pick(host, kind):
    host.title("Copy a " + kind)
    host.status()
    host.set_status("Loading...")
    host.back_button()
    host.background(_list_originals, host, kind,
                    done=lambda res, err: host.replace(_pick_list, kind, res) if err is None
                    else host.set_status("Error: %s" % str(err)[:150]))


def _list_originals(host, kind):
    if kind == "workflow":
        main = [i["name"] for i in _req(host, "GET", "/contents/" + WF_DIR, params={"ref": "main"}).json()
                if i["name"].endswith((".yml", ".yaml")) and not i["name"].startswith("lab-")]
        have = set(_tree(host, "lab"))
        return sorted(n for n in main if WF_DIR + "/" + n not in have)
    plugins = [i["name"] for i in _req(host, "GET", "/contents/plugins", params={"ref": "config"}).json()
               if i["name"].endswith(".py")]
    idx = {p.get("file") for p in _index(host).get("plugins", [])}
    return sorted(n for n in plugins if n[:-3] + "_copy.py" not in idx)


def _pick_list(host, kind, names):
    host.title("Copy a " + kind)
    if not names:
        host.text("Nothing left to copy.")
    for name in names:
        host.button(name, lambda n=name: host.show(_copy_run, kind, n))
    host.back_button()


def _copy_run(host, kind, name):
    host.title("Copying " + name)
    host.status()
    host.set_status("Copying to the lab branch...")
    host.back_button()
    host.background(_copy_workflow if kind == "workflow" else _copy_plugin, host, name,
                    done=lambda res, err: host.replace(_copy_done, res) if err is None
                    else host.set_status("Error: %s" % str(err)[:200]))


def _copy_done(host, message):
    host.title("Done")
    host.text(message)
    host.button("My copies: run / discard", lambda: host.replace(_copies))
    host.back_button("Back")


def _copy_workflow(host, name):
    text = host.gh.read_file(WF_DIR + "/" + name, ref="main")
    main_tree, lab_tree = _tree(host, "main"), _tree(host, "lab")
    wanted = set()
    for tok in set(re.findall(r"[\w./\-]+", text)):
        tok = tok.strip("./") if tok.startswith("./") else tok
        if tok in main_tree and not tok.startswith(".github/"):
            d = tok.rsplit("/", 1)[0] if "/" in tok else ""
            if d:
                wanted |= {p for p in main_tree if p.rsplit("/", 1)[0] == d and "/" in p}
            else:
                wanted.add(tok)
    copied, skipped = 0, []
    for path in sorted(wanted):
        if path in lab_tree:
            continue
        if main_tree[path].get("size", 0) > MAX_FILE:
            skipped.append(path)
            continue
        try:
            content = host.gh.read_file(path, ref="main")
        except Exception:
            skipped.append(path)
            continue
        host.set_status("Copying %s..." % path)
        _write_lab(host, path, content, "lab: copy %s (for %s)" % (path, name))
        copied += 1
    _write_lab(host, WF_DIR + "/" + name, text, "lab: copy of workflow %s from main" % name)
    host.log("copied workflow", name, copied, "file(s)", skipped)
    msg = "Copied %s to the lab branch" % name
    if copied:
        msg += " with %d file(s) it runs (e.g. scripts)" % copied
    if skipped:
        msg += ". Not copied (big or not text): " + ", ".join(skipped)
    return msg + ".\n\nEdit it on GitHub (branch lab). \"Run from lab\" starts the copy; the normal buttons still run main."


def _copy_plugin(host, name):
    stem = name[:-3]
    text = host.gh.read_file("plugins/" + name, ref="config")
    modules = []
    try:
        cfg = json.loads(host.gh.read_file("config.json", ref="config"))
        for a in cfg.get("actions", []):
            if a.get("plugin") == stem:
                modules = list(a.get("modules") or [])
    except Exception:
        pass
    lab_tree = _tree(host, "lab")
    for mod in modules:
        target = "lab/" + mod
        if target in lab_tree:
            continue
        host.set_status("Copying %s..." % mod)
        _write_lab(host, target, host.gh.read_file("plugins/" + mod, ref="config"), "lab: copy module %s" % mod)
    _write_lab(host, "lab/%s_copy.py" % stem, text, "lab: copy of plugin %s from config" % name)
    data = _index(host)
    entry = {"id": stem + "_copy", "title": "%s (copy)" % stem, "file": stem + "_copy.py",
             "description": "Lab copy of plugins/%s. The original is untouched." % name, "min_host": 1}
    if modules:
        entry["modules"] = modules
    data["plugins"] = [p for p in data.get("plugins", []) if p.get("id") != entry["id"]] + [entry]
    _save_index(host, data, "lab: add %s_copy to the index" % stem)
    host.log("copied plugin", name, modules)
    return "Copied %s as lab/%s_copy.py. It is in the Lab list now as \"%s\". Edit it on GitHub (branch lab)." % (
        name, stem, entry["title"])


# ---------------------------------------------------------------- my copies
def _copies(host):
    host.title("My copies")
    host.status()
    host.set_status("Loading...")
    host.back_button()
    host.background(_list_copies, host,
                    done=lambda res, err: host.replace(_copies_list, res) if err is None
                    else host.set_status("Error: %s" % str(err)[:150]))


def _list_copies(host):
    lab = _tree(host, "lab")
    wfs = sorted(p.split("/")[-1] for p in lab if p.startswith(WF_DIR + "/") and p.count("/") == 2
                 and not p.split("/")[-1].startswith("lab-"))
    main_names = {i["name"] for i in _req(host, "GET", "/contents/" + WF_DIR, params={"ref": "main"}).json()}
    plugins = [p for p in _index(host).get("plugins", []) if str(p.get("id", "")).endswith("_copy")]
    return {"wfs": wfs, "main": sorted(main_names), "plugins": plugins}


def _copies_list(host, res):
    host.title("My copies")
    if not res["wfs"] and not res["plugins"]:
        host.text("No copies yet.")
    for name in res["wfs"]:
        host.button("Workflow: " + name, lambda n=name: host.show(_wf_menu, n, n in res["main"]))
    for p in res["plugins"]:
        host.button("Plugin: " + p["id"], lambda e=p: host.show(_plugin_menu, e))
    host.back_button()


def _wf_menu(host, name, on_main):
    host.title(name)
    if on_main:
        host.button("Run from lab", lambda: host.show(_run_load, name))
    else:
        host.text("Not on main, so the app cannot start it by name yet (it needs a stub file on main).")
    host.button("Discard this copy", lambda: host.show(_discard, "workflow", name))
    host.back_button()


def _plugin_menu(host, entry):
    host.title(entry["id"])
    host.text("Open it from the Lab list. Edit lab/%s on GitHub (branch lab)." % entry["file"])
    host.button("Discard this copy", lambda: host.show(_discard, "plugin", entry))
    host.back_button()


def _discard(host, kind, item):
    label = item if kind == "workflow" else item["id"]
    host.title("Discard %s?" % label)
    host.text("This deletes the copy from the lab branch. The original is not touched.")
    host.status()

    def go():
        host.set_status("Deleting...")
        host.background(_do_discard, host, kind, item,
                        done=lambda res, err: host.replace(_copy_done, res) if err is None
                        else host.set_status("Error: %s" % str(err)[:150]))

    host.button("Yes, discard", go)
    host.back_button("Back")


def _do_discard(host, kind, item):
    if kind == "workflow":
        _delete_lab(host, WF_DIR + "/" + item, "lab: discard copy of %s" % item)
        return "Discarded %s from the lab branch. (Scripts copied with it stay; delete them on GitHub if you want.)" % item
    _delete_lab(host, "lab/" + item["file"], "lab: discard copy %s" % item["id"])
    data = _index(host)
    data["plugins"] = [p for p in data.get("plugins", []) if p.get("id") != item["id"]]
    _save_index(host, data, "lab: remove %s from the index" % item["id"])
    return "Discarded %s." % item["id"]


# ---------------------------------------------------------------- run from lab
def _run_load(host, name):
    host.title(name)
    host.status()
    host.set_status("Reading the inputs...")
    host.back_button()
    host.background(lambda: parse_inputs(host.gh.read_file(WF_DIR + "/" + name, ref="lab")),
                    done=lambda res, err: host.replace(_run_form, name, res) if err is None
                    else host.set_status("Error: %s" % str(err)[:150]))


def _run_form(host, name, inputs):
    host.title("Run " + name + " (lab copy)")
    boxes = {}
    for key, spec in inputs.items():
        if key in SKIP_INPUTS:
            continue
        host.text("%s%s%s" % (key, " *" if spec["required"] else "", (" - " + spec["description"]) if spec["description"] else ""))
        if spec["options"]:
            default = spec["default"] if spec["default"] in spec["options"] else spec["options"][0]
            boxes[key] = host.choice(spec["options"], default=default)
        else:
            boxes[key] = host.input(spec["default"] or key, text=spec["default"], paste=False)
    host.status()

    def start():
        values, missing = {}, []
        for key, box in boxes.items():
            v = (getattr(box, "text", None) if hasattr(box, "text") else box.value)
            v = str(v or "").strip()
            if v:
                values[key] = v
            elif inputs[key]["required"]:
                missing.append(key)
        if missing:
            host.set_status("Fill in: " + ", ".join(missing))
            return
        host.show(_run_screen, name, values)

    host.button("Start (from lab)", start)
    host.back_button()


def _run_screen(host, name, values):
    state = {"run_id": None, "stop": threading.Event()}
    host.title(name + " (lab copy)")
    host.status()
    host.set_status("Starting...")

    def cancel():
        state["stop"].set()
        if state["run_id"]:
            host.background(host.gh.cancel, state["run_id"])
        host.back()

    host.button("Cancel", cancel)
    host.back_button("Back")
    host.background(_work, host, name, values, state, done=lambda res, err: _done(host, res, err))


def _work(host, name, values, state):
    run_id = host.gh.dispatch(name, values)      # a Lab tool dispatches with ref=lab
    if not run_id:
        return {"error": "Could not detect the run. It may still be running on GitHub Actions."}
    state["run_id"] = run_id
    host.set_status("Run %s started" % run_id)
    conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status(_STATUS_TEXT.get(s, str(s)) + "..."),
                              stop_event=state["stop"])
    if conclusion == "cancelled_locally":
        return {"cancelled": True}
    if conclusion != "success":
        return {"error": "Run %s finished with: %s. %s" % (run_id, conclusion, _failed_step(host, run_id))}
    links = []
    try:
        links = host.gh.release_links(run_id, attempts=3, delay=2) or []
    except Exception:
        links = []
    return {"run_id": run_id, "links": links}


def _failed_step(host, run_id):
    try:
        for job in _req(host, "GET", "/actions/runs/%s/jobs" % run_id).json().get("jobs", []):
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    return "Failed step: " + str(step.get("name"))
    except Exception:
        pass
    return "Open the run log on GitHub."


def _done(host, res, err):
    if err is not None:
        host.set_status("Error: %s" % str(err)[:200])
        return
    if res.get("cancelled"):
        return
    if res.get("error"):
        host.notify("Lab copy", "Failed")
        host.replace(_copy_done, res["error"])
        return
    links = res["links"]
    host.notify("Lab copy", "Run %s finished" % res["run_id"])
    if links:
        host.result("Run %s finished: %d file(s)" % (res["run_id"], len(links)), link=links[0],
                    links=links if len(links) > 1 else None)
    else:
        host.result("Run %s finished (no release files found)." % res["run_id"])
