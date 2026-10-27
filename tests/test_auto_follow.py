import datetime as dt

import auto_follow as af
from core import rerun

TZ = dt.timezone(dt.timedelta(hours=3, minutes=30))


def at(day, hour, minute=0):          # 2026-10-26 is a Monday
    return dt.datetime(2026, 10, day, hour, minute, tzinfo=TZ)


def entries(*pairs):
    return [{"id": i, "title": t, "duration": 3600, "ts": None} for i, t in pairs]


def test_episode_number_from_titles():
    assert af.episode_of("\u0642\u0633\u0645\u062a \u06f8\u06f0 \u0633\u0631\u06cc\u0627\u0644") == 80
    assert af.episode_of("Show S02E15 HD") == 15
    assert af.episode_of("episode 7") == 7
    assert af.episode_of("no number") is None


def test_time_window_including_past_midnight():
    day = {"start": "20:00", "end": "23:59", "days": []}
    assert af.in_window(day, at(26, 21)) and not af.in_window(day, at(26, 19))
    night = {"start": "22:00", "end": "02:00", "days": [0]}      # Monday night
    assert af.in_window(night, at(26, 23))
    assert af.in_window(night, at(27, 1))                        # Tuesday 01:00 still belongs to Monday
    assert not af.in_window(night, at(28, 1))


def test_is_due_rules():
    f = {"enabled": True, "mode": "series", "start": "20:00", "end": "23:59", "days": []}
    now = at(26, 21)
    assert af.is_due(f, {}, now)[0]
    assert not af.is_due(f, {"last_hit_day": "2026-10-26"}, now)[0]
    assert not af.is_due(f, {"done": "x"}, now, force=True)[0]    # a finished channel stays finished
    assert not af.is_due(dict(f, enabled=False), {}, now)[0]
    latest = dict(f, mode="latest", every_days=3)
    assert not af.is_due(latest, {"last_check_day": "2026-10-25"}, now)[0]
    assert af.is_due(latest, {"last_check_day": "2026-10-22"}, now)[0]


def test_series_takes_the_next_episodes_oldest_first():
    f = {"site": "youtube", "mode": "series", "max_per_run": 2, "include": [], "exclude": [], "stop": {}}
    es = entries(("c", "episode 83"), ("b", "episode 82"), ("a", "episode 81"), ("old", "episode 79"))
    assert [e["episode"] for e in af.select(f, {"last_episode": 80, "seen": []}, es)] == [81, 82]


def test_series_respects_stop_episode_and_seen():
    f = {"site": "youtube", "mode": "series", "max_per_run": 5, "include": [], "exclude": [], "stop": {"episode": 82}}
    es = entries(("c", "episode 83"), ("b", "episode 82"), ("a", "episode 81"))
    assert [e["episode"] for e in af.select(f, {"last_episode": 80, "seen": ["b"]}, es)] == [81]


def test_latest_mode_oldest_first():
    f = {"site": "youtube", "mode": "latest", "max_per_run": 2, "include": [], "exclude": [], "stop": {}}
    es = entries(("3", "c"), ("2", "b"), ("1", "a"))
    assert [e["id"] for e in af.select(f, {}, es)] == ["1", "2"]


def test_filters():
    f = {"site": "youtube", "min_minutes": 30, "max_minutes": 90, "include": ["news"], "exclude": ["trailer"]}
    assert af.passes(f, {"title": "Daily News 1", "duration": 3600})
    assert not af.passes(f, {"title": "Daily News", "duration": 600})
    assert not af.passes(f, {"title": "Daily News", "duration": 7200})
    assert not af.passes(f, {"title": "Sports", "duration": 3600})
    assert not af.passes(f, {"title": "News trailer", "duration": 3600})


def test_first_look_and_start_from_episode():
    f = {"site": "youtube", "mode": "series", "min_minutes": 0, "include": [], "exclude": [],
         "start_from": {"type": "now"}}
    st = {}
    af.apply_baseline(f, st, entries(("b", "episode 12"), ("a", "episode 11")))
    assert set(st["seen"]) == {"a", "b"} and st["last_episode"] == 12
    g = dict(f, start_from={"type": "episode", "value": "75"})
    st2 = {}
    af.apply_baseline(g, st2, entries(("a", "episode 80")))
    assert st2["last_episode"] == 74


def test_stop_rule_finishes_the_channel():
    f = {"mode": "series", "stop": {"episode": 82}}
    st = {"last_episode": 81}
    af.finish_check(f, st, [{"id": "x", "title": "ep 82", "episode": 82}], at(26, 21), 0)
    assert st["last_episode"] == 82 and st["done"] == "reached the last episode"
    assert st["last_hit_day"] == "2026-10-26"


def test_run_again_packing_matches_the_app():
    inputs = {"video_url": "https://youtu.be/x", "release_tag": "auto-a", "job_id": "1"}
    assert rerun.unpack_inputs(af.pack_inputs(inputs)) == {"video_url": "https://youtu.be/x", "release_tag": "auto-a"}


def test_workflow_inputs_for_youtube_and_aparat():
    f = {"site": "youtube", "quality": "720p", "slug": "s", "id": "i", "name": "N"}
    wf, inputs, _title = af.dispatch_inputs(f, [{"id": "abc", "title": "T"}])
    assert wf == "download.yml" and inputs["video_url"].endswith("v=abc") and inputs["release_tag"] == "auto-s"
    g = {"site": "aparat", "quality": "best", "slug": "s", "id": "i", "url": "https://aparat.com/n", "name": "N"}
    wf2, inputs2, _ = af.dispatch_inputs(g, [{"id": "a1"}, {"id": "a2"}])
    assert wf2 == "aparat-download.yml" and inputs2["video_ids"] == "a1,a2"


def test_a_failed_start_keeps_the_order():
    f = {"site": "youtube", "quality": "best", "slug": "s", "id": "i"}
    calls = []

    def fake(workflow, inputs, title):
        calls.append(inputs["video_url"])
        if len(calls) == 2:
            raise RuntimeError("boom")

    picked = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    started = af.start_downloads(f, picked, dispatch=fake)
    assert [e["id"] for e in started] == ["a"] and len(calls) == 2
