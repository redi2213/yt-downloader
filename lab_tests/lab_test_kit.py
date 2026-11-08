"""Test kit for the Lab plugins (not an app file): a fake plugin host that talks to the real repo, loads the
plugins from the lab branch, drives their screens and measures how much of the text is translated.
Use:  exec(kit_source); K = setup(proxy_execute); K.collect(); print(K.report())"""
import base64, contextlib, importlib.util, io, json, re, sys, types
from types import SimpleNamespace

REPO = "/repos/redi2213/yt-downloader"


class FakeResp:
    def __init__(self, data, status=200, text=None):
        self._d = data; self.status_code = status; self._t = text
    def json(self):
        return json.loads(json.dumps(self._d, default=str)) if self._d is not None else {}
    @property
    def text(self):
        return self._t if self._t is not None else json.dumps(self._d)


class HttpErr(Exception):
    def __init__(self, status, body):
        super().__init__("%s %s" % (status, body)); self.response = FakeResp(body, status)


def make_kit(proxy):
    SEEN = []

    class FakeGH:
        def request(self, method, path, **kw):
            ep = REPO + (path if path.startswith("/") else ("/" + path if path else ""))
            with contextlib.redirect_stdout(io.StringIO()):
                r, e = proxy(method, ep, "github", query_params=kw.get("params"), body=kw.get("json"))
            if e:
                m = re.search(r"status (\d+)", str(e)); st = int(m.group(1)) if m else 500
                raise HttpErr(st, r.get("data") if isinstance(r, dict) else {"message": str(e)})
            return FakeResp(r if r is not None else {})
        def read_file(self, path, ref=None):
            r = self.request("GET", "/contents/" + path, params={"ref": ref})
            return base64.b64decode(r.json()["content"]).decode("utf-8")

    class UIHost:
        def __init__(self, source="lab"):
            self.gh = FakeGH(); self.stack = []; self.logs = []; self.copied = None; self.status_text = ""; self.store_d = {}
            self.source = source; self.id = "test"; self.opened = None
            self.store = SimpleNamespace(get=lambda k, d=None: self.store_d.get(k, d), set=lambda k, v: self.store_d.__setitem__(k, v))
            self._reset()
        def _reset(self): self.buttons = []; self.texts = []; self.inputs = []; self.choices = []
        def _enter(self, fn, *a): self._reset(); fn(self, *a)
        def show(self, fn, *a): self.stack.append((fn, a)); self._enter(fn, *a)
        def replace(self, fn, *a):
            if self.stack: self.stack[-1] = (fn, a)
            else: self.stack.append((fn, a))
            self._enter(fn, *a)
        def back(self):
            if len(self.stack) > 1: self.stack.pop(); fn, a = self.stack[-1]; self._enter(fn, *a)
        def title(self, t): self.texts.append(("title", t)); SEEN.append(t)
        def text(self, t, **k): self.texts.append(("text", t)); SEEN.append(t)
        def button(self, text, on_press=None, height=52): self.buttons.append((text, on_press)); SEEN.append(text)
        def input(self, hint="", text="", multiline=False, height=None, paste=True):
            o = SimpleNamespace(hint=hint, text=text); self.inputs.append(o); SEEN.append(hint); return o
        def choice(self, options, default=None, on_change=None):
            pairs = [(o[0], o[1]) if isinstance(o, (tuple, list)) else (o, o) for o in options]
            for p in pairs: SEEN.append(str(p[0]))
            o = SimpleNamespace(pairs=pairs, value=default if default is not None else pairs[0][1]); self.choices.append(o); return o
        def status(self): pass
        def set_status(self, t): self.status_text = str(t); SEEN.append(str(t))
        def back_button(self, text="Back", to=None): self.buttons.append((text, self.back)); SEEN.append(text)
        def background(self, fn, *a, done=None, same_screen=True):
            try: r, e = fn(*a), None
            except Exception as ex: r, e = None, ex
            if done: done(r, e)
        def log(self, *p): self.logs.append(" ".join(str(x) for x in p))
        def copy(self, t): self.copied = t
        def open_url(self, u): self.opened = u; return True
        def get(self, url, **kw):
            import requests
            return requests.get(url, timeout=20, **kw)
        def press(self, prefix):
            for t, f in self.buttons:
                if t.startswith(prefix): return f()
            raise AssertionError("no button %r in %s" % (prefix, [b[0] for b in self.buttons]))
        def screen_text(self): return "\n".join(t for k, t in self.texts)

    K = SimpleNamespace(SEEN=SEEN, UIHost=UIHost, HttpErr=HttpErr, FakeResp=FakeResp)
    H = UIHost()
    K.h = H

    def gh(path, ref):
        try: return H.gh.read_file(path, ref=ref)
        except HttpErr: return None

    # the app's own translation tables (main branch) + the real tr()
    core_pkg = types.ModuleType("core"); core_pkg.__path__ = []; sys.modules["core"] = core_pkg
    def loadc(name):
        text = gh("core/%s.py" % name, "main")
        m = types.ModuleType("core." + name); sys.modules["core." + name] = m; setattr(core_pkg, name, m)
        exec(compile(text, name, "exec"), m.__dict__); return m
    for n in ("fa_strings_msgs", "fa_strings_more", "fa_strings", "i18n"): loadc(n)
    K.i18n = sys.modules["core.i18n"]; K.fas = sys.modules["core.fa_strings"]; K.i18n.set_language("fa")

    # the Lab plugins as they are on the lab branch right now
    labx = types.ModuleType("labx"); labx.__path__ = []; sys.modules["labx"] = labx
    idx = json.loads(gh("lab/index.json", "lab")); K.index = idx["plugins"]
    mods = []
    for p in K.index:
        for m in p.get("modules") or []:
            if m not in mods: mods.append(m)
    K.src = {}
    def loadlab(rel, name):
        text = gh("lab/" + rel, "lab"); K.src[rel] = text
        m = types.ModuleType("labx." + name); sys.modules["labx." + name] = m; setattr(labx, name, m)
        exec(compile(text, rel, "exec"), m.__dict__); return m
    order = ["lib/lab_fa.py"] + [m for m in mods if m != "lib/lab_fa.py"] if "lib/lab_fa.py" in mods or gh("lab/lib/lab_fa.py", "lab") else mods
    for rel in order:
        name = rel.rsplit("/", 1)[-1][:-3]
        if "labx." + name not in sys.modules: loadlab(rel, name)
    K.labx = labx
    for p in K.index:
        if not p.get("imported"):
            try: K.__dict__["plugin_" + p["id"]] = loadlab(p["file"], "plugin_" + p["id"])
            except Exception as e: print("could not load plugin", p["id"], repr(e)[:80])

    def safe(fn, *a):
        try: return fn(*a)
        except Exception as e:
            print("  (skipped %s: %s)" % (getattr(fn, "__name__", fn), repr(e)[:100])); return None
    K.safe = safe
    K.H = lambda: UIHost()

    def collect():
        L = K.labx; pf = L.promote_flow; imp = L.wf_import; rn = L.wf_runner; wc = L.wf_core
        SEEN.clear(); Hn = K.H
        # ---- Promote
        h = Hn(); h.show(pf.build); safe(pf._perm_done, Hn(), "Workflow files (main): OK - can write\nBranch config: readable")
        data = pf._list_tools(h); safe(h.show, pf._pick_list, data)
        for row in data["rows"]:
            try: a = pf._analyze(Hn(), data, row)
            except Exception as e: print("analyze failed", row["entry"]["id"], repr(e)[:70]); continue
            safe(Hn().show, pf._check_result, a)
            if not a["errors"]:
                h5 = Hn(); h5.show(pf._form, a)
                form = {"title": "T", "id": row["entry"]["id"] + "_x", "plugin_file": row["entry"]["file"], "replace_origin": False, "group": "", "domains": [], "enabled": True,
                        "wf_names": {w["name"]: w["name"][4:] if w["name"].startswith("lab-") else w["name"] for w in a["workflows"] if w["promote"]}, "copy_scripts": True, "keep": True}
                plan = safe(pf._make_plan, h5, a, form)
                if plan:
                    safe(Hn().show, pf._preview_ready, plan)
                    if plan["risky"]: safe(Hn().show, pf._confirm2, plan)
        res = {"done": ["config branch updated (3 file(s) + config.json, version 12)", "main branch updated (2 file(s))", "lab/index.json marked"],
               "verify": ["config.json has the action: yes", "plugins/x.py on config: yes", ".github/workflows/x.yml on main: yes"], "record": "p-1", "action_id": "x"}
        safe(Hn().show, pf._apply_done, res)
        safe(Hn().show, pf._apply_failed, pf.StepError("Could not write main: 403 - Resource not accessible\nThe config branch is already updated: use Rollback to undo it.", ["config branch updated (3 file(s) + config.json, version 12)"]))
        safe(Hn().show, pf._apply_failed, RuntimeError("boom"))
        rec = {"id": "p-1", "tool": "x", "action_id": "x", "time": "2026-11-06T10:00:00Z", "status": "done", "previous_action": {"id": "x"}, "config_created": ["plugins/a.py"],
               "config_overwritten": {"plugins/b.py": "x"}, "main_created": [".github/workflows/x.yml"], "main_overwritten": {}}
        safe(Hn().show, pf._rb_list_ready, [rec, dict(rec, id="p-2", status="rolled_back")]); safe(Hn().show, pf._rb_list_ready, [])
        safe(Hn().show, pf._rb_detail_ready, {"rec": rec, "notes": ["The action 'x' was changed after this promotion; Rollback will overwrite it.", "plugins/x.py on main changed after the promotion"]})
        safe(Hn().show, pf._rb_detail_ready, {"rec": dict(rec, previous_action=None, status="rolled_back"), "notes": []})
        safe(Hn().show, pf._rb_done, {"done": ["config branch restored (config_version 12)", "main branch restored", "lab/index.json restored"]})
        safe(Hn().show, pf._rb_failed, pf.StepError("Could not restore main: boom", ["config branch restored (config_version 12)"]))
        safe(Hn().show, pf._error, "Could not load the list", "404 Not Found")
        row = next(r for r in data["rows"] if r["entry"]["id"] == "hello"); a = pf._analyze(Hn(), data, row)
        a["row"] = dict(a["row"], origin={"action_id": "tiktok_download", "file": "tiktok_download.py", "action": {"title": "T", "group": "upload"}})
        a["workflows"] = [{"name": "download.yml", "promote": True, "main_real": True, "state": "x", "lab_text": "a", "main_text": "b"},
                          {"name": "lab-x.yml", "promote": True, "main_real": False, "state": "x", "lab_text": "a", "main_text": None}]
        a["scripts"] = [{"path": "lab_scripts/a.py", "state": "new on main", "mode": "100644", "text": "x"}]; a["main_wf_names"] = ["download.yml"]
        safe(Hn().show, pf._form, a)
        safe(Hn().show, pf._check_result, dict(a, errors=["lib/x.py: syntax error, line 3: invalid syntax"], warnings=["x line 4: hardcoded ref"], info=["min_host 1 (app has 1)"]))
        form = {"title": "T", "id": "tiktok_download", "plugin_file": "tiktok_download.py", "replace_origin": True, "group": "", "domains": [], "enabled": True,
                "wf_names": {"download.yml": "download.yml", "lab-x.yml": "x.yml"}, "copy_scripts": True, "keep": True}
        plan = safe(pf._make_plan, Hn(), a, form)
        if plan: safe(Hn().show, pf._preview_ready, plan)
        # ---- Add workflow
        h = Hn(); h.show(imp.build); safe(Hn().show, imp._url_screen); safe(Hn().show, imp._paste_screen, None); safe(Hn().show, imp._upload_screen, None)
        safe(Hn().show, imp._choose_yml, [("a.yml", "x"), ("b.yml", "y")], {}, [], None)
        src = {"text": "name: Demo\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python scripts/x.py \"${{ inputs.u }}\"\n      - run: gh release create v1 f\n",
               "name": "demo.yml", "url": "", "info": None, "origin": "uploaded from the phone", "uploaded_deps": {}, "uploaded_missing": ["scripts/x.py"],
               "notes": ["notes.txt was not used by the workflow (ignored)"]}
        an = imp._do_analyze(Hn(), src, None); safe(Hn().show, imp._review, an)
        safe(Hn().show, imp._review, dict(an, deps={"scripts/x.py": "x"}, same=["scripts/y.py"], libs_ok=False))
        ex = {"id": "demo", "title": "Demo [imported]", "imported": {"workflow": "lab-demo.yml", "source": "https://github.com/a/b/blob/main/x.yml", "files": ["a", "b"], "added": "2026-11-06T10:00:00Z"}}
        safe(Hn().show, imp._review, dict(an, existing=ex))
        safe(Hn().show, imp._added, {"done": ["lab branch: workflow, 2 script file(s), the tool and its index entry", "main branch: registration stub", "fixed: add workflow_dispatch (so the app can start it)",
                                      "could not fix add_inputs: on: is not a normal block", "the old file name lab-a.yml was removed"], "title": "Demo [imported]", "id": "demo", "workflow": "lab-demo.yml"})
        safe(Hn().show, imp._mine_list, []); safe(Hn().show, imp._mine_list, [ex]); safe(Hn().show, imp._tool, ex)
        safe(Hn().show, imp._tool, dict(ex, imported=dict(ex["imported"], source="pasted"))); safe(Hn().show, imp._remove, ex)
        safe(Hn().show, imp._removed, ["lab branch cleaned", "stub removed from main"]); safe(Hn().show, imp._pick_file, {"items": [{"name": "a.yml", "path": "x/a.yml"}], "info": {}, "url": "u"}, None)
        safe(imp._copy_guide, Hn())
        SEEN.extend(["Picking a file works only inside the app on the phone. Use Paste workflow text here.", "No .yml file among the chosen files.",
                     "This is not a GitHub link to a .yml file, folder or repo.", "The file name must end with .yml", "Paste the workflow text first",
                     "Not found (is the repo public? is the link right?): https://x", "GitHub refused (rate limit?). Try again later.", "No .yml workflow files in .github/workflows"])
        # ---- runner screens
        d = {"text": "x", "ref": "lab", "inputs": {"url": {"description": "Direct link", "required": True, "default": "", "type": "string", "options": []},
             "quality": {"description": "", "required": False, "default": "720", "type": "choice", "options": ["480", "720"]},
             "flag": {"description": "yes or no", "required": False, "default": "false", "type": "boolean", "options": []}}}
        safe(Hn().show, rn._main, "lab-x.yml", "X [imported]", d)
        bad = wc.check("name: x\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: python scripts/a.py \"${{ inputs.q }}\" ${{ secrets.TOK }}\n      - run: gh release create v1 f\n", {"files": set(), "secrets": set()})
        safe(Hn().show, rn._check_done, "lab-x.yml", "X", {"ref": "lab", "findings": bad, "fixable": wc.fixable(bad), "text": "x"})
        safe(Hn().show, rn._check_done, "lab-x.yml", "X", {"ref": "lab", "findings": [], "fixable": [], "text": "x"})
        fail = {"run_id": 5, "conclusion": "failure", "failed": "run > Download the file", "url": "https://x", "links": [], "report": "r", "errors": ["##[error]Process completed with exit code 1."],
                "causes": wc.explain_log("ModuleNotFoundError: No module named 'requests'\nProcess completed with exit code 1"), "tail": [], "inputs": {}}
        safe(Hn().show, rn._run_done, "lab-x.yml", "X", fail)
        safe(Hn().show, rn._run_done, "lab-x.yml", "X", dict(fail, conclusion="success", links=["https://f/a.mp4"], causes=[], errors=[], failed=""))
        safe(Hn().show, rn._run_done, "lab-x.yml", "X", dict(fail, conclusion="success", links=[], causes=[], errors=[], failed=""))
        safe(Hn().show, rn._fixed, "lab-x.yml", "X", ["Fixed on the lab branch: add workflow_dispatch (so the app can start it)", "The stub on main was updated too."])
        safe(Hn().show, rn._last, "lab-x.yml", "X")
        SEEN.extend(["Fill in url", "This tool has no run yet.", "Starting workflow...", "Queued on GitHub (run 5)", "Running (run 5)", "Finishing (run 5)", "Reading the result...",
                     "Run 5 started", "Reading lab-x.yml...", "Checking...", "Writing...", "Loading...", "Starting...",
                     "Could not detect the workflow run. It may still be running on GitHub Actions.", "Action failed (failure)", "Error: boom",
                     "The workflow was started but its run was not found. Look in the repo's Actions tab."])
        # ---- messages made in wf_core
        cases = ["name: x\\n".replace("\\n", "\n") + "on:\n\tpush:\njobs:\n  a:\n    steps: []\n",
                 "name: x\njobs:\n  a:\n    runs-on: self-hosted\n    steps:\n      - run: python3 s/a.py\n      - uses: ./act\n      - run: gh release create v1 f\n        env:\n          T: ${{ secrets.A }}\n", wc._SAMPLE,
                 "on:\n  workflow_dispatch:\n    inputs:\n      a:\n        type: string\njobs:\n  a:\n    runs-on: x\n    steps:\n      - run: python3 _repo/scripts/storage_publish.py publish --dir out --tag t\n      - run: echo ${{ inputs.b }}\n  b:\n    runs-on: x\n    steps: []\n", "x: [\n"]
        for t in cases:
            for ctx in ({"files": {"z"}, "secrets": {"B"}}, {"files": None, "secrets": None}):
                for f in wc.check(t, ctx): SEEN.append(f["msg"])
        SEEN.extend(wc.FIXES.values())
        for rx, cause, hint in wc._CAUSES:
            SEEN.append(cause % "NAME" if "%s" in cause else cause); SEEN.append(hint)
        for w in wc.scan_assumptions('host.gh.read_file("lab/x")\nfoo(ref="lab")\nhost.gh.dispatch("a.yml", {}, ref="x")'): SEEN.append(w["msg"])
        for w in wc.scan_workflow("        ref: lab\n"): SEEN.append(w["msg"])
        # ---- the other Lab tools: first screens
        for p in K.index:
            if p["id"] in ("copy_tools", "hello", "link_lab", "mornye_lab", "m3u8_sniffer"):
                mod = K.__dict__.get("plugin_" + p["id"])
                if mod:
                    hh = Hn(); safe(hh.show, mod.build)
                    SEEN.extend([p.get("title", ""), p.get("description", "")])
        return len(set(SEEN))
    K.collect = collect

    ENG = re.compile(r"[A-Za-z]{3,}")
    ALLOW = {"GitHub", "YAML", "yml", "yaml", "Actions", "config", "main", "lab", "workflow_dispatch", "job_id", "run_title", "rerun", "contents", "write", "ntfy", "Arvan", "Cloud",
             "APK", "URL", "id", "py", "sh", "txt", "json", "env", "yt", "dlp", "boto", "run", "name", "storage", "secrets", "inputs", "out", "release", "tag", "tools"}
    def english_left(line):
        # drop things that are names, not words: paths, ids, files, quoted/backticked, with . / _ - : digits
        s = re.sub(r"`[^`]*`|'[^']*'|\"[^\"]*\"", " ", line)
        s = re.sub(r"\S*[./_\\:=#@$\d]\S*", " ", s)
        return [w for w in ENG.findall(s) if w not in ALLOW]
    def report(limit=400):
        out = []
        for t in sorted(set(SEEN)):
            if not t or not str(t).strip(): continue
            tr = K.i18n.tr(t)
            for line in str(tr).split("\n"):
                left = english_left(line)
                if len(left) >= 1 and (t, line) not in out:
                    out.append((t, line))
                    break
        return out
    K.report = report
    return K
