"""Lab: Promote tool to Download Anything.

Moves a tested Lab tool to Download Anything with no APK build, and can undo it.

  config branch   plugins/<file>.py (+ modules), config.json (action added or updated,
                  config_version +1), promotions.json (the record Rollback uses)  - ONE commit
  main branch     the real workflow(s) the plugin starts (replacing the Lab stub) and the
                  scripts they run                                                - ONE commit
  lab branch      lab/index.json gets "promoted": true (the Lab copy stays, so you can
                  keep editing it and promote again = update)                     - ONE commit

Pure logic (config upsert, workflow detection, stub detection, ...) is in
lib/promote_core.py. The app code on main is never touched. Rollback restores the
previous action, deletes the files the promotion created and puts the replaced
files/workflows back.
"""
import base64
import json
import re
import time
import traceback

from labx import promote_core as core

CONFIG = "config"
LAB = "lab"
_BRANCH = {"main": "main"}          # default branch name, filled in by _init()
WF = core.WF_DIR
NONE_GROUP = "(none)"


class StepError(Exception):
    """A step of Apply/Rollback failed. ``done`` lists what had already worked."""

    def __init__(self, message, done=None):
        super().__init__(message)
        self.done = list(done or [])


# =============================================================== GitHub helpers
def _code(e):
    c = getattr(getattr(e, "response", None), "status_code", None)
    if c:
        return int(c)
    m = re.search(r"\b([45]\d\d)\b", str(e))
    return int(m.group(1)) if m else None


def _explain(e):
    text = str(e).strip().splitlines()[0][:200] if str(e).strip() else e.__class__.__name__
    try:
        body = e.response.json().get("message")
    except Exception:
        body = None
    if body and str(body) not in text:
        text += " - " + str(body)[:200]
    low = text.lower()
    if "workflow" in low and ("permission" in low or "scope" in low or "refusing" in low):
        text += ("\nThe app's GitHub sign-in cannot write workflow files: a GitHub App needs the "
                 "'Workflows' permission (read and write) on this repo; a token needs the 'workflow' scope.")
    return text


def _req(host, method, path, **kw):
    last = None
    for attempt in range(3):
        try:
            return host.gh.request(method, path, **kw)
        except Exception as e:
            last = e
            code = _code(e)
            if attempt < 2 and (code is None or code >= 500):
                time.sleep(1.5)
                continue
            raise
    raise last


def _init(host):
    try:
        _BRANCH["main"] = _req(host, "GET", "").json().get("default_branch") or "main"
    except Exception:
        _BRANCH["main"] = "main"


def _head(host, branch):
    sha = _req(host, "GET", "/git/ref/heads/" + branch).json()["object"]["sha"]
    return sha, _req(host, "GET", "/git/commits/" + sha).json()["tree"]["sha"]


def _files(host, tree_sha):
    d = _req(host, "GET", "/git/trees/" + tree_sha, params={"recursive": "1"}).json()
    if d.get("truncated"):
        raise RuntimeError("The repo is too big to list through the API.")
    return {e["path"]: e for e in d.get("tree", []) if e.get("type") == "blob"}


def _blob(host, sha):
    d = _req(host, "GET", "/git/blobs/" + sha).json()
    return base64.b64decode(d.get("content", "")).decode("utf-8")


def _text(host, files, path):
    e = files.get(path)
    return None if e is None else _blob(host, e["sha"])


def _commit(host, branch, head, changes, message, modes=None):
    """One commit: ``changes`` = {path: text, or None to delete}."""
    commit_sha, tree_sha = head
    entries = []
    for path, text in sorted(changes.items()):
        if text is None:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        else:
            entries.append({"path": path, "mode": (modes or {}).get(path, "100644"),
                            "type": "blob", "content": text})
    tree = _req(host, "POST", "/git/trees", json={"base_tree": tree_sha, "tree": entries}).json()["sha"]
    new = _req(host, "POST", "/git/commits",
               json={"message": message, "tree": tree, "parents": [commit_sha]}).json()["sha"]
    _req(host, "PATCH", "/git/refs/heads/" + branch, json={"sha": new, "force": False})
    return new


def _atomic(host, branch, build, message):
    """Reads the branch, lets ``build(files)`` -> (changes, modes, extra) decide what to
    write from the LATEST content, then makes one commit. Tries again if someone else
    committed in between. -> (commit_sha or None, extra)"""
    last = None
    for attempt in range(3):
        head = _head(host, branch)
        files = _files(host, head[1])
        changes, modes, extra = build(files)
        if not changes:
            return None, extra
        try:
            return _commit(host, branch, head, changes, message, modes), extra
        except Exception as e:
            last = e
            if _code(e) in (409, 422) and "workflow" not in _explain(e).lower() and attempt < 2:
                time.sleep(1.5)
                continue
            raise
    raise last


# =============================================================== main screen
def build(host):
    host.title("Promote tool")
    host.text("Move a tested Lab tool into Download Anything without building the APK. "
              "Every promotion can be rolled back.")
    host.button("Promote a tool", lambda: host.show(_pick))
    host.button("Rollback", lambda: host.show(_rb_list))
    host.button("Test write access", lambda: host.show(_perm))
    host.status()
    host.back_button("Back")


def _error(host, what, err):
    text = what + "\n" + (err if isinstance(err, str) else _explain(err))
    host.log("error:", text)
    host.title("Error")
    host.text(text)
    host.button("Copy error", lambda: host.copy(text))
    host.back_button()


