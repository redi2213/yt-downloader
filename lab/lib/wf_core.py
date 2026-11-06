"""Pure helpers for "Add workflow" and the workflow runner (no Kivy, no network).

Works on the text of a GitHub Actions workflow file. No YAML library is needed
(the phone may not have one): the few things we read or change are found with
careful line handling, and a change is only used when the result still parses
(when a YAML library exists) - otherwise the original text is kept.

Findings are dicts {"level": "error|warn|info", "id": str, "msg": str, "fix": id or None}.
"""
import hashlib
import re

RUN_INPUTS = ("job_id", "run_title", "rerun")      # inputs the app fills in itself
APP_TAG = "run-${{ github.run_id }}"
STUB_NOTE = ["# REGISTRATION STUB. GitHub only starts a workflow by file name when the file exists on main.",
             "# The real definition lives on the `lab` branch (same path) and is what runs when the app",
             "# dispatches this file with ref=lab. Do not put steps here."]
FIXES = {
    "add_dispatch": "add workflow_dispatch (so the app can start it)",
    "add_inputs": "add the job_id / run_title inputs the app fills in",
    "set_run_name": "set run-name so the app finds its run",
    "add_permissions": "add permissions: contents: write",
    "fix_tag": "use the tag run-${{ github.run_id }}",
}
_FIX_ORDER = ["add_dispatch", "add_inputs", "set_run_name", "add_permissions", "fix_tag"]


def _f(level, fid, msg, fix=None):
    return {"level": level, "id": fid, "msg": msg, "fix": fix}


def git_blob_sha(text):
    """The sha GitHub gives a file with this text (compare without downloading)."""
    b = text.encode("utf-8")
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


_STUB_RE = re.compile(r"registration stub|stub (?:from|on) main", re.I)


def is_stub(text):
    """A Lab registration stub (same wording rules as Promote)."""
    text = text or ""
    if "STUB from main" in text or _STUB_RE.search(text):
        return True
    return len(text) < 3000 and bool(re.search(r"(?m)^  stub:\s*$", text))


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")
    return s[:30] or "workflow"


# ---------------------------------------------------------------- text structure
def _indent(line):
    return len(line) - len(line.lstrip(" "))


def _blank(line):
    return line.strip() == "" or line.lstrip().startswith("#")


def block_end(lines, start):
    """Index after the last line of the block that starts at ``start`` (lines that
    are indented, or "- " list items at column 0)."""
    last = start + 1
    i = start + 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            i += 1
            continue
        if line.lstrip().startswith("#") and _indent(line) == 0:
            i += 1
            continue
        if _indent(line) > 0 or line.startswith("- "):
            last = i + 1
            i += 1
            continue
        break
    return last


_TOP = re.compile(r"""^(["']?)([A-Za-z_][\w\-]*)\1\s*:(.*)$""")


def top_level(text):
    """{key: (line_index, rest_of_line)} for keys at column 0 (first one wins)."""
    out = {}
    for i, line in enumerate(text.split("\n")):
        if not line or line[0] in " \t#-":
            continue
        m = _TOP.match(line)
        if m and m.group(2) not in out:
            out[m.group(2)] = (i, m.group(3).split(" #")[0].strip())
    return out


def _unq(v):
    v = v.strip()
    if " #" in v and not v.startswith(("'", '"')):
        v = v.split(" #", 1)[0].strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1]
    return v


def workflow_title(text, fallback="Workflow"):
    top = top_level(text)
    return _unq(top["name"][1]) if "name" in top and top["name"][1] else fallback


