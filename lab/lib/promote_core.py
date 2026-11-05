"""Pure helpers for the Promote tool (lab/promote.py): no Kivy, no network.

Everything here works on plain text and dicts, so it can be tested on a computer
(see selftest()). The plugin imports it as ``from labx import promote_core``.
"""
import copy
import datetime
import difflib
import hashlib
import json
import re

WF_DIR = ".github/workflows"
STUB_MARK = "STUB from main"
PROTECTED = ("build-apk.yml", "build-apk.yaml")        # never written by Promote
SKIP_DIRS = ("logs/", "backups/", ".github/")
_WF_NAME = re.compile(r"""["']([A-Za-z0-9][\w.\-]*\.ya?ml)["']""")


# ---------------------------------------------------------------- small utils
def iso_now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def new_record_id(tool):
    return "p-%s-%s" % (datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S"), tool)


def git_blob_sha(text):
    """The sha GitHub gives a file with this text (lets us compare without reading)."""
    b = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


_STUB_RE = re.compile(r"registration stub|stub (?:from|on) main", re.I)


def is_stub(text):
    """A Lab registration stub on main: the file only exists so GitHub accepts the
    dispatch (the real one runs from lab). Matches the wording used in this repo
    ("STUB from main", "REGISTRATION STUB", "Stub on main") or a tiny file whose only
    job is called stub."""
    text = text or ""
    if STUB_MARK in text or _STUB_RE.search(text):
        return True
    return len(text) < 3000 and bool(re.search(r"(?m)^  stub:\s*$", text))


def is_protected(name):
    return name.rsplit("/", 1)[-1] in PROTECTED


def diff_summary(old, new, max_lines=6):
    """(added, removed, sample_lines) between two texts."""
    plus = minus = 0
    sample = []
    for line in difflib.unified_diff((old or "").splitlines(), (new or "").splitlines(),
                                     lineterm="", n=0):
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            plus += 1
        elif line.startswith("-"):
            minus += 1
        if len(sample) < max_lines:
            sample.append(line[:90])
    return plus, minus, sample


# ---------------------------------------------------------------- plugin code scan
def detect_workflows(code):
    """Workflow file names the plugin mentions as string literals, in order:
    .dispatch("x.yml", ...), {"workflow": "x.yml"}, WORKFLOW = "x.yml", ..."""
    out = []
    for m in _WF_NAME.finditer(code):
        if m.group(1) not in out:
            out.append(m.group(1))
    return out


def _call_args(code, start):
    depth, i, quote = 1, start, None
    while i < len(code):
        ch = code[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return code[start:i]
        i += 1
    return code[start:]


def _top_args(args):
    parts, cur, depth, quote = [], [], 0, None
    i = 0
    while i < len(args):
        ch = args[i]
        if quote:
            cur.append(ch)
            if ch == "\\" and i + 1 < len(args):
                i += 1
                cur.append(args[i])
            elif ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            cur.append(ch)
        elif ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    if "".join(cur).strip():
        parts.append("".join(cur))
    return parts


def scan_assumptions(code):
    """Things that behave differently once the tool runs from Download Anything
    (config branch) instead of the Lab. Returns [{"level","line","msg"}]."""
    out = []
    lines = code.splitlines()
    for n, line in enumerate(lines, 1):
        if line.strip().startswith("#"):
            continue
        if re.search(r"""\bref\s*=\s*["']lab["']|["']ref["']\s*:\s*["']lab["']""", line):
            out.append({"level": "warn", "line": n,
                        "msg": 'hardcoded ref "lab": it will still read/run the lab branch after promotion'})
        if re.search(r"""["']lab/""", line):
            out.append({"level": "warn", "line": n,
                        "msg": 'path starting with "lab/": that folder exists only on the lab branch'})
    for m in re.finditer(r"\.read_file\(", code):
        args = _call_args(code, m.end())
        parts = _top_args(args)
        if len(parts) < 2 and not re.search(r"\bref\s*=", args):
            out.append({"level": "warn", "line": code.count("\n", 0, m.start()) + 1,
                        "msg": 'gh.read_file() without ref: the default changes from the lab branch '
                               'to the config branch after promotion - add ref= on purpose'})
    for m in re.finditer(r"\.dispatch\(", code):
        args = _call_args(code, m.end())
        if len(_top_args(args)) >= 3 or re.search(r"\bref\s*=", args):
            out.append({"level": "info", "line": code.count("\n", 0, m.start()) + 1,
                        "msg": "dispatch() with an explicit ref: it keeps using that ref after promotion"})
    return out


def scan_workflow(text):
    """Lines of a workflow that depend on the lab branch."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        if re.search(r"(?:^|\s)ref:\s*['\"]?lab\b|--branch[ =]lab\b|checkout\s+lab\b|origin/lab\b", line):
            out.append({"level": "warn", "line": n,
                        "msg": "checks out the lab branch explicitly: on main this would still use lab files"})
    return out


def rename_literal(code, old, new):
    """Replaces "old" / 'old' (quoted) with the new name; nothing else is touched."""
    return code.replace('"%s"' % old, '"%s"' % new).replace("'%s'" % old, "'%s'" % new)


# ---------------------------------------------------------------- workflow files
def workflow_file_refs(text, lab_paths):
    """Repo files (that exist on lab) which a workflow's text mentions: single
    files, or the files of a mentioned folder (small folders only)."""
    paths = set(lab_paths)
    out = set()
    for tok in set(re.findall(r"[\w./\-]+", text)):
        t = tok[2:] if tok.startswith("./") else tok
        t = t.strip("/")
        if not t or (t + "/").startswith(SKIP_DIRS) or t in (".", "..", "lab"):
            continue
        if t in paths:
            out.add(t)
            continue
        below = [p for p in paths if p.startswith(t + "/")]
        if below and len(below) <= 30 and not t.startswith(("lab/", ".")):
            out.update(below)
    return sorted(out)


def sibling_deps(path, text, paths):
    """Files in the same folder that this script imports / names."""
    folder = path.rsplit("/", 1)[0] if "/" in path else ""
    out = []
    for p in paths:
        if p == path:
            continue
        if (p.rsplit("/", 1)[0] if "/" in p else "") != folder:
            continue
        name = p.rsplit("/", 1)[-1]
        stem = name.rsplit(".", 1)[0]
        imp = r"(?m)^\s*(?:from\s+%s\b|import\s+(?:[\w.]+\s*,\s*)*%s\b)" % (re.escape(stem), re.escape(stem))
        if re.search(imp, text) or name in text:
            out.append(p)
    return out


def closure(start, read_fn, paths, limit=40):
    """``start`` plus the sibling scripts they import, recursively."""
    seen, queue = [], list(start)
    while queue and len(seen) < limit:
        p = queue.pop(0)
        if p in seen:
            continue
        seen.append(p)
        if p.endswith((".py", ".sh")):
            try:
                text = read_fn(p)
            except Exception:
                continue
            queue += [q for q in sibling_deps(p, text, paths) if q not in seen]
    return seen


# ---------------------------------------------------------------- config.json
def detect_indent(text):
    m = re.search(r'\n( +)["\[{]', text)
    return len(m.group(1)) if m else 2


def dump_json(data, indent=2):
    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"


def roundtrip_ok(text):
    """True when re-dumping the JSON gives the same bytes (so editing it only
    changes what we meant to change)."""
    try:
        return dump_json(json.loads(text), detect_indent(text)) == text
    except ValueError:
        return False


def parse_domains(text):
    return [d.strip().lower() for d in re.split(r"[,\s]+", text or "") if d.strip()]


def build_action(entry, aid, title, domains, group, enabled, plugin_file, modules):
    a = {"id": aid, "title": title, "icon": "download", "enabled": bool(enabled)}
    if domains:
        a["domains"] = list(domains)
    a.update({"plugin": aid, "file": plugin_file, "source": "config",
              "min_host": int(entry.get("min_host") or 1)})
    if group:
        a["group"] = group
    if modules:
        a["modules"] = list(modules)
    return a


def upsert_action(config_text, action):
    """Adds the action or replaces the one with the same id; bumps config_version.
    Other actions and keys are untouched. -> dict(text, previous, index, version_before, version_after)"""
    data = json.loads(config_text)
    indent = detect_indent(config_text)
    acts = data.setdefault("actions", [])
    idx = next((i for i, a in enumerate(acts) if a.get("id") == action["id"]), None)
    previous = copy.deepcopy(acts[idx]) if idx is not None else None
    if idx is None:
        acts.append(copy.deepcopy(action))
    else:
        acts[idx] = copy.deepcopy(action)
    before = int(data.get("config_version") or 0)
    data["config_version"] = before + 1
    return {"text": dump_json(data, indent), "previous": previous, "index": idx,
            "version_before": before, "version_after": before + 1}


def restore_action(config_text, action_id, previous, index):
    """Undo of upsert_action: puts the previous action back (or removes the new one).
    config_version goes UP by one (never back) so phones notice the change."""
    data = json.loads(config_text)
    indent = detect_indent(config_text)
    acts = data.setdefault("actions", [])
    idx = next((i for i, a in enumerate(acts) if a.get("id") == action_id), None)
    if previous is None:
        if idx is not None:
            del acts[idx]
    elif idx is not None:
        acts[idx] = copy.deepcopy(previous)
    else:
        acts.insert(min(index if index is not None else len(acts), len(acts)), copy.deepcopy(previous))
    before = int(data.get("config_version") or 0)
    data["config_version"] = before + 1
    return {"text": dump_json(data, indent), "version_before": before, "version_after": before + 1}


def find_action(config_text, action_id):
    for a in json.loads(config_text).get("actions", []):
        if a.get("id") == action_id:
            return a
    return None


def set_index_flags(index_text, tool_id, flags):
    """flags: {key: value or None}; None removes the key. -> (new_text, previous_flags)"""
    data = json.loads(index_text)
    plugins = data.get("plugins") if isinstance(data, dict) else data
    entry = next(p for p in plugins if isinstance(p, dict) and p.get("id") == tool_id)
    previous = {}
    for k, v in flags.items():
        previous[k] = entry.get(k)
        if v is None:
            entry.pop(k, None)
        else:
            entry[k] = v
    return dump_json(data, detect_indent(index_text)), previous


# ---------------------------------------------------------------- promotions.json
def load_records(text):
    if not text:
        return []
    data = json.loads(text)
    return data if isinstance(data, list) else data.get("records", [])


def add_record(text, record, keep=15):
    """Adds the record, or replaces the one with the same id; keeps the newest ``keep``."""
    recs = [r for r in load_records(text) if r.get("id") != record["id"]]
    recs.append(record)
    return dump_json(recs[-keep:])


# ---------------------------------------------------------------- self test
_SAMPLE_CFG = ('{\n  "config_version": 7,\n  "actions": [\n    {\n      "id": "a",\n      "title": "A",\n'
               '      "workflow": "a.yml"\n    },\n    {\n      "id": "b",\n      "title": "B \u062a\u0633\u062a",\n'
               '      "plugin": "b",\n      "group": "upload"\n    }\n  ],\n  "error_help": {\n    "x": "y"\n  }\n}\n')


def selftest():
    # stub + regex detection
    assert is_stub('run: echo "STUB from main (x)"') and not is_stub("real")
    assert is_stub('# REGISTRATION STUB. GitHub only starts...\njobs:\n  stub:\n    runs-on: x\n')
    assert is_stub('      - run: echo "Stub on main. The real workflow runs from the lab branch."')
    assert is_stub('jobs:\n  stub:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n')
    assert not is_stub('jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo stubborn\n')
    code = ('WORKFLOW = "my-flow.yml"\nhost.gh.dispatch("a.yml", {})\n'
            'host.run_action({"workflow": "b.yml", "workflow_inputs": {}}, {})\n')
    assert detect_workflows(code) == ["my-flow.yml", "a.yml", "b.yml"], detect_workflows(code)
    assert detect_workflows('x = "readme.txt"') == []
    # assumptions
    warns = scan_assumptions('host.gh.read_file("lab/x.txt")\nhost.gh.read_file("a", ref="config")\n'
                             'host.gh.read_file("a", "main")\nfoo(ref="lab")\nhost.gh.dispatch("a.yml", {}, ref="x")')
    kinds = [w["msg"][:20] for w in warns]
    assert sum("without ref" in w["msg"] for w in warns) == 1, warns
    assert any("hardcoded ref" in w["msg"] for w in warns) and any("explicit ref" in w["msg"] for w in warns)
    assert any("lab/" in w["msg"] for w in warns), kinds
    assert scan_workflow("      - uses: actions/checkout@v4\n        with:\n          ref: lab\n")
    assert not scan_workflow("      ref: ${{ github.ref }}")
    # rename
    assert rename_literal('d("lab-x.yml"); e(\'lab-x.yml\'); lab-x.yml', "lab-x.yml", "x.yml") == \
        'd("x.yml"); e(\'x.yml\'); lab-x.yml'
    # workflow file refs + closure
    lab = ["lab_scripts/a.py", "lab_scripts/b.py", "lab_scripts/c.sh", "lab/hello.py", "logs/x.txt", "README.md"]
    refs = workflow_file_refs("run: python lab_scripts/a.py\n cat logs/x.txt\n ref: lab\n uses: actions/checkout@v4", lab)
    assert refs == ["lab_scripts/a.py"], refs
    assert workflow_file_refs("cp -r lab_scripts .", lab) == ["lab_scripts/a.py", "lab_scripts/b.py", "lab_scripts/c.sh"]
    texts = {"lab_scripts/a.py": "import b\nprint(1)", "lab_scripts/b.py": "x=1", "lab_scripts/c.sh": "echo"}
    assert closure(["lab_scripts/a.py"], texts.__getitem__, lab) == ["lab_scripts/a.py", "lab_scripts/b.py"]
    # config upsert / restore
    assert roundtrip_ok(_SAMPLE_CFG)
    act = build_action({"min_host": 1}, "hello_test", "Hello", ["x.com"], "upload", True, "hello.py", ["lib/h.py"])
    r1 = upsert_action(_SAMPLE_CFG, act)
    assert r1["previous"] is None and r1["version_after"] == 8
    d1 = json.loads(r1["text"])
    assert [a["id"] for a in d1["actions"]] == ["a", "b", "hello_test"] and d1["error_help"] == {"x": "y"}
    r1b = upsert_action(r1["text"], dict(act, title="Hello 2"))       # re-promote = update, no duplicate
    d1b = json.loads(r1b["text"])
    assert [a["id"] for a in d1b["actions"]].count("hello_test") == 1 and r1b["previous"]["title"] == "Hello"
    assert d1b["config_version"] == 9
    back = restore_action(r1["text"], "hello_test", r1["previous"], r1["index"])
    dback = json.loads(back["text"])
    orig = json.loads(_SAMPLE_CFG)
    assert dback["actions"] == orig["actions"] and dback["error_help"] == orig["error_help"]
    assert dback["config_version"] == 9                                  # goes up, never back
    back2 = restore_action(r1b["text"], "hello_test", r1b["previous"], r1b["index"])
    assert json.loads(back2["text"])["actions"][-1]["title"] == "Hello"
    # records
    t = add_record(None, {"id": "p1", "status": "x"})
    t = add_record(t, {"id": "p2"})
    t = add_record(t, {"id": "p1", "status": "y"})
    assert [r["id"] for r in load_records(t)] == ["p2", "p1"] and load_records(t)[1]["status"] == "y"
    # index flags
    idx = '{\n  "plugins": [\n    {\n      "id": "h",\n      "file": "h.py"\n    }\n  ]\n}\n'
    t2, prev = set_index_flags(idx, "h", {"promoted": True, "promoted_as": "h"})
    assert json.loads(t2)["plugins"][0]["promoted"] is True and prev == {"promoted": None, "promoted_as": None}
    t3, _ = set_index_flags(t2, "h", prev)
    assert t3 == idx
    # sha + diff
    assert git_blob_sha("hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert diff_summary("a\nb\n", "a\nc\nd\n")[:2] == (2, 1)
    assert parse_domains("X.com, y.org  z.net") == ["x.com", "y.org", "z.net"]
    return "ok"


if __name__ == "__main__":
    print(selftest())