def _fail(host, what, err):
    host.replace(_error, what, err)


# =============================================================== write-access test
def _perm(host):
    host.title("Test write access")
    host.status()
    host.set_status("Testing...")
    host.back_button()
    host.background(_perm_test, host, done=lambda r, e: host.replace(_perm_done, r) if e is None
                    else _fail(host, "Test failed", e))


def _perm_test(host):
    """Pushes a throw-away branch holding a workflow file, then deletes it. Nothing on
    main, config or lab changes."""
    _init(host)
    name = "promote-permtest"
    out = []
    head = _head(host, _BRANCH["main"])
    wf = ("name: promote-permtest\non: workflow_dispatch\njobs:\n  t:\n    runs-on: ubuntu-latest\n"
          "    steps:\n      - run: echo test\n")
    try:
        try:
            _req(host, "DELETE", "/git/refs/heads/" + name)
        except Exception:
            pass
        tree = _req(host, "POST", "/git/trees", json={"base_tree": head[1], "tree": [
            {"path": WF + "/promote-permtest.yml", "mode": "100644", "type": "blob", "content": wf}]}).json()["sha"]
        c = _req(host, "POST", "/git/commits", json={"message": "promote: permission test", "tree": tree,
                                                      "parents": [head[0]]}).json()["sha"]
        _req(host, "POST", "/git/refs", json={"ref": "refs/heads/" + name, "sha": c})
        out.append("Workflow files (main): OK - can write")
    except Exception as e:
        out.append("Workflow files (main): FAILED - " + _explain(e))
    finally:
        try:
            _req(host, "DELETE", "/git/refs/heads/" + name)
        except Exception:
            pass
    for branch in (CONFIG, LAB):
        try:
            _head(host, branch)
            out.append("Branch %s: readable" % branch)
        except Exception as e:
            out.append("Branch %s: FAILED - %s" % (branch, _explain(e)))
    return "\n".join(out)


def _perm_done(host, text):
    host.title("Write access")
    host.text(text)
    host.back_button()


# =============================================================== 1. list
def _origin(entry, actions):
    """If this Lab tool is a copy of a Download Anything plugin (made by Copy tools):
    {"action_id", "file", "action"}; else None."""
    cf = entry.get("copied_from")
    if isinstance(cf, dict) and cf.get("action_id") in actions:
        return {"action_id": cf["action_id"], "file": cf.get("file") or (actions[cf["action_id"]].get("file") or ""),
                "action": actions[cf["action_id"]]}
    m = re.match(r"Lab copy of plugins/(\S+?\.py)", entry.get("description") or "")
    if m:
        for aid, act in actions.items():
            if act.get("plugin") and (act.get("file") or act["plugin"] + ".py") == m.group(1):
                return {"action_id": aid, "file": m.group(1), "action": act}
    return None


def _list_tools(host):
    _init(host)
    idx = json.loads(host.gh.read_file("lab/index.json", ref=LAB))
    plugins = idx.get("plugins") if isinstance(idx, dict) else idx
    cfg = json.loads(host.gh.read_file("config.json", ref=CONFIG))
    actions = {a.get("id"): a for a in cfg.get("actions", [])}
    rows = []
    for p in plugins:
        if not isinstance(p, dict) or not p.get("id") or not p.get("file"):
            continue
        if p.get("enabled", True) is False or p["id"] == "promote":
            continue
        act = actions.get(p.get("promoted_as") or p["id"])
        act = act if act and act.get("plugin") else None
        state = "Lab only" if not act else ("bundled" if act.get("source") == "bundled" else "in Download Anything")
        rows.append({"entry": p, "state": state, "action": act, "origin": _origin(p, actions)})
    groups = sorted({a["group"] for a in cfg.get("actions", []) if a.get("group")})
    return {"rows": rows, "groups": groups, "version": cfg.get("config_version"), "action_ids": list(actions)}


def _pick(host):
    host.title("Promote a tool")
    host.status()
    host.set_status("Loading the Lab list...")
    host.back_button()
    host.background(_list_tools, host, done=lambda r, e: host.replace(_pick_list, r) if e is None
                    else _fail(host, "Could not load the list", e))


def _pick_list(host, data):
    host.title("Promote a tool")
    if not data["rows"]:
        host.text("No tools in lab/index.json.")
    for row in data["rows"]:
        note = ("  |  copy of Download Anything: %s" % row["origin"]["action_id"]) if row.get("origin") else ""
        host.button("%s\n[%s%s]" % (row["entry"].get("title") or row["entry"]["id"], row["state"], note),
                    lambda r=row: host.show(_check, data, r), height=64)
    host.back_button()


