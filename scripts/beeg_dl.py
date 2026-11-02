"""Lab test: download ONE beeg.com video with unofficial-api-for-beeg (module beeg_api).

Env: BEEG_URL, BEEG_QUALITY (best / half / worst), BEEG_PROXY (optional), BEEG_OUT (default out)
Result: the video file(s) in the out folder; exit code 1 when nothing was downloaded.
"""
import asyncio
import os
import re
import sys
import traceback
from importlib import metadata
from pathlib import Path

URL = os.environ.get("BEEG_URL", "").strip()
QUALITY = (os.environ.get("BEEG_QUALITY", "best").strip() or "best")
PROXY = os.environ.get("BEEG_PROXY", "").strip()
OUT = Path(os.environ.get("BEEG_OUT", "out")).resolve()

VIDEO_EXT = {".mp4", ".mkv", ".ts", ".webm", ".m4v", ".mov"}


def fail(message):
    print("::error::" + message)
    sys.exit(1)


def clean_name(name):
    # GitHub Release asset names reject 4-byte unicode (emoji) - strip them
    name = re.sub(r"[\U00010000-\U0010FFFF]", "", name)
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", name)
    return re.sub(r"\s+", " ", name).strip(" .") or "beeg-video"


def collect_files():
    return sorted(p for p in OUT.rglob("*") if p.is_file())


async def run():
    from beeg_api import Client, DownloadConfigHLS

    client = Client()
    video = await client.get_video(URL)
    print("Title:   ", getattr(video, "title", "?"))
    print("Duration:", getattr(video, "duration", "?"))

    OUT.mkdir(parents=True, exist_ok=True)
    config = DownloadConfigHLS(quality=QUALITY, path=str(OUT) + os.sep)
    print(f"Downloading, quality={QUALITY} ...")
    await video.download(config)


def main():
    if not re.match(r"^https?://([a-z0-9-]+\.)*beeg\.com/", URL, re.I):
        fail("The link must be a beeg.com video link (https://beeg.com/...)")

    for pkg in ("unofficial-api-for-beeg", "eaf-base-api", "curl-cffi"):
        try:
            print(f"{pkg} {metadata.version(pkg)}")
        except Exception:
            print(f"{pkg} (version unknown)")

    if PROXY:
        for key in ("ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "all_proxy", "https_proxy", "http_proxy"):
            os.environ[key] = PROXY
        print("A proxy is set (from the proxy box).")

    try:
        asyncio.run(run())
    except Exception:
        traceback.print_exc()
        files = collect_files() if OUT.exists() else []
        if not files:
            fail("beeg_api failed (see the traceback above). If it says blocked / 403, try the proxy box.")
        print("An error happened, but files exist - continuing with them.")

    files = collect_files()
    renamed = []
    for p in files:
        new = p.with_name(clean_name(p.stem) + p.suffix.lower())
        if new != p:
            p.rename(new)
            p = new
        renamed.append(p)

    videos = [p for p in renamed if p.suffix.lower() in VIDEO_EXT]
    if not videos:
        print("Files in out:", [str(p) for p in renamed])
        fail("No video file was produced.")
    for p in videos:
        print(f"OK  {p.name}  {p.stat().st_size / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