def on_info(text):
    """How the triggers are written: form missing|scalar|list|inline_map|block_map|block_list."""
    lines = text.split("\n")
    top = top_level(text)
    if "on" not in top:
        return {"form": "missing", "events": [], "dispatch": False, "line": None, "end": None}
    i, rest = top["on"]
    if rest and rest[0] == "[":
        events = [e.strip().strip("'\"") for e in rest.strip("[]").split(",") if e.strip()]
        return {"form": "list", "events": events, "dispatch": "workflow_dispatch" in events, "line": i, "end": i + 1}
    if rest and rest[0] == "{":
        events = re.findall(r"([\w\-]+)\s*:", rest)
        return {"form": "inline_map", "events": events, "dispatch": "workflow_dispatch" in events, "line": i, "end": i + 1}
    if rest:
        return {"form": "scalar", "events": [rest.strip("'\"")], "dispatch": rest.strip("'\"") == "workflow_dispatch",
                "line": i, "end": i + 1}
    end = block_end(lines, i)
    body = [l for l in lines[i + 1:end] if not _blank(l)]
    if body and body[0].lstrip().startswith("- "):
        events = [l.lstrip()[2:].split("#")[0].strip().strip("'\"") for l in body if l.lstrip().startswith("- ")]
        return {"form": "block_list", "events": events, "dispatch": "workflow_dispatch" in events, "line": i, "end": end,
                "child_indent": _indent(body[0])}
    ci = min((_indent(l) for l in body), default=2)
    events = [m.group(1) for l in body if _indent(l) == ci for m in [re.match(r"\s*([\w\-]+)\s*:", l)] if m]
    return {"form": "block_map", "events": events, "dispatch": "workflow_dispatch" in events, "line": i, "end": end,
            "child_indent": ci}


def _dispatch_pos(lines, on):
    """(line index, indent, end) of the workflow_dispatch: line inside a block-map ``on``."""
    for i in range(on["line"] + 1, on["end"]):
        if re.match(r"\s*workflow_dispatch\s*:", lines[i]) and _indent(lines[i]) == on["child_indent"]:
            end = i + 1
            for j in range(i + 1, on["end"]):
                if lines[j].strip() == "" or _indent(lines[j]) > on["child_indent"]:
                    if lines[j].strip() != "":
                        end = j + 1
                else:
                    break
            return i, on["child_indent"], end
    return None


def declared_inputs(text):
    """{name: {description, required, default, type, options}} of workflow_dispatch."""
    lines = text.split("\n")
    on = on_info(text)
    out = {}
    if on["form"] != "block_map":
        return out
    pos = _dispatch_pos(lines, on)
    if not pos:
        return out
    i, w, end = pos
    k = i + 1
    while k < end and not re.match(r"\s*inputs\s*:\s*$", lines[k]):
        k += 1
    if k >= end:
        return out
    base = _indent(lines[k])
    head, cur = None, None
    for line in lines[k + 1:end]:
        if _blank(line):
            continue
        ind = _indent(line)
        if ind <= base:
            break
        if head is None:
            head = ind
        s = line.strip()
        if ind == head:
            m = re.match(r"^([\w\-]+):\s*$", s)
            if m:
                cur = {"description": "", "required": False, "default": "", "type": "string", "options": []}
                out[m.group(1)] = cur
            continue
        if cur is None:
            continue
        if s.startswith("- "):
            cur["options"].append(_unq(s[2:]))
            continue
        m = re.match(r"^([\w\-]+):\s*(.*)$", s)
        if m:
            key, val = m.group(1), _unq(m.group(2))
            if key == "required":
                cur["required"] = val.lower() == "true"
            elif key in ("description", "default", "type"):
                cur[key] = val
    return out


_USED = re.compile(r"""\binputs\.([A-Za-z_][\w\-]*)|github\.event\.inputs\.([A-Za-z_][\w\-]*)|inputs\[['"]([\w\-]+)['"]\]""")


def used_inputs(text):
    out = []
    for m in _USED.finditer(text):
        n = next(g for g in m.groups() if g)
        if n not in out:
            out.append(n)
    return out


def used_secrets(text):
    return sorted({m for m in re.findall(r"\bsecrets\.([A-Za-z_]\w*)", text) if m != "GITHUB_TOKEN"})


_EXEC = re.compile(r"""(?:^|[\s;&|(])(?:python3?|bash|sh|zsh|node|ruby|php|perl|source)\s+(?:-[\w\-]+(?:=\S+|\s+(?!\S+\.(?:py|sh|js)\b)\S+)?\s+)*(?:\./)?([A-Za-z0-9_][\w\-./]*\.(?:py|sh|js|mjs|rb|php|pl))\b""")
_REQ = re.compile(r"""pip3?\s+install\s+(?:[^\n]*?\s)?-r\s*(?:\./)?([A-Za-z0-9_][\w\-./]*\.txt)""")
_LOCAL_USES = re.compile(r"uses:\s*(\./[\w\-./]+)")


