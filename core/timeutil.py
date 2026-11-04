"""Converting GitHub's UTC timestamps (and our own UTC datetimes) to the
local time shown in the app. See LOCAL_UTC_OFFSET_MINUTES in core/config.py.
"""
from datetime import datetime, timedelta, timezone

from core import config

_ISO_FORMAT = "%Y-%m-%dT%H:%M:%S"

# Settings > Appearance and language > Date format: "gregorian" or "jalali" (Shamsi).
_date_mode = "gregorian"


def set_date_mode(mode):
    global _date_mode
    _date_mode = "jalali" if mode == "jalali" else "gregorian"


def date_mode():
    return _date_mode


_G_DAYS = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def gregorian_to_jalali(gy, gm, gd):
    """(year, month, day) of the Gregorian calendar -> the Jalali (Shamsi) date."""
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + _G_DAYS[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        return jy, 1 + days // 31, 1 + days % 31
    return jy, 7 + (days - 186) // 30, 1 + (days - 186) % 30


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
    local = dt.astimezone(_local_tz())
    if _date_mode == "jalali" and "%" in fmt:
        jy, jm, jd = gregorian_to_jalali(local.year, local.month, local.day)
        fmt = fmt.replace("%Y", f"{jy:04d}").replace("%m", f"{jm:02d}").replace("%d", f"{jd:02d}")
    return local.strftime(fmt)


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
