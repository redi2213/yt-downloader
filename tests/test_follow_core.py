from core import follow as fc


def test_clean_url_and_names():
    assert fc.clean_url("https://youtube.com/@chan/?si=abc") == "https://youtube.com/@chan"
    assert fc.name_from_url("https://www.youtube.com/@eshghe_abadi") == "eshghe_abadi"
    assert fc.name_from_url("https://www.youtube.com/@x/videos") == "x"


def test_site_and_one_video_detection():
    assert fc.site_of("https://www.aparat.com/name") == "aparat"
    assert fc.site_of("https://youtu.be/x") == "youtube"
    assert fc.looks_like_video("https://youtu.be/abc")
    assert fc.looks_like_video("https://www.youtube.com/watch?v=abc")
    assert not fc.looks_like_video("https://www.youtube.com/@chan")


def test_validate():
    good = fc.new_follow("https://www.youtube.com/@chan")
    assert fc.validate(good) == ""
    assert "one video" in fc.validate(fc.new_follow("https://youtu.be/abc"))
    assert "Series mode" in fc.validate(dict(good, mode="series", site="aparat"))


def test_slug_is_unique():
    assert fc.slugify("My Channel!", taken={"my-channel"}) == "my-channel-2"


def test_cron_only_wakes_in_the_needed_hours():
    assert fc.cron_for([]) == fc.OFF_CRON
    f = dict(fc.new_follow("https://youtube.com/@a"), start="20:00", end="23:59", enabled=True)
    cron = fc.cron_for([f])
    assert cron.startswith("7,37 ")
    hours = [int(h) for h in cron.split()[1].split(",")]
    assert min(hours) == 16 and max(hours) == 20     # Tehran 20:00-23:59 = UTC 16:30-20:29


def test_with_cron_and_ticks():
    text = "on:\n  schedule:\n    - cron: '17 * * * *'\n  workflow_dispatch:\n"
    out = fc.with_cron(text, "7,37 16 * * *")
    assert "- cron: '7,37 16 * * *'" in out and "17 * * * *" not in out
    assert fc.with_cron("no cron here", "x") is None
    assert fc.ticks_per_day("7,37 16,17 * * *") == 4
    assert fc.ticks_per_day(fc.OFF_CRON) == 0


def test_words_and_to_int():
    assert fc.words("a, b \u060c c") == ["a", "b", "c"]
    assert fc.to_int("12") == 12 and fc.to_int("x", 5) == 5
