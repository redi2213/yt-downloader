"""Lab: Add workflow.

Brings a workflow made somewhere else into the Lab as a new tool under test:

  * from a link to a public GitHub file / folder / repo (the scripts it runs are fetched
    from the same repo), or
  * from pasted .yml text.

It checks the workflow against what the app needs (workflow_dispatch, job_id / run_title
inputs, run-name, release tag run-<id>, files, secrets) and offers one-tap fixes. Then:

  lab branch   .github/workflows/<name>.yml (real), the scripts, lab/wf_<id>.py, lab/index.json
  main branch  a registration stub with the same name and inputs (GitHub starts a workflow
               by file name only when it exists on main; the real file runs from lab)

The new tool (Lab > its name) has a form made from the workflow's inputs, Run, Check, and
an error report you can copy. When it works, use Promote to move it to Download Anything.
"""
import json
import re
import time

from labx import wf_core as core
from labx import wf_runner as rn

LAB = "lab"
WF = ".github/workflows"
LIBS = ["lib/wf_core.py", "lib/wf_runner.py"]
MAX_DEPS = 20
MAX_BYTES = 200000


def _fail(host, what, err):
    rn.fail(host, what, err)


# =============================================================== main screen
def build(host):
    host.title("Add workflow")
    host.text("Bring a workflow made elsewhere into the Lab as a new tool to test. It is checked against what the app "
              "needs and can be fixed automatically.")
    host.button("From a GitHub link", lambda: host.show(_url_screen))
    host.button("Paste workflow text", lambda: host.show(_paste_screen))
    host.button("My imported tools", lambda: host.show(_mine))
    host.status()
    host.back_button("Back")


# =============================================================== source: link
def _url_screen(host):
    host.title("From a GitHub link")
    host.text("A link to a workflow file, a folder (.github/workflows) or a whole repo. Public repos only; the app's "
              "GitHub sign-in is never sent to other repos.")
    url = host.input("https://github.com/owner/repo/blob/main/.github/workflows/x.yml", text="")
    host.status()

    def go():
        if core.parse_github_url(url.text) is None:
            host.set_status("This is not a GitHub link to a .yml file, folder or repo.")
            return
        host.show(_fetch, url.text.strip(), None)

    host.button("Fetch", go)
    host.back_button()


def _get(host, url):
    r = host.get(url)
    if r.status_code == 404:
        raise RuntimeError("Not found (is the repo public? is the link right?): " + url)
    if r.status_code == 403:
        raise RuntimeError("GitHub refused (rate limit?). Try again later.")
    r.raise_for_status()
    return r


def _fetch(host, url, existing=None):
    host.title("Fetching")
    host.status()
    host.set_status("Reading the link...")
    host.back_button()
    host.background(_do_fetch, host, url, done=lambda r, e: _fetched(host, r, existing) if e is None
                    else _fail(host, "Could not read the link", e))


def _do_fetch(host, url):
    info = core.parse_github_url(url)
    if info["kind"] == "raw":
        return {"src": {"text": _get(host, info["url"]).text, "name": info["path"], "url": url, "info": None}}
    if info["kind"] == "file":
        text = _get(host, core.raw_url(info)).text
        return {"src": {"text": text, "name": info["path"].rsplit("/", 1)[-1], "url": url, "info": info}}
    if not info["ref"]:
        info["ref"] = _get(host, "https://api.github.com/repos/%s/%s" % (info["owner"], info["repo"])).json().get("default_branch", "main")
    folder = info["path"] or ".github/workflows"
    items = _get(host, "https://api.github.com/repos/%s/%s/contents/%s?ref=%s" % (info["owner"], info["repo"], folder, info["ref"])).json()
    names = [i for i in items if isinstance(i, dict) and i.get("type") == "file" and i["name"].endswith((".yml", ".yaml"))]
    if not names:
        raise RuntimeError("No .yml workflow files in %s" % folder)
    return {"items": [{"name": i["name"], "path": i["path"]} for i in names], "info": info, "url": url}


def _fetched(host, res, existing):
    if "src" in res:
        host.replace(_analyze, res["src"], existing)
    else:
        host.replace(_pick_file, res, existing)


