"""Auto follow: the channels the app watches (pure helpers, no Kivy, no network).

A followed channel is one dict; the list is saved as ``follows.json`` on the
``config`` branch and read by scripts/auto_follow.py in the Auto-Follow.yml
workflow (the keys are documented there). What was already fetched is kept by
that script in ``follow-state.json`` next to it.
"""
import re
import uuid
from datetime import date

TZ_NAME = "Asia/Tehran"
TZ_OFFSET_MIN = 210          # UTC+03:30, no daylight saving time since 2022

# Iranian week order for the buttons: (label, weekday number with Monday = 0)
WEEK_BUTTONS = [("Sat", 5), ("Sun", 6), ("Mon", 0), ("Tue", 1), ("Wed", 2), ("Thu", 3), ("Fri", 4)]
ALL_DAYS = [d for _l, d in WEEK_BUTTONS]
QUALITIES = ["best", "1080p", "720p", "480p", "360p", "audio"]
MODES = [("Series: next episode each time", "series"), ("Latest videos", "latest")]
FROM_TYPES = [("Only new from now on", "now"), ("From episode number", "episode"),
              ("From date", "date"), ("Also the last N videos", "last_n")]
PER_RUN = ["1", "2", "3", "5", "10"]
EVERY_DAYS = ["1", "2", "3", "5", "7", "14"]
HOURS = [f"{h:02d}:{m:02d}" for h in range(24) for m in (0, 30)] + ["23:59"]


def site_of(url):
    u = (url or "").lower()
    if "aparat.com" in u:
        return "aparat"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    return ""


def clean_url(url):
    """The link without tracking parameters (?si=...), but a playlist keeps its list=."""
    url = (url or "").strip().split("#")[0]
    base, _, query = url.partition("?")
    if "list=" in query and "playlist" in base:
        return base + "?" + "&".join(p for p in query.split("&") if p.startswith("list="))
    return base.rstrip("/")


def name_from_url(url):
    """'@eshghe_abadi' -> 'eshghe_abadi'; aparat.com/rest_in_peace -> 'rest_in_peace'."""
    tail = clean_url(url).rstrip("/").split("/")[-1]
    if tail in ("videos", "featured", "streams"):
        tail = clean_url(url).rstrip("/").split("/")[-2]
    return tail.lstrip("@") or "channel"


def slugify(name, taken=()):
    base = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")[:30] or "channel"
    slug, n = base, 2
    while slug in taken:
        slug, n = f"{base}-{n}", n + 1
    return slug


def new_follow(url, existing=()):
    url = clean_url(url)
    taken = {f.get("slug") for f in existing}
    name = name_from_url(url)
    return {
        "id": "f" + uuid.uuid4().hex[:8], "slug": slugify(name, taken), "name": name,
        "site": site_of(url), "url": url, "enabled": True,
        "mode": "latest", "days": [], "start": "20:00", "end": "23:59", "every_days": 3,
        "quality": "best", "min_minutes": 0, "max_minutes": 0, "include": [], "exclude": [],
        "start_from": {"type": "now", "value": None},
        "stop": {"episode": None, "date": None, "count": None},
        "max_per_run": 1, "zip": False,
    }


def words(text):
    """'a, b ، c' -> ['a', 'b', 'c']"""
    return [w.strip() for w in re.split(r"[,\u060c;\n]+", text or "") if w.strip()]


def to_int(text, default=0):
    try:
        return int(str(text).strip())
    except ValueError:
        return default


