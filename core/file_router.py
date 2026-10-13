"""Working out where loose files belong in the repo. Pure Python (no Kivy,
no network) so it can be tested anywhere.

Input: files with only a name (``upload-file (1).yml``) or a path inside a
zip (``update/services/x.py``). Output: a PLAN - one dict per file:

    name, base, content, mode      the file
    status                         EXACT / SAME / SIMILAR / AMBIGUOUS / NEW
    candidates                     [(branch, path)] existing repo files it may replace
    choice                         (branch, path) it will be written to (None = not decided)
    skip, selected                 the user's decisions (see ``included``)
    stats                          {(branch, path): (added, removed) | None}
    folder_suggestions             [folder] where a NEW file probably belongs

Matching order for a file:
  1. config.json                        -> the ``config`` branch
  2. same path / same name in the repo  -> EXACT (one place) or AMBIGUOUS
     (e.g. __init__.py exists in several folders)
  3. same name once case, "(1)", "_v2", "-new", a trailing number... are
     ignored, or a very close spelling -> SIMILAR (the user is asked)
  4. nothing like it                    -> NEW (folders are suggested)
"""
import difflib
import posixpath
import re

from core.zip_tools import git_blob_sha

MAIN_BRANCH = "main"
CONFIG_BRANCH = "config"
CONFIG_FILE = "config.json"

EXACT, SAME, SIMILAR, AMBIGUOUS, NEW = "exact", "same", "similar", "ambiguous", "new"
NEEDS_CHOICE = (SIMILAR, AMBIGUOUS, NEW)

SIMILAR_RATIO = 0.86
MAX_SIMILAR = 3
MAX_SUGGESTIONS = 3

# "upload-file (1)", "x_v2", "x-new", "x copy", "x2" ... -> the same stem
_SUFFIX_RE = re.compile(r"(?:[\s._-]*(?:\(\d+\)|copy|new|old|final|fixed|latest|v\d+|\d+))+$", re.I)
_SEPARATORS_RE = re.compile(r"[\s._-]+")


def join_path(folder: str, base: str) -> str:
    return f"{folder}/{base}" if folder else base


def name_key(name: str) -> str:
    """Name with case, separators and 'copy'-style endings ignored."""
    stem, ext = posixpath.splitext(name)
    stripped = _SUFFIX_RE.sub("", stem)
    if len(stripped.strip(" ._-")) < 3:
        stripped = stem
    stripped = _SEPARATORS_RE.sub("_", stripped.lower()).strip("_")
    return stripped + ext.lower()


def diff_stats(old: bytes, new: bytes):
    """(added_lines, removed_lines), or None for binary / very large files."""
    try:
        a = old.decode("utf-8-sig").splitlines()
        b = new.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError:
        return None
    if len(a) + len(b) > 20000:
        return None
    added = removed = 0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed


class RepoIndex:
    """Lookup tables over {branch: {path: blob_sha}}."""

    def __init__(self, files_by_branch: dict):
        self.files = files_by_branch
        self.by_base, self.by_base_lower, self.by_key = {}, {}, {}
        for branch in sorted(files_by_branch, key=lambda b: (b != MAIN_BRANCH, b)):
            for path in sorted(files_by_branch[branch]):
                base = posixpath.basename(path)
                ref = (branch, path)
                self.by_base.setdefault(base, []).append(ref)
                self.by_base_lower.setdefault(base.lower(), []).append(ref)
                self.by_key.setdefault(name_key(base), []).append(ref)
        main = files_by_branch.get(MAIN_BRANCH, {})
        # folders that directly hold files ("" = project root)
        self.folders = sorted({posixpath.dirname(p) for p in main})

    def sha(self, ref):
        return self.files.get(ref[0], {}).get(ref[1])


def _exact_candidates(index: RepoIndex, name: str, base: str) -> list:
    refs = index.by_base.get(base) or index.by_base_lower.get(base.lower()) or []
    if "/" in name:  # the zip's own folders narrow the choice
        narrowed = [
            (b, p) for b, p in refs
            if name == p or name.endswith("/" + p) or p.endswith("/" + name)
        ]
        if narrowed:
            return narrowed
    return list(refs)


def _similar_candidates(index: RepoIndex, base: str) -> list:
    if base == "__init__.py":
        return []
    key = name_key(base)
    ext = posixpath.splitext(key)[1]
    keys = [key] if key in index.by_key else []
    pool = [k for k in index.by_key if posixpath.splitext(k)[1] == ext and k != key]
    keys += difflib.get_close_matches(key, pool, n=MAX_SIMILAR, cutoff=SIMILAR_RATIO)
    refs = []
    for k in keys:
        for ref in index.by_key[k]:
            if ref not in refs:
                refs.append(ref)
    return refs[:MAX_SIMILAR]