def referenced_files(text):
    """Repo files the workflow runs or installs from (scripts, requirements)."""
    out = []
    for rx in (_EXEC, _REQ):
        for m in rx.finditer(text):
            p = m.group(1)
            if "${{" in p or p.startswith(("http", "/")) or ".." in p.split("/"):
                continue
            if p not in out:
                out.append(p)
    return out


def local_actions(text):
    return [m.group(1) for m in _LOCAL_USES.finditer(text)]


def python_imports(text):
    """Module names a Python script imports (to find sibling files)."""
    mods = []
    for m in re.finditer(r"(?m)^\s*(?:from\s+([A-Za-z_][\w]*)|import\s+([A-Za-z_][\w, ]*))", text):
        if m.group(1):
            mods.append(m.group(1))
        else:
            mods += [x.strip().split(" ")[0] for x in m.group(2).split(",") if x.strip()]
    return mods


_REL = re.compile(r"gh\s+release\s+(?:create|upload|edit)|softprops/action-gh-release|actions/create-release|"
                  r"ncipollo/release-action|actions/upload-release-asset|marvinpinto/action-automatic-releases")
_TAG_OK = re.compile(r"run-\$\{\{\s*github\.run_id\s*\}\}|run-\$\{?GITHUB_RUN_ID\}?")


def uses_release(text):
    return bool(_REL.search(text))


def tag_ok(text):
    return bool(_TAG_OK.search(text))


def validate_yaml(text):
    """(True|False|None, message): None when no YAML library is available."""
    try:
        import yaml
    except Exception:
        return None, "not checked (no YAML library)"
    try:
        data = yaml.safe_load(text)
    except Exception as e:
        return False, str(e).splitlines()[0][:160] if str(e) else "YAML error"
    if not isinstance(data, dict):
        return False, "the file is not a YAML mapping"
    return True, "ok"


# ---------------------------------------------------------------- checks
def check(text, ctx=None):
    """Static findings. ctx: {"files": set of repo paths on the branch it will run from,
    "secrets": set of secret names or None (unknown)}."""
    ctx = ctx or {}
    out = []
    if any(l.startswith("\t") or re.match(r" *\t", l) for l in text.split("\n")):
        out.append(_f("error", "tabs", "The file indents with tab characters; YAML only allows spaces."))
    ok, msg = validate_yaml(text)
    if ok is False:
        out.append(_f("error", "yaml", "YAML error: " + msg))
    top = top_level(text)
    if "jobs" not in top:
        out.append(_f("error", "no_jobs", "No jobs: section found."))
    on = on_info(text)
    if on["form"] == "missing":
        out.append(_f("error", "no_on", "No on: section found.", "add_dispatch"))
    elif not on["dispatch"]:
        out.append(_f("error", "no_dispatch", "No workflow_dispatch trigger: the app can only start a workflow "
                      "that has it (now: %s)." % (", ".join(on["events"]) or "?"), "add_dispatch"))
    declared = declared_inputs(text)
    missing_app = [n for n in ("job_id", "run_title") if n not in declared]
    if missing_app:
        out.append(_f("warn", "inputs", "Missing input(s) %s: the app sends them with every run (job_id lets it find "
                      "exactly its run; run_title names it)." % ", ".join(missing_app), "add_inputs"))
    rn = top.get("run-name")
    if rn is None or "job_id" not in rn[1]:
        out.append(_f("warn", "run_name", "run-name does not contain inputs.job_id: the app cannot match the run "
                      "it started and falls back to guessing by time.", "set_run_name"))
    used = used_inputs(text)
    undeclared = [n for n in used if n not in declared and n not in RUN_INPUTS]
    if undeclared:
        out.append(_f("error", "undeclared", "Used but not declared as an input: %s (name typo?)" % ", ".join(undeclared)))
    rel = uses_release(text)
    if rel and not tag_ok(text):
        has_tag_name = bool(re.search(r"(?m)^\s*tag_name\s*:", text))
        out.append(_f("warn", "tag", "A release is made but its tag is not %s; the app finds the files by that tag." % APP_TAG,
                      "fix_tag" if has_tag_name else None))
    elif not rel:
        out.append(_f("info", "no_release", "No release upload found: fine for a test (read the log), but the app "
                      "will have no files to show."))
    if rel and not re.search(r"contents\s*:\s*write", text):
        out.append(_f("warn", "perm", "Makes a release but has no 'contents: write' permission (it fails with 403).",
                      "add_permissions"))
    secrets = used_secrets(text)
    if secrets:
        known = ctx.get("secrets")
        if known is None:
            out.append(_f("info", "secrets", "Uses secrets %s - make sure they exist in the repo "
                          "(could not check)." % ", ".join(secrets)))
        else:
            lost = [s for s in secrets if s not in known]
            out.append(_f("error" if lost else "info", "secrets",
                          ("Secret(s) not defined in this repo: %s" % ", ".join(lost)) if lost
                          else "Secrets used and defined: %s" % ", ".join(secrets)))
    files = ctx.get("files")
    if files is not None:
        for p in referenced_files(text):
            if p not in files:
                out.append(_f("error", "missing_file", "Runs %s but that file is not in the repo branch it runs from." % p))
        for p in local_actions(text):
            if not any(f.startswith(p.lstrip("./").rstrip("/") + "/") for f in files):
                out.append(_f("error", "missing_action", "Uses the local action %s which is not in the repo." % p))
    if re.search(r"runs-on\s*:\s*\[?\s*self-hosted", text):
        out.append(_f("warn", "self_hosted", "Needs a self-hosted runner; GitHub's own runners will not pick it up."))
    if on["dispatch"] and any(e in ("schedule", "push", "pull_request") for e in on["events"]):
        out.append(_f("info", "triggers", "Other triggers (%s) only work from the main branch; the Lab copy runs "
                      "only when started from the app." % ", ".join(e for e in on["events"] if e != "workflow_dispatch")))
    njobs = len(re.findall(r"(?m)^  [A-Za-z_][\w\-]*:\s*$", text[text.find("jobs:"):])) if "jobs" in top else 0
    if njobs > 1:
        out.append(_f("info", "jobs", "%d jobs: the app's progress view follows the first job." % njobs))
    return out


