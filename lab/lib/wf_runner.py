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
import os
import re
import sys
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
        if name in core.APP_SET_INPUTS:
            continue
        title_line = "%s%s" % (name, " *" if spec["required"] else "")
        if spec["description"]:
            title_line += "\n" + spec["description"][:90]
        host.text(title_line)                      # the title always sits above the box
        kind = core.widget_for(spec)
        if kind["kind"] == "choice":
            pick = getattr(host, "dropdown", None) or host.choice      # popup window; old builds: buttons
            widgets[name] = pick(kind["options"], default=kind["default"])
        else:
            widgets[name] = host.input("", text=core.default_token(spec["default"]),
                                       multiline=("urls" in name or "links" in name))
    host.status()

    def collect():
        values = {}
        for name, w in widgets.items():
            v = w.value if hasattr(w, "value") else w.text.strip()
            if v == "" and data["inputs"][name]["required"]:
                host.set_status("Fill in %s" % name)
                return None
            if v == "":
                continue
            values[name] = v
        return values

    def run():
        values = collect()
        if values is not None:
            host.show(_run, workflow, title, values, data["text"])

    def run_phone_wf():
        values = collect()
        if values is not None:
            host.show(_phone_workflow, workflow, title, values, data["text"])

    host.button("Run", run)
    try:
        if analyze(data["text"])["can"]:
            host.button("Run on this phone (Python steps only)", run_phone_wf)
    except Exception as e:
        host.log("phone check failed:", repr(e))
    adapter = _pending_adapter(data["text"])
    if adapter and _phone_lib() is not None:
        def phone():
            link = ""
            for key in ("url", "urls", "links"):
                link = (getattr(widgets.get(key), "text", "") or "").strip().split("\n")[0].strip()
                if link:
                    break
            if not link:
                host.set_status("Fill in the video link first")
                return
            host.show(_phone, adapter, title, link)
        host.button("Run on this phone (fast, no proxy)", phone)
    host.button("Check workflow", lambda: host.show(_check, workflow, title))
    host.button("Report of the last run", lambda: host.show(_last, workflow, title))
    host.back_button("Back")


# ============================================================ run a workflow on this phone
# The Python / shell steps of the workflow run inside the app with the phone's own network.
# GitHub-only steps (checkout, publish to a release, notifications) are skipped.
_SKIP_RE = re.compile(r"storage_publish|gh release|gh api|ntfy|softprops|git push|api\.github\.com|upload-artifact", re.I)
_BLOCK_RE = re.compile(r"\b(apt-get|apt|sudo|docker|ffmpeg|ffprobe|node|npm|npx|java|cargo|curl|wget|jq|unzip|zip|git|chromium|playwright)\b")
_PY_FILE_RE = re.compile(r"(?m)^\s*python3?\s+(?!-\s*<<)(?!-m\s+pip)\S")
_HEREDOC_RE = re.compile(r"(?ms)^python3?\s+-\s*<<-?\s*['\"]?(\w+)['\"]?[ \t]*\n(.*?)\n\1[ \t]*$")
_IMPORT_NAMES = {"beautifulsoup4": "bs4", "pyyaml": "yaml", "pillow": "PIL", "python-dateutil": "dateutil",
                 "opencv-python": "cv2", "scikit-learn": "sklearn", "pycryptodome": "Crypto", "pysocks": "socks",
                 "attrs": "attr", "typing-extensions": "typing_extensions"}
PHONE_KEEP_RUNS = 3


def _unq(v):
    v = (v or "").strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _indent_of(line):
    return len(line) - len(line.lstrip())


