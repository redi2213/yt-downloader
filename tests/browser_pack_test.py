"""Browser pack (plain Python, no Kivy needed):  python3 tests/browser_pack_test.py

Publishes a pack from the repo's own files into a temp folder, then checks the loader: a good pack is used,
a damaged / wrong / crashing one is refused and the built-in code stays or comes back.
"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core import browser_pack as bp  # noqa: E402

# the screens need Kivy: this test runs the pure-Python part of the pack
CORE_ONLY = tuple(p for p in bp.PACK_FILES if p.startswith("core/"))
FULL = bp.PACK_FILES
bp.PACK_FILES = CORE_ONLY

tmp = tempfile.mkdtemp()
try:
    bp.BASE_DIR = os.path.join(tmp, "phone")
    pub = os.path.join(tmp, "pub")

    def publish(repo=ROOT, force=False):
        # the publisher reads PACK_FILES from core/browser_pack.py: run it on a copy limited to CORE_ONLY
        work = os.path.join(tmp, "repo")
        shutil.rmtree(work, ignore_errors=True)
        for p in CORE_ONLY + ("core/browser_pack.py",):
            os.makedirs(os.path.dirname(os.path.join(work, p)), exist_ok=True)
            shutil.copy(os.path.join(repo, p), os.path.join(work, p))
        pack_py = os.path.join(work, "core", "browser_pack.py")
        text = open(pack_py, encoding="utf-8").read()
        start = text.index("PACK_FILES = (")
        end = text.index(")\n", start) + 2
        text = text[:start] + f"PACK_FILES = {CORE_ONLY!r}\n" + text[end:]
        open(pack_py, "w", encoding="utf-8").write(text)
        cmd = [sys.executable, os.path.join(ROOT, "scripts", "publish_browser_pack.py"), "--repo", work, "--out", pub]
        return subprocess.run(cmd + (["--force"] if force else []), capture_output=True, text=True, check=True).stdout

    def fake_fetch(rel):
        with open(os.path.join(pub, rel), encoding="utf-8") as f:
            return f.read()

    bp._fetch = fake_fetch
    builtin_media = sys.modules.get("core.browser_media")
    if builtin_media is None:
        from core import browser_media as builtin_media  # noqa: F401

    # -- publish, nothing new the second time
    assert "changed=1" in publish()
    assert "changed=0" in publish()
    manifest = json.load(open(os.path.join(pub, "manifest.json")))
    assert bp.check_manifest(manifest) == "" and set(manifest["files"]) == set(CORE_ONLY)
    texts = {p: open(os.path.join(pub, bp.flat(p)), encoding="utf-8").read() for p in CORE_ONLY}
    assert bp.validate(manifest, texts) == ""

    # -- refused packs
    bad = copy.deepcopy(manifest)
    bad["api"] = 99
    assert "another app" in bp.check_manifest(bad)
    bad = copy.deepcopy(manifest)
    bad["native_api"] = bp.NATIVE_API + 1
    assert "newer app" in bp.check_manifest(bad)
    bad = copy.deepcopy(manifest)
    bad["files"]["core/evil.py"] = bad["files"].pop(CORE_ONLY[0])
    assert bp.check_manifest(bad)
    bad = copy.deepcopy(manifest)
    bad["version"] = "../x"
    assert bp.check_manifest(bad)
    broken = dict(texts, **{CORE_ONLY[0]: texts[CORE_ONLY[0]] + "\n# edited\n"})
    assert "checksum" in bp.validate(manifest, broken)
    assert "syntax" in bp._scan("x.py", "def (:")
    assert "eval" in bp._scan("x.py", "x = eval('1')")
    assert "subprocess" in bp._scan("x.py", "import subprocess")
    assert "ctypes" in bp._scan("x.py", "from ctypes import cdll")
    assert bp._scan("x.py", "import os\nx = 1") == ""

    # -- download, activate
    res = bp.check_update()
    assert res["result"] == "new", res
    ver = res["version"]
    assert bp.check_update()["result"] == "same"
    st = bp.status()
    assert st["current"] == ver and st["waiting"] and st["source"] == "builtin"
    st = bp.activate()
    assert st["source"] == "pack" and st["version"] == ver, st
    media = sys.modules["core.browser_media"]
    assert media is not builtin_media and media.__file__.startswith("<browserpack")
    from core import browser_media as seen
    assert seen is media                       # "from core import browser_media" sees the pack
    assert bp.load_state()["pending"] == ver   # not confirmed yet
    bp.confirm()
    assert bp.load_state()["pending"] == ""
    assert bp.activate()["version"] == ver     # once per start

    # -- a crash before confirm: that version is blocked, the built-in code comes back
    st0 = bp.load_state()
    st0["pending"] = ver
    bp.save_state(st0)
    st = bp.activate(force=True)
    assert st["source"] == "builtin" and ver in st["blocked"], st
    assert sys.modules["core.browser_media"] is builtin_media
    assert bp.check_update()["result"] == "blocked"
    assert bp.check_update(force=True)["result"] == "new"    # Check for update unblocks on purpose
    assert bp.activate(force=True)["version"] == ver
    bp.confirm()

    # -- a new version that fails (missing name): refused when loaded, the older good one keeps running
    src = os.path.join(tmp, "repo", "core", "browser_media.py")
    text = open(src, encoding="utf-8").read().replace("def fmt_size(", "def fmt_size_renamed(")
    open(src, "w", encoding="utf-8").write(text)
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "publish_browser_pack.py"),
                          "--repo", os.path.join(tmp, "repo"), "--out", pub], capture_output=True, text=True,
                         check=True).stdout
    assert "changed=1" in out
    res = bp.check_update()
    assert res["result"] == "new" and res["version"] != ver
    ver2 = res["version"]
    assert bp.load_state()["previous"][0] == ver
    st = bp.activate(force=True)
    assert st["version"] == ver and ver2 in st["blocked"] and "fmt_size" in st["last_error"], st
    assert sys.modules["core.browser_media"].__file__.startswith("<browserpack")
    bp.confirm()

    # -- fall_back, go back, built-in
    assert bp.fall_back("test") is True
    st = bp.status()
    assert st["source"] == "builtin" and ver in st["blocked"]
    assert bp.fall_back("again") is False
    # the broken version is still the published one: forced check + activate refuse it again
    assert bp.check_update(force=True)["result"] == "new"
    assert bp.activate(force=True)["source"] == "builtin"
    # a fixed version is published
    open(src, "w", encoding="utf-8").write(text.replace("def fmt_size_renamed(", "def fmt_size("))
    out = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "publish_browser_pack.py"),
                          "--repo", os.path.join(tmp, "repo"), "--out", pub], capture_output=True, text=True,
                         check=True).stdout
    assert "changed=1" in out
    assert bp.check_update()["result"] == "new"
    assert bp.activate(force=True)["source"] == "pack"
    bp.use_builtin()
    assert bp.activate(force=True)["source"] == "builtin"
    assert bp.go_back() is False

    # -- automatic check only when it is on and not too often
    bp.set_auto(False)
    assert bp.start_background_check() is False
    bp.set_auto(True)
    st1 = bp.load_state()
    st1["last_check"] = 9e12
    bp.save_state(st1)
    assert bp.start_background_check() is False

    # -- the real list of files
    bp.PACK_FILES = FULL
    assert len(set(FULL)) == len(FULL) and all(p in bp._REQUIRED for p in FULL)
    for p in FULL:
        assert os.path.isfile(os.path.join(ROOT, p)), p
    print("browser_pack_test: ok")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