def fixable(findings):
    ids = []
    for f in findings:
        if f["fix"] and f["fix"] not in ids:
            ids.append(f["fix"])
    return [i for i in _FIX_ORDER if i in ids]


# ---------------------------------------------------------------- fixes
def _input_block(names, ei, step):
    desc = {"job_id": "Set by the app: unique id put in the run name so it can find this run",
            "run_title": "Set by the app: short name for this run"}
    out = []
    for n in names:
        out += [" " * ei + n + ":", " " * (ei + step) + "description: '%s'" % desc[n],
                " " * (ei + step) + "required: false", " " * (ei + step) + "default: ''",
                " " * (ei + step) + "type: string"]
    return out


def _fix_dispatch(text):
    lines = text.split("\n")
    on = on_info(text)
    f = on["form"]
    if f == "missing":
        top = top_level(text)
        if "jobs" not in top:
            raise ValueError("no jobs: section")
        at = top["jobs"][0]
        lines[at:at] = ["on:", "  workflow_dispatch:", ""]
    elif f == "scalar":
        lines[on["line"]:on["end"]] = ["on:", "  %s:" % on["events"][0], "  workflow_dispatch:"]
    elif f == "list":
        lines[on["line"]:on["end"]] = ["on:"] + ["  %s:" % e for e in on["events"]] + ["  workflow_dispatch:"]
    elif f == "block_map":
        lines.insert(on["line"] + 1, " " * on["child_indent"] + "workflow_dispatch:")
    elif f == "block_list":
        body = lines[on["line"] + 1:on["end"]]
        new = []
        for l in body:
            if _blank(l):
                new.append(l)
            elif l.lstrip().startswith("- ") and ":" not in l:
                new.append("  %s:" % l.lstrip()[2:].split("#")[0].strip().strip("'\""))
            else:
                raise ValueError("on: list has complex items")
        lines[on["line"] + 1:on["end"]] = new + ["  workflow_dispatch:"]
    else:
        raise ValueError("on: is written as an inline map")
    return "\n".join(lines)


