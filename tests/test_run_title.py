from core import run_title as rt


def test_youtube_title_comes_from_oembed():
    assert rt.build_title({"video_url": "https://youtu.be/abcdefghijk"}, fetch=lambda url: '{"title":"My Video"}') == "My Video"


def test_failed_lookup_falls_back_to_the_video_id():
    def boom(url):
        raise OSError("no network")
    assert rt.build_title({"video_url": "https://www.youtube.com/watch?v=abcdefghijk"}, fetch=boom) == "abcdefghijk"


def test_file_link_uses_the_file_name():
    assert rt.build_title({"file_url": "https://x.com/dl/My%20Movie_480p.mkv?dl=1"}) == "My Movie 480p"


def test_several_links_add_a_count():
    assert rt.build_title({"urls": "https://a.com/x\nhttps://b.com/y"}).endswith("+1")


def test_no_link_no_title():
    assert rt.build_title({"quality": "720"}) == ""


def test_google_play_package_name():
    assert rt.build_title({"play_url": "https://play.google.com/store/apps/details?id=com.foo.bar"}) == "com.foo.bar"


def test_clean_title():
    assert rt.clean_title("a [b] {c}\n d") == "a b c d"
    assert len(rt.clean_title("x" * 200)) <= 70
