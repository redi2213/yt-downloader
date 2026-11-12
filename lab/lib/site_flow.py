"""Lab > Add workflow > "Add a tested site to Link Lab" (and the list of the sites already added).

A site adapter that was tested as a tool (lab_scripts/sites_pending/<id>.py, brought in with Add workflow)
is copied to lab_scripts/sites/<id>.py and listed in lab_scripts/sites/index.json, one commit on the lab
branch. From then on Link Lab (GitHub run: lab_scripts/links.py, phone: site_phone) uses it for the
domains of the site. Removing a site is one commit too. Nothing here touches the main branch.
"""
import json
import time

from labx import site_phone as sp
from labx import wf_runner as rn

LAB = "lab"


def _file_path(f):
    return f if isinstance(f, str) else str((f or {}).get("path", ""))


def pending_adapters(host):
    """[(tool dict, adapter path)] of the imported tools that hold an adapter under test."""
    text = rn.read_or_none(host, "lab/index.json", LAB)
    out = []
    for p in (json.loads(text).get("plugins", []) if text else []):
        for f in (p.get("imported") or {}).get("files", []):
            path = _file_path(f)
            if path.startswith(sp.PENDING_DIR) and path.endswith(".py"):
                out.append((p, path))
    return out


def build(host):
    host.title("Link Lab sites")
    host.text("A site that works as a tool (made with the guide for AI, tested on GitHub or on the phone) can be "
              "added to Link Lab itself here. Then Get links, Download and the phone check support it.")
    host.button("Add a tested site", lambda: host.show(_pick))
    host.button("Sites in Link Lab", lambda: host.show(_list))
    host.status()
    host.back_button("Back")


# ------------------------------------------------------------------ add
def _pick(host):
    host.title("Add a tested site")
    host.status()
    host.set_status("Looking for tested adapters...")
    host.back_button("Back")

    def done(items, err):
        if err is not None:
            rn.fail(host, "Could not read the tools.", err)
        else:
            host.replace(_pick_render, items)

    host.background(lambda: pending_adapters(host), done=done)


def _pick_render(host, items):
    host.title("Add a tested site")
    if not items:
        host.text("No adapter found. Bring in the adapter file and its test workflow with Add workflow first "
                  "(the guide for AI 'Link Lab site' tells the AI how to write them).")
    for tool, path in items:
        host.button("%s\n%s" % (tool.get("title", tool.get("id")), path), lambda p=path, t=tool: host.show(_confirm, p, t.get("title", "")))
    host.back_button("Back")


def confirm_for_tool(host, tool):
    """Called from a tool's own screen: its adapter, if it has one."""
    for f in (tool.get("imported") or {}).get("files", []):
        path = _file_path(f)
        if path.startswith(sp.PENDING_DIR) and path.endswith(".py"):
            host.show(_confirm, path, tool.get("title", ""))
            return
    host.set_status("This tool has no adapter file.")


def _confirm(host, path, title):
    host.title("Add to Link Lab")
    host.status()
    host.set_status("Reading the adapter...")
    host.back_button("Back")

    def work():
        return rn.read_or_none(host, path, LAB), sp.parse_index(rn.read_or_none(host, sp.INDEX, LAB))

    def done(res, err):
        if err is not None:
            rn.fail(host, "Could not read the adapter.", err)
        elif res[0] is None:
            rn.fail(host, path + " is not on the lab branch.", "Add the tool again with Add workflow.")
        else:
            host.replace(_confirm_render, path, title, res[0], res[1])

    host.background(work, done=done)


def _confirm_render(host, path, title, code, entries):
    info = sp.adapter_info(code)
    probs = sp.problems(info)
    sid = info.get("site_id") or ""
    lines = ["Adapter: %s" % path, "Site: %s (%s)" % (info.get("title") or sid or "?", sid or "no SITE_ID")]
    lines.append("Domains in the file: %s" % (", ".join(info["domains"]) or "-"))
    bad_imports = sp.unsafe_imports(info)
    lines.append("Phone: %s" % ("not available, it needs %s (GitHub only)" % ", ".join(bad_imports) if bad_imports
                                else "works (only requests / standard library)"))
    if any(e["id"] == sid for e in entries):
        lines.append("A site with this id is already added: adding replaces it.")
    host.title("Add to Link Lab")
    host.text("\n".join(lines))
    if probs:
        host.text("Cannot be added:\n- " + "\n- ".join(probs))
        host.back_button("Back")
        return
    box = host.input("Domains, comma separated", text=", ".join(info["domains"]))
    host.status()

    def go():
        domains = sp.clean_domains(box.text)
        if not domains:
            host.set_status("Type at least one domain (for example mysite.com).")
            return
        for e in entries:
            clash = [d for d in clean(e) if any(sp.domain_matches(d, x) or sp.domain_matches(x, d) for x in domains)]
            if e["id"] != sid and clash:
                host.set_status("%s is already used by the site %s." % (clash[0], e["id"]))
                return
        host.show(_apply, path, code, info, domains, title)

    host.button("Add to Link Lab", go)
    host.back_button("Back")