def _fix_inputs(text):
    names = [n for n in ("job_id", "run_title") if n not in declared_inputs(text)]
    if not names:
        return text
    lines = text.split("\n")
    on = on_info(text)
    if on["form"] != "block_map":
        raise ValueError("on: is not a normal block")
    pos = _dispatch_pos(lines, on)
    if not pos:
        raise ValueError("workflow_dispatch: not found")
    i, w, end = pos
    step = 2
    rest = lines[i].split(":", 1)[1].split(" #")[0].strip()
    if rest in ("{}", "null", "~", ""):
        lines[i] = " " * w + "workflow_dispatch:"
    else:
        raise ValueError("workflow_dispatch has an unusual value")
    k = i + 1
    while k < end and not re.match(r"\s*inputs\s*:", lines[k]):
        k += 1
    if k < end:
        head = lines[k]
        irest = head.split(":", 1)[1].split(" #")[0].strip()
        if irest in ("{}", "null", "~"):
            lines[k] = " " * _indent(head) + "inputs:"
        elif irest:
            raise ValueError("inputs: has an unusual value")
        ei = None
        for l in lines[k + 1:end]:
            if not _blank(l):
                ei = _indent(l)
                break
        if ei is None or ei <= _indent(head):
            ei = _indent(head) + step
        lines[k + 1:k + 1] = _input_block(names, ei, step)
    else:
        lines[i + 1:i + 1] = [" " * (w + step) + "inputs:"] + _input_block(names, w + 2 * step, step)
    return "\n".join(lines)


def _fix_run_name(text, hint):
    lines = text.split("\n")
    top = top_level(text)
    name = _unq(top["name"][1]) if "name" in top else hint
    name = re.sub(r"[^\w .\-]", "", name).replace("'", "''")[:40] or "Run"
    new = "run-name: ${{ inputs.run_title || '%s' }} [${{ inputs.job_id }}]" % name
    if "run-name" in top:
        i, rest = top["run-name"]
        if rest[:1] in (">", "|"):
            raise ValueError("run-name is a multi-line value")
        lines[i] = new
    elif "name" in top:
        lines.insert(top["name"][0] + 1, new)
    else:
        lines.insert(0, new)
    return "\n".join(lines)


def _fix_permissions(text):
    lines = text.split("\n")
    top = top_level(text)
    if "permissions" in top:
        i, rest = top["permissions"]
        if rest:
            lines[i:i + 1] = ["permissions:", "  contents: write"]
        else:
            end = block_end(lines, i)
            for k in range(i + 1, end):
                if re.match(r"\s*contents\s*:", lines[k]):
                    lines[k] = re.sub(r"contents\s*:.*", "contents: write", lines[k].split("#")[0])
                    return "\n".join(lines)
            lines.insert(i + 1, "  contents: write")
    else:
        if "jobs" not in top:
            raise ValueError("no jobs: section")
        lines[top["jobs"][0]:top["jobs"][0]] = ["permissions:", "  contents: write", ""]
    return "\n".join(lines)


def _fix_tag(text):
    return re.sub(r"(?m)^(\s*)tag_name\s*:.*$", lambda m: "%stag_name: %s" % (m.group(1), APP_TAG), text)


def apply_fixes(text, ids, hint="Workflow"):
    """-> (new_text, applied_ids, failed[(id, reason)]). Never returns text that no longer
    parses (when a YAML library can tell): then the original text and a failure come back."""
    cur, applied, failed = text, [], []
    for fid in _FIX_ORDER:
        if fid not in ids:
            continue
        try:
            if fid == "add_dispatch":
                new = _fix_dispatch(cur) if not on_info(cur)["dispatch"] else cur
            elif fid == "add_inputs":
                new = _fix_inputs(cur)
            elif fid == "set_run_name":
                new = _fix_run_name(cur, hint)
            elif fid == "add_permissions":
                new = _fix_permissions(cur)
            else:
                new = _fix_tag(cur)
        except ValueError as e:
            failed.append((fid, str(e)))
            continue
        ok, msg = validate_yaml(new)
        if ok is False:
            failed.append((fid, "the result was not valid YAML (%s)" % msg))
            continue
        if new != cur:
            cur = new
            applied.append(fid)
    return cur, applied, failed


