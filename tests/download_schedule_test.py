"""Downloads scheduler time rules (plain Python, no Kivy needed):
    python3 tests/download_schedule_test.py"""
import os
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import download_schedule as ds  # noqa: E402


def at(h, m=0):
    return datetime(2026, 11, 16, h, m)


assert ds.parse_hm("02:30") == (2, 30) and ds.parse_hm(" 7:05 ") == (7, 5)
assert ds.parse_hm("") is None and ds.parse_hm("24:00") is None and ds.parse_hm("12:60") is None
assert ds.parse_hm("abc") is None and ds.parse_hm(None) is None
assert ds.fmt_hm((2, 5)) == "02:05" and ds.fmt_hm(None) == ""

# same-day window
assert ds.in_window((2, 0), (6, 0), at(2, 0)) and ds.in_window((2, 0), (6, 0), at(5, 59))
assert not ds.in_window((2, 0), (6, 0), at(6, 0)) and not ds.in_window((2, 0), (6, 0), at(1, 59))
# window across midnight
assert ds.in_window((22, 0), (6, 0), at(23, 30)) and ds.in_window((22, 0), (6, 0), at(0, 15))
assert not ds.in_window((22, 0), (6, 0), at(12, 0)) and not ds.in_window((22, 0), (6, 0), at(6, 0))
# no stop time: open from the start time until midnight
assert ds.in_window((2, 0), None, at(2, 0)) and ds.in_window((2, 0), None, at(23, 59))
assert not ds.in_window((2, 0), None, at(1, 59))
# no start time: never open
assert not ds.in_window(None, (6, 0), at(3, 0))
print("download_schedule_test: ok")