# =============================================================== 2. pre-flight
def _analyze(host, data, row):
    entry = row["entry"]
    a = {"entry": entry, "row": row, "errors": [], "warnings": [], "info": [], "codes": {},
         "workflows": [], "scripts": [], "groups": data["groups"], "action_ids": data["action_ids"],
         "version": data["version"]}
    host.set_status("Reading the lab branch...")
    lab_head = _head(host, LAB)
    lab = _files(host, lab_head[1])
    main = _files(host, _head(host, _BRANCH["main"])[1])
    a["main_wf_names"] = sorted(p[len(WF) + 1:] for p in main if p.startswith(WF + "/"))

    # files + syntax
    rels = list(entry.get("modules") or []) + [entry["file"]]
    for rel in rels:
        path = "lab/" + rel
        try:
            text = _text(host, lab, path)
        except UnicodeDecodeError:
            a["errors"].append("%s is not a text file" % path)
            continue
        if text is None:
            a["errors"].append("%s not found on the lab branch" % path)
            continue
        a["codes"][rel] = text
        try:
            compile(text, path, "exec")
        except SyntaxError as e:
            a["errors"].append("%s: syntax error, line %s: %s" % (path, e.lineno, e.msg))
        for w in core.scan_assumptions(text):
            a["warnings" if w["level"] == "warn" else "info"].append("%s line %d: %s" % (rel, w["line"], w["msg"]))
    if not entry["file"] in a["codes"] and not a["errors"]:
        a["errors"].append("Main file is missing")

    # host version
    try:
        from core.plugin_loader import HOST_API_VERSION as have
    except Exception:
        have = 1
    try:
        need = int(entry.get("min_host") or 1)
    except (TypeError, ValueError):
        need = 1
    if need > have:
        a["errors"].append("min_host %d is newer than this app's plugin API (%d)" % (need, have))
    else:
        a["info"].append("min_host %d (app has %d)" % (need, have))

    # workflows the plugin starts
    names = []
    for text in a["codes"].values():
        for n in core.detect_workflows(text):
            if n not in names:
                names.append(n)
    texts = {}                                    # lab path -> text (reads cached)
    lab_data = []

    def lab_read(path):
        if path not in texts:
            texts[path] = _text(host, lab, path)
        return texts[path]

    need_scripts = []
    for n in names:
        wf_path = WF + "/" + n
        on_lab, on_main = wf_path in lab, wf_path in main
        if core.is_protected(n):
            a["errors"].append("%s is protected: Promote never touches it" % n)
            continue
        if not on_lab and not on_main:
            a["info"].append("%s is mentioned in the code but exists on neither branch (ignored)" % n)
            continue
        item = {"name": n, "lab_text": None, "main_text": None, "promote": False}
        if on_main:
            item["main_text"] = _text(host, main, wf_path)
        if on_lab:
            item["lab_text"] = lab_read(wf_path)
        if not on_lab:
            item["state"] = "already on main (nothing to move)"
        elif not on_main:
            item["state"] = "lab only: will be created on main"
            item["promote"] = True
        elif core.is_stub(item["main_text"]):
            item["state"] = "main has a stub: the real file will replace it"
            item["promote"] = True
        elif item["main_text"] == item["lab_text"]:
            item["state"] = "main already has the same file"
        else:
            item["state"] = "main has a DIFFERENT real file: it would be overwritten (asks again)"
            item["promote"] = True
        item["main_real"] = bool(item["main_text"]) and not core.is_stub(item["main_text"])
        a["workflows"].append(item)
        if item["promote"]:
            hits = core.scan_workflow(item["lab_text"])
            item["lab_checkout"] = bool(hits)
            for w in hits:
                a["warnings"].append("%s line %d: %s" % (n, w["line"], w["msg"]))
            need_scripts += core.workflow_file_refs(item["lab_text"], lab)

    # files the promoted workflows run (they only exist on lab)
    if need_scripts:
        host.set_status("Checking the workflow's scripts...")
        for p in core.closure(sorted(set(need_scripts)), lab_read, list(lab)):
            if p.startswith(WF + "/"):
                continue
            if p.startswith("lab/"):                      # the plugin store and its data stay on lab
                lab_data.append(p)
                continue
            cur = main.get(p)
            if cur is not None and cur["sha"] == lab[p]["sha"]:
                continue
            a["scripts"].append({"path": p, "state": "new on main" if cur is None else "DIFFERENT on main (would overwrite)",
                                 "mode": lab[p].get("mode", "100644"), "text": lab_read(p)})
    if a["scripts"]:
        a["warnings"].append("%d file(s) the workflow runs exist only on lab; on main they would be missing" % len(a["scripts"]))
    if need_scripts and lab_data:
        a["warnings"].append("The workflow uses lab-only data (%s): not copied, it stays on the lab branch" % ", ".join(lab_data[:4]))
    return a


def _check(host, data, row):
    host.title("Checking")
    host.status()
    host.set_status("Checking %s..." % row["entry"]["id"])
    host.back_button()
    host.background(_analyze, host, data, row, done=lambda r, e: host.replace(_check_result, r) if e is None
                    else _fail(host, "Check failed", e))


def _report(a):
    e = a["entry"]
    L = ["%s (%s)" % (e.get("title") or e["id"], e["id"]), "Status: %s" % a["row"]["state"]]
    if a["row"].get("origin"):
        o = a["row"]["origin"]
        L.append("Copy of the Download Anything tool '%s' (plugins/%s): it can replace the original in place." % (o["action_id"], o["file"]))
    L.append("")
    if a["errors"]:
        L += ["ERRORS (must be fixed on the lab branch):"] + ["  x " + t for t in a["errors"]] + [""]
    if a["warnings"]:
        L += ["WARNINGS:"] + ["  ! " + t for t in a["warnings"]] + [""]
    if a["info"]:
        L += ["INFO:"] + ["  - " + t for t in a["info"]] + [""]
    if a["workflows"]:
        L += ["WORKFLOWS the plugin starts:"] + ["  %s: %s" % (w["name"], w["state"]) for w in a["workflows"]] + [""]
    if a["scripts"]:
        L += ["FILES the workflow runs (copied to main if you agree):"] + [
            "  %s (%s)" % (s["path"], s["state"]) for s in a["scripts"]] + [""]
    if not a["errors"]:
        L.append("Syntax of %d file(s): OK" % len(a["codes"]))
    return "\n".join(L)