# ---------------------------------------------------------------- stub for main
def _dispatch_block(text):
    """Lines of the workflow_dispatch: block, re-indented to sit under 'on:' (2 spaces)."""
    on = on_info(text)
    if on["form"] != "block_map":
        return ["  workflow_dispatch:"]
    lines = text.split("\n")
    pos = _dispatch_pos(lines, on)
    if not pos:
        return ["  workflow_dispatch:"]
    i, w, end = pos
    shift = 2 - w
    out = []
    for k in range(i, end):
        l = lines[k]
        out.append("" if l.strip() == "" else " " * max(0, _indent(l) + shift) + l.strip())
    out[0] = "  workflow_dispatch:"
    while out and out[-1] == "":
        out.pop()
    return out


def make_stub(text, workflow_file):
    """The registration stub that goes to main: same name, run-name and
    workflow_dispatch inputs, but no real steps (the real file runs from lab)."""
    top = top_level(text)
    lines = text.split("\n")
    out = []
    stem = workflow_file.rsplit(".", 1)[0]
    out.append(lines[top["name"][0]] if "name" in top else "name: %s" % stem)
    if "run-name" in top and top["run-name"][1][:1] not in (">", "|"):
        out.append(lines[top["run-name"][0]])
    out += ["", "on:"] + _dispatch_block(text)
    if "permissions" in top:
        i = top["permissions"][0]
        out += [""] + lines[i:block_end(lines, i)]
    else:
        out += ["", "permissions:", "  contents: write"]
    out += [""] + STUB_NOTE + ["jobs:", "  stub:", "    runs-on: ubuntu-latest", "    steps:",
                              '      - run: echo "Stub on main. The real workflow runs from the lab branch."', ""]
    return "\n".join(out)


# ---------------------------------------------------------------- GitHub links
def parse_github_url(url):
    """-> {"kind": "file"|"dir"|"repo"|"raw", owner, repo, ref, path} or None."""
    u = (url or "").strip().split("#")[0].split("?")[0].rstrip("/")
    m = re.match(r"https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", u)
    if m:
        return {"kind": "file", "owner": m.group(1), "repo": m.group(2), "ref": m.group(3), "path": m.group(4)}
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/(?:blob|raw)/([^/]+)/(.+)$", u)
    if m:
        return {"kind": "file", "owner": m.group(1), "repo": m.group(2), "ref": m.group(3), "path": m.group(4)}
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)(?:/(.+))?$", u)
    if m:
        return {"kind": "dir", "owner": m.group(1), "repo": m.group(2), "ref": m.group(3), "path": m.group(4) or ""}
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?$", u)
    if m:
        return {"kind": "repo", "owner": m.group(1), "repo": m.group(2), "ref": None, "path": ""}
    if re.match(r"https?://\S+\.ya?ml$", u):
        return {"kind": "raw", "url": u, "owner": None, "repo": None, "ref": None,
                "path": u.rsplit("/", 1)[-1]}
    return None


def raw_url(info, path=None):
    return "https://raw.githubusercontent.com/%s/%s/%s/%s" % (info["owner"], info["repo"], info["ref"], path or info["path"])


