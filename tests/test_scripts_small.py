import finglish_name as fn
import quality_probe as qp


def test_quality_written_in_the_file_name():
    assert qp._from_name("My_Video_720p_30fps.mp4") == ("720p", 30.0)
    assert qp._from_name("x_1080p.mkv") == ("1080p", 0)
    assert qp._from_name("nothing.mp4") == ("", 0)


def test_non_media_files_are_ignored(tmp_path):
    f = tmp_path / "a.zip"
    f.write_bytes(b"x")
    assert qp.probe_file(str(f)) == {}
    assert qp.probe_files([str(f)]) == {}


def test_merge_keeps_the_workflows_numbers():
    out = qp.merge({"resolution": "1080p", "codec": "VP9"},
                   {"resolution": "720p", "by_file": {"a": {"resolution": "720p"}}})
    assert out["resolution"] == "1080p" and out["by_file"] == {"a": {"resolution": "720p"}}


def test_persian_name_becomes_ascii():
    out = fn.safe_name("\u0633\u0644\u0627\u0645 \u062f\u0646\u06cc\u0627")
    assert out.isascii() and len(out) >= 3


def test_unsafe_characters_and_fallback():
    out = fn.safe_name("My Video: part 1/2?")
    assert out.startswith("My Video") and not any(c in out for c in "/:?")
    assert fn.safe_name("\U0001F3AC\U0001F3AC", fallback="video_9") == "video_9"
    assert fn.safe_name("", fallback="x") == "x"
    assert len(fn.safe_name("a" * 500, max_len=40)) <= 40