def _pick_file(host, res, existing):
    host.title("Pick the workflow")
    for it in res["items"]:
        host.button(it["name"], lambda i=it: host.show(_fetch_one, res["info"], i, existing))
    host.back_button()


def _fetch_one(host, info, item, existing):
    host.title("Fetching")
    host.status()
    host.set_status("Reading %s..." % item["name"])
    host.back_button()

    def work():
        one = dict(info, path=item["path"], kind="file")
        return {"text": _get(host, core.raw_url(one)).text, "name": item["name"], "info": one,
                "url": "https://github.com/%s/%s/blob/%s/%s" % (info["owner"], info["repo"], info["ref"], item["path"])}

    host.background(work, done=lambda r, e: host.replace(_analyze, r, existing) if e is None
                    else _fail(host, "Could not read the file", e))


# =============================================================== source: paste
def _paste_screen(host):
    host.title("Paste workflow text")
    host.text("Copy the whole .yml file and paste it below. Scripts it runs cannot come with pasted text: "
              "the check lists them, add them to the lab branch by hand.")
    name = host.input("File name, e.g. my-tool.yml", text="workflow.yml", paste=False)
    body = host.input("Paste the workflow here", multiline=True, height=260)
    host.status()

    def go():
        n = name.text.strip()
        if not re.fullmatch(r"[A-Za-z0-9][\w.\-]*\.ya?ml", n):
            host.set_status("The file name must end with .yml")
            return
        if not body.text.strip():
            host.set_status("Paste the workflow text first")
            return
        host.show(_analyze, {"text": body.text.replace("\r\n", "\n"), "name": n, "url": "", "info": None}, None)

    host.button("Analyze", go)
    host.back_button()


# =============================================================== analyze
def _analyze(host, src, existing=None):
    host.title("Analyzing")
    host.status()
    host.set_status("Checking the workflow...")
    host.back_button()
    host.background(_do_analyze, host, src, existing, done=lambda r, e: host.replace(_review, r) if e is None
                    else _fail(host, "Analysis failed", e))


def _fetch_deps(host, src):
    """Scripts the workflow runs, from the same public repo: {path: text}, [not found]."""
    info = src.get("info")
    deps, missing = {}, []
    if not info or info["kind"] != "file":
        return deps, missing
    direct = core.referenced_files(src["text"])
    queue = list(direct)
    seen = set()
    while queue and len(deps) < MAX_DEPS:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        if path.startswith((".github/", "lab/", "logs/")):
            continue
        try:
            r = host.get(core.raw_url(info, path))
        except Exception:
            missing.append(path)
            continue
        if r.status_code != 200 or len(r.content) > MAX_BYTES:
            missing.append(path)
            continue
        try:
            text = r.content.decode("utf-8")
        except UnicodeDecodeError:
            missing.append(path)
            continue
        deps[path] = text
        if path.endswith(".py"):                       # sibling modules it imports
            folder = path.rsplit("/", 1)[0] + "/" if "/" in path else ""
            for mod in core.python_imports(text):
                cand = "%s%s.py" % (folder, mod)
                if cand not in seen and cand not in queue:
                    queue.append(cand)
    # a guessed sibling that does not exist is not a problem; a script the workflow names is
    return deps, [m for m in missing if m in direct]


