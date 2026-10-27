from core.links import split_links


def test_split_by_whitespace_and_dedupe():
    text = "https://a.com/x\nhttps://a.com/x  http://b.org/y\nnot a link"
    assert split_links(text) == ["https://a.com/x", "http://b.org/y"]


def test_comma_stays_inside_the_link():
    url = "https://cdn.x.com/f.mp4?secure=abc==,1791772209"
    assert split_links(url) == [url]


def test_empty_input():
    assert split_links("") == []
    assert split_links(None) == []