def _check_result(host, a):
    host.title("Pre-flight")
    text = _report(a)
    host.text(text)
    if a["errors"]:
        host.text("Fix the errors above on the lab branch, then check again.")
    else:
        host.button("Next: settings", lambda: host.show(_form, a))
    host.button("Copy report", lambda: host.copy(text))
    host.back_button()


# =============================================================== 3. form
def _form(host, a):
    e = a["entry"]
    origin = a["row"].get("origin")
    ex = a["row"]["action"] or (origin or {}).get("action") or {}
    mode = None
    if origin:
        host.text("This tool is a copy of the Download Anything tool '%s' (plugins/%s)." % (origin["action_id"], origin["file"]))
        mode = host.choice([("Replace the original '%s' (same button, same file)" % origin["action_id"], "replace"),
                            ("Add as a new tool", "new")], default="replace")
    meta = e.get("meta") or {}
    title = host.input("Button title", text=ex.get("title") or meta.get("title") or (e.get("title") or e["id"]).replace(" [imported]", ""))
    aid = host.input("Action id (used when adding as new)" if origin else "Action id (letters, digits, _)",
                     text=(e.get("promoted_as") or e["id"]) if origin else (ex.get("id") or e.get("promoted_as") or e["id"]))
    groups = [NONE_GROUP] + a["groups"]
    mgroup = meta.get("group", "")
    gch = host.choice(groups, default=ex.get("group") if ex.get("group") in groups else (mgroup if mgroup in groups else NONE_GROUP))
    gnew = host.input("New group name (optional, overrides the choice)", text=(mgroup if mgroup and mgroup not in groups and not ex.get("group") else ""))
    dom = host.input("Domains for share-links (comma separated, optional)", text=",".join(ex.get("domains") or meta.get("domains") or []))
    en = host.choice([("Enabled", True), ("Hidden", False)], default=ex.get("enabled", True))
    wf_inputs = {}
    for w in a["workflows"]:
        if not w["promote"]:
            continue
        if w.get("main_real"):
            host.text("The workflow %s already exists on main (a real one)." % w["name"])
            wmode = host.choice([("Replace it on main", "replace"), ("Add as a new workflow, named below", "new")],
                                default="replace" if origin else "new")
            stem, _, ext = w["name"].rpartition(".")
            n, cand = 2, "%s-v2.%s" % (stem, ext)
            while cand in a["main_wf_names"]:
                n += 1
                cand = "%s-v%d.%s" % (stem, n, ext)
            wf_inputs[w["name"]] = (wmode, host.input("New workflow name on main", text=cand))
        else:
            stripped = w["name"][4:] if w["name"].startswith("lab-") else w["name"]
            default = stripped if stripped not in a["main_wf_names"] else w["name"]   # never default onto an existing file
            wf_inputs[w["name"]] = (None, host.input("Name on main for %s" % w["name"], text=default))
    sc = None
    if a["scripts"]:
        sc = host.choice([("Copy the %d script file(s) to main" % len(a["scripts"]), True),
                          ("Do not copy them", False)])
    keep = host.choice([("Keep in the Lab list", True), ("Hide from the Lab list", False)])
    host.status()

    def go():
        replace = bool(origin) and mode.value == "replace"
        names = {old: (old if (wmode is not None and wmode.value == "replace") else inp.text.strip())
                 for old, (wmode, inp) in wf_inputs.items()}
        form = {"title": title.text.strip(), "id": origin["action_id"] if replace else aid.text.strip(),
                "plugin_file": origin["file"] if replace else e["file"], "replace_origin": replace,
                "group": (gnew.text.strip() or ("" if gch.value == NONE_GROUP else gch.value)),
                "domains": core.parse_domains(dom.text), "enabled": en.value, "wf_names": names,
                "copy_scripts": True if sc is None else sc.value, "keep": keep.value}
        problem = _validate(form, a)
        if problem:
            host.set_status(problem)
            return
        host.show(_preview, a, form)

    host.button("Preview (nothing is written yet)", go)
    host.back_button()


def _validate(form, a):
    if not re.fullmatch(r"[a-z0-9_]{1,40}", form["id"]):
        return "Action id: use a-z, 0-9 and _ only"
    if not form["title"]:
        return "Give the button a title"
    for old, new in form["wf_names"].items():
        if not re.fullmatch(r"[A-Za-z0-9][\w.\-]*\.ya?ml", new):
            return "Workflow name for %s must end with .yml" % old
        if core.is_protected(new):
            return "%s is protected" % new
        w = next((x for x in a["workflows"] if x["name"] == old), None)
        if w and w.get("main_real") and new != old and new in a["main_wf_names"]:
            return "%s already exists on main. Choose another new name." % new
    if len(set(form["wf_names"].values())) != len(form["wf_names"]):
        return "Two workflows have the same new name"
    return ""


