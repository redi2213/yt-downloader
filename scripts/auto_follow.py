#!/usr/bin/env python3
"""The scheduler of "Auto follow" (runs inside Auto-Follow.yml).

Every tick (the workflow wakes up every 30 minutes) it reads ``follows.json`` -
the channels the user follows, written by the app - and ``follow-state.json``
(what was already fetched; written by this script), and for every channel that
is DUE (right weekday, inside its time window, not already served today) it
lists the channel, picks the new videos and starts the normal download
workflow (download.yml for YouTube, aparat-download.yml for Aparat) with
``release_tag=auto-<slug>``: every channel keeps ONE release that grows, so the
automatic downloads never mix with the Release History.

follows.json   {"tz": "Asia/Tehran", "follows": [ {..channel..} ]}
follow-state.json   {"<id>": {"seen": [...], "last_episode": 80, ...}}

A channel (all keys written by the app):
  id, slug, name, site (youtube|aparat), url, enabled
  mode           series (next episode number each time) | latest (new videos)
  days           weekdays to check, Monday=0 ... Sunday=6; [] = every day
  start, end     time window "HH:MM" (local, tz above); end < start = past midnight
  every_days     latest mode: check at most every N days
  quality        best | 1080p | 720p | 480p | 360p | audio
  min_minutes, max_minutes   YouTube only: video length limits (0 = no limit)
  include, exclude           lists of words the title must / must not contain
  start_from     {"type": now|episode|date|last_n, "value": ...}
  stop           {"episode": N|null, "date": "YYYY-MM-DD"|null, "count": N|null}
  max_per_run    most videos started per check
  zip            Aparat only: one zip per check instead of separate files
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
import zlib
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

LIST_LIMIT = 40          # newest videos looked at per check
SEEN_KEEP = 400          # ids remembered per channel
ASCII_DIGITS = str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9"
                             "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669", "01234567890123456789")
YOUTUBE_WORKFLOW = "download.yml"
APARAT_WORKFLOW = "aparat-download.yml"


def log(*a):
    print(*a, flush=True)


# -- time -----------------------------------------------------------------------------
def _hhmm(text, default):
    try:
        h, m = str(text).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return default


def in_window(follow, now):
    """True when ``now`` (aware, local) is on one of the follow's days and inside its window."""
    start, end = _hhmm(follow.get("start"), 0), _hhmm(follow.get("end"), 24 * 60 - 1)
    minute = now.hour * 60 + now.minute
    days = follow.get("days") or []
    if start <= end:
        return (not days or now.weekday() in days) and start <= minute <= end
    # the window runs past midnight: the part after midnight belongs to the day before
    if minute >= start:
        return not days or now.weekday() in days
    if minute <= end:
        return not days or (now - dt.timedelta(days=1)).weekday() in days
    return False


def is_due(follow, st, now, force=False):
    if not follow.get("enabled", True) or st.get("done"):
        return False, "off or finished"
    if force:
        return True, "forced"
    if not in_window(follow, now):
        return False, "outside the window"
    today = now.date().isoformat()
    if follow.get("mode") == "series":
        if st.get("last_hit_day") == today:
            return False, "already served today"
        return True, "in window"
    gap = max(1, int(follow.get("every_days") or 1))
    last = st.get("last_check_day")
    if last:
        try:
            if (now.date() - dt.date.fromisoformat(last)).days < gap:
                return False, f"checked less than {gap} day(s) ago"
        except ValueError:
            pass
    return True, "in window"


# -- episode number / filters ----------------------------------------------------------------------------
_EP_RES = [
    re.compile(r"S\d{1,2}\s*E(\d{1,4})", re.I),
    re.compile(r"\u0642\u0633\u0645\u062a\s*[-_:]?\s*(\d{1,4})"),           # قسمت 80
    re.compile(r"\b(?:episode|ep)\.?\s*[-_:]?\s*(\d{1,4})", re.I),
    re.compile(r"\bE(\d{1,4})\b"),
    re.compile(r"#\s*(\d{1,4})\b"),
]


def episode_of(title):
    text = str(title or "").translate(ASCII_DIGITS)
    for rx in _EP_RES:
        m = rx.search(text)
        if m:
            return int(m.group(1))
    return None


