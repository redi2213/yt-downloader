"""Converting GitHub's UTC timestamps (and our own UTC datetimes) to the
local time shown in the app. See LOCAL_UTC_OFFSET_MINUTES in core/config.py.
"""
from datetime import datetime, timedelta, timezone

from core import config

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"


def _local_tz():
    return timezone(timedelta(minutes=config.LOCAL_UTC_OFFSET_MINUTES))


def parse_utc(iso):
    """'2026-10-04T17:41:05Z' (also with fractions / +00:00) -> aware UTC
    datetime, or None if it can't be parsed."""
    if not iso or not isinstance(iso, str):
        return None
    try:
        return datetime.strptime(iso[:19], _ISO_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def datetime_to_local(dt, fmt="%Y-%m-%d %H:%M"):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(_local_tz()).strftime(fmt)


def utc_iso_to_local(iso, fmt="%Y-%m-%d %H:%M"):
    """GitHub UTC timestamp -> local time text ('' if missing/invalid)."""
    return datetime_to_local(parse_utc(iso), fmt)


def duration_text(start_iso, end_iso, now=None):
    """'12s', '1m 05s', '1h 02m' between two UTC timestamps. A step that has
    started but not finished is measured up to ``now``. '' if unknown."""
    start = parse_utc(start_iso)
    if start is None:
        return ""
    end = parse_utc(end_iso)
    if end is None:
        end = now or datetime.now(timezone.utc)
    seconds = max(0, int((end - start).total_seconds()))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"