def clean(entry):
    return sp.clean_domains(entry.get("domains"))


def _apply(host, path, code, info, domains, title):
    sid = info["site_id"]
    host.title("Adding...")
    host.status()
    host.set_status("Saving to the lab branch...")

    def work():
        def build_files(files):
            cur = sp.parse_index(rn.blob_text(host, files[sp.INDEX])) if sp.INDEX in files else []
            entry = {"id": sid, "title": info.get("title") or sid, "domains": domains,
                     "file": sp.SITES_DIR + sid + ".py", "phone": not sp.unsafe_imports(info),
                     "enabled": True, "source": path, "added": time.strftime("%Y-%m-%d")}
            text = json.dumps({"sites": [e for e in cur if e["id"] != sid] + [entry]}, indent=2, ensure_ascii=False) + "\n"
            return {entry["file"]: code, sp.INDEX: text}, {}, None
        return rn.atomic(host, LAB, build_files, "Link Lab: add site " + sid)

    def done(res, err):
        if err is not None:
            rn.fail(host, "Could not add the site.", err)
        else:
            host.replace(_added, sid, domains)

    host.background(work, done=done)


def _added(host, sid, domains):
    host.title("Added")
    host.text("%s is now supported by Link Lab (%s).\nOpen Link Lab and paste a link of this site: Get links and "
              "Download use the adapter (GitHub: GitHub IP, proxies, configs; phone: this phone's network)." % (sid, ", ".join(domains)))
    host.button("Sites in Link Lab", lambda: host.replace(_list))
    host.back_button("Back")


# ------------------------------------------------------------------ list / remove
def _list(host):
    host.title("Sites in Link Lab")
    host.status()
    host.set_status("Loading...")
    host.back_button("Back")

    def done(entries, err):
        if err is not None:
            rn.fail(host, "Could not read the sites.", err)
        else:
            host.replace(_list_render, entries)

    host.background(lambda: sp.parse_index(rn.read_or_none(host, sp.INDEX, LAB)), done=done)


def _list_render(host, entries):
    host.title("Sites in Link Lab")
    if not entries:
        host.text("No site added yet.")
    for e in entries:
        host.button("%s\n%s%s" % (e.get("title") or e["id"], ", ".join(clean(e)), "" if e.get("phone", True) else "  (GitHub only)"),
                    lambda e=e: host.show(_remove_confirm, e))
    host.back_button("Back")


def _remove_confirm(host, entry):
    host.title("Remove %s?" % (entry.get("title") or entry["id"]))
    host.text("Link Lab stops using this adapter for %s. The tool you tested with stays." % ", ".join(clean(entry)))
    host.button("Remove from Link Lab", lambda: host.show(_remove, entry))
    host.back_button("Back")


def _remove(host, entry):
    host.title("Removing...")
    host.status()
    host.set_status("Saving to the lab branch...")

    def work():
        def build_files(files):
            cur = sp.parse_index(rn.blob_text(host, files[sp.INDEX])) if sp.INDEX in files else []
            text = json.dumps({"sites": [e for e in cur if e["id"] != entry["id"]]}, indent=2, ensure_ascii=False) + "\n"
            changes = {sp.INDEX: text}
            if entry["file"] in files:
                changes[entry["file"]] = None
            return changes, {}, None
        return rn.atomic(host, LAB, build_files, "Link Lab: remove site " + entry["id"])

    def done(res, err):
        if err is not None:
            rn.fail(host, "Could not remove the site.", err)
        else:
            host.replace(_list)

    host.background(work, done=done)
