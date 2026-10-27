from core import run_labels as rl
from core import storage_format as sf
from core import timeutil as tu


def test_bucket_ids_and_next_id():
    names = ["ARVAN_ACCESS_KEY", "ARVAN_2_ACCESS_KEY", "ARVAN_10_ACCESS_KEY", "ARVAN_3_BUCKET", "OTHER"]
    assert sf.bucket_ids(names) == ["main", "2", "10"]
    assert sf.next_bucket_id([]) == "main"
    assert sf.next_bucket_id(["main"]) == "2"
    assert sf.next_bucket_id(["main", "2"]) == "3"
    assert sf.secret_prefix("main") == "ARVAN" and sf.secret_prefix("3") == "ARVAN_3"


def test_quota_and_sizes():
    assert sf.parse_quota("2,5") == 2.5 and sf.parse_quota("x") == 5.0 and sf.parse_quota("-1") == 5.0
    assert sf.fmt_bytes(0) == "0 KB" and sf.fmt_bytes(5 * 1024 ** 2) == "5.0 MB" and sf.fmt_bytes(1024 ** 3) == "1.00 GB"
    assert sf.fmt_expiry(None) == "" and sf.fmt_expiry(0) == "expires at the next cleanup"
    assert sf.fmt_expiry(72) == "3 days left" and sf.fmt_expiry(5) == "5 h left"


def test_times_are_shown_in_tehran():
    assert tu.utc_iso_to_local("2026-10-04T17:41:05Z") == "2026-10-04 21:11"
    assert tu.utc_iso_to_local("") == "" and tu.utc_iso_to_local("garbage") == ""


def test_duration_text():
    start = "2026-10-04T10:00:00Z"
    assert tu.duration_text(start, "2026-10-04T10:00:12Z") == "12s"
    assert tu.duration_text(start, "2026-10-04T10:01:05Z") == "1m 05s"
    assert tu.duration_text(start, "2026-10-04T11:02:00Z") == "1h 02m"
    assert tu.duration_text(None, None) == ""


def test_status_words():
    assert rl.status_word("completed", "success") == ("OK", "ok")
    assert rl.status_word("completed", "failure") == ("FAILED", "fail")
    assert rl.status_word("in_progress") == ("RUNNING", "running")
    assert rl.status_word("queued")[1] == "waiting"


def test_tool_labels_and_short_titles():
    assert rl.tool_label("new-thing.yml") == "new-thing" and rl.tool_label("") == "?"
    assert rl.short_title("Download https://www.youtu.be/abc?x=1 [t]") == "youtu.be/abc?x=1"
    assert rl.short_title("plain name") == ""
    assert len(rl.short_title("https://example.com/" + "a" * 100)) <= 34
    assert rl.escape_markup("[b]x&") == "&bl;b&br;x&amp;"
