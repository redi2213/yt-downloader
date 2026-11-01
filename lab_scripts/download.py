#!/usr/bin/env python3
"""
After xh_links.json exists:
  pick best m3u8 (prefer CDN playlists without proxy-IP binding),
  download with yt-dlp/ffmpeg like Upload File (test),
  publish GitHub Release.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


def safe_name(title: str, idx: int) -> str:
    t = re.sub(r"[^\w\s\-.]+", "", title or "video")
    t = re.sub(r"\s+", "_", t).strip("._")[:80] or "video"
    return f"{idx:02d}_{t}"


def height_of(link: str, quality: str = "") -> int:
    for s in (quality, link):
        m = re.search(r"(\d{3,4})p", s or "", re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d{3,4})x(\d{3,4})", s or "")
        if m:
            return int(m.group(2))
    return 0


def is_proxy_bound(url: str) -> bool:
    # xhcdn often embeds extractor IP: data=1.2.3.4-dvp
    return bool(re.search(r"data=\d+\.\d+\.\d+\.\d+", url or ""))


def pick_media(item: dict, quality_pref: str) -> tuple[str | None, str]:
    """Return (download_url, kind) kind in m3u8|page."""
    pref = (quality_pref or "best").strip().lower()
    target_h = None
    m = re.search(r"(\d{3,4})", pref)
    if m and pref not in ("best", "max"):
        target_h = int(m.group(1))

    candidates: list[tuple[int, int, str]] = []
    # score: higher better — (not_proxy_bound, height)
    for q in item.get("qualities") or []:
        link = q.get("link") or ""
        if not link:
            continue
        ext = (q.get("ext") or "").lower()
        h = height_of(link, str(q.get("quality") or ""))
        if target_h and h and h > target_h:
            continue
        bound = 0 if is_proxy_bound(link) else 1
        # prefer m3u8 for reliability on Actions
        is_hls = 1 if (ext == "m3u8" or ".m3u8" in link) else 0
        candidates.append((is_hls, bound, h, link))

    m3u8 = item.get("m3u8") or ""
    if m3u8:
        h = height_of(m3u8)
        bound = 0 if is_proxy_bound(m3u8) else 1
        candidates.append((1, bound, h, m3u8))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
        best = candidates[0][3]
        return best, "m3u8" if ".m3u8" in best else "direct"

    # last resort: page URL (yt-dlp extracts again)
    if item.get("url"):
        return item["url"], "page"
    return None, ""


def download_hls(url: str, referer: str, out_base: str, out_dir: Path) -> Path | None:
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    # no proxy for CDN — proxy was causing 30min stalls
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--no-part",
        "--no-mtime",
        "-N",
        "16",
        "--retries",
        "10",
        "--fragment-retries",
        "10",
        "--user-agent",
        UA,
        "--referer",
        referer or url,
        "--remux-video",
        "mp4",
        "-o",
        str(out_dir / f"{out_base}.%(ext)s"),
        url,
    ]
    print("yt-dlp:", " ".join(cmd), flush=True)
    p = subprocess.run(cmd)
    if p.returncode == 0:
        files = sorted(
            out_dir.glob(f"{out_base}.*"),
            key=lambda x: x.stat().st_size,
            reverse=True,
        )
        files = [f for f in files if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".ts"}]
        if files and files[0].stat().st_size > 1000:
            # reject leftover playlist text
            head = files[0].read_bytes()[:16]
            if head.startswith(b"#EXTM3U"):
                print("still a playlist, try ffmpeg")
            else:
                print(f"OK {files[0]} ({files[0].stat().st_size} bytes)")
                return files[0]

    print("yt-dlp failed or empty — ffmpeg fallback", flush=True)
    out_mp4 = out_dir / f"{out_base}.mp4"
    if out_mp4.exists():
        out_mp4.unlink()
    ff = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-y",
        "-user_agent",
        UA,
        "-headers",
        f"Referer: {referer or url}\r\n",
        "-i",
        url,
        "-c",
        "copy",
        str(out_mp4),
    ]
    print("ffmpeg:", " ".join(ff), flush=True)
    p2 = subprocess.run(ff)
    if p2.returncode == 0 and out_mp4.is_file() and out_mp4.stat().st_size > 1000:
        print(f"OK ffmpeg {out_mp4} ({out_mp4.stat().st_size} bytes)")
        return out_mp4
    return None


def main() -> int:
    if os.environ.get("UPLOAD", "true").lower() not in {"1", "true", "yes"}:
        print("UPLOAD disabled")
        return 0

    data_path = Path("xh_links.json")
    if not data_path.is_file():
        print("xh_links.json missing")
        return 1

    results = json.loads(data_path.read_text(encoding="utf-8"))
    quality = os.environ.get("QUALITY", "best")
    out_dir = Path("downloads")
    out_dir.mkdir(exist_ok=True)

    files: list[Path] = []
    notes = ["Lab download (HLS via yt-dlp, Upload-File style)", f"quality={quality}", ""]

    for i, item in enumerate(results, 1):
        page = item.get("url") or ""
        title = item.get("title") or f"video_{i}"
        media, kind = pick_media(item, quality)
        print(f"\n=== [{i}] {title}")
        print(f"page: {page}")
        print(f"pick ({kind}): {media}")
        notes.append(f"- {title}")
        notes.append(f"  page: {page}")
        notes.append(f"  media: {media}")

        if not media:
            print("no media url")
            continue

        base = safe_name(title, i)
        # Prefer direct HLS URL with page as referer (works without proxy for many xhcdn links)
        path = download_hls(media, referer=page or media, out_base=base, out_dir=out_dir)
        if not path and page and kind != "page":
            print("retry via page URL")
            path = download_hls(page, referer=page, out_base=base, out_dir=out_dir)
        if path:
            files.append(path)
        else:
            print("FAILED this item")

    if not files:
        print("All downloads failed")
        return 1

    tag = f"run-{os.environ.get('GITHUB_RUN_ID', 'local')}"   # same tag style as the app's other workflows
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")
    if not token or not repo:
        print("No GH token — files kept in downloads/")
        return 0

    Path("release_notes.md").write_text("\n".join(notes), encoding="utf-8")
    env = os.environ.copy()
    env["GH_TOKEN"] = token
    title = f"Lab: {results[0].get('title') or tag}"[:100]
    subprocess.run(
        ["gh", "release", "delete", tag, "--yes", "--repo", repo],
        env=env,
        capture_output=True,
    )
    cmd = [
        "gh",
        "release",
        "create",
        tag,
        "--repo",
        repo,
        "--prerelease",
        "--title",
        title,
        "--notes-file",
        "release_notes.md",
    ] + [str(f) for f in files]
    print("Creating release", tag, flush=True)
    p = subprocess.run(cmd, env=env, capture_output=True, text=True)
    sys.stdout.write(p.stdout or "")
    sys.stderr.write(p.stderr or "")
    if p.returncode != 0:
        return 1

    release_url = f"https://github.com/{repo}/releases/tag/{tag}"
    print("RELEASE_URL=", release_url)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n## Download & Release\n\n")
            fh.write(f"- **Release:** {release_url}\n")
            for path in files:
                mb = max(1, path.stat().st_size // (1024 * 1024))
                fh.write(f"- `{path.name}` (~{mb} MB)\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