def validate(f):
    """'' when the follow can be saved, else what is wrong."""
    if not f.get("url"):
        return "Paste the channel link."
    if not f.get("site"):
        return "Only YouTube and Aparat channels can be followed."
    if f["site"] == "aparat" and "/v/" in f["url"]:
        return "Use the channel link (aparat.com/<channel>), not a video link."
    if f.get("mode") == "series" and f["site"] == "aparat":
        return "Series mode needs episode numbers in the titles: use it for YouTube. Aparat: Latest videos."
    if not f.get("name"):
        return "Give the channel a name."
    sf = f.get("start_from") or {}
    if sf.get("type") == "episode" and not str(sf.get("value") or "").isdigit():
        return "Type the episode number to start from."
    if sf.get("type") == "last_n" and not str(sf.get("value") or "").isdigit():
        return "Type how many of the last videos to take now."
    if sf.get("type") == "date":
        try:
            date.fromisoformat(str(sf.get("value")))
        except ValueError:
            return "Type the start date like 2026-10-19."
    stop = f.get("stop") or {}
    if stop.get("date"):
        try:
            date.fromisoformat(str(stop["date"]))
        except ValueError:
            return "Type the end date like 2026-12-31."
    if f.get("min_minutes") and f.get("max_minutes") and f["min_minutes"] > f["max_minutes"]:
        return "The shortest length is bigger than the longest."
    return ""


def days_text(f):
    days = f.get("days") or []
    if not days or len(days) == 7:
        return "every day"
    return " ".join(label for label, d in WEEK_BUTTONS if d in days)


def summary_text(f, st=None):
    """One-line description of a follow for the list."""
    st = st or {}
    mode = "series" if f.get("mode") == "series" else f"latest, every {f.get('every_days', 1)} day(s)"
    parts = [f"{f.get('site', '?')} {mode}", f"{days_text(f)} {f.get('start')}-{f.get('end')}"]
    if st.get("done"):
        parts.append(f"FINISHED: {st['done']}")
    elif not f.get("enabled", True):
        parts.append("PAUSED")
    return "  |  ".join(parts)


def status_text(f, st=None):
    """Multi-line status for the channel's page."""
    st = st or {}
    lines = [summary_text(f, st)]
    if f.get("mode") == "series" and st.get("last_episode"):
        lines.append(f"Last episode fetched: {st['last_episode']}")
    if st.get("count"):
        lines.append(f"Videos started so far: {st['count']}")
    if st.get("last_video"):
        lines.append(f"Last video: {st['last_video']}")
    lines.append(f"Last check: {st.get('last_check') or 'not yet'}")
    if st.get("last_error"):
        lines.append(f"Last problem: {st['last_error']}")
    return "\n".join(lines)


def release_tag(f):
    return "auto-" + (f.get("slug") or f["id"])


# -- schedule (the cron line of Auto-Follow.yml) -------------------------------------------------
def _minutes(text, default):
    try:
        h, m = str(text).split(":")
        return int(h) * 60 + int(m)
    except ValueError:
        return default


def _in_window_minutes(f, local_minute):
    start, end = _minutes(f.get("start"), 0), _minutes(f.get("end"), 1439)
    if start <= end:
        return start <= local_minute <= end
    return local_minute >= start or local_minute <= end


TICK_MINUTES = (7, 37)
OFF_CRON = "0 0 1 1 *"       # once a year: practically off when nothing is followed


def cron_for(follows):
    """The cron line that wakes the scheduler only in the hours the (enabled)
    channels' windows need, in UTC. The script itself still checks the exact
    weekday and time, so a tick outside a window costs about a minute and does nothing."""
    active = [f for f in follows if f.get("enabled", True)]
    hours = []
    for h in range(24):
        for m in TICK_MINUTES:
            local = (h * 60 + m + TZ_OFFSET_MIN) % 1440
            if any(_in_window_minutes(f, local) for f in active):
                hours.append(h)
                break
    if not hours:
        return OFF_CRON
    return f"{','.join(str(m) for m in TICK_MINUTES)} {','.join(str(h) for h in hours)} * * *"


_CRON_LINE = re.compile(r"^(\s*- cron: )'[^']*'\s*$", re.M)


def with_cron(workflow_text, cron):
    """The workflow file text with its cron line replaced (None if it has none)."""
    if not _CRON_LINE.search(workflow_text):
        return None
    return _CRON_LINE.sub(lambda m: f"{m.group(1)}'{cron}'", workflow_text, count=1)


def ticks_per_day(cron):
    parts = cron.split()
    if len(parts) != 5 or cron == OFF_CRON:
        return 0
    return len(parts[0].split(",")) * len(parts[1].split(","))
