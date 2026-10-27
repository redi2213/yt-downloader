from core import run_log

LOG = """2026-10-04T17:41:05.1234567Z ##[group]Run echo hi
2026-10-04T17:41:05.2000000Z echo hi
2026-10-04T17:41:05.3000000Z ##[endgroup]
2026-10-04T17:41:06.0000000Z hi
2026-10-04T17:41:07.0000000Z ##[error]Process completed with exit code 1.
"""


def test_markers_are_cleaned():
    texts = [t for _ts, t in run_log.parse_log(LOG)]
    assert "> Run echo hi" in texts and "hi" in texts
    assert any(t.startswith("ERROR: Process completed") for t in texts)
    assert not any("endgroup" in t for t in texts)


def test_lines_of_one_step_by_time():
    entries = run_log.parse_log(LOG)
    assert run_log.lines_for_step(entries, "2026-10-04T17:41:06Z", "2026-10-04T17:41:06Z") == ["hi"]
    assert run_log.lines_for_step(entries, None, None) == []


def test_last_line_tail_and_clip():
    entries = run_log.parse_log(LOG)
    assert run_log.last_line(entries).startswith("ERROR")
    assert run_log.tail(list("abcdef"), 2) == ["e", "f"]
    assert run_log.clip("x" * 200, 10) == "x" * 7 + "..."
