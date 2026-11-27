"""Full page export (plain Python, no Kivy needed):  python3 tests/page_export_test.py"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import page_export as pe


def main():
    now = datetime(2026, 11, 27, 13, 5, 9)
    assert pe.folder("https://www.example.com/a?b=1", now) == "www.example.com/2026-11-27_13-05-09"
    assert pe.folder("", now).startswith("unknown-site/")
    where, files = pe.build_files(
        "https://a.test/x", "UA", "# cookies\n",
        [{"url": "https://a.test/api", "resp": "x" * (pe.MAX_TEXT + 5)}],
        [{"url": "https://a.test/v.m3u8", "size": 5}], '{"localStorage": {}}', "<html></html>", now)
    assert where == "a.test/2026-11-27_13-05-09"
    assert tuple(files) == pe.FILES
    meta = json.loads(files["meta.json"])
    assert meta["url"] == "https://a.test/x" and meta["requests"] == 1 and meta["media_found"] == 1
    reqs = json.loads(files["requests.json"])
    assert reqs["requests"][0]["resp_cut"] is True and len(reqs["requests"][0]["resp"]) == pe.MAX_TEXT
    assert reqs["media_found"][0]["url"].endswith(".m3u8")
    assert files["cookies.txt"] == "# cookies\n" and files["page.html"] == "<html></html>"
    assert json.loads(files["storage.json"]) == {"localStorage": {}}
    _, bad = pe.build_files("https://a.test/", "", "", [], [], "not json", "", now)
    assert "error" in json.loads(bad["storage.json"]) and "not read" in bad["page.html"]
    _, none = pe.build_files("", "", "", None, None, None, None, now)
    assert "error" in json.loads(none["storage.json"])
    print("page_export_test: OK")


if __name__ == "__main__":
    main()
