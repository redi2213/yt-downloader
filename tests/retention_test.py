"""Release lifetime rules and the Jalali date conversion (plain Python, no Kivy needed):
    python3 tests/retention_test.py"""
import os
import sys
import types
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from scripts import retention_core as R  # noqa: E402

now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
keep = R.parse_keep("text\n<!--ytb-quality:{}-->")
assert keep == {"files": {}}
assert R.iso(R.expires_at("run", "2026-11-01T00:00:00Z", keep, 5)) == "2026-11-08T00:00:00Z"
assert R.expires_at("job", "2026-10-01T00:00:00Z", keep, 5) is None
assert R.kind_of("random") is None and R.kind_of("tg-1", bot=True) == "bot" and R.kind_of("tg-1") is None
assert R.iso(R.expires_at("auto", "2026-10-01T00:00:00Z", keep, 5)) == R.GRACE_UNTIL
cur = R.expires_at("run", "2026-11-01T00:00:00Z", keep, 5)
keep["files"]["5"] = R.iso(R.extended(cur, 7, now))
body = R.with_keep("text\n<!--ytb-quality:{}-->", keep)
assert "<!--ytb-quality:{}-->" in body
assert R.iso(R.expires_at("run", "2026-11-01T00:00:00Z", R.parse_keep(body), 5)) == "2026-11-15T00:00:00Z"
keep["files"]["5"] = R.FOREVER
assert R.expires_at("run", "2026-11-01T00:00:00Z", keep, 5) is None
assert R.deadline_text(None, True, now) == "Kept forever"
assert R.with_keep(body, {"files": {}}) == "text\n<!--ytb-quality:{}-->"
assert R.deadline_text(R.parse_iso("2026-11-08T00:00:00Z"), False, now) == "3 days left"

# Jalali dates (core/timeutil.py loaded without the app's config module)
cfg = types.ModuleType("core.config")
cfg.LOCAL_UTC_OFFSET_MINUTES = 210
import core  # noqa: E402
sys.modules["core.config"] = core.config = cfg
from core import timeutil  # noqa: E402
assert timeutil.gregorian_to_jalali(2026, 11, 4) == (1405, 8, 13)
assert timeutil.gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
assert timeutil.gregorian_to_jalali(2025, 3, 20) == (1403, 12, 30)
timeutil.set_date_mode("jalali")
assert timeutil.utc_iso_to_local("2026-11-04T10:15:00Z") == "1405-08-13 13:45"
timeutil.set_date_mode("gregorian")
assert timeutil.utc_iso_to_local("2026-11-04T10:15:00Z") == "2026-11-04 13:45"
print("retention tests ok")