def _do_analyze(host, src, existing):
    host.set_status("Reading the lab and main branches...")
    lab = rn.files_of(host, rn.head(host, LAB)[1])
    main_branch = rn.default_branch(host)
    main = rn.files_of(host, rn.head(host, main_branch)[1])
    host.set_status("Fetching the scripts it runs...")
    deps, missing = _fetch_deps(host, src)
    try:
        secrets = {s["name"] for s in rn.req(host, "GET", "/actions/secrets", params={"per_page": 100}).json().get("secrets", [])}
    except Exception:
        secrets = None
    own = set(((existing or {}).get("imported") or {}).get("files", []))
    findings = core.check(src["text"], {"files": set(lab) | set(deps), "secrets": secrets})
    new_files, same_files, conflicts = {}, [], []
    for path, text in deps.items():
        cur = lab.get(path)
        if cur is None or path in own:
            new_files[path] = text
        elif cur["sha"] == core.git_blob_sha(text):
            same_files.append(path)
        else:
            conflicts.append(path)
    for p in conflicts:
        findings.append({"level": "error", "id": "conflict", "fix": None,
                         "msg": "%s already exists on the lab branch with different content (used by another tool); it is not overwritten." % p})
    for p in missing:
        findings.append({"level": "error", "id": "missing_file", "fix": None,
                         "msg": "%s is run by the workflow but could not be fetched from the repo." % p})
    index = json.loads(rn.read_or_none(host, "lab/index.json", LAB) or '{"plugins": []}')
    plugins = index.get("plugins") if isinstance(index, dict) else index
    return {"src": src, "findings": findings, "fixable": core.fixable(findings), "deps": new_files, "same": same_files,
            "lab_files": {p: e["sha"] for p, e in lab.items() if p.startswith((WF + "/", "lab/"))},
            "main_workflows": {p[len(WF) + 1:]: e["sha"] for p, e in main.items() if p.startswith(WF + "/")},
            "main_branch": main_branch, "ids": [p.get("id") for p in plugins if isinstance(p, dict)],
            "existing": existing, "libs_ok": all("lab/" + l in lab for l in LIBS)}


# =============================================================== review + add
def _report_text(a):
    src = a["src"]
    L = ["Source: %s" % (src["url"] or "pasted text"), "Workflow: %s" % src["name"], ""]
    L.append(rn.format_findings(a["findings"]))
    if a["fixable"]:
        L += ["", "Automatic fixes:"] + ["  - " + core.FIXES[i] for i in a["fixable"]]
    if a["deps"] or a["same"]:
        L += ["", "Scripts from the repo (added to the lab branch):"] + ["  + " + p for p in sorted(a["deps"])] + \
             ["  = %s (already there)" % p for p in a["same"]]
    return "\n".join(L)


def _review(host, a):
    src, ex = a["src"], a["existing"]
    stem = src["name"].rsplit(".", 1)[0]
    host.title("Review")
    text = _report_text(a)
    host.text(text)
    if not a["libs_ok"]:
        host.text("x The helper files lib/wf_core.py and lib/wf_runner.py are missing on the lab branch.")
    imp = (ex or {}).get("imported") or {}
    tid = host.input("Tool id (letters, digits, _)", text=(ex or {}).get("id") or core.slugify(stem))
    ttl = host.input("Tool title", text=((ex or {}).get("title") or core.workflow_title(src["text"], stem)).replace(" [imported]", ""))
    wfn = host.input("Workflow file name on the lab branch", text=imp.get("workflow") or (stem if stem.startswith("lab-") else "lab-" + stem) + ".yml")
    fix = None
    if a["fixable"]:
        fix = host.choice([("Apply the %d suggested fixes (recommended)" % len(a["fixable"]), True), ("Add exactly as it is", False)])
    host.status()

    def go():
        form = {"id": tid.text.strip(), "title": ttl.text.strip(), "workflow": wfn.text.strip(), "fix": True if fix is None else fix.value}
        problem = _validate(a, form)
        if problem:
            host.set_status(problem)
            return
        host.show(_add, a, form)

    host.button("Add to the Lab", go)
    host.button("Copy report", lambda: host.copy(text))
    host.back_button()


