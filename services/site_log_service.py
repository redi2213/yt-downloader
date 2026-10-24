"""Site log: which sites worked and which did not.

Any-Site-Upload.yml adds one line per link to ``site-log.jsonl`` on the config branch
(status: success = file over 10 MB, small = under 10 MB, fail = error, unknown = size not
measurable). This service reads that file for two things: the "this site failed before"
question asked before an Any site run starts, and the Site log screen in Settings.

A site counts as "failed before" only when it has at least one fail/small and never a success;
a site that works sometimes is not warned about.
"""
import json
import urllib.parse

from api.github import client
from api.github.auth import auth_headers
from core.async_utils import run_in_background
from core.config import API_BASE
from core.exceptions import AuthenticationError

CONFIG_BRANCH = "config"
FILE_NAME = "site-log.jsonl"


def host_of(url):
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def urls_from(text):
    """The links of the form text (same rules as the workflow: '#' lines skipped, no duplicates)."""
    lines = [l for l in (text or "").splitlines() if not l.lstrip().startswith("#")]
    urls = [u for u in " ".join(lines).split() if u.lower().startswith(("http://", "https://"))]
    return list(dict.fromkeys(urls))


def parse(text):
    records = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def stats(records):
    """{domain: {"n": {success, small, fail, unknown}, "last": date, "reason": text}}"""
    rows = {}
    for r in records:
        domain = r.get("domain")
        if not domain:
            continue
        row = rows.setdefault(domain, {"domain": domain,
                                       "n": {"success": 0, "small": 0, "fail": 0, "unknown": 0},
                                       "last": "", "reason": ""})
        status = r.get("status") or "unknown"
        row["n"][status if status in row["n"] else "unknown"] += 1
        row["last"] = (r.get("ts") or "")[:10]
        if status in ("fail", "small"):
            row["reason"] = (r.get("reason") or "")[:120]
    return rows


def warnings_for(urls_text, records):
    """[{domain, bad, reason}] for the links whose site failed before and never worked."""
    rows = stats(records)
    out = {}
    for url in urls_from(urls_text):
        domain = host_of(url)
        row = rows.get(domain)
        if not row or domain in out:
            continue
        bad = row["n"]["fail"] + row["n"]["small"]
        if bad and not row["n"]["success"]:
            out[domain] = {"domain": domain, "bad": bad, "reason": row["reason"]}
    return list(out.values())


def _read_records():
    headers = dict(auth_headers())
    headers["Accept"] = "application/vnd.github.raw+json"
    r = client.get_allow_missing(f"{API_BASE}/contents/{FILE_NAME}",
                                 params={"ref": CONFIG_BRANCH}, headers=headers)
    if r.status_code == 404:
        return []                      # nothing logged yet
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    return parse(r.text)


def start_check_history(urls_text, on_done):
    """on_done({'ok': True, 'warnings': [...]}) from a background thread. When the log
    cannot be read the answer is 'no warnings': the log must never block a download."""
    def work():
        try:
            on_done({"ok": True, "warnings": warnings_for(urls_text, _read_records())})
        except Exception:
            on_done({"ok": False, "warnings": []})
    run_in_background(work)


def start_load_summary(on_done):
    """on_done({'ok': True, 'rows': [...]}) - one row per site, the busiest first."""
    def work():
        try:
            rows = list(stats(_read_records()).values())
            rows.sort(key=lambda r: (-sum(r["n"].values()), r["domain"]))
            on_done({"ok": True, "rows": rows})
        except AuthenticationError:
            on_done({"ok": False, "error": "GitHub token invalid or expired. Update it and retry."})
        except Exception as e:
            on_done({"ok": False, "error": f"Could not read the site log: {str(e)[:80]}"})
    run_in_background(work)