# =============================================================== 4. plan / dry run
def _make_plan(host, a, form):
    e, aid = a["entry"], form["id"]
    host.set_status("Reading config and main...")
    cfg_head = _head(host, CONFIG)
    cfg_files = _files(host, cfg_head[1])
    main_files = _files(host, _head(host, _BRANCH["main"])[1])
    cfg_text = _text(host, cfg_files, "config.json")
    actions = json.loads(cfg_text).get("actions", [])
    plan = {"entry": e, "form": form, "errors": [], "risky": [], "lines_config": [], "lines_main": [],
            "config_writes": {}, "main_writes": {}, "main_modes": {}}

    rename = {old: new for old, new in form["wf_names"].items() if old != new}

    def final(text):
        for old, new in rename.items():
            text = core.rename_literal(text, old, new)
        return text

    modules = list(e.get("modules") or [])
    plugin_file = form.get("plugin_file") or e["file"]
    action = core.build_action(e, aid, form["title"], form["domains"], form["group"], form["enabled"],
                               plugin_file, modules)
    plan["action"] = action

    # action id rules
    clash = next((x for x in actions if x.get("id") == aid), None)
    if clash is not None and not clash.get("plugin"):
        plan["errors"].append("The id '%s' belongs to a built-in action (not a plugin). Choose another id." % aid)

    # which files do other plugin actions use?
    used = {}
    for x in actions:
        if x.get("plugin") and x.get("id") != aid:
            used["plugins/" + (x.get("file") or x["plugin"] + ".py")] = x["id"]
            for m in x.get("modules") or []:
                used["plugins/" + m] = x["id"]

    def classify(path, text, files, owner_map, label, risky_list, lines, mode_note=""):
        cur = files.get(path)
        if cur is None:
            lines.append("  + %s (new)%s" % (path, mode_note))
            return "new"
        if cur["sha"] == core.git_blob_sha(text):
            lines.append("  = %s (identical, skipped)" % path)
            return "same"
        who = owner_map.get(path)
        old = _blob(host, cur["sha"])
        plus, minus, _ = core.diff_summary(old, text)
        lines.append("  ~ %s (overwrite, +%d/-%d lines)" % (path, plus, minus))
        if who:
            risky_list.append("%s is used by the action '%s' and would be overwritten" % (path, who))
        return "overwrite"

    # config branch files
    plan["lines_config"].append("CONFIG branch (one commit):")
    texts = {plugin_file: final(a["codes"][e["file"]])}
    for m in modules:
        texts[m] = final(a["codes"][m])
    for rel, text in texts.items():
        path = "plugins/" + rel
        classify(path, text, cfg_files, used, "plugin", plan["risky"], plan["lines_config"])
        plan["config_writes"][path] = text              # identical files are rewritten harmlessly
    up = core.upsert_action(cfg_text, action)
    plan["lines_config"].append("  ~ config.json: %s action '%s', config_version %d -> %d" % (
        "update" if up["previous"] else "add", aid, up["version_before"], up["version_after"]))
    if not core.roundtrip_ok(cfg_text):
        plan["lines_config"].append("    (config.json will be re-formatted; content is unchanged)")
    plan["lines_config"].append("  + promotions.json (record for Rollback)")

    # main branch: workflows + scripts
    plan["lines_main"].append("MAIN branch (one commit):")
    any_main = False
    for w in a["workflows"]:
        if not w["promote"]:
            continue
        new_name = form["wf_names"].get(w["name"], w["name"])
        path = WF + "/" + new_name
        if core.is_protected(new_name):
            plan["errors"].append("%s is protected" % new_name)
            continue
        cur = main_files.get(path)
        if cur is None:
            plan["lines_main"].append("  + %s (new)" % path)
        elif cur["sha"] == core.git_blob_sha(w["lab_text"]):
            plan["lines_main"].append("  = %s (identical, skipped)" % path)
            continue
        else:
            old = _blob(host, cur["sha"])
            if core.is_stub(old):
                plan["lines_main"].append("  ~ %s (replaces the stub)" % path)
            else:
                plus, minus, sample = core.diff_summary(old, w["lab_text"])
                plan["lines_main"].append("  ~ %s (REAL file overwritten, +%d/-%d lines)" % (path, plus, minus))
                plan["risky"].append("%s on main is a real workflow: +%d/-%d lines would change. First changes:\n    %s" % (
                    path, plus, minus, "\n    ".join(sample)))
        if w.get("lab_checkout"):
            plan["risky"].append("%s still checks out the lab branch: on main it keeps depending on lab files" % new_name)
        plan["main_writes"][path] = w["lab_text"]
        any_main = True
    if form["copy_scripts"]:
        for s in a["scripts"]:
            cur = main_files.get(s["path"])
            if cur is not None and cur["sha"] == core.git_blob_sha(s["text"]):
                continue
            if cur is None:
                plan["lines_main"].append("  + %s (new)" % s["path"])
            else:
                plan["lines_main"].append("  ~ %s (overwrite)" % s["path"])
                plan["risky"].append("%s exists on main and differs from the lab copy" % s["path"])
            plan["main_writes"][s["path"]] = s["text"]
            plan["main_modes"][s["path"]] = s.get("mode", "100644")
            any_main = True
    elif a["scripts"]:
        plan["risky"].append("The workflow runs %d file(s) that exist only on lab and you chose not to copy them: "
                             "it would fail on main." % len(a["scripts"]))
    if not any_main:
        plan["lines_main"].append("  (nothing to change on main)")

    # lab
    plan["lines_lab"] = ["LAB branch (one commit):",
                         "  ~ lab/index.json: promoted flag%s" % ("" if form["keep"] else " + hidden from the Lab list")]
    plan["text"] = "\n".join(
        ["Promote '%s' as action '%s'%s" % (e["id"], aid, " (update)" if up["previous"] else ""),
         ("It REPLACES the original Download Anything tool '%s' in place (same button, plugins/%s)." % (aid, plugin_file))
         if form.get("replace_origin") else "It is added as a new tool."]
        + [""] + plan["lines_config"] + [""] + plan["lines_main"] + [""] + plan["lines_lab"]
        + (["", "NEEDS A SECOND CONFIRM:"] + ["  ! " + r for r in plan["risky"]] if plan["risky"] else [])
        + (["", "BLOCKED:"] + ["  x " + r for r in plan["errors"]] if plan["errors"] else [])
        + ["", "Then open Download Anything and use Reload list."])
    return plan