def _validate(a, form):
    if not a["libs_ok"]:
        return "lib/wf_core.py and lib/wf_runner.py must be on the lab branch"
    if not re.fullmatch(r"[a-z0-9_]{1,30}", form["id"]):
        return "Tool id: use a-z, 0-9 and _ only"
    if not form["title"]:
        return "Give the tool a title"
    if not re.fullmatch(r"[A-Za-z0-9][\w.\-]*\.ya?ml", form["workflow"]):
        return "The workflow file name must end with .yml"
    if form["workflow"] in ("build-apk.yml", "build-apk.yaml"):
        return "build-apk.yml is protected"
    ex = a["existing"]
    own_id = (ex or {}).get("id")
    if form["id"] in [p for p in a["ids"] if p != own_id]:
        return "The id '%s' is used by another Lab tool" % form["id"]
    wf_path = WF + "/" + form["workflow"]
    own_files = set(((ex or {}).get("imported") or {}).get("files", []))
    if wf_path in a["lab_files"] and wf_path not in own_files:
        return "%s already exists on the lab branch (another tool). Choose another name." % form["workflow"]
    if form["workflow"] in a["main_workflows"] and wf_path not in own_files:
        return "%s already exists on main. Choose another name (a Lab workflow needs a name main does not use)." % form["workflow"]
    plugin = "lab/wf_%s.py" % form["id"]
    if plugin in a["lab_files"] and plugin not in own_files:
        return "%s already exists" % plugin
    return None


def _add(host, a, form):
    host.title("Adding")
    host.status()
    host.set_status("Writing to the lab branch...")
    host.back_button()
    host.background(_do_add, host, a, form, done=lambda r, e: host.replace(_added, r) if e is None
                    else _fail(host, "Could not add the tool", e))


def _plugin_source(workflow, title):
    return ('"""Imported workflow tool (made by Lab > Add workflow). The workflow is %s/%s on the lab branch."""\n'
            "from labx import wf_runner\n\nWORKFLOW = %s\nTITLE = %s\n\n\ndef build(host):\n    wf_runner.build(host, WORKFLOW, TITLE)\n"
            % (WF, workflow, json.dumps(workflow), json.dumps(title)))


