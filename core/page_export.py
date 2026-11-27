"""Full page export: the files of one export (pure Python: no Kivy, no network).

Layout in the private repository: <site domain>/<date_time>/ with meta.json, requests.json, cookies.txt,
storage.json and page.html. The cookies are not encrypted: the privacy of the repository protects them.
"""
import json
import re
from datetime import datetime
from urllib.parse import urlsplit

MAX_TEXT = 200000       # a logged request / answer body longer than this is cut (and marked ``..._cut``)
FILES = ("meta.json", "requests.json", "cookies.txt", "storage.json", "page.html")


def host_folder(page):
    host = (urlsplit(str(page or "")).hostname or "").lower()
    host = re.sub(r"[^a-z0-9.-]", "-", host).strip(".-")
    return host or "unknown-site"


def stamp(now=None):
    return (now or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")


def folder(page, now=None):
    return f"{host_folder(page)}/{stamp(now)}"


def _trim(item):
    try:
        data = json.loads(json.dumps(item, default=str))
    except Exception:
        return {"value": str(item)[:500]}
    if isinstance(data, dict):
        for key in ("resp", "body"):
            value = data.get(key)
            if isinstance(value, str) and len(value) > MAX_TEXT:
                data[key] = value[:MAX_TEXT]
                data[key + "_cut"] = True
    return data


def _storage_text(text):
    text = str(text or "")
    if not text:
        return json.dumps({"error": "storage was not read"}, indent=2)
    try:
        json.loads(text)
        return text
    except Exception:
        return json.dumps({"error": "storage answer is not valid JSON", "raw": text[:2000]}, indent=2)


def _dump(data):
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def build_files(page, ua, cookies_txt, net_items, media_items, storage_text, html, now=None):
    """(folder, {file name: text}) of one export."""
    now = now or datetime.now()
    requests_ = [_trim(r) for r in (net_items or [])]
    media = [_trim(m) for m in (media_items or [])]
    where = folder(page, now)
    meta = {"url": str(page or ""), "user_agent": str(ua or ""), "time": now.isoformat(timespec="seconds"),
            "folder": where, "requests": len(requests_), "media_found": len(media)}
    files = {
        "meta.json": _dump(meta),
        "requests.json": _dump({"requests": requests_, "media_found": media}),
        "cookies.txt": str(cookies_txt or ""),
        "storage.json": _storage_text(storage_text),
        "page.html": str(html or "") or "<!-- the page HTML was not read -->\n",
    }
    return where, files