def _preview(host, a, form):
    host.title("Preview")
    host.status()
    host.set_status("Building the preview...")
    host.back_button()
    host.background(_make_plan, host, a, form, done=lambda r, e: host.replace(_preview_ready, r) if e is None
                    else _fail(host, "Preview failed", e))


def _preview_ready(host, plan):
    host.title("Dry run")
    host.text(plan["text"])
    host.button("Copy plan", lambda: host.copy(plan["text"]))
    if not plan["errors"]:
        if plan["risky"]:
            host.button("Confirm... (overwrites existing files)", lambda: host.show(_confirm2, plan))
        else:
            host.button("Confirm and promote", lambda: host.show(_apply, plan))
    host.back_button()


def _confirm2(host, plan):
    host.title("Are you sure?")
    host.text("These existing files will be overwritten (Rollback can restore them):\n\n"
              + "\n\n".join("! " + r for r in plan["risky"]))
    host.button("Yes, overwrite and promote", lambda: host.replace(_apply, plan))
    host.back_button()


# =============================================================== 5. apply
def _apply(host, plan):
    host.title("Promoting")
    host.status()
    host.set_status("Starting...")
    host.back_button()
    host.background(_apply_plan, host, plan, done=lambda r, e: host.replace(_apply_done, r) if e is None
                    else host.replace(_apply_failed, e))


def _apply_plan(host, plan):
    e, form, action = plan["entry"], plan["form"], plan["action"]
    aid = action["id"]
    done = []
    rec = {"id": core.new_record_id(e["id"]), "time": core.iso_now(), "tool": e["id"], "action_id": aid,
           "status": "started", "new_action": action, "config_created": [], "config_overwritten": {},
           "main_created": [], "main_overwritten": {}, "written": {}, "commits": {}}

    # what is on main right now (for Rollback)
    host.set_status("Reading main...")
    try:
        main_head = _head(host, _BRANCH["main"])
        main_files = _files(host, main_head[1])
        for path in plan["main_writes"]:
            if path in main_files:
                rec["main_overwritten"][path] = _text(host, main_files, path)
            else:
                rec["main_created"].append(path)
    except Exception as ex:
        raise StepError("Could not read main: " + _explain(ex), done)

    # --- config branch: plugin files + config.json + promotions.json, ONE commit
    host.set_status("Writing the config branch...")

    def build_config(files):
        cfg_text = _text(host, files, "config.json")
        up = core.upsert_action(cfg_text, action)
        changes = dict(plan["config_writes"])
        rec["config_created"], rec["config_overwritten"], rec["written"] = [], {}, {}
        for path, text in plan["config_writes"].items():
            if path in files:
                rec["config_overwritten"][path] = _text(host, files, path)
            else:
                rec["config_created"].append(path)
            rec["written"][path] = core.git_blob_sha(text)
        for path, text in plan["main_writes"].items():
            rec["written"][path] = core.git_blob_sha(text)
        rec.update({"previous_action": up["previous"], "previous_index": up["index"],
                    "config_version_before": up["version_before"], "config_version_after": up["version_after"],
                    "status": "config_done"})
        changes["config.json"] = up["text"]
        changes["promotions.json"] = core.add_record(_text(host, files, "promotions.json"), rec)
        return changes, None, up

    try:
        sha, up = _atomic(host, CONFIG, build_config, "promote: %s (config)" % e["id"])
    except Exception as ex:
        raise StepError("Could not write the config branch (nothing was changed): " + _explain(ex), done)
    rec["commits"]["config"] = sha
    done.append("config branch updated (%d file(s) + config.json, version %d)" % (
        len(plan["config_writes"]), up["version_after"]))

    # --- main branch: workflows + scripts, ONE commit
    if plan["main_writes"]:
        host.set_status("Writing workflows to main...")

        def build_main(files):
            return dict(plan["main_writes"]), plan["main_modes"], None

        try:
            sha, _ = _atomic(host, _BRANCH["main"], build_main, "promote: %s (main)" % e["id"])
            rec["commits"]["main"] = sha
            done.append("main branch updated (%d file(s))" % len(plan["main_writes"]))
        except Exception as ex:
            raise StepError("Could not write main: " + _explain(ex) + "\nThe config branch is already updated: "
                            "use Rollback to undo it.", done)
    else:
        done.append("main branch: nothing to change")

    # --- lab branch: promoted flag
    host.set_status("Marking the tool in the Lab list...")
    flags = {"promoted": True, "promoted_at": core.iso_now(), "promoted_as": aid}
    if not form["keep"]:
        flags["enabled"] = False

    def build_lab(files):
        text = _text(host, files, "lab/index.json")
        new, prev = core.set_index_flags(text, e["id"], flags)
        rec["lab_before"] = prev
        return {"lab/index.json": new}, None, None

    try:
        sha, _ = _atomic(host, LAB, build_lab, "promote: %s (lab)" % e["id"])
        rec["commits"]["lab"] = sha
        done.append("lab/index.json marked")
    except Exception as ex:
        done.append("lab/index.json NOT marked (not important): " + _explain(ex)[:100])

    # --- final record + verification
    rec["status"] = "done"

    def build_rec(files):
        return {"promotions.json": core.add_record(_text(host, files, "promotions.json"), rec)}, None, None

    try:
        _atomic(host, CONFIG, build_rec, "promote: %s (record)" % e["id"])
    except Exception as ex:
        done.append("record not finalised: " + _explain(ex)[:100])

    host.set_status("Verifying...")
    verify = []
    try:
        cfg = json.loads(host.gh.read_file("config.json", ref=CONFIG))
        ok_action = any(x.get("id") == aid and x.get("plugin") for x in cfg.get("actions", []))
        ok_file = bool(host.gh.read_file("plugins/" + e["file"], ref=CONFIG))
        verify.append("config.json has the action: %s" % ("yes" if ok_action else "NO"))
        verify.append("plugins/%s on config: %s" % (e["file"], "yes" if ok_file else "NO"))
        for path in plan["main_writes"]:
            if path.startswith(WF + "/"):
                verify.append("%s on main: %s" % (path, "yes" if host.gh.read_file(path, ref=_BRANCH["main"]) else "NO"))
    except Exception as ex:
        verify.append("verification failed: " + _explain(ex)[:120])
    return {"done": done, "verify": verify, "record": rec["id"], "action_id": aid}


