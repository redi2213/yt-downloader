"""Runner for one workflow: a form made from its inputs, Run, the result, and
help when something is wrong. Used by the tools made with Lab > Add workflow
(and still works after such a tool is promoted to Download Anything).

  Run                  starts the workflow, waits, shows the files or the error
  Check workflow       static checks: what the app needs, missing files, secrets...
  Report               one text with the log, the causes and the workflow, to copy

Also holds the small GitHub helpers (one commit per branch) that Add workflow uses.
Helper modules are imported as ``from labx import wf_core``.
"""
import base64
import re
import time

from labx import wf_core as core


# ============================================================ GitHub helpers
def code(e):
    c = getattr(getattr(e, "response", None), "status_code", None)
    if c:
        return int(c)
    m = re.search(r"\b([45]\d\d)\b", str(e))
    return int(m.group(1)) if m else None


def explain(e):
    text = str(e).strip().splitlines()[0][:200] if str(e).strip() else e.__class__.__name__
    try:
        body = e.response.json().get("message")
    except Exception:
        body = None
    if body and str(body) not in text:
        text += " - " + str(body)[:200]
    low = text.lower()
    if "workflow" in low and ("permission" in low or "scope" in low or "refusing" in low):
        text += "\nThe app's GitHub sign-in cannot write workflow files (needs the 'Workflows' permission)."
    return text


def req(host, method, path, **kw):
    last = None
    for attempt in range(3):
        try:
            return host.gh.request(method, path, **kw)
        except Exception as e:
            last = e
            c = code(e)
            if attempt < 2 and (c is None or c >= 500):
                time.sleep(1.5)
                continue
            raise
    raise last


def default_branch(host):
    try:
        return req(host, "GET", "").json().get("default_branch") or "main"
    except Exception:
        return "main"


def ref_of(host):
    """The branch the workflow file is read from: lab for a Lab tool, else the default branch."""
    return "lab" if getattr(host, "source", "lab") == "lab" else default_branch(host)


def head(host, branch):
    sha = req(host, "GET", "/git/ref/heads/" + branch).json()["object"]["sha"]
    return sha, req(host, "GET", "/git/commits/" + sha).json()["tree"]["sha"]


def files_of(host, tree_sha):
    d = req(host, "GET", "/git/trees/" + tree_sha, params={"recursive": "1"}).json()
    if d.get("truncated"):
        raise RuntimeError("The repo is too big to list through the API.")
    return {e["path"]: e for e in d.get("tree", []) if e.get("type") == "blob"}


def blob_text(host, entry):
    d = req(host, "GET", "/git/blobs/" + entry["sha"]).json()
    return base64.b64decode(d.get("content", "")).decode("utf-8")


def commit(host, branch, hd, changes, message, modes=None):
    """One commit; changes = {path: text, or None to delete}."""
    entries = []
    for path, text in sorted(changes.items()):
        if text is None:
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
        else:
            entries.append({"path": path, "mode": (modes or {}).get(path, "100644"), "type": "blob", "content": text})
    tree = req(host, "POST", "/git/trees", json={"base_tree": hd[1], "tree": entries}).json()["sha"]
    new = req(host, "POST", "/git/commits", json={"message": message, "tree": tree, "parents": [hd[0]]}).json()["sha"]
    req(host, "PATCH", "/git/refs/heads/" + branch, json={"sha": new, "force": False})
    return new


def atomic(host, branch, build, message):
    """build(files) -> (changes, modes, extra) from the LATEST state; one commit; retried
    when somebody else committed in between. -> (commit sha or None, extra)"""
    last = None
    for attempt in range(3):
        hd = head(host, branch)
        files = files_of(host, hd[1])
        changes, modes, extra = build(files)
        if not changes:
            return None, extra
        try:
            return commit(host, branch, hd, changes, message, modes), extra
        except Exception as e:
            last = e
            if code(e) in (409, 422) and "workflow" not in explain(e).lower() and attempt < 2:
                time.sleep(1.5)
                continue
            raise
    raise last