def _parse_step(lines, step_indent):
    key_indent = step_indent + 2
    ls = list(lines)
    ls[0] = " " * (step_indent + 2) + ls[0].lstrip()[2:]
    step = {"name": "", "run": "", "env": {}, "uses": "", "if": ""}
    i = 0
    while i < len(ls):
        line = ls[i]
        if not line.strip() or _indent_of(line) != key_indent:
            i += 1
            continue
        m = re.match(r"^\s*([A-Za-z_-]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, val = m.group(1), m.group(2).strip()
        if key in ("run", "env") and (key == "env" or val[:1] in ("|", ">")):
            j = i + 1
            block = []
            while j < len(ls) and (not ls[j].strip() or _indent_of(ls[j]) > key_indent):
                block.append(ls[j])
                j += 1
            if key == "run":
                nonempty = [b for b in block if b.strip()]
                cut = min((_indent_of(b) for b in nonempty), default=0)
                step["run"] = "\n".join(b[cut:] if b.strip() else "" for b in block).rstrip() + "\n"
            else:
                for b in block:
                    em = re.match(r"^\s+([A-Za-z_]\w*):\s*(.*)$", b)
                    if em:
                        step["env"][em.group(1)] = _unq(em.group(2))
            i = j
            continue
        if key == "run":
            step["run"] = _unq(val) + "\n"
        elif key == "name":
            step["name"] = _unq(val)
        elif key == "uses":
            step["uses"] = _unq(val)
        elif key == "if":
            step["if"] = _unq(val)
        i += 1
    return step


def steps_of(text):
    """The steps of the first job, read from the YAML text (no YAML library needed)."""
    lines = text.split("\n")
    si = next((i for i, l in enumerate(lines) if re.match(r"^\s+steps:\s*$", l)), None)
    if si is None:
        return []
    base = _indent_of(lines[si])
    groups, step_indent = [], None
    for l in lines[si + 1:]:
        if not l.strip() or l.lstrip().startswith("#"):
            if groups:
                groups[-1].append(l)
            continue
        ind = _indent_of(l)
        if ind <= base:
            break
        if step_indent is None:
            step_indent = ind
        if ind == step_indent and l.lstrip().startswith("- "):
            groups.append([l])
        elif groups:
            groups[-1].append(l)
    return [_parse_step(g, step_indent) for g in groups]


def _pip_packages(run):
    pk = []
    for m in re.finditer(r"pip3?\s+install\s+([^\n|&;]*)", run or ""):
        for tok in m.group(1).split():
            tok = tok.strip("'\"")
            if tok.startswith("-") or "$" in tok or tok.endswith((".txt", ".whl")) or "/" in tok:
                continue
            name = re.split(r"[=<>!~\[;]", tok)[0].strip()
            if name and name not in pk:
                pk.append(name)
    return pk


def _importable(pkg):
    import importlib.util
    name = _IMPORT_NAMES.get(pkg.lower(), re.sub(r"[-.]+", "_", pkg.lower()))
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def classify_step(step):
    """-> (mode, why): mode is run | libs | skip | blocked."""
    run = step.get("run") or ""
    cond = (step.get("if") or "").strip()
    if step.get("uses"):
        return "skip", "a GitHub action (%s)" % step["uses"].split("@")[0]
    if not run.strip():
        return "skip", "nothing to run"
    if cond and cond not in ("always()", "success()"):
        return "skip", "has a condition (not evaluated on the phone)"
    if _SKIP_RE.search(run):
        return "skip", "publishes or notifies through GitHub"
    lines = [l for l in run.splitlines() if l.strip() and not l.strip().startswith("#")]
    if lines and all(re.search(r"pip3?\s+install", l) for l in lines):
        return "libs", "installs libraries"
    heredoc = _HEREDOC_RE.search(run)
    scrubbed = run if not heredoc else run[:heredoc.start()] + run[heredoc.end():]
    m = _BLOCK_RE.search(scrubbed)
    if m:
        return "blocked", "needs the tool '%s', which a phone does not have" % m.group(1)
    if _PY_FILE_RE.search(scrubbed):
        return "blocked", "runs a script file of the repo"
    if re.search(r"(?m)^\S.*\bpython3?\s+-\s*<<", scrubbed):
        return "blocked", "uses the result of an inline Python script inside a shell command"
    return "run", "runs on this phone"


def analyze(text):
    """{steps:[{name, mode, why}], packages:[...], missing:[...], blocked:[why], can: bool}"""
    out = {"steps": [], "packages": [], "missing": [], "blocked": [], "can": False}
    steps = steps_of(text)
    for n, st in enumerate(steps, 1):
        mode, why = classify_step(st)
        name = st.get("name") or ("step %d" % n)
        out["steps"].append({"name": name, "mode": mode, "why": why})
        if mode in ("run", "libs"):
            for p in _pip_packages(st.get("run")):
                if p not in out["packages"]:
                    out["packages"].append(p)
        if mode == "blocked":
            out["blocked"].append("%s: %s" % (name, why))
    out["missing"] = [p for p in out["packages"] if not _importable(p)]
    out["can"] = bool(steps) and not out["blocked"] and any(s["mode"] == "run" for s in out["steps"])
    return out


# ---- libraries: pure-Python wheels from PyPI, downloaded on demand into the app's own folder
def _pypi_json(name):
    import requests
    r = requests.get("https://pypi.org/pypi/%s/json" % name, timeout=20)
    r.raise_for_status()
    return r.json()


def _pure_wheel(data):
    for f in data.get("urls") or []:
        if f.get("packagetype") == "bdist_wheel" and re.search(r"-(?:py2\.)?py3-none-any\.whl$", f.get("filename", "")):
            return f
    return None


def _requirements(data):
    names = []
    for req in (data.get("info") or {}).get("requires_dist") or []:
        base, _, marker = req.partition(";")
        if "extra" in marker or re.search(r"win32|Windows|python_version\s*<|implementation_name", marker):
            continue
        m = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", base)
        if m:
            names.append(m.group(1))
    return names


def plan_libs(packages, depth=3):
    """What has to be downloaded for these packages. Needs the network.
    -> {items:[{name, version, filename, url, size, sha256}], problems:[text], total:bytes}"""
    plan = {"items": [], "problems": [], "total": 0}
    seen = set()

    def visit(name, level):
        key = re.sub(r"[-_.]+", "-", name.lower())
        if key in seen or _importable(name):
            return
        seen.add(key)
        try:
            data = _pypi_json(name)
        except Exception as e:
            plan["problems"].append("%s: not found on PyPI (%s)" % (name, str(e)[:60]))
            return
        f = _pure_wheel(data)
        if not f:
            plan["problems"].append("%s: has native code (no pure-Python build), so it cannot run on a phone" % name)
            return
        plan["items"].append({"name": name, "version": (data.get("info") or {}).get("version", ""),
                              "filename": f["filename"], "url": f["url"], "size": f.get("size") or 0,
                              "sha256": (f.get("digests") or {}).get("sha256", "")})
        plan["total"] += f.get("size") or 0
        if level < depth:
            for dep in _requirements(data):
                visit(dep, level + 1)

    for p in packages:
        visit(p, 0)
    return plan


def _libdir(base):
    d = os.path.join(base, "phone_libs")
    os.makedirs(d, exist_ok=True)
    if d not in sys.path:
        sys.path.insert(0, d)
    return d


def install_libs(plan, base, on_log):
    import hashlib
    import importlib
    import requests
    import zipfile
    import io as _io
    target = _libdir(base)
    for it in plan["items"]:
        on_log("Downloading %s %s ..." % (it["name"], it["version"]))
        r = requests.get(it["url"], timeout=90)
        r.raise_for_status()
        if it["sha256"] and hashlib.sha256(r.content).hexdigest() != it["sha256"]:
            raise RuntimeError("%s: the download is damaged (checksum)" % it["name"])
        with zipfile.ZipFile(_io.BytesIO(r.content)) as z:
            for member in z.namelist():
                if member.startswith("/") or ".." in member.split("/"):
                    raise RuntimeError("%s: unsafe file name inside the package" % it["name"])
            z.extractall(target)
    importlib.invalidate_caches()


# ---- running the steps
def _atom(p, values, defaults):
    p = p.strip()
    if p[:1] in ("'", '"'):
        return p.strip("'\"")
    m = re.fullmatch(r"inputs\.(\w+)", p)
    if m:
        return values.get(m.group(1), defaults.get(m.group(1), ""))
    m = re.fullmatch(r"github\.(\w+)", p)
    if m:
        return {"run_id": "phone", "run_number": "1", "repository": "phone/local", "actor": "phone"}.get(m.group(1), "")
    return ""


def resolve(value, values, defaults):
    """${{ inputs.x }}, ${{ github.run_id }}, ${{ inputs.a || 'b' }}; anything fancier becomes ''."""
    def one(m):
        for part in m.group(1).split("||"):
            v = _atom(part, values, defaults)
            if v not in (None, ""):
                return str(v)
        return ""
    return re.sub(r"\$\{\{(.*?)\}\}", one, value or "", flags=re.S)


class _Tee:
    def __init__(self, on_log):
        self.on_log = on_log
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.on_log(line)
        return len(s)

    def flush(self):
        if self.buf:
            self.on_log(self.buf)
            self.buf = ""

    def isatty(self):
        return False


def _shell(script, env, cwd, on_log, state, want_env=False):
    """Runs shell lines with the phone's own sh. -> the exported variables when want_env."""
    import subprocess
    sh = "/system/bin/sh" if os.path.exists("/system/bin/sh") else "sh"
    if "ANDROID_ROOT" in env or os.path.exists("/system/bin/sh"):
        script = re.sub(r"(?m)^\s*set\s+-o\s+pipefail\s*$", "true", script)
        script = re.sub(r"(?m)^(\s*set\s+-[A-Za-z]*?)o\s+pipefail\b", r"\1", script)
    if want_env:
        script += "\nprintf '\\n__ENV_START__\\n'\nenv\n"
    try:
        p = subprocess.Popen([sh, "-c", script], cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace")
    except FileNotFoundError:
        raise RuntimeError("this phone has no shell to run the shell lines of the step")
    state["proc"] = p
    seen_env, exported = False, {}
    for line in p.stdout:
        line = line.rstrip("\n")
        if want_env and line == "__ENV_START__":
            seen_env = True
            continue
        if seen_env:
            if "=" in line and re.match(r"^[A-Za-z_]\w*=", line):
                k, v = line.split("=", 1)
                exported[k] = v
        else:
            on_log(line)
    p.wait()
    state["proc"] = None
    if state.get("cancel"):
        raise KeyboardInterrupt()
    if p.returncode != 0:
        raise RuntimeError("a shell line failed (exit code %s)" % p.returncode)
    return exported


def _python(body, env, cwd, on_log, state):
    """Runs the inline Python of a step inside the app (same phone, same network)."""
    saved = {k: os.environ.get(k) for k in env}
    old_cwd, old_out, old_err = os.getcwd(), sys.stdout, sys.stderr
    tee = _Tee(on_log)
    state["tid"] = __import__("threading").get_ident()
    try:
        for k, v in env.items():
            if os.environ.get(k) != v:
                os.environ[k] = v
        os.chdir(cwd)
        sys.stdout = sys.stderr = tee
        exec(compile(body, "<workflow step>", "exec"), {"__name__": "__main__"})
    except SystemExit as e:
        if e.code not in (None, 0):
            raise RuntimeError("the script stopped with exit code %s" % e.code)
    finally:
        tee.flush()
        sys.stdout, sys.stderr = old_out, old_err
        os.chdir(old_cwd)
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        state["tid"] = None


def cancel_phone(state):
    """Stops the run: kills the shell, or raises KeyboardInterrupt inside the Python step."""
    state["cancel"] = True
    p = state.get("proc")
    if p is not None:
        try:
            p.kill()
        except Exception:
            pass
    tid = state.get("tid")
    if tid:
        import ctypes
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(tid), ctypes.py_object(KeyboardInterrupt))


def _collect(workdir):
    out = []
    folder = os.path.join(workdir, "out")
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                out.append({"name": name, "path": path, "size": os.path.getsize(path)})
    return out


def phone_run(text, values, base, on_log, state):
    """Runs the workflow's steps on this phone. Blocking: call from a thread.
    -> {ok, error, files:[{name, path, size}], workdir}"""
    import shutil
    runs = os.path.join(base, "phone_runs")
    os.makedirs(runs, exist_ok=True)
    for old in sorted(os.listdir(runs))[:-PHONE_KEEP_RUNS]:
        shutil.rmtree(os.path.join(runs, old), ignore_errors=True)
    workdir = os.path.join(runs, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(workdir, exist_ok=True)
    _libdir(base)
    defaults = {n: core.default_token(s.get("default")) for n, s in core.declared_inputs(text).items()}
    gh_env_file = os.path.join(workdir, ".github_env")
    base_env = dict(os.environ)
    base_env.update({"CI": "true", "GITHUB_WORKSPACE": workdir, "RUNNER_TEMP": workdir, "GITHUB_RUN_ID": "phone",
                     "GITHUB_ENV": gh_env_file, "GITHUB_OUTPUT": os.path.join(workdir, ".github_output"),
                     "GITHUB_STEP_SUMMARY": os.path.join(workdir, ".github_summary"),
                     "PYTHONUNBUFFERED": "1"})
    carried = {}
    result = {"ok": False, "error": "", "files": [], "workdir": workdir}
    try:
        for n, st in enumerate(steps_of(text), 1):
            if state.get("cancel"):
                raise KeyboardInterrupt()
            mode, why = classify_step(st)
            name = st.get("name") or ("step %d" % n)
            if mode != "run":
                on_log("-- %s: skipped (%s)" % (name, why))
                continue
            on_log("== %s" % name)
            env = dict(base_env)
            env.update(carried)
            for k, v in (st.get("env") or {}).items():
                env[k] = resolve(v, values, defaults)
            run = resolve(st["run"], values, defaults) if "${{" in st["run"] else st["run"]
            m = _HEREDOC_RE.search(run)
            if m:
                pre, body, post = run[:m.start()], m.group(2), run[m.end():]
                if pre.strip():
                    env.update(_shell(pre, env, workdir, on_log, state, want_env=True))
                _python(body, env, workdir, on_log, state)
                if post.strip():
                    _shell(post, env, workdir, on_log, state)
            else:
                _shell(run, env, workdir, on_log, state)
            if os.path.exists(gh_env_file):
                for line in open(gh_env_file, errors="replace").read().splitlines():
                    if "=" in line:
                        k, v = line.split("=", 1)
                        carried[k] = v
        result["ok"] = True
    except KeyboardInterrupt:
        result["error"] = "Stopped."
    except Exception as e:
        result["error"] = str(e)[:300] or e.__class__.__name__
        on_log("!! " + result["error"])
    result["files"] = _collect(workdir)
    return result


# ---- screens
def _phone_base(host):
    import tempfile
    path = getattr(getattr(host, "store", None), "_path", None)
    return os.path.dirname(path) if isinstance(path, str) and path else tempfile.gettempdir()


def _size_text(n):
    return "%d B" % n if n < 1024 else ("%.1f KB" % (n / 1024.0) if n < 1048576 else "%.1f MB" % (n / 1048576.0))


def _phone_workflow(host, workflow, title, values, text):
    a = analyze(text)
    host.title("Run on this phone")
    lines = []
    for s in a["steps"]:
        mark = {"run": "RUN ", "libs": "LIBS", "skip": "skip", "blocked": "NO  "}[s["mode"]]
        lines.append("[%s] %s - %s" % (mark, s["name"], s["why"]))
    host.text("\n".join(lines))
    if a["blocked"]:
        host.text("This workflow cannot run on a phone:\n" + "\n".join(a["blocked"]) + "\nUse Run (GitHub).")
        host.back_button("Back")
        return
    if a["missing"]:
        host.text("Needs libraries that are not in the app: %s. They are checked on PyPI when you press Run "
                  "and the size is shown before anything is downloaded." % ", ".join(a["missing"]))
    host.status()

    def go():
        if a["missing"]:
            host.show(_phone_libs, workflow, title, values, text, a)
        else:
            host.show(_phone_running, workflow, title, values, text)
    host.button("Run on this phone", go)
    host.back_button("Back")


def _phone_libs(host, workflow, title, values, text, a):
    host.title("Libraries")
    host.text("Checking PyPI for: %s ..." % ", ".join(a["missing"]))
    host.status()
    host.back_button("Back")

    def work():
        return plan_libs(a["missing"])

    def done(plan, err):
        if err is not None:
            host.set_status("Could not check PyPI: %s" % str(err)[:80])
            return
        host.replace(_phone_libs_ask, workflow, title, values, text, plan)
    host.background(work, done=done)


def _phone_libs_ask(host, workflow, title, values, text, plan):
    host.title("Libraries")
    if plan["problems"]:
        host.text("Cannot run on a phone:\n" + "\n".join(plan["problems"]) + "\nUse Run (GitHub).")
        host.back_button("Back")
        return
    names = "\n".join("%s %s - %s" % (i["name"], i["version"], _size_text(i["size"])) for i in plan["items"])
    host.text("Download these libraries into the app (%s total)?\n\n%s" % (_size_text(plan["total"]), names))
    host.button("Download and run", lambda: host.replace(_phone_running, workflow, title, values, text, plan))
    host.back_button("Back")


def _phone_running(host, workflow, title, values, text, plan=None):
    host.title("Running on this phone")
    host.text("The workflow's steps run inside the app with this phone's network. Stop cancels it.")
    host.status()
    host.set_status("Starting...")
    log = host.input("", text="", multiline=True, height=320, paste=False)
    log.readonly = True
    state = {"lines": [], "cancel": False, "proc": None, "tid": None, "n": 0}

    def on_log(line):
        state["lines"].append(line)
        if len(state["lines"]) > 600:
            del state["lines"][:100]

    def refresh():
        if state["n"] != len(state["lines"]):
            state["n"] = len(state["lines"])
            log.text = "\n".join(state["lines"][-120:])
            host.set_status("Running... (%d lines)" % state["n"])
    host.every(1.0, refresh)
    host.button("Stop", lambda: cancel_phone(state))

    def work():
        base = _phone_base(host)
        if plan and plan["items"]:
            install_libs(plan, base, on_log)
        res = phone_run(text, values, base, on_log, state)
        res["log"] = list(state["lines"])
        return res

    def done(res, err):
        if err is not None:
            res = {"ok": False, "error": str(err)[:200], "files": [], "log": list(state["lines"]), "workdir": ""}
        host.replace(_phone_result, workflow, title, res)
    host.background(work, done=done)


_PROXY_LINE = re.compile(r"^\s*(?:\w+://)?(\d{1,3}(?:\.\d{1,3}){3}:\d{2,5})\b")


def _proxy_only(text):
    rows = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    hits = [m.group(1) for m in (_PROXY_LINE.match(ln) for ln in rows) if m]
    return "\n".join(hits) if rows and len(hits) * 2 >= len(rows) else ""


_TEXT_EXT = (".txt", ".json", ".csv", ".tsv", ".log", ".md", ".yml", ".yaml", ".xml", ".ini", ".list")


def _phone_result(host, workflow, title, res):
    host.title("Done on this phone" if res.get("ok") else "Not finished")
    if res.get("error"):
        host.text(res["error"])
    files = res.get("files") or []
    if not files and res.get("ok"):
        host.text("The workflow finished but put no file in out/.")
    for f in files[:3]:
        if f["name"].lower().endswith(_TEXT_EXT) and f["size"] <= 200 * 1024:
            try:
                content = open(f["path"], encoding="utf-8", errors="replace").read()
            except OSError:
                content = ""
            lines = len([ln for ln in content.splitlines() if ln.strip()])
            host.text("%s - %d line(s), %s" % (f["name"], lines, _size_text(f["size"])))
            box = host.input("", text=content or "(empty file)", multiline=True, height=320, paste=False)
            box.readonly = True
            host.button("Copy all", lambda c=content: host.copy(c))
            only = _proxy_only(content)
            if only:
                host.button("Copy IP:PORT only", lambda c=only: host.copy(c))
        else:
            host.text("%s - %s\nSaved on the phone: %s" % (f["name"], _size_text(f["size"]), f["path"]))
    log_text = "\n".join(res.get("log") or [])
    if log_text:
        host.button("Copy log", lambda: host.copy(log_text))
    host.back_button("Back")


# ---------------------------------------------------------------- Link Lab site adapter on the phone
PENDING_DIR = "lab_scripts/sites_pending/"


def _pending_adapter(text):
    """The adapter file a Link Lab site test workflow runs (lab_scripts/sites_pending/<id>.py), or None."""
    for f in core.referenced_files(text):
        if f.startswith(PENDING_DIR) and f.endswith(".py"):
            return f
    return None


def _phone_lib():
    try:
        from labx import site_phone
        return site_phone
    except Exception:
        return None


def _phone(host, adapter, title, link):
    host.title("On this phone")
    host.text("Runs the adapter inside the app with this phone's own network: no proxy, no config, no GitHub run.")
    host.status()
    host.set_status("Running...")
    host.back_button("Back")
    sp = _phone_lib()

    def work():
        text = read_or_none(host, adapter, "lab")
        if text is None:
            return {"error": adapter + " is not on the lab branch", "rows": [], "title": link, "extractor": "adapter"}
        return sp.run_code(text, link)

    def done(res, err):
        if err is not None:
            res = {"error": explain(err), "rows": [], "title": link, "extractor": "adapter"}
        host.replace(_phone_result, adapter, title, link, res)

    host.background(work, done=done)


def _phone_result(host, adapter, title, link, res):
    rows = res.get("rows") or []
    host.title("Done" if rows else "Nothing found")
    lines = ["%s" % (res.get("title") or link), "Phone run (this phone's network), %s" % res.get("extractor", "adapter")]
    if res.get("error"):
        lines.append("Error: %s" % res["error"])
    for row in rows:
        lines.append("%s  %s%s" % ("%sp" % row["h"] if row["h"] else "?", "m3u8" if row["hls"] else row["ext"], ""))
    host.text("\n".join(lines))
    for row in rows:
        host.button("Copy %s link" % ("%sp" % row["h"] if row["h"] else "this"), lambda u=row["url"]: host.copy(u))
    if len(rows) > 1:
        host.button("Copy all links", lambda: host.copy("\n".join(x["url"] for x in rows)))
    report = "\n".join(["Link Lab site adapter, run on the phone", "tool: %s" % title, "adapter: %s" % adapter,
                        "link: %s" % link, "error: %s" % (res.get("error") or "none")]
                       + ["%s %s" % (x["h"], x["url"]) for x in rows])
    host.button("Copy report", lambda: host.copy(report))
    host.button("Run again", lambda: host.replace(_phone, adapter, title, link))
    host.back_button("Back")


# ---------------------------------------------------------------- run
def _run_native(host, workflow, title, values, text):
    """Runs it with the app's own progress screen (the run's steps, cancel, Running jobs, notification and
    the same result screen as the other tools). Returns False when this app version cannot do that."""
    nav = getattr(host, "nav", None)
    if nav is None or not hasattr(nav, "job_manager") or not hasattr(nav, "_status_and_complete_callbacks"):
        return False
    from core.async_utils import run_in_background
    from services import generic_action_service as gas
    jm = nav.job_manager
    action = {"id": getattr(host, "id", "") or workflow, "title": title, "workflow": workflow, "workflow_inputs": {}}
    job = gas.create_action_job(jm, action, dict(values))
    nav.show_working("Starting workflow...", job=job)
    on_status, on_complete = nav._status_and_complete_callbacks(job)

    def fail(message):
        jm.complete(job, ok=False, error=message)
        on_complete(job)

    def thread():
        try:
            on_status("Starting workflow...")
            run_id = host.gh.dispatch(workflow, values)
            job.run_id = run_id
            if getattr(job, "cancel_requested", False):
                if run_id:
                    try:
                        req(host, "POST", "/actions/runs/%s/cancel" % run_id)
                    except Exception:
                        pass
                return
            if run_id is None:
                fail("Could not detect the workflow run. It may still be running on GitHub Actions.")
                return
            host.store.set("last_run", {"workflow": workflow, "run_id": run_id, "inputs": values})

            def relay(status):
                job.status = status
                on_status("%s..." % status)

            conclusion = host.gh.wait(run_id, on_status=relay)
            if job.is_done:
                return                                   # cancelled while waiting
            if conclusion != "success":
                fail("Action failed (%s)" % conclusion)
                return
            try:
                links = list(host.gh.release_links(run_id, attempts=3, delay=2) or [])
            except Exception:
                links = []
            if links:
                gas._finish_action(jm, run_id, job, on_complete)   # the app's own result screen (files, share, download)
                return
            res = diagnose(host, run_id, "success", text)          # a workflow that makes no release: our own result
            res.update({"run_id": run_id, "conclusion": "success", "inputs": values, "links": []})
            res["report"] = _report(host, workflow, res, text)
            jm.complete(job, ok=True, result_data={})

            def show():
                if getattr(jm, "current_job", None) is job:
                    host.replace(_run_done, workflow, title, res)

            nav.schedule(show)
        except Exception as e:
            fail("Error: %s" % str(e)[:60])

    run_in_background(thread)
    return True


def _run(host, workflow, title, values, text):
    try:
        if _run_native(host, workflow, title, values, text):
            return
    except Exception as e:
        host.log("the app's progress screen could not be used:", repr(e))
    host.title("Running")
    host.status(height=560)
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
    try:
        from labx import lab_jobs
    except Exception:
        lab_jobs = None
    if lab_jobs is not None:
        conclusion = lab_jobs.wait(host, run_id, host.set_status)     # the jobs of the run, like the Actions tab
    else:
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
