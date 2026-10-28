#!/usr/bin/env python3
"""Downloads the xHamster HLS link chosen by xh_pick.py (link.txt) into work/<NAME>.

Same method as download_hls() in xh_download.yml (link_downloader): NO proxy for the CDN, yt-dlp with
16 fragments and the video page as Referer, ffmpeg as fallback, then the page URL as a last try.
Needs: URL (the page), NAME (the file name). Writes size.txt.
"""
import os
import subprocess
import sys
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def run(cmd):
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd).returncode


def good(path):
    if not path.is_file() or path.stat().st_size < 1000:
        return False
    with open(path, "rb") as fh:
        return not fh.read(16).startswith(b"#EXTM3U")


def hls(url, referer, out):
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    base = str(out)[: -len(out.suffix)] if out.suffix else str(out)
    rc = run(["yt-dlp", "--no-playlist", "--no-part", "--no-mtime", "-N", "16",
              "--retries", "10", "--fragment-retries", "10",
              "--user-agent", UA, "--referer", referer or url,
              "--remux-video", "mp4", "-o", base + ".%(ext)s", url])
    if rc == 0 and good(out):
        return True
    print("yt-dlp failed or gave no video - ffmpeg fallback", flush=True)
    if out.exists():
        out.unlink()
    rc = run(["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y", "-user_agent", UA,
              "-headers", f"Referer: {referer or url}\r\n", "-i", url, "-c", "copy", str(out)])
    return rc == 0 and good(out)


def main():
    page = os.environ["URL"]
    name = os.environ["NAME"]
    with open("link.txt", encoding="utf-8") as fh:
        link = fh.read().split()[0]
    out = Path("work") / name
    ok = hls(link, page, out)
    if not ok and page != link:
        print("retry through the page URL", flush=True)
        ok = hls(page, page, out)
    if not ok:
        print("::error::Could not download the xHamster video (the link may have expired or been refused).")
        sys.exit(1)
    size = out.stat().st_size
    Path("size.txt").write_text(str(size))
    print(f"OK {out} ({size / 1048576:.1f} MB)")


if __name__ == "__main__":
    main()
