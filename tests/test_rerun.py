from core import rerun

YML = """name: X
on:
  workflow_dispatch:
    inputs:
      url:
        description: 'u'
        required: true
        default: 'https://x'
      q:
        required: false
        default: "720"
jobs:
  a: {}
"""


def test_pack_roundtrip_skips_the_apps_own_keys():
    inputs = {"video_url": "https://youtu.be/x", "format_id": "720p", "job_id": "abc",
              "storage": "github", "run_title": "t", "empty": ""}
    packed = rerun.pack_inputs(inputs)
    assert packed and "/" not in packed
    assert rerun.unpack_inputs(packed) == {"video_url": "https://youtu.be/x", "format_id": "720p"}


def test_nothing_to_pack_or_unpack():
    assert rerun.pack_inputs({"job_id": "x"}) == ""
    assert rerun.unpack_inputs("") is None
    assert rerun.unpack_inputs("!!!notvalid") is None


def test_split_run_name():
    packed = rerun.pack_inputs({"a": "1"})
    assert rerun.split_run_name(f"My title [0123456789ab] ~{packed}") == ("My title", packed)
    assert rerun.split_run_name("Plain name") == ("Plain name", "")
    assert rerun.inputs_from_name(f"x [0123456789ab] ~{packed}") == {"a": "1"}


def test_parse_declared_inputs():
    assert rerun.parse_declared_inputs(YML) == [
        {"name": "url", "default": "https://x", "required": True},
        {"name": "q", "default": "720", "required": False}]