# ---------------------------------------------------------------- reading a failed run
_CAUSES = [
    (r"ModuleNotFoundError: No module named ['\"]([\w.\-]+)", "A Python package is missing: %s.",
     "Add a step before it: pip install <package> (or list it in requirements.txt and pip install -r)."),
    (r"ImportError: cannot import name", "An import failed (wrong version or name).", "Pin the package version, or check the name."),
    (r"(\S+): command not found", "A command is not installed on the runner: %s.", "Install it first (apt-get install -y ... or a setup action)."),
    (r"can't open file ['\"]?([^\s'\"]+)", "Python could not open the script %s.", "The file is not in the branch that runs (check the path and that it was copied)."),
    (r"No such file or directory[:\s]+['\"]?([^\s'\"]+)", "A file or folder is missing: %s.", "Check the path; a script that is only on another branch is not there."),
    (r"Resource not accessible by integration", "GitHub refused the write (403).", "Add 'permissions: contents: write' to the workflow."),
    (r"HttpError: Not Found|HTTP 404|404 Not Found", "A request returned 404 (a release, tag, file or URL does not exist).", "Check the tag/URL the step uses."),
    (r"HTTP 403|403 Forbidden", "A request was forbidden (403).", "The site blocked the runner, or the token lacks permission."),
    (r"HTTP Error 429|429 Too Many Requests|rate limit", "Rate limited (429).", "Wait, or use a proxy / fewer requests."),
    (r"already_exists|tag .* already exists|Validation Failed", "The release/tag already exists.", "Use a tag that is unique per run: " + APP_TAG),
    (r"Input required and not supplied: (\w+)", "An action needs the input %s.", "Pass it with 'with:' (maybe from a secret)."),
    (r"Unrecognized named-value: ['\"]?(\w+)", "A ${{ }} expression uses an unknown name: %s.", "Check the spelling in the expression."),
    (r"Invalid workflow file|workflow is not valid|You have an error in your yaml", "GitHub could not read the workflow file.", "Fix the YAML (indentation, quotes) - the run has no jobs."),
    (r"Unable to locate package ([\w.\-+]+)", "apt cannot find the package %s.", "Run 'sudo apt-get update' first, or check the name."),
    (r"SyntaxError:", "A Python script has a syntax error.", "Open the script on the lab branch and fix the line shown in the log."),
    (r"yt_dlp.*ERROR|ERROR: \[", "yt-dlp reported an error for the link.", "Check the link, update yt-dlp, or try a proxy / cookies."),
    (r"Process completed with exit code (\d+)", "A step ended with exit code %s.", "See the lines above it in the log for the real reason."),
    (r"The process '[^']*' failed with exit code (\d+)", "An action step failed (exit code %s).", "See its log lines."),
]


def explain_log(text):
    """[{"cause","hint"}] recognised in a log (most specific first, no repeats)."""
    out, seen = [], set()
    for rx, cause, hint in _CAUSES:
        m = re.search(rx, text or "", re.I)
        if not m:
            continue
        msg = cause % m.group(1) if "%s" in cause and m.groups() else cause
        if msg not in seen:
            seen.add(msg)
            out.append({"cause": msg, "hint": hint})
    return out


def log_tail(text, n=60):
    """Last n lines of a job log without the timestamps, plus all ##[error] lines."""
    lines = [re.sub(r"^\d{4}-\d\d-\d\dT[\d:.]+Z ", "", l) for l in (text or "").splitlines()]
    errors = [l for l in lines if "##[error]" in l]
    return lines[-n:], errors[:15]


def build_report(tool, workflow, inputs, run, findings, causes, tail, errors, yml, source=""):
    """One text the person can paste to get help fixing the tool."""
    L = ["# Workflow test report", "tool: %s" % tool, "workflow: %s" % workflow]
    if source:
        L.append("source: %s" % source)
    if inputs:
        L.append("inputs sent: " + ", ".join("%s=%s" % (k, (str(v)[:60] + "...") if len(str(v)) > 60 else v) for k, v in inputs.items()))
    if run:
        L += ["", "## Run", "id: %s" % run.get("id"), "result: %s" % run.get("conclusion"),
              "failed job/step: %s" % (run.get("failed") or "-"), "link: %s" % (run.get("url") or "-")]
    if findings:
        L += ["", "## Static checks"] + ["- [%s] %s" % (f["level"], f["msg"]) for f in findings if f["level"] != "info"]
    if causes:
        L += ["", "## Probable causes"] + ["- %s Fix: %s" % (c["cause"], c["hint"]) for c in causes]
    if errors:
        L += ["", "## Error lines"] + errors
    if tail:
        L += ["", "## Last lines of the log"] + tail
    if yml:
        L += ["", "## Workflow file", "```yaml", yml[:6000], "```"]
    return "\n".join(L)


# ---------------------------------------------------------------- self test
_SAMPLE = """name: My Tool
on:
  push:
    branches: [main]
jobs:
  go:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/run.py "${{ inputs.url }}"
      - run: gh release create v1 out.mp4
"""