def _apply_done(host, res):
    host.title("Promoted")
    host.text("\n".join(["Done:"] + ["  - " + d for d in res["done"]] + ["", "Checked:"] + ["  - " + v for v in res["verify"]]
                        + ["", "Now open Download Anything and use Reload list (no build needed)."]))
    host.button("Rollback this promotion", lambda: host.show(_rb_detail, res["record"]))
    host.back_button()


def _apply_failed(host, err):
    text = "Promotion stopped.\n\n" + (_explain(err) if not isinstance(err, StepError) else str(err))
    if isinstance(err, StepError) and err.done:
        text += "\n\nAlready done:\n" + "\n".join("  - " + d for d in err.done)
    host.log("apply failed:", text, "".join(traceback.format_exception(type(err), err, err.__traceback__)))
    host.title("Stopped")
    host.text(text)
    host.button("Copy error", lambda: host.copy(text))
    if isinstance(err, StepError) and err.done:
        host.button("Rollback", lambda: host.show(_rb_list))
    host.back_button()


# =============================================================== 6. rollback
def _rb_load(host):
    _init(host)
    try:
        return core.load_records(host.gh.read_file("promotions.json", ref=CONFIG))
    except Exception as e:
        if _code(e) == 404:
            return []
        raise


def _rb_list(host):
    host.title("Rollback")
    host.status()
    host.set_status("Loading...")
    host.back_button()
    host.background(_rb_load, host, done=lambda r, e: host.replace(_rb_list_ready, r) if e is None
                    else _fail(host, "Could not load promotions", e))


def _rb_list_ready(host, recs):
    host.title("Rollback")
    if not recs:
        host.text("No promotions recorded yet.")
    for r in reversed(recs):
        host.button("%s\n%s - %s" % (r.get("tool"), r.get("time", "")[:16].replace("T", " "), r.get("status")),
                    lambda i=r["id"]: host.show(_rb_detail, i), height=64)
    host.back_button()


def _rb_detail(host, rec_id):
    host.title("Rollback")
    host.status()
    host.set_status("Loading...")
    host.back_button()
    host.background(_rb_prepare, host, rec_id, done=lambda r, e: host.replace(_rb_detail_ready, r) if e is None
                    else _fail(host, "Could not load the record", e))


def _rb_prepare(host, rec_id):
    _init(host)
    recs = core.load_records(host.gh.read_file("promotions.json", ref=CONFIG))
    rec = next((r for r in recs if r["id"] == rec_id), None)
    if rec is None:
        raise RuntimeError("Record not found: " + rec_id)
    notes = []
    cur = core.find_action(host.gh.read_file("config.json", ref=CONFIG), rec["action_id"])
    if cur != rec.get("new_action") and rec["status"] != "rolled_back":
        notes.append("The action '%s' was changed after this promotion; Rollback will overwrite it." % rec["action_id"])
    main_files = _files(host, _head(host, _BRANCH["main"])[1])
    for path, sha in rec.get("written", {}).items():
        if path in rec.get("main_created", []) or path in rec.get("main_overwritten", {}):
            now = main_files.get(path)
            if now is None:
                notes.append("%s is already gone from main" % path)
            elif now["sha"] != sha:
                notes.append("%s on main changed after the promotion" % path)
    return {"rec": rec, "notes": notes}