def suggest_folders(name: str, index: RepoIndex) -> list:
    """Folders ("" = project root) where a new file probably belongs, best
    first. Learned from the repo: folders holding files with the same
    extension and the same name pattern (``*_service.py`` -> services)."""
    base = posixpath.basename(name)
    stem, ext = posixpath.splitext(base)
    ext = ext.lower()
    tokens = [t for t in re.split(r"[\s._-]+", stem.lower()) if t]
    first, last = (tokens[0], tokens[-1]) if tokens else ("", "")

    scores = {}
    for path in index.files.get(MAIN_BRANCH, {}):
        pbase = posixpath.basename(path)
        pstem, pext = posixpath.splitext(pbase)
        if pext.lower() != ext or pbase == "__init__.py":
            continue
        folder = posixpath.dirname(path)
        ptokens = [t for t in re.split(r"[\s._-]+", pstem.lower()) if t]
        score = 1
        if len(tokens) > 1 and ptokens and ptokens[-1] == last:
            score += 3
        if ptokens and ptokens[0] == first:
            score += 2
        scores[folder] = scores.get(folder, 0) + score

    ranked = [f for f, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]
    out = []
    zip_dir = posixpath.dirname(name)
    if zip_dir:
        out.append(zip_dir)  # the folder the file already sat in
    if ext in (".yml", ".yaml") and ".github/workflows" not in ranked:
        ranked.insert(0, ".github/workflows")
    for f in ranked:
        if f not in out:
            out.append(f)
    return out[:MAX_SUGGESTIONS]


def _new_item(name, base, content, mode):
    return {
        "name": name, "base": base, "content": content, "mode": mode,
        "status": NEW, "candidates": [], "choice": None,
        "skip": False, "selected": True, "creates": False,
        "stats": {}, "folder_suggestions": [],
    }


def plan_one(name: str, content: bytes, mode: str, index: RepoIndex) -> dict:
    name = name.replace("\\", "/").strip("/")
    base = posixpath.basename(name)
    item = _new_item(name, base, content, mode)
    item["folder_suggestions"] = suggest_folders(name, index)

    if base.lower() == CONFIG_FILE and CONFIG_BRANCH in index.files:
        ref = (CONFIG_BRANCH, CONFIG_FILE)
        item["candidates"] = [ref]
        item["choice"] = ref
        item["creates"] = index.sha(ref) is None
        item["status"] = SAME if index.sha(ref) == git_blob_sha(content) else EXACT
        return item

    candidates = _exact_candidates(index, name, base)
    if len(candidates) == 1:
        ref = candidates[0]
        item["candidates"] = candidates
        item["choice"] = ref
        item["status"] = SAME if index.sha(ref) == git_blob_sha(content) else EXACT
    elif candidates:
        item["candidates"] = candidates
        item["status"] = AMBIGUOUS
    else:
        similar = _similar_candidates(index, base)
        if similar:
            item["candidates"] = similar
            item["status"] = SIMILAR
    return item


def plan(items, index: RepoIndex) -> list:
    """items: [(name, content, mode)] -> list of plan dicts."""
    return [plan_one(name, content, mode, index) for name, content, mode in items]


# -- reading the user's decisions ------------------------------------------
def included(item: dict) -> bool:
    """Will this file be written?"""
    return bool(
        item["choice"] is not None and not item["skip"]
        and item["selected"] and item["status"] != SAME
    )


def pending(items) -> int:
    """Files that still need a decision from the user."""
    return sum(
        1 for it in items
        if it["status"] in NEEDS_CHOICE and it["choice"] is None and not it["skip"]
    )


def conflicts(items):
    """A readable message when two files would be written to the same place."""
    seen = {}
    for it in items:
        if not included(it):
            continue
        ref = it["choice"]
        if ref in seen:
            return f'"{seen[ref]}" and "{it["name"]}" would both replace {ref[1]}.'
        seen[ref] = it["name"]
    return None


def collect(items) -> dict:
    """{branch: {path: (bytes, mode)}} of every file that will be written."""
    out = {}
    for it in items:
        if included(it):
            branch, path = it["choice"]
            out.setdefault(branch, {})[path] = (it["content"], it["mode"])
    return out
