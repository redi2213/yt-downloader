"""Builds the browser pack: copies the browser's Python files and writes manifest.json (version + SHA-256).

Run by .github/workflows/publish-browser-pack.yml (main -> config branch, folder plugins/browser/).
The list of files, PACK_API and NATIVE_API are read from core/browser_pack.py without importing it.

  python3 scripts/publish_browser_pack.py --repo . --out cfg/plugins/browser [--force]

Prints "changed=1" / "changed=0" lines (for $GITHUB_OUTPUT). Standard library only.
"""
import argparse
import ast
import hashlib
import json
import os
import py_compile
import shutil
import sys
import tempfile
import time


def read_constants(pack_py):
    with open(pack_py, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("PACK_API", "NATIVE_API", "PACK_FILES"):
                found[node.targets[0].id] = ast.literal_eval(node.value)
    for key in ("PACK_API", "NATIVE_API", "PACK_FILES"):
        if key not in found:
            sys.exit(f"core/browser_pack.py has no {key}")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    consts = read_constants(os.path.join(args.repo, "core", "browser_pack.py"))
    files = {}
    for path in consts["PACK_FILES"]:
        full = os.path.join(args.repo, path)
        if not os.path.isfile(full):
            sys.exit(f"Missing file: {path}")
        with open(full, "rb") as f:
            data = f.read()
        if b"\r" in data:
            data = data.replace(b"\r\n", b"\n")
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "x.py")
            with open(src, "wb") as f:
                f.write(data)
            try:
                py_compile.compile(src, doraise=True)
            except py_compile.PyCompileError as e:
                sys.exit(f"{path}: {e.msg}")
        files[path] = data

    hashes = {p: {"sha256": hashlib.sha256(d).hexdigest(), "size": len(d)} for p, d in files.items()}
    manifest_path = os.path.join(args.out, "manifest.json")
    old = {}
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                old = json.load(f)
        except ValueError:
            old = {}
    same = (old.get("files") == hashes and old.get("api") == consts["PACK_API"]
            and old.get("native_api") == consts["NATIVE_API"])
    if same and not args.force:
        print("No change in the browser files: nothing to publish.")
        print("changed=0")
        return

    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    version = time.strftime("%Y%m%d.%H%M%S", time.gmtime()) + (f"-{sha}" if sha else "")
    version_txt = os.path.join(args.repo, "version.txt")
    app_version = open(version_txt, encoding="utf-8").read().strip() if os.path.isfile(version_txt) else ""

    if os.path.isdir(args.out):
        shutil.rmtree(args.out)
    os.makedirs(args.out)
    for path, data in files.items():
        with open(os.path.join(args.out, path.replace("/", "__")), "wb") as f:
            f.write(data)
    manifest = {"schema": 1, "version": version, "api": consts["PACK_API"], "native_api": consts["NATIVE_API"],
                "app_version": app_version, "commit": os.environ.get("GITHUB_SHA", ""),
                "built": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "files": hashes}
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"Browser pack {version}: {len(files)} files, native level {consts['NATIVE_API']}.")
    print("changed=1")


if __name__ == "__main__":
    main()
