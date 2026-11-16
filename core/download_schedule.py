"""Download scheduler time rules (plain Python, no Kivy): one daily window by the phone's clock.

``start`` / ``stop`` are ``(hour, minute)`` tuples or None. A window that ends before it starts
(22:00 -> 06:00) crosses midnight. No stop time = open from the start time until midnight.
"""
from datetime import datetime


def parse_hm(text):
    """``"02:30"`` -> ``(2, 30)``; None when empty or not a valid time."""
    try:
        hour, minute = str(text).strip().split(":", 1)
        hour, minute = int(hour), int(minute)
    except Exception:
        return None
    return (hour, minute) if 0 <= hour <= 23 and 0 <= minute <= 59 else None


def fmt_hm(hm):
    return f"{hm[0]:02d}:{hm[1]:02d}" if hm else ""


def in_window(start, stop, now=None):
    """True while the phone's clock is inside the window."""
    if not start:
        return False
    now = now or datetime.now()
    cur = now.hour * 60 + now.minute
    s = start[0] * 60 + start[1]
    if not stop:
        return cur >= s
    e = stop[0] * 60 + stop[1]
    if s == e:
        return True
    return s <= cur < e if s < e else (cur >= s or cur < e)


def phone_time_text(now=None):
    return (now or datetime.now()).strftime("%H:%M")
