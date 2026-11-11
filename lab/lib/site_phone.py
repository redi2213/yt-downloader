"""Site adapters on the phone (Lab). No Kivy, no widgets: Link Lab, the workflow runner and
site_flow use it.

A site adapter is the small module written with LINKLAB_SITE_GUIDE.md (SITE_ID, DOMAINS,
extract(url, proxy)). On the phone it runs with this phone's own network (proxy = None), so no
proxy or config is needed there. The code comes from the lab branch:

  lab_scripts/sites/index.json      the sites registered in Link Lab
  lab_scripts/sites/<id>.py         their adapters
  lab_scripts/sites_pending/<id>.py an adapter under test (read by the workflow runner)

Everything that reads GitHub is blocking: call it inside host.background().
"""
import ast
import json
import re
import sys
import types

LAB = "lab"
INDEX = "lab_scripts/sites/index.json"
SITES_DIR = "lab_scripts/sites/"
PENDING_DIR = "lab_scripts/sites_pending/"
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,30}$")
_PHONE_OK = {"requests", "yt_dlp", "certifi", "urllib3", "idna", "charset_normalizer"}
_STD_FALLBACK = {"re", "json", "os", "sys", "time", "html", "base64", "hashlib", "hmac", "math", "random", "string",
                 "datetime", "urllib", "itertools", "functools", "collections", "typing", "uuid", "ast", "types",
                 "binascii", "struct", "zlib", "gzip", "io", "textwrap", "difflib", "copy", "operator", "enum",
                 "dataclasses", "decimal", "fractions", "http", "email", "xml", "secrets", "pathlib", "__future__"}


def _stdlib():
    return set(getattr(sys, "stdlib_module_names", ())) or _STD_FALLBACK


def host_of(url):
    m = re.match(r"^[a-z][a-z0-9+.-]*://(?:[^/@]*@)?([^/:?#]+)", str(url or "").strip(), re.I)
    h = (m.group(1) if m else "").lower()
    return h[4:] if h.startswith("www.") else h


def clean_domains(value):
    """'A.com, www.b.com;c.com' -> ['a.com', 'b.com', 'c.com'] (no duplicates)."""
    items = value if isinstance(value, (list, tuple)) else re.split(r"[\s,;]+", str(value or ""))
    out = []
    for d in items:
        d = str(d).strip().lower()
        d = re.sub(r"^[a-z][a-z0-9+.-]*://", "", d).split("/")[0].lstrip(".")
        if d.startswith("www."):
            d = d[4:]
        if d and re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", d) and d not in out:
            out.append(d)
    return out


def domain_matches(host, domain):
    return bool(host) and bool(domain) and (host == domain or host.endswith("." + domain))


