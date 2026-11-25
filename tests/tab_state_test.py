"""App tabs rules (plain Python, no Kivy needed):
    python3 tests/tab_state_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import tab_state as ts  # noqa: E402

# state of one tab
assert ts.tab_state(True, False, None, False, False) == ts.RUNNING
assert ts.tab_state(False, True, True, False, False) == ts.DONE
assert ts.tab_state(False, True, False, False, False) == ts.ERROR
assert ts.tab_state(False, True, True, False, True) == ts.IDLE          # already seen
assert ts.tab_state(False, True, False, True, False) == ts.IDLE         # cancelled by the user
assert ts.tab_state(False, False, None, False, False) == ts.IDLE
assert ts.tab_state(True, True, True, False, False) == ts.RUNNING       # a new job started meanwhile

# percent of a GitHub job
job = {"steps": [{"status": "completed", "conclusion": "success"}, {"status": "in_progress"},
                 {"status": "queued"}, {"status": "completed", "conclusion": "skipped"}]}
assert ts.job_percent(job) == 33
assert ts.job_percent({"steps": [{"status": "completed", "conclusion": "success"}]}) == 100
assert ts.job_percent({"steps": []}) is None and ts.job_percent(None) is None
assert ts.job_percent({"steps": [{"status": "completed", "conclusion": "skipped"}]}) is None

# the Tabs button badge: other tabs' results first, the tab on screen only while running
assert ts.badge_state([ts.IDLE, ts.IDLE], 0) == ts.IDLE
assert ts.badge_state([ts.RUNNING, ts.IDLE], 0) == ts.RUNNING
assert ts.badge_state([ts.DONE, ts.IDLE], 0) == ts.IDLE                 # the tab you look at
assert ts.badge_state([ts.IDLE, ts.DONE], 0) == ts.DONE
assert ts.badge_state([ts.RUNNING, ts.DONE], 0) == ts.DONE
assert ts.badge_state([ts.IDLE, ts.ERROR, ts.DONE], 0) == ts.ERROR
assert ts.badge_suffix(ts.RUNNING) == " *" and ts.badge_suffix(ts.IDLE) == ""

# which tab makes room for a new one
assert ts.pick_to_replace([ts.RUNNING, ts.IDLE, ts.IDLE, ts.RUNNING]) == 1
assert ts.pick_to_replace([ts.RUNNING, ts.DONE, ts.ERROR, ts.RUNNING]) == 1
assert ts.pick_to_replace([ts.RUNNING, ts.ERROR, ts.DONE, ts.RUNNING]) == 2
assert ts.pick_to_replace([ts.RUNNING] * 4) is None

assert ts.status_text(ts.RUNNING, 40) == "Status: running 40%"
assert ts.status_text(ts.RUNNING) == "Status: running" and ts.status_text(ts.IDLE) == "Status: idle"
print("tab_state_test OK")
