"""Shared Aparat logic.

Used by both the Termux CLI (aparat.py) and the GitHub Actions workflow
(aparat_workflow.py). Nothing in here reads input(), touches local data
files or depends on folder layout, so it can be imported anywhere.
"""
import re
import time
from datetime import datetime, timedelta

import requests

API_BASE_URL = "https://www.aparat.com/api/fa/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.aparat.com/",
}
headers = HEADERS  # kept for older code that used the lowercase name

RETRY_COUNT = 3
RETRY_DELAY = 2  # seconds


# ---------- small helpers ----------

def clean_name(s, max_len=80):
    s = re.sub(r'[\\/:*?"<>|\n\r\t]', " ", s)
    s = re.sub(r"[^\w\s\-().\[\]]", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:max_len] or "video"


def request_json(url, retries=RETRY_COUNT):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(RETRY_DELAY)
    print(f"Request failed after {retries} attempts: {url}")
    print(f"  error: {last_err}")
    return None


def profile_height(profile):
    """'720p' -> 720. Unknown formats -> 0."""
    digits = re.sub(r"\D", "", str(profile))
    return int(digits) if digits else 0


def make_filename(out_name, n, title):
    """Final file name, same pattern the CLI rename step uses."""
    return f"{clean_name(out_name, max_len=120)}_{n:02d} - {clean_name(title)}.mp4"


# ---------- fetching video info ----------

def get_video(uid, playlist=None):
    q = f"?playlist={playlist}&pr=1&mf=1" if playlist else ""
    j = request_json(f"{API_BASE_URL}/video/video/show/videohash/{uid}{q}")
    if not j:
        return None

    try:
        a = j["data"]["attributes"]
    except (KeyError, TypeError):
        print(f"Unexpected response for uid {uid}")
        return None

    links = a.get("file_link_all") or []

    return {
        "title": a.get("title", "video"),
        "uid": uid,
        "playlist": playlist,
        "links": [
            {"profile": x["profile"], "url": x["urls"][0]}
            for x in links
        ],
    }


def get_playlist(pid):
    """Returns (video_ids, title) or (None, None) if the playlist can't load."""
    j = request_json(f"{API_BASE_URL}/video/playlist/one/playlist_id/{pid}")
    if not j:
        return None, None

    ids = [
        x["attributes"]["uid"]
        for x in j.get("included", [])
        if x["type"] == "Video"
    ]

    title = None
    for row in j.get("data", []):
        if not isinstance(row, dict):
            continue
        t = row.get("attributes", {}).get("title", {})
        if isinstance(t, dict) and t.get("text"):
            title = t["text"]
            break

    return ids, title


def fetch_channel_page(username, page, perpage, next_url=None):
    url = next_url or (
        f"{API_BASE_URL}/user/video/last_videos_more/username/{username}"
        f"/page/{page}/perpage/{perpage}"
    )
    j = request_json(url)
    if not j:
        return [], None

    included = {
        x["id"]: x["attributes"]
        for x in j.get("included", [])
        if x["type"] == "Video"
    }

    ordered = []
    rows = j.get("data", [])
    if rows:
        rel = rows[0].get("relationships", {}).get("video", {}).get("data", [])
        for r in rel:
            vid_id = r.get("id")
            if vid_id in included:
                ordered.append(included[vid_id])

    if not ordered:
        ordered = list(included.values())

    next_link = None
    if rows:
        next_link = rows[0].get("attributes", {}).get("link", {}).get("next")

    return ordered, next_link


def get_channel_uids_by_count(username, count):
    uids = []
    page = 1
    perpage = 10
    next_url = None

    while len(uids) < count:
        items, next_url = fetch_channel_page(username, page, perpage, next_url)
        if not items:
            break

        new_count = 0
        for a in items:
            uid = a["uid"]
            if uid not in uids:
                uids.append(uid)
                new_count += 1

        if new_count == 0 or not next_url:
            break
        page += 1

    return uids[:count]


def get_channel_uids_by_days(username, days):
    cutoff = datetime.now() - timedelta(days=days)
    uids = []
    page = 1
    perpage = 10
    next_url = None
    max_pages = 30

    while page <= max_pages:
        items, next_url = fetch_channel_page(username, page, perpage, next_url)
        if not items:
            break

        stop = False
        for a in items:
            sdate = a.get("sdate_rss")
            if not sdate:
                continue
            try:
                dt = datetime.strptime(sdate, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            if dt < cutoff:
                stop = True
                break

            uid = a["uid"]
            if uid not in uids:
                uids.append(uid)

        if stop or not next_url:
            break
        page += 1

    return uids


# ---------- links and quality ----------

def parse_link(link):
    """Returns (kind, value): ('video', uid) / ('playlist', id) / ('channel', username)."""
    link = link.strip().split("#")[0].split("?")[0].rstrip("/")
    if "/playlist/" in link:
        return "playlist", link.split("/")[-1]
    if "/v/" in link:
        return "video", link.split("/")[-1]
    return "channel", link.split("/")[-1]


def pick_link(links, quality):
    """Choose one entry from a video's links.

    quality: 'best' (or empty) for the highest available, or a profile like
    '720p'. If that exact profile is missing: nearest lower, else nearest
    higher. Returns (link_or_None, exact_match_bool).
    """
    if not links:
        return None, False

    ordered = sorted(links, key=lambda x: profile_height(x["profile"]))

    if not quality or str(quality).lower() in ("best", "auto"):
        return ordered[-1], True

    target = profile_height(quality)
    for x in ordered:
        if profile_height(x["profile"]) == target:
            return x, True

    lower = [x for x in ordered if profile_height(x["profile"]) < target]
    higher = [x for x in ordered if profile_height(x["profile"]) > target]
    if lower:
        return lower[-1], False
    if higher:
        return higher[0], False
    return None, False


def parse_limit(spec):
    """'count:10' -> ('count', 10), 'days:7' -> ('days', 7). Falls back to count:5."""
    try:
        mode, value = str(spec).split(":", 1)
        value = int(value)
        if mode in ("count", "days") and value > 0:
            return mode, value
    except (ValueError, AttributeError):
        pass
    return "count", 5


# ---------- non-interactive link resolver (used by the workflow) ----------

def resolve_simple(link, limit="count:5"):
    """Link -> (video_ids, output_basename, info), or (None, None, None).

    `limit` only matters for channel links, e.g. 'count:10' or 'days:7'.
    """
    kind, value = parse_link(link)

    if kind == "playlist":
        ids, title = get_playlist(value)
        if not ids:
            print("Could not load playlist or it is empty")
            return None, None, None
        name_part = clean_name(title, 30) if title else value
        return ids, f"playlist_{value}_{name_part}", {
            "kind": "playlist", "playlist_id": value}

    if kind == "video":
        return [value], f"video_{value}", {"kind": "video"}

    mode, n = parse_limit(limit)
    if mode == "days":
        ids = get_channel_uids_by_days(value, n)
        out_name = f"{value}_{n}days"
    else:
        ids = get_channel_uids_by_count(value, n)
        out_name = f"{value}_last{n}"

    if not ids:
        print("No videos found for this channel")
        return None, None, None
    return ids, out_name, {"kind": "channel", "username": value}
