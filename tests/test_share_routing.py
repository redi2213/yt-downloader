from core import share_routing as sr


def test_extract_url_strips_trailing_punctuation():
    assert sr.extract_url("look: https://youtu.be/abc123xyz12.") == "https://youtu.be/abc123xyz12"
    assert sr.extract_url("no link here") is None


def test_google_redirect_is_unwrapped():
    wrapped = "https://www.google.com/url?sa=t&url=https%3A%2F%2Fexample.com%2Fvideo&usg=x"
    assert sr.extract_url(wrapped) == "https://example.com/video"


def test_youtube_hosts_and_playlists():
    assert sr.is_youtube("https://www.youtube.com/watch?v=x")
    assert sr.is_youtube("https://m.youtube.com/watch?v=x")
    assert sr.is_youtube("https://youtu.be/x")
    assert not sr.is_youtube("https://evilyoutube.com/x")
    assert sr.is_youtube_playlist("https://www.youtube.com/playlist?list=PL123")
    assert not sr.is_youtube_playlist("https://www.youtube.com/watch?v=abc&list=PL123")


def test_classify_quick():
    assert sr.classify_quick("hey https://youtu.be/abc")["kind"] == "youtube_video"
    assert sr.classify_quick("https://www.youtube.com/playlist?list=PL1")["kind"] == "youtube_playlist"
    assert sr.classify_quick("https://example.com") is None


def test_match_action_by_domain_and_disabled():
    actions = [{"id": "a", "domains": ["aparat.com"]}, {"id": "off", "domains": ["x.com"], "enabled": False}]
    assert sr.match_action("https://www.aparat.com/v/abc", actions)["id"] == "a"
    assert sr.match_action("https://x.com/1", actions) is None
    assert sr.match_action("https://other.org", actions) is None


def test_unknown_link_goes_to_the_chooser():
    assert sr.classify("https://example.com/v", [])["kind"] == "chooser"