def passes(follow, entry):
    title = str(entry.get("title") or "").lower()
    dur = entry.get("duration")
    if follow.get("site") == "youtube" and dur:
        minutes = float(dur) / 60.0
        if follow.get("min_minutes") and minutes < float(follow["min_minutes"]):
            return False
        if follow.get("max_minutes") and minutes > float(follow["max_minutes"]):
            return False
    inc = [w.lower() for w in follow.get("include") or [] if str(w).strip()]
    if inc and not any(w in title for w in inc):
        return False
    exc = [w.lower() for w in follow.get("exclude") or [] if str(w).strip()]
    if any(w in title for w in exc):
        return False
    return True


# -- listing ------------------------------------------------------------------------------------------------------
def youtube_list_url(url):
    url = str(url).strip().split("#")[0]
    base, _, query = url.partition("?")
    if "playlist" in base and "list=" in query:
        return url
    base = base.rstrip("/")
    for tab in ("/videos", "/streams", "/shorts", "/featured", "/live"):
        if base.endswith(tab):
            base = base[: -len(tab)]
    return base + "/videos"


def list_youtube(url, cookies="cookies.txt"):
    """Newest first: [{id, title, duration (s), ts (unix, approximate)}]."""
    cmd = [sys.executable, "-m", "yt_dlp", "-J", "--flat-playlist", "--playlist-end", str(LIST_LIMIT),
           "--extractor-args", "youtubetab:approximate_date", "--no-warnings"]
    if cookies and os.path.exists(cookies) and os.path.getsize(cookies) > 5:
        cmd += ["--cookies", cookies]
    cmd.append(youtube_list_url(url))
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError("yt-dlp could not list the channel: " + (out.stderr.strip().splitlines() or ["?"])[-1][:200])
    info = json.loads(out.stdout)
    entries = []
    for e in info.get("entries") or []:
        if not e or not e.get("id"):
            continue
        entries.append({"id": e["id"], "title": e.get("title") or "", "duration": e.get("duration"),
                        "ts": e.get("timestamp")})
    return entries


def list_aparat(url):
    import aparat_core as core
    kind, value = core.parse_link(url)
    if kind != "channel":
        raise RuntimeError("Aparat follow needs a channel link.")
    entries = core.get_channel_entries_by_count(value, LIST_LIMIT)
    core.fill_titles(entries)
    return [{"id": e["uid"], "title": e.get("title") or "", "duration": None, "ts": None} for e in entries]


# -- what to fetch -----------------------------------------------------------------------------------------------------
def _ts_day(ts):
    try:
        return dt.datetime.fromtimestamp(float(ts), dt.timezone.utc).date()
    except Exception:
        return None


def apply_baseline(follow, st, entries):
    """The first time a channel is seen: decide what counts as already fetched."""
    if st.get("baseline"):
        return
    st["baseline"] = True
    st.setdefault("seen", [])
    st.setdefault("last_episode", 0)
    sf = follow.get("start_from") or {"type": "now"}
    kind, value = sf.get("type", "now"), sf.get("value")
    ok = [e for e in entries if passes(follow, e)]
    if kind == "episode":
        st["last_episode"] = max(0, int(value or 1) - 1)
    elif kind == "date":
        try:
            since = dt.date.fromisoformat(str(value))
        except ValueError:
            since = dt.date.today()
        st["seen"] += [e["id"] for e in entries if (_ts_day(e.get("ts")) or since) < since]
    elif kind == "last_n":
        keep = {e["id"] for e in ok[: max(1, int(value or 1))]}
        st["seen"] += [e["id"] for e in entries if e["id"] not in keep]
    else:   # now: everything online today is old news
        st["seen"] += [e["id"] for e in entries]
        eps = [episode_of(e["title"]) for e in ok]
        eps = [x for x in eps if x]
        if eps:
            st["last_episode"] = max(eps)


