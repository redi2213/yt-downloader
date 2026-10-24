"""\"Run again\": repeating an earlier run with the same inputs.

GitHub does not return the inputs of a ``workflow_dispatch`` run, so the app
packs them (zlib + base64url, one short line) into the run's NAME:

    <title> [<12 hex token>] ~<packed inputs>

The workflows take the packed text as the optional input ``rerun`` and add
`` ~<it>`` to their ``run-name``. Run lists hide that tail (see
api/github/workflows.py); Run again reads it back here.

Pure text helpers - no Kivy, no network.
"""
import base64
import json
import re
import zlib

# Inputs the app sets itself on every dispatch: never packed, never repeated.
SKIP_KEYS = frozenset({"job_id", "run_title", "storage", "arvan_bucket", "rerun"})
# Longer than this and the run name gets unwieldy: such a run is repeated
# through the manual-run page instead.
MAX_PACKED = 900

# "<title> [token] ~packed"
_NAME_RE = re.compile(
    r"^(?P<title>.*?)\s*\[(?P<token>[0-9a-f]{12})\](?:\s+~(?P<packed>[A-Za-z0-9_\-]+))?\s*$",
    re.DOTALL)
PACKED_TAIL_RE = r"(?:\s+~[A-Za-z0-9_\-]+)?"

# The input that carries the link, per workflow (to prefill the manual page)
URL_KEYS = {
    "download.yml": "video_url",
    "download-batch.yml": "urls",
    "list-formats.yml": "video_url",
    "list-playlist.yml": "playlist_url",
    "aparat-download.yml": "aparat_url",
    "telegram-download.yml": "telegram_url",
    "google-play-download.yml": "play_url",
    "filimo-direct-link.yml": "url",
    "Any-Site-Upload.yml": "urls",
    "upload-file.yml": "file_url",
    "Series-Links.yml": "url",
    "drive-to-release.yml": "drive_url",
}


def pack_inputs(inputs):
    """The inputs (without the app's own keys) as one short text, or ''."""
    data = {str(k): str(v) for k, v in (inputs or {}).items()
            if k not in SKIP_KEYS and v is not None and str(v) != ""}
    if not data:
        return ""
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")
    return packed if len(packed) <= MAX_PACKED else ""


def unpack_inputs(packed):
    """{name: value} from ``pack_inputs`` text, or None when it cannot be read."""
    if not packed:
        return None
    try:
        padded = packed + "=" * (-len(packed) % 4)
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(padded)).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items()}


def split_run_name(name):
    """(title, packed) of a run name; the title has no token / packed tail.
    A name without the app's token is returned whole with packed ''."""
    m = _NAME_RE.match(name or "")
    if not m:
        return (name or "").strip(), ""
    return m.group("title").strip(), m.group("packed") or ""


def inputs_from_name(name):
    return unpack_inputs(split_run_name(name)[1])


def prefill_lines(workflow_file, title, declared):
    """Text for the manual-run box when a run's own inputs are unknown:
    ``name=value`` for every input the workflow file declares (without the
    app's own ones), starting from its default; the link input is filled from
    the run's name when that name is a link. ``declared``: parse_declared_inputs()."""
    url_key = URL_KEYS.get(workflow_file)
    link = ""
    m = re.search(r"https?://\S+", title or "")
    if m:
        link = m.group(0)
    lines = []
    for item in declared:
        if item["name"] in SKIP_KEYS:
            continue
        value = item.get("default", "")
        if link and item["name"] == url_key:
            value = link
        lines.append(f"{item['name']}={value}")
    if not lines and url_key and link:
        lines.append(f"{url_key}={link}")
    return "\n".join(lines)


def parse_declared_inputs(yaml_text):
    """[{"name", "default", "required"}] of a workflow file's workflow_dispatch
    inputs, read with plain text rules (no YAML library on the phone)."""
    items, in_inputs, current = [], False, None
    lines = (yaml_text or "").splitlines()
    for i, line in enumerate(lines):
        if not in_inputs:
            if re.match(r"^\s{2}workflow_dispatch:\s*$", line) and i + 1 < len(lines) \
                    and re.match(r"^\s{4}inputs:\s*$", lines[i + 1]):
                in_inputs = True
            continue
        if line.strip() == "" or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 4 and not re.match(r"^\s{4}inputs:\s*$", line):
            break   # next section (permissions, jobs, ...)
        m = re.match(r"^\s{6}([A-Za-z0-9_\-]+):\s*$", line)
        if m:
            current = {"name": m.group(1), "default": "", "required": False}
            items.append(current)
            continue
        if current is not None:
            d = re.match(r"^\s{8}default:\s*(.*)$", line)
            if d:
                current["default"] = d.group(1).strip().strip("'\"")
            r = re.match(r"^\s{8}required:\s*(\w+)", line)
            if r:
                current["required"] = r.group(1).lower() == "true"
    return items