def selftest():
    assert is_stub('run: echo "STUB from main (x)"') and not is_stub("real")
    assert is_stub('# REGISTRATION STUB.\njobs:\n  stub:\n    runs-on: x\n')
    assert not is_stub('jobs:\n  build:\n    steps:\n      - run: echo stubborn\n')
    f = check(_SAMPLE, {"files": {"scripts/other.py"}})
    ids = [x["id"] for x in f]
    assert "no_dispatch" in ids and "inputs" in ids and "run_name" in ids and "tag" in ids and "perm" in ids, ids
    assert "undeclared" in ids and "missing_file" in ids, ids
    fixed, applied, failed = apply_fixes(_SAMPLE, fixable(f), "My Tool")
    assert set(applied) >= {"add_dispatch", "add_inputs", "set_run_name", "add_permissions"}, (applied, failed)
    ok, msg = validate_yaml(fixed)
    assert ok in (True, None), msg
    d = declared_inputs(fixed)
    assert "job_id" in d and "run_title" in d, d
    assert "run-name: ${{ inputs.run_title || 'My Tool' }} [${{ inputs.job_id }}]" in fixed
    assert "contents: write" in fixed and on_info(fixed)["dispatch"]
    f2 = check(fixed)
    assert not [x for x in f2 if x["id"] in ("no_dispatch", "inputs", "run_name", "perm")], f2
    again, applied2, _ = apply_fixes(fixed, fixable(f2))
    assert again == fixed and not applied2
    for src in ("on: push\njobs:\n  a:\n    runs-on: x\n", "on: [push, pull_request]\njobs:\n  a:\n    runs-on: x\n",
                "on:\n  - push\n  - release\njobs:\n  a:\n    runs-on: x\n", "jobs:\n  a:\n    runs-on: x\n"):
        out, ap, fa = apply_fixes(src, ["add_dispatch"])
        assert on_info(out)["dispatch"] and not fa, (src, out, fa)
    ex = ("on:\n  workflow_dispatch:\n    inputs:\n      url:\n        required: true\n        type: string\n"
          "jobs:\n  a:\n    runs-on: x\n")
    out, ap, fa = apply_fixes(ex, ["add_inputs"])
    d = declared_inputs(out)
    assert set(d) == {"url", "job_id", "run_title"} and d["url"]["required"], (d, out)
    stub = make_stub(fixed, "lab-x.yml")
    assert "workflow_dispatch:" in stub and "job_id:" in stub and "REGISTRATION STUB" in stub and "scripts/run.py" not in stub
    assert is_stub(stub) and "push" not in stub.split("jobs:")[0]
    ok, _ = validate_yaml(stub); assert ok in (True, None)
    assert referenced_files("run: python -u scripts/a.py x\nrun: pip install -r req/r.txt\nrun: bash ./b.sh") == \
        ["scripts/a.py", "b.sh", "req/r.txt"]
    assert referenced_files('run: python -m pip install x\nrun: echo "out.json"') == []
    assert used_secrets("${{ secrets.TOKEN_X }} ${{ secrets.GITHUB_TOKEN }}") == ["TOKEN_X"]
    assert python_imports("import os, helper\nfrom lib2 import x\n") == ["os", "helper", "lib2"]
    assert parse_github_url("https://github.com/o/r/blob/main/.github/workflows/a.yml") == \
        {"kind": "file", "owner": "o", "repo": "r", "ref": "main", "path": ".github/workflows/a.yml"}
    assert parse_github_url("https://raw.githubusercontent.com/o/r/dev/x/a.yml")["ref"] == "dev"
    assert parse_github_url("https://github.com/o/r")["kind"] == "repo"
    assert parse_github_url("https://github.com/o/r/tree/main/.github/workflows")["kind"] == "dir"
    assert parse_github_url("https://example.com/a/b.yml")["kind"] == "raw" and parse_github_url("hello") is None
    causes = explain_log("ModuleNotFoundError: No module named 'requests'\n##[error]Process completed with exit code 1.")
    assert causes[0]["cause"].endswith("requests.") and len(causes) == 2, causes
    assert slugify("My-Tool v2!") == "my_tool_v2" and workflow_title(fixed) == "My Tool"
    assert git_blob_sha("hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    rep = build_report("t", "w.yml", {"a": 1}, {"id": 5, "conclusion": "failure"}, f, causes, ["l1"], ["e1"], "name: x")
    assert "Probable causes" in rep and "```yaml" in rep
    return "ok"


if __name__ == "__main__":
    print(selftest())