def _rb_detail_ready(host, d):
    r = d["rec"]
    lines = ["Tool: %s -> action '%s'" % (r["tool"], r["action_id"]), "Time: %s" % r.get("time"),
             "Status: %s" % r.get("status"), "",
             "Rollback will:",
             "  - %s the action '%s' in config.json" % ("restore the previous version of" if r.get("previous_action") else "remove", r["action_id"]),
             "  - delete %d and restore %d file(s) on config" % (len(r.get("config_created", [])), len(r.get("config_overwritten", {}))),
             "  - delete %d and restore %d file(s) on main" % (len(r.get("main_created", [])), len(r.get("main_overwritten", {}))),
             "  - clear the promoted flag in lab/index.json",
             "config_version goes up by one so phones reload the list."]
    if d["notes"]:
        lines += ["", "Note:"] + ["  ! " + n for n in d["notes"]]
    host.title("Rollback")
    host.text("\n".join(lines))
    if r.get("status") != "rolled_back":
        host.button("Roll back now", lambda: host.replace(_rb_run, r["id"]))
    host.back_button()


def _rb_run(host, rec_id):
    host.title("Rolling back")
    host.status()
    host.set_status("Starting...")
    host.back_button()
    host.background(_rollback, host, rec_id, done=lambda r, e: host.replace(_rb_done, r) if e is None
                    else host.replace(_rb_failed, e))


def _rollback(host, rec_id):
    done, box = [], {}
    _init(host)

    def build_config(files):
        recs = core.load_records(_text(host, files, "promotions.json"))
        rec = next((r for r in recs if r["id"] == rec_id), None)
        if rec is None:
            raise RuntimeError("Record not found")
        if rec.get("status") == "rolled_back":
            raise RuntimeError("Already rolled back")
        box["rec"] = rec
        if rec.get("status") == "rollback_partial":          # config part was restored earlier
            return {}, None, {"version_after": "(restored earlier)"}
        res = core.restore_action(_text(host, files, "config.json"), rec["action_id"],
                                  rec.get("previous_action"), rec.get("previous_index"))
        changes = {"config.json": res["text"]}
        for path in rec.get("config_created", []):
            if path in files:
                changes[path] = None
        for path, text in rec.get("config_overwritten", {}).items():
            changes[path] = text
        rec["status"] = "rollback_partial"
        changes["promotions.json"] = core.add_record(_text(host, files, "promotions.json"), rec)
        return changes, None, res

    host.set_status("Restoring the config branch...")
    try:
        _, res = _atomic(host, CONFIG, build_config, "rollback: %s (config)" % rec_id)
    except Exception as ex:
        raise StepError("Could not restore the config branch (nothing was changed): " + _explain(ex), done)
    rec = box["rec"]
    done.append("config branch restored (config_version %s)" % res["version_after"])

    host.set_status("Restoring main...")

    def build_main(files):
        changes = {}
        for path in rec.get("main_created", []):
            if path in files:
                changes[path] = None
        for path, text in rec.get("main_overwritten", {}).items():
            if text is not None and not (path in files and files[path]["sha"] == core.git_blob_sha(text)):
                changes[path] = text
        return changes, None, None

    try:
        sha, _ = _atomic(host, _BRANCH["main"], build_main, "rollback: %s (main)" % rec_id)
        done.append("main branch restored" if sha else "main branch: nothing to restore")
    except Exception as ex:
        raise StepError("Could not restore main: " + _explain(ex) + "\nThe config branch is already restored. "
                        "Fix the problem and press Rollback again: it will only redo main and lab.", done)

    host.set_status("Clearing the Lab flag...")

    def build_lab(files):
        text = _text(host, files, "lab/index.json")
        try:
            new, _ = core.set_index_flags(text, rec["tool"], rec.get("lab_before") or {"promoted": None, "promoted_at": None, "promoted_as": None})
        except StopIteration:
            return {}, None, None
        return {"lab/index.json": new}, None, None

    try:
        _atomic(host, LAB, build_lab, "rollback: %s (lab)" % rec_id)
        done.append("lab/index.json restored")
    except Exception as ex:
        done.append("lab/index.json not restored (not important): " + _explain(ex)[:100])

    def build_final(files):
        recs = core.load_records(_text(host, files, "promotions.json"))
        for r in recs:
            if r["id"] == rec_id:
                r["status"] = "rolled_back"
                r["rolled_back_at"] = core.iso_now()
        return {"promotions.json": core.dump_json(recs)}, None, None

    try:
        _atomic(host, CONFIG, build_final, "rollback: %s (record)" % rec_id)
    except Exception as ex:
        done.append("record not finalised: " + _explain(ex)[:100])
    return {"done": done}


def _rb_done(host, res):
    host.title("Rolled back")
    host.text("\n".join(["Done:"] + ["  - " + d for d in res["done"]] + ["", "Use Reload list in Download Anything."]))
    host.back_button()


def _rb_failed(host, err):
    text = "Rollback stopped.\n\n" + (str(err) if isinstance(err, StepError) else _explain(err))
    if isinstance(err, StepError) and err.done:
        text += "\n\nAlready done:\n" + "\n".join("  - " + d for d in err.done)
    host.log("rollback failed:", text)
    host.title("Stopped")
    host.text(text)
    host.button("Copy error", lambda: host.copy(text))
    host.back_button()
