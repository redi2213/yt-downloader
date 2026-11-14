"""HLS (.m3u8) download on the phone: playlist reading (plain Python, no Kivy, no network):
    python3 tests/hls_download_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import hls_download as h  # noqa: E402

assert h.looks_like_hls("https://x.test/a/chunk.m3u8?wmsAuthSign=abc")
assert not h.looks_like_hls("https://x.test/a/video.mp4")

plain = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:5\n#EXTINF:4,\ns1.ts?t=1\n#EXTINF:4,\ns2.ts?t=1\n#EXT-X-ENDLIST\n"
p = h.parse_media(plain, "https://x.test/v/chunk.m3u8?wmsAuthSign=abc")
assert [s["url"] for s in p["segments"]] == ["https://x.test/v/s1.ts?t=1", "https://x.test/v/s2.ts?t=1"]
assert [s["seq"] for s in p["segments"]] == [5, 6] and p["ended"] and p["init"] is None

enc = ("#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"k.key\",IV=0x0A\n#EXTINF:4,\ns1.ts\n#EXT-X-MAP:URI=\"init.mp4\"\n"
       "#EXT-X-ENDLIST\n")
e = h.parse_media(enc, "https://x.test/v/m.m3u8")
assert e["segments"][0]["key"] == ("https://x.test/v/k.key", "0x0A") and e["init"] == "https://x.test/v/init.mp4"
assert h._iv("0x0A", 0) == bytes(15) + b"\x0a" and h._iv(None, 3)[-1] == 3
assert h._unpad(b"abc" + b"\x05" * 5) == b"abc" and h._unpad(b"abcdefgh") == b"abcdefgh"

assert not h.parse_media("#EXTM3U\n#EXTINF:4,\ns1.ts\n", "https://x.test/m.m3u8")["ended"]     # live
for bad in ("#EXT-X-KEY:METHOD=SAMPLE-AES,URI=\"k\"\n#EXTINF:4,\ns.ts\n", "#EXT-X-BYTERANGE:100@0\ns.ts\n"):
    try:
        h.parse_media("#EXTM3U\n" + bad, "https://x.test/m.m3u8")
    except h.HlsError:
        pass
    else:
        raise AssertionError("must refuse: " + bad)
print("hls_download_test: ok")