def select(follow, st, entries):
    """The videos to start now, oldest first (at most max_per_run)."""
    seen = set(st.get("seen") or [])
    stop = follow.get("stop") or {}
    cands = [e for e in entries if e["id"] not in seen and passes(follow, e)]
    limit = max(1, int(follow.get("max_per_run") or 1))
    if stop.get("count"):
        limit = min(limit, max(0, int(stop["count"]) - int(st.get("count") or 0)))
    if follow.get("mode") == "series":
        last = int(st.get("last_episode") or 0)
        by_ep = {}
        for e in cands:                       # list is newest first: keep the newest upload of an episode
            ep = episode_of(e["title"])
            if ep and ep > last and (not stop.get("episode") or ep <= int(stop["episode"])):
                by_ep.setdefault(ep, {**e, "episode": ep})
        picked = [by_ep[k] for k in sorted(by_ep)]
    else:
        picked = list(reversed(cands))
    return picked[:limit]


def finish_check(follow, st, picked, now, remaining):
    """Updates the state after a successful check; ``remaining`` = candidates left."""
    st["last_check"] = now.isoformat(timespec="minutes")
    st["last_check_day"] = now.date().isoformat()
    if picked:
        seen = list(st.get("seen") or []) + [e["id"] for e in picked]
        st["seen"] = seen[-SEEN_KEEP:]
        st["count"] = int(st.get("count") or 0) + len(picked)
        eps = [e.get("episode") for e in picked if e.get("episode")]
        if eps:
            st["last_episode"] = max(int(st.get("last_episode") or 0), max(eps))
        st["last_video"] = picked[-1]["title"][:120]
    if follow.get("mode") == "series" and picked and remaining == 0:
        st["last_hit_day"] = now.date().isoformat()
    stop = follow.get("stop") or {}
    if stop.get("episode") and int(st.get("last_episode") or 0) >= int(stop["episode"]):
        st["done"] = "reached the last episode"
    if stop.get("count") and int(st.get("count") or 0) >= int(stop["count"]):
        st["done"] = "reached the video count"
    if stop.get("date"):
        try:
            if now.date() > dt.date.fromisoformat(stop["date"]):
                st["done"] = "reached the end date"
        except ValueError:
            pass
    st["last_error"] = ""


# -- starting the download workflows -------------------------------------------------------------------------------------
def pack_inputs(inputs):
    """Same packing as the app's core/rerun.py, so "Run again" works on these runs."""
    skip = {"job_id", "run_title", "storage", "arvan_bucket", "rerun"}
    data = {str(k): str(v) for k, v in inputs.items() if k not in skip and str(v) != ""}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    packed = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")
    return packed if len(packed) <= 900 else ""


def tag_of(follow):
    return "auto-" + (follow.get("slug") or follow["id"])


def dispatch_inputs(follow, picked):
    """(workflow file, inputs) for the picked videos."""
    q = follow.get("quality") or "best"
    if follow.get("site") == "aparat":
        ids = ",".join(e["id"] for e in picked)
        inputs = {"aparat_url": follow["url"], "quality": "best" if q in ("audio", "best") else q,
                  "output": "upload_zip" if follow.get("zip") else "upload_separate",
                  "video_ids": ids, "release_tag": tag_of(follow)}
        return APARAT_WORKFLOW, inputs, f"Auto: {follow.get('name') or 'Aparat'} ({len(picked)})"
    e = picked[0]
    inputs = {"video_url": f"https://www.youtube.com/watch?v={e['id']}",
              "format_id": "bestvideo+bestaudio" if q in ("best", "audio") else q,
              "audio_only": "true" if q == "audio" else "false",
              "release_tag": tag_of(follow), "split_large": "true"}
    return YOUTUBE_WORKFLOW, inputs, "Auto: " + (e["title"] or e["id"])[:80]


def gh_dispatch(workflow, inputs, title):
    inputs = dict(inputs)
    packed = pack_inputs(inputs)
    inputs["job_id"] = uuid.uuid4().hex[:12]
    inputs["run_title"] = title
    if packed:
        inputs["rerun"] = packed
    cmd = ["gh", "workflow", "run", workflow, "--repo", os.environ.get("GITHUB_REPOSITORY", "")]
    ref = os.environ.get("GITHUB_REF_NAME")
    if ref:
        cmd += ["--ref", ref]
    for k, v in inputs.items():
        cmd += ["-f", f"{k}={v}"]
    done = subprocess.run(cmd, capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"could not start {workflow}: {(done.stderr or done.stdout).strip()[:200]}")