# ------------------------------------------------------------------ reading an adapter
def adapter_info(code):
    """What the adapter file says about itself, read WITHOUT running it:
    {"site_id", "title", "domains", "has_extract", "has_matches", "imports", "error"}."""
    info = {"site_id": None, "title": None, "domains": [], "has_extract": False, "has_matches": False,
            "imports": [], "error": None}
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        info["error"] = "syntax error, line %s: %s" % (e.lineno, e.msg)
        return info
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("SITE_ID", "TITLE", "DOMAINS"):
                try:
                    value = ast.literal_eval(node.value)
                except Exception:
                    continue
                if name == "SITE_ID" and isinstance(value, str):
                    info["site_id"] = value
                elif name == "TITLE" and isinstance(value, str):
                    info["title"] = value
                elif name == "DOMAINS" and isinstance(value, (list, tuple)):
                    info["domains"] = clean_domains(value)
        elif isinstance(node, ast.FunctionDef):
            if node.name == "extract":
                info["has_extract"] = True
            elif node.name == "matches":
                info["has_matches"] = True
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods += [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.append(node.module.split(".")[0])
    info["imports"] = sorted(set(mods))
    return info


def unsafe_imports(info):
    """Imports that are not inside the app (the phone cannot run the adapter then). The helper that the
    `__main__` block of every adapter imports (site_runner) is fine: that block never runs on the phone."""
    ok = _stdlib() | _PHONE_OK | {"site_runner"}
    return [m for m in info.get("imports", []) if m not in ok]


def problems(info):
    """Blocking problems of an adapter (an empty list = it can be added)."""
    out = []
    if info.get("error"):
        out.append(info["error"])
        return out
    if not info.get("has_extract"):
        out.append("There is no extract(url, proxy) function.")
    sid = info.get("site_id")
    if not sid:
        out.append('SITE_ID is missing (for example SITE_ID = "mysite").')
    elif not ID_RE.match(sid):
        out.append("SITE_ID must be lowercase letters, digits and _ (2-31 characters, starting with a letter).")
    if not info.get("domains") and not info.get("has_matches"):
        out.append('DOMAINS is missing (for example DOMAINS = ["mysite.com"]).')
    return out


# ------------------------------------------------------------------ running one
def load_module(code, name="linklab_site"):
    mod = types.ModuleType(name)
    mod.__file__ = "<%s>" % name
    exec(compile(code, name + ".py", "exec"), mod.__dict__)
    if not callable(getattr(mod, "extract", None)):
        raise RuntimeError("the adapter has no extract() function")
    return mod


def _height(q):
    for key in ("height", "quality", "resolution"):
        m = re.search(r"(\d{3,4})", str(q.get(key) if isinstance(q, dict) else ""))
        if m:
            return int(m.group(1))
    return 0


def normalize(res, url, site_id=""):
    """The adapter's answer as the rows the Link Lab phone screen shows:
    {"url", "title", "extractor", "error", "rows": [{"h", "ext", "hls", "size", "url"}], "m3u8"}."""
    out = {"url": url, "title": url, "extractor": ("adapter:" + site_id) if site_id else "adapter",
           "error": None, "rows": [], "m3u8": None, "note": ""}
    if not isinstance(res, dict):
        out["error"] = "the adapter returned no dict"
        return out
    out["title"] = res.get("title") or url
    if res.get("error"):
        out["error"] = str(res["error"])[:200]
        return out
    out["m3u8"] = res.get("m3u8")
    rows = []
    for q in res.get("qualities") or []:
        if not isinstance(q, dict):
            continue
        link = str(q.get("link") or q.get("url") or "")
        if not link.startswith("http"):
            continue
        hls = ".m3u8" in link.lower() or str(q.get("ext") or "").lower() == "m3u8"
        rows.append({"h": _height(q), "ext": "mp4" if hls else (str(q.get("ext") or "mp4")), "hls": hls,
                     "size": "", "url": link.split("#")[0]})
    rows.sort(key=lambda r: r["h"], reverse=True)
    out["rows"] = rows
    if not rows and not out["m3u8"]:
        out["error"] = "the adapter found no quality"
    return out


def run_code(code, url, site_id=""):
    """Runs an adapter given as text on THIS phone (proxy = None). Never raises: an error is in the result."""
    try:
        info = adapter_info(code)
        sid = site_id or info.get("site_id") or ""
        mod = load_module(code, "linklab_site_" + (sid or "x"))
        return normalize(mod.extract(url, None), url, sid)
    except Exception as e:
        return {"url": url, "title": url, "extractor": "adapter", "rows": [], "m3u8": None, "note": "",
                "error": ("%s: %s" % (e.__class__.__name__, e)).strip()[:200]}


# ------------------------------------------------------------------ GitHub (blocking)
def read_text(host, path):
    try:
        return host.gh.read_file(path, ref=LAB)
    except Exception:
        return None


def parse_index(text):
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return []
    sites = data.get("sites") if isinstance(data, dict) else data
    return [s for s in (sites or []) if isinstance(s, dict) and s.get("id") and s.get("file")]


def load_index(host):
    return parse_index(read_text(host, INDEX))


def find_entry(entries, url):
    h = host_of(url)
    for e in entries:
        if e.get("enabled") is False:
            continue
        if any(domain_matches(h, d) for d in clean_domains(e.get("domains"))):
            return e
    return None


def try_registered(host, url, entries=None):
    """The result for a link of a site registered in Link Lab, or None when the site is not registered."""
    entries = load_index(host) if entries is None else entries
    entry = find_entry(entries, url)
    if entry is None:
        return None
    code = read_text(host, entry["file"])
    if code is None:
        return {"url": url, "title": url, "extractor": "adapter:" + str(entry["id"]), "rows": [], "m3u8": None,
                "note": "", "error": "the adapter file %s is not on the lab branch" % entry["file"]}
    return run_code(code, url, str(entry["id"]))


def selftest():
    code = ('SITE_ID = "demo"\nTITLE = "Demo"\nDOMAINS = ["demo.test", "www.Other.test"]\nimport requests, json\n'
            'def extract(url, proxy=None):\n    if "bad" in url:\n        return {"error": "nope"}\n'
            '    return {"title": "T", "qualities": [{"quality": "480p", "link": "https://c/480.m3u8"},\n'
            '                                      {"quality": "1080p", "link": "https://c/1080.mp4"}]}\n'
            'if __name__ == "__main__":\n    import site_runner\n')
    info = adapter_info(code)
    assert info["site_id"] == "demo" and info["domains"] == ["demo.test", "other.test"] and info["has_extract"], info
    assert problems(info) == [] and unsafe_imports(info) == [], (problems(info), unsafe_imports(info))
    bad = adapter_info("import curl_cffi\nSITE_ID='x'\n")
    assert unsafe_imports(bad) == ["curl_cffi"] and problems(bad), bad
    assert adapter_info("def (:")["error"]
    r = run_code(code, "https://demo.test/v/1")
    assert [x["h"] for x in r["rows"]] == [1080, 480] and r["rows"][1]["hls"] and not r["error"], r
    assert run_code(code, "https://demo.test/bad")["error"] == "nope"
    assert run_code("def extract(:", "u")["error"]
    idx = parse_index('{"sites": [{"id": "demo", "file": "lab_scripts/sites/demo.py", "domains": ["demo.test"]}, 5]}')
    assert find_entry(idx, "https://www.sub.demo.test/x")["id"] == "demo" and find_entry(idx, "https://x.com/") is None

    class _Gh:
        def read_file(self, path, ref=None):
            return code if path.endswith("demo.py") else json.dumps({"sites": idx})

    class _Host:
        gh = _Gh()
    got = try_registered(_Host(), "https://demo.test/v/9")
    assert got["rows"] and got["extractor"] == "adapter:demo", got
    assert try_registered(_Host(), "https://other.org/") is None
    assert clean_domains("A.com, https://www.b.com/x;bad") == ["a.com", "b.com"]
    return "ok"


if __name__ == "__main__":
    print(selftest())
