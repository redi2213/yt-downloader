"""Reading the cron schedules of a workflow file and saying them in plain words.
Pure text helpers - no Kivy, no network.

GitHub runs cron schedules in UTC; ``describe`` shows them in the phone's local
time (``offset_minutes`` ahead of UTC).
"""
import re

_CRON_RE = re.compile(r"^[ \t]*-?[ \t]*cron:[ \t]*['\"]([^'\"]+)['\"]", re.MULTILINE)
_DAYS_EN = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
_DAYS_FA = ("یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه")
_FA_ORDER = (6, 0, 1, 2, 3, 4, 5)       # the Persian week starts on Saturday
_EN_ORDER = (0, 1, 2, 3, 4, 5, 6)
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def find_crons(text):
    """Every active ``cron: '...'`` line of a workflow file's text."""
    return [m.group(1).strip() for m in _CRON_RE.finditer(text or "")]


def _days(field):
    """Day-of-week field -> set of 0..6 (0 = Sunday), or None when it has names/steps."""
    out = set()
    for chunk in field.split(","):
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            if not (a.isdigit() and b.isdigit()):
                return None
            out.update(range(int(a), int(b) + 1))
        elif chunk.isdigit():
            out.add(int(chunk))
        else:
            return None
    return {d % 7 for d in out}


def _num(value, fa):
    text = str(value)
    return text.translate(_FA_DIGITS) if fa else text


def _local(hour, minute, offset_minutes):
    """UTC time -> (hour, minute, day_shift) in local time."""
    total = hour * 60 + minute + offset_minutes
    return (total % 1440) // 60, total % 60, total // 1440


def describe(cron, offset_minutes=0, fa=False):
    """'0 3 * * *' -> 'Every day at 03:00' (local time); Persian when ``fa``.
    A schedule it cannot read is returned as written."""
    parts = (cron or "").split()
    if len(parts) != 5 or parts[3] != "*":
        return cron or ""
    minute, hour, dom, _month, dow = parts

    step = re.fullmatch(r"\*/(\d+)", minute)
    if step and hour == dom == dow == "*":
        n = int(step.group(1))
        if n <= 1:
            return "هر دقیقه" if fa else "Every minute"
        return f"هر {_num(n, fa)} دقیقه" if fa else f"Every {n} minutes"

    if minute.isdigit() and dom == "*" and dow == "*":
        at = (int(minute) + offset_minutes) % 60
        extra = ""
        if at:
            extra = f"، دقیقه‌ی {_num(at, fa)}" if fa else f", at minute {at}"
        every = re.fullmatch(r"\*/(\d+)", hour)
        if hour == "*" or (every and int(every.group(1)) <= 1):
            return ("هر ساعت" if fa else "Every hour") + extra
        if every:
            n = int(every.group(1))
            return (f"هر {_num(n, fa)} ساعت" if fa else f"Every {n} hours") + extra

    if not (minute.isdigit() and hour.isdigit()):
        return cron
    h, m, shift = _local(int(hour), int(minute), offset_minutes)
    clock = _num(f"{h:02d}:{m:02d}", fa)
    if dom == "*" and dow == "*":
        return f"هر روز ساعت {clock}" if fa else f"Every day at {clock}"
    if dom == "*":
        days = _days(dow)
        if not days:
            return cron
        days = {(d + shift) % 7 for d in days}
        if len(days) == 7:
            return f"هر روز ساعت {clock}" if fa else f"Every day at {clock}"
        order = _FA_ORDER if fa else _EN_ORDER
        names = [(_DAYS_FA if fa else _DAYS_EN)[d] for d in order if d in days]
        if fa:
            return f"هر {'، '.join(names)} ساعت {clock}"
        return f"Every {', '.join(names)} at {clock}"
    if dow == "*" and dom.isdigit():
        day = int(dom) + shift
        if not 1 <= day <= 28:
            return cron
        if fa:
            return f"هر ماه، روز {_num(day, fa)}، ساعت {clock}"
        return f"Every month on day {day} at {clock}"
    return cron