def put_file(host, path, text, branch, message):
    """Create or replace one file (contents API)."""
    body = {"message": message, "branch": branch, "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    try:
        cur = req(host, "GET", "/contents/" + path, params={"ref": branch}).json()
        body["sha"] = cur.get("sha")
    except Exception as e:
        if code(e) != 404:
            raise
    req(host, "PUT", "/contents/" + path, json=body)


def read_or_none(host, path, ref):
    try:
        return host.gh.read_file(path, ref=ref)
    except Exception as e:
        if code(e) == 404:
            return None
        raise


# ============================================================ the tool's screens
def _fail(host, what, err):
    text = what + "\n" + (err if isinstance(err, str) else explain(err))
    host.log("error:", text)

    def screen(h):
        h.title("Error")
        h.text(text)
        h.button("Copy error", lambda: h.copy(text))
        h.back_button()
    host.replace(screen)


def fail(host, what, err):
    _fail(host, what, err)


def build(host, workflow, title):
    host.title(title)
    host.status()
    host.set_status("Reading %s..." % workflow)
    host.back_button("Back")
    host.background(_load, host, workflow, done=lambda r, e: host.replace(_main, workflow, title, r) if e is None
                    else _fail(host, "Could not read the workflow file", e))


def _load(host, workflow):
    ref = ref_of(host)
    text = host.gh.read_file(".github/workflows/" + workflow, ref=ref)
    return {"text": text, "ref": ref, "inputs": core.declared_inputs(text)}


def _main(host, workflow, title, data):
    host.title(title)
    quick = core.check(data["text"])
    bad = sum(1 for f in quick if f["level"] == "error")
    warn = sum(1 for f in quick if f["level"] == "warn")
    host.text("%s on branch %s.\nQuick check: %d error(s), %d warning(s) - press Check for details."
              % (workflow, data["ref"], bad, warn))
    widgets = {}
    for name, spec in data["inputs"].items():
        if name in core.RUN_INPUTS:
            continue
        label = "%s%s%s" % (name, " *" if spec["required"] else "", (" - " + spec["description"][:60]) if spec["description"] else "")
        if spec["options"]:
            host.text(label)
            widgets[name] = host.choice(spec["options"], default=spec["default"] or spec["options"][0])
        elif spec["type"] == "boolean":
            host.text(label)
            widgets[name] = host.choice([("true", "true"), ("false", "false")], default=(spec["default"] or "false").lower())
        else:
            widgets[name] = host.input(label, text=spec["default"], multiline=("urls" in name or "links" in name))
    host.status()

    def run():
        values = {}
        for name, w in widgets.items():
            v = w.value if hasattr(w, "value") else w.text.strip()
            if v == "" and data["inputs"][name]["required"]:
                host.set_status("Fill in %s" % name)
                return
            if v == "":
                continue
            values[name] = v
        host.show(_run, workflow, title, values, data["text"])

    host.button("Run", run)
    host.button("Check workflow", lambda: host.show(_check, workflow, title))
    host.button("Report of the last run", lambda: host.show(_last, workflow, title))
    host.back_button("Back")


# ---------------------------------------------------------------- run
def _run(host, workflow, title, values, text):
    host.title("Running")
    host.status()
    host.set_status("Starting...")
    host.back_button("Back")
    host.background(_do_run, host, workflow, values, text, done=lambda r, e: host.replace(_run_done, workflow, title, r)
                    if e is None else _fail(host, "The run could not be started", e))


def _do_run(host, workflow, values, text):
    run_id = host.gh.dispatch(workflow, values)
    if not run_id:
        raise RuntimeError("The workflow was started but its run was not found. Look in the repo's Actions tab.")
    host.store.set("last_run", {"workflow": workflow, "run_id": run_id, "inputs": values})
    names = {"queued": "Queued on GitHub", "in_progress": "Running", "completed": "Finishing"}
    host.set_status("Run %s started" % run_id)
    conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s (run %s)" % (names.get(s, s), run_id)))
    host.set_status("Reading the result...")
    res = diagnose(host, run_id, conclusion, text)
    res.update({"run_id": run_id, "conclusion": conclusion, "inputs": values, "links": []})
    if conclusion == "success":
        try:
            res["links"] = list(host.gh.release_links(run_id, attempts=3, delay=2) or [])
        except Exception:
            pass
    res["report"] = _report(host, workflow, res, text)
    return res


def diagnose(host, run_id, conclusion, text):
    """What went wrong in a run: failed step, log tail, probable causes."""
    info = {"url": "", "failed": "", "tail": [], "errors": [], "causes": []}
    try:
        info["url"] = req(host, "GET", "/actions/runs/%s" % run_id).json().get("html_url", "")
    except Exception:
        pass
    if conclusion == "success":
        return info
    try:
        jobs = req(host, "GET", "/actions/runs/%s/jobs" % run_id, params={"per_page": 30}).json().get("jobs", [])
    except Exception:
        jobs = []
    if not jobs:
        info["causes"].append({"cause": "The run has no jobs: GitHub could not read the workflow file (or it was cancelled "
                                        "before starting).", "hint": "Check the YAML (indentation, quotes); press Check workflow."})
        return info
    bad = [j for j in jobs if j.get("conclusion") not in ("success", "skipped", None)] or jobs
    job = bad[0]
    step = next((s.get("name") for s in job.get("steps", []) if s.get("conclusion") == "failure"), "")
    info["failed"] = "%s > %s" % (job.get("name"), step or "?")
    log = ""
    try:
        log = req(host, "GET", "/actions/jobs/%s/logs" % job["id"]).text
    except Exception as e:
        info["errors"].append("(the log could not be downloaded: %s)" % explain(e)[:100])
    info["tail"], errs = core.log_tail(log, 50)
    info["errors"] += errs
    info["causes"] = core.explain_log(log)
    return info


def _report(host, workflow, res, text, findings=None):
    run = {"id": res.get("run_id"), "conclusion": res.get("conclusion"), "failed": res.get("failed"), "url": res.get("url")}
    return core.build_report(getattr(host, "id", "") or workflow, workflow, res.get("inputs"), run, findings or [],
                             res.get("causes"), res.get("tail"), res.get("errors"), text)


def _run_done(host, workflow, title, res):
    ok = res["conclusion"] == "success"
    host.title("Finished OK" if ok else "FAILED (%s)" % res["conclusion"])
    lines = ["Run %s" % res["run_id"]]
    if ok:
        lines.append("Files:" if res["links"] else "No release files found (the workflow may not upload any).")
        lines += res["links"]
    else:
        lines.append("Failed at: %s" % (res["failed"] or "?"))
        for c in res["causes"]:
            lines += ["", "- " + c["cause"], "  Fix: " + c["hint"]]
        if res["errors"]:
            lines += ["", "Error lines:"] + res["errors"][:6]
        lines += ["", "Copy report puts the log, the causes and the workflow in one text to paste for help."]
    host.text("\n".join(lines))
    host.button("Copy report", lambda: host.copy(res["report"]))
    if res.get("links"):
        host.button("Copy links", lambda: host.copy("\n".join(res["links"])))
    if res.get("url"):
        host.button("Open the run on GitHub", lambda: host.open_url(res["url"]))
    host.button("Check workflow", lambda: host.replace(_check, workflow, title))
    host.back_button("Back")


# ---------------------------------------------------------------- last run report
def _last(host, workflow, title):
    host.title("Last run")
    host.status()
    host.set_status("Loading...")
    host.back_button("Back")
    last = host.store.get("last_run")
    if not last or last.get("workflow") != workflow:
        host.set_status("This tool has no run yet.")
        return
    host.background(_do_last, host, workflow, last, done=lambda r, e: host.replace(_run_done, workflow, title, r)
                    if e is None else _fail(host, "Could not read the run", e))


def _do_last(host, workflow, last):
    run_id = last["run_id"]
    run = req(host, "GET", "/actions/runs/%s" % run_id).json()
    conclusion = run.get("conclusion") or run.get("status")
    text = host.gh.read_file(".github/workflows/" + workflow, ref=ref_of(host))
    res = diagnose(host, run_id, conclusion, text)
    res.update({"run_id": run_id, "conclusion": conclusion, "inputs": last.get("inputs"), "links": []})
    if conclusion == "success":
        try:
            res["links"] = list(host.gh.release_links(run_id, attempts=1, delay=1) or [])
        except Exception:
            pass
    res["report"] = _report(host, workflow, res, text)
    return res


# ---------------------------------------------------------------- static check
def _check(host, workflow, title):
    host.title("Check workflow")
    host.status()
    host.set_status("Checking...")
    host.back_button("Back")
    host.background(do_check, host, workflow, done=lambda r, e: host.replace(_check_done, workflow, title, r)
                    if e is None else _fail(host, "Check failed", e))


def do_check(host, workflow):
    ref = ref_of(host)
    text = host.gh.read_file(".github/workflows/" + workflow, ref=ref)
    files = set(files_of(host, head(host, ref)[1]))
    try:
        secrets = {s["name"] for s in req(host, "GET", "/actions/secrets", params={"per_page": 100}).json().get("secrets", [])}
    except Exception:
        secrets = None
    findings = core.check(text, {"files": files, "secrets": secrets})
    return {"text": text, "findings": findings, "fixable": core.fixable(findings), "ref": ref}


def format_findings(findings):
    order = {"error": 0, "warn": 1, "info": 2}
    sign = {"error": "x", "warn": "!", "info": "-"}
    return "\n".join("%s %s" % (sign[f["level"]], f["msg"]) + ("   [fixable]" if f["fix"] else "")
                     for f in sorted(findings, key=lambda f: order[f["level"]])) or "Nothing found."


def _check_done(host, workflow, title, data):
    host.title("Check: %s" % workflow)
    host.text("Branch %s\n\n%s" % (data["ref"], format_findings(data["findings"])))
    if data["fixable"]:
        host.text("Automatic fixes:\n" + "\n".join("  - " + core.FIXES[i] for i in data["fixable"]))
        if getattr(host, "source", "lab") == "lab":
            host.button("Apply the %d fix(es) to the lab branch" % len(data["fixable"]),
                        lambda: host.show(_fixing, workflow, title, data))
    rep = core.build_report(workflow, workflow, None, None, data["findings"], [], [], [], data["text"])
    host.button("Copy report", lambda: host.copy(rep))
    host.button("Check again", lambda: host.replace(_check, workflow, title))
    host.back_button("Back")


def _fixing(host, workflow, title, data):
    host.title("Applying fixes")
    host.status()
    host.set_status("Writing...")
    host.back_button("Back")
    host.background(apply_fix_to_lab, host, workflow, data["text"], data["fixable"],
                    done=lambda r, e: host.replace(_fixed, workflow, title, r) if e is None
                    else _fail(host, "Could not write the fix", e))


def apply_fix_to_lab(host, workflow, text, ids):
    """Fixes the workflow on the lab branch and keeps its stub on main in step."""
    new, applied, failed = core.apply_fixes(text, ids, core.workflow_title(text, workflow))
    lines = []
    if not applied:
        return ["Nothing could be fixed automatically."] + ["  %s: %s" % f for f in failed]
    path = ".github/workflows/" + workflow
    put_file(host, path, new, "lab", "lab: fix %s for the app (%s)" % (workflow, ", ".join(applied)))
    lines.append("Fixed on the lab branch: " + ", ".join(core.FIXES[i] for i in applied))
    lines += ["Could not fix %s: %s" % f for f in failed]
    main = default_branch(host)
    cur = read_or_none(host, path, main)
    if cur is not None and core.is_stub(cur):
        stub = core.make_stub(new, workflow)
        if stub != cur:
            put_file(host, path, stub, main, "lab: update the stub of %s" % workflow)
            lines.append("The stub on %s was updated too." % main)
    return lines


def _fixed(host, workflow, title, lines):
    host.title("Fixed")
    host.text("\n".join(lines))
    host.button("Check again", lambda: host.replace(_check, workflow, title))
    host.back_button("Back")
