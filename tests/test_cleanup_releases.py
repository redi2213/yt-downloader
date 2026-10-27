import datetime as dt

import cleanup_releases as cr

NOW = dt.datetime(2026, 10, 26, 12, tzinfo=dt.timezone.utc)


def rel(tag, hours_old, assets=("v.mp4",), name="x", body="", draft=False):
    stamp = (NOW - dt.timedelta(hours=hours_old)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"tag_name": tag, "name": name, "published_at": stamp, "created_at": stamp,
            "assets": [{"name": a} for a in assets], "body": body, "draft": draft}


def test_recent_release_is_kept_and_old_video_goes():
    assert cr.reason_to_delete(rel("run-1", 5), NOW) is None
    assert "older than 7 days" in cr.reason_to_delete(rel("run-1", 24 * 8), NOW)


def test_apk_builds_and_backups_are_kept():
    apk = rel("run-2", 24 * 30, assets=("YT-Bridge-2.3.apk",), name="YT Bridge 2.3 (build #9)")
    backup = rel("run-3", 24 * 30, assets=("project-backup.zip",), name="Project backup 2026-10-01")
    assert cr.reason_to_delete(apk, NOW) is None and cr.reason_to_delete(backup, NOW) is None


def test_a_release_only_named_like_the_app_is_not_protected():
    assert cr.reason_to_delete(rel("run-4", 24 * 30, assets=("movie.mp4",), name="YT Bridge sneaky"), NOW)


def test_empty_release_has_a_grace_period():
    assert cr.reason_to_delete(rel("run-5", 1, assets=()), NOW) is None
    assert "empty" in cr.reason_to_delete(rel("run-5", 3, assets=()), NOW)


def test_release_with_files_on_arvan_is_kept():
    body = '<!--ytb-storage:{"v":1,"files":[{"name":"a","url":"u"}]}-->'
    assert cr.reason_to_delete(rel("run-6", 100, assets=(), body=body), NOW) is None


def test_other_tags_drafts_and_bad_dates_are_never_touched():
    assert cr.reason_to_delete(rel("auto-x", 24 * 30), NOW) is None
    assert cr.reason_to_delete(rel("v1", 24 * 30), NOW) is None
    assert cr.reason_to_delete(rel("run-7", 24 * 30, draft=True), NOW) is None
    broken = rel("run-8", 24 * 30)
    broken["published_at"] = broken["created_at"] = ""
    assert cr.reason_to_delete(broken, NOW) is None


def test_job_releases_are_not_deleted_by_age_alone():
    assert cr.reason_to_delete(rel("job-1", 24 * 30), NOW) is None