def start_downloads(follow, picked, dispatch=gh_dispatch):
    """Starts the workflows; returns the picked videos that really started."""
    started = []
    if follow.get("site") == "aparat":
        wf, inputs, title = dispatch_inputs(follow, picked)
        dispatch(wf, inputs, title)
        return list(picked)
    for e in picked:
        wf, inputs, title = dispatch_inputs(follow, [e])
        try:
            dispatch(wf, inputs, title)
        except RuntimeError as ex:
            log(f"::warning::{ex}")
            break            # keep the order: the next check continues from here
        started.append(e)
    return started


# -- one check of one channel -----------------------------------------------------------------------------------------------
def check_follow(follow, st, now, lister, dispatch=gh_dispatch):
    """Returns the list of videos that were started (state ``st`` is updated)."""
    entries = lister(follow)
    apply_baseline(follow, st, entries)
    picked = select(follow, st, entries)
    started = start_downloads(follow, picked, dispatch) if picked else []
    remaining = max(0, len(select({**follow, "max_per_run": 999}, {**st, "seen": list(st.get("seen") or []) +
                                                                  [e["id"] for e in started]}, entries)))
    if picked and not started:
        raise RuntimeError("the download workflow could not be started")
    finish_check(follow, st, started, now, remaining)
    return started


def default_lister(follow):
    if follow.get("site") == "aparat":
        return list_aparat(follow["url"])
    return list_youtube(follow["url"])


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(default)) else default
    except (OSError, ValueError):
        return default


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--follows", required=True)
    p.add_argument("--state", required=True)
    p.add_argument("--only", default="")
    p.add_argument("--force", default="false")
    p.add_argument("--summary", default="auto-summary.txt")
    p.add_argument("--due-only", action="store_true",
                   help="only count the channels that are due (no network, no state change)")
    args = p.parse_args(argv)

    cfg = load_json(args.follows, {})
    state = load_json(args.state, {})
    tz = ZoneInfo(cfg.get("tz") or "Asia/Tehran")
    now = dt.datetime.now(tz)
    force = args.force.strip().lower() == "true"
    if args.due_only:       # the cheap first step of the workflow: nothing due = stop here
        due = sum(1 for f in cfg.get("follows") or []
                  if f.get("id") and (not args.only or f["id"] == args.only)
                  and is_due(f, state.get(f["id"], {}), now, force or bool(args.only))[0])
        log(f"{due} channel(s) due")
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a", encoding="utf-8") as fh:
                fh.write(f"due={due}\n")
        return 0
    lines, errors, started_total = [], 0, 0
    log(f"Now: {now:%Y-%m-%d %H:%M} ({cfg.get('tz') or 'Asia/Tehran'}), {len(cfg.get('follows') or [])} channel(s)")
    for follow in cfg.get("follows") or []:
        fid = follow.get("id")
        if not fid or (args.only and fid != args.only):
            continue
        st = state.setdefault(fid, {})
        due, why = is_due(follow, st, now, force or bool(args.only))
        log(f"- {follow.get('name') or fid}: {'CHECK' if due else 'skip'} ({why})")
        if not due:
            continue
        try:
            started = check_follow(follow, st, now, default_lister)
            started_total += len(started)
            for e in started:
                lines.append(f"{follow.get('name') or fid}: {e.get('title') or e['id']}")
            if st.get("done"):
                lines.append(f"{follow.get('name') or fid}: finished ({st['done']})")
            log(f"  started {len(started)} download(s)")
        except Exception as ex:   # one broken channel must not stop the others
            errors += 1
            st["last_error"] = str(ex)[:200]
            st["last_check"] = now.isoformat(timespec="minutes")
            lines.append(f"{follow.get('name') or fid}: ERROR {str(ex)[:120]}")
            log(f"::error::{follow.get('name') or fid}: {ex}")
    with open(args.state, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with open(args.summary, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"started={started_total}\nerrors={errors}\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