def _do_add(host, a, form):
    src, ex = a["src"], a["existing"]
    text, applied, failed = src["text"], [], []
    if form["fix"] and a["fixable"]:
        text, applied, failed = core.apply_fixes(text, a["fixable"], core.workflow_title(text, form["id"]))
    wf_path = WF + "/" + form["workflow"]
    plugin_path = "lab/wf_%s.py" % form["id"]
    files = [wf_path, plugin_path] + sorted(a["deps"])
    title = form["title"] + " [imported]"
    entry = {"id": form["id"], "title": title, "file": "wf_%s.py" % form["id"], "modules": list(LIBS),
             "description": "Imported workflow %s. Run, Check and a copyable error report inside; edit the workflow on the lab branch." % form["workflow"],
             "min_host": 1,
             "imported": {"workflow": form["workflow"], "source": src["url"] or "pasted", "files": files, "fixes": applied,
                          "added": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}
    done = []
    old_id = (ex or {}).get("id", form["id"])

    def build_lab(tree):
        changes = {wf_path: text, plugin_path: _plugin_source(form["workflow"], title)}
        changes.update(a["deps"])
        idx = json.loads(rn.blob_text(host, tree["lab/index.json"]))
        plugins = idx.get("plugins") if isinstance(idx, dict) else idx
        plugins = [p for p in plugins if not (isinstance(p, dict) and p.get("id") in (old_id, form["id"]))] + [entry]
        changes["lab/index.json"] = core.dump_index(plugins)
        return changes, None, None

    try:
        rn.atomic(host, LAB, build_lab, "lab: add imported workflow %s (%s)" % (form["workflow"], form["id"]))
    except Exception as e:
        raise RuntimeError("Could not write the lab branch (nothing changed): " + rn.explain(e))
    done.append("lab branch: workflow, %d script file(s), the tool and its index entry" % len(a["deps"]))
    main = a["main_branch"]
    stub = core.make_stub(text, form["workflow"])

    def build_main(tree):
        cur = tree.get(wf_path)
        if cur is not None and not core.is_stub(rn.blob_text(host, cur)):
            raise RuntimeError("%s on main is a real workflow; not overwritten" % form["workflow"])
        if cur is not None and cur["sha"] == core.git_blob_sha(stub):
            return {}, None, None
        return {wf_path: stub}, None, None

    try:
        sha, _ = rn.atomic(host, main, build_main, "lab: stub for %s" % form["workflow"])
        done.append("%s branch: registration stub%s" % (main, "" if sha else " (already there)"))
    except Exception as e:
        raise RuntimeError("The tool was added to the lab branch, but the stub on %s failed: %s\nWithout it the workflow cannot be "
                           "started. Fix the problem and add it again, or remove the tool from My imported tools." % (main, rn.explain(e)))
    for fid in applied:
        done.append("fixed: " + core.FIXES[fid])
    for f in failed:
        done.append("could not fix %s: %s" % f)
    return {"done": done, "title": title, "id": form["id"]}


def _added(host, res):
    host.title("Added")
    host.text("\n".join(["Done:"] + ["  - " + d for d in res["done"]] +
                        ["", "Open Lab and look for \"%s\": it has the form, Run, Check and the error report." % res["title"],
                         "When it works, use Promote to move it to Download Anything."]))
    host.back_button("Back")


# =============================================================== my imported tools
def _mine(host):
    host.title("My imported tools")
    host.status()
    host.set_status("Loading...")
    host.back_button()

    def work():
        idx = json.loads(rn.read_or_none(host, "lab/index.json", LAB) or '{"plugins": []}')
        plugins = idx.get("plugins") if isinstance(idx, dict) else idx
        return [p for p in plugins if isinstance(p, dict) and p.get("imported")]

    host.background(work, done=lambda r, e: host.replace(_mine_list, r) if e is None else _fail(host, "Could not load", e))


def _mine_list(host, tools):
    host.title("My imported tools")
    if not tools:
        host.text("Nothing imported yet.")
    for t in tools:
        host.button("%s\n%s" % (t.get("title"), t["imported"].get("workflow")), lambda x=t: host.show(_tool, x), height=64)
    host.back_button()


def _tool(host, t):
    imp = t["imported"]
    host.title(t.get("title", t["id"]))
    host.text("Workflow: %s\nSource: %s\nAdded: %s\nFiles: %d" % (imp.get("workflow"), imp.get("source"), imp.get("added"), len(imp.get("files", []))))
    if imp.get("source") and imp["source"] != "pasted":
        host.button("Update from the source link", lambda: host.show(_fetch, imp["source"], t))
    host.button("Remove this tool", lambda: host.show(_remove, t))
    host.back_button()


def _remove(host, t):
    host.title("Remove?")
    host.text("Deletes the tool, its workflow and scripts from the lab branch, and the stub from main. "
              "(A workflow already promoted to Download Anything is kept on main.)")
    host.button("Yes, remove it", lambda: host.replace(_removing, t))
    host.back_button()


def _removing(host, t):
    host.title("Removing")
    host.status()
    host.set_status("Removing...")
    host.back_button()
    host.background(_do_remove, host, t, done=lambda r, e: host.replace(_removed, r) if e is None else _fail(host, "Remove failed", e))


def _do_remove(host, t):
    imp = t["imported"]
    wf_path = WF + "/" + imp["workflow"]
    done = []

    def build_lab(tree):
        idx = json.loads(rn.blob_text(host, tree["lab/index.json"]))
        plugins = idx.get("plugins") if isinstance(idx, dict) else idx
        keep_files = set()
        for p in plugins:
            if isinstance(p, dict) and p.get("id") != t["id"]:
                keep_files |= set((p.get("imported") or {}).get("files", []))
        changes = {f: None for f in imp.get("files", []) if f in tree and f not in keep_files}
        plugins = [p for p in plugins if not (isinstance(p, dict) and p.get("id") == t["id"])]
        changes["lab/index.json"] = core.dump_index(plugins)
        return changes, None, None

    rn.atomic(host, LAB, build_lab, "lab: remove imported tool %s" % t["id"])
    done.append("lab branch cleaned")
    main = rn.default_branch(host)

    def build_main(tree):
        cur = tree.get(wf_path)
        if cur is not None and core.is_stub(rn.blob_text(host, cur)):
            return {wf_path: None}, None, None
        return {}, None, None

    sha, _ = rn.atomic(host, main, build_main, "lab: remove the stub of %s" % imp["workflow"])
    done.append("stub removed from %s" % main if sha else "main: nothing to remove (no stub)")
    return done


def _removed(host, done):
    host.title("Removed")
    host.text("\n".join("  - " + d for d in done))
    host.back_button("Back")
