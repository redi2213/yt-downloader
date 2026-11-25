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

TARGET_H: int | None = None  # max height from QUALITY (set in main); used by yt-dlp -S res:N


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


def _clean_partial(out_dir: Path, out_base: str) -> None:
    """Remove leftovers of a failed try (with --no-part a half file looks like a finished one)."""
    for f in out_dir.glob(f"{out_base}.*"):
        try:
            f.unlink()
        except OSError:
            pass


def download_hls(url: str, referer: str, out_base: str, out_dir: Path, proxy: str | None = None) -> Path | None:
    _clean_partial(out_dir, out_base)
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    # Default: no proxy for the CDN (a proxy can make it very slow). The proxy is only used
    # by the last-chance retry below, with the proxy that found the links.
    cmd = [
        "yt-dlp",
        "--socket-timeout",
        "30",
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
    if TARGET_H:
        # page-URL / HLS retries must keep the quality the user chose (not the best one)
        cmd[1:1] = ["-S", f"res:{TARGET_H}"]
    if "peekvids.com" in (url or ""):
        cmd[1:1] = ["--ies", "Generic,HTML5"]
    if proxy:
        cmd[1:1] = ["--proxy", proxy]
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

    if proxy:
        # ffmpeg cannot use socks proxies, so with a proxy only yt-dlp is tried
        return None
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


HERE = Path(__file__).resolve().parent
MAX_FALLBACK_ROUTES = 8


def _norm_proxy(line: str) -> str:
    line = (line or "").strip()
    if not line or line.startswith("#"):
        return ""
    return line if "://" in line else "http://" + line


def collect_proxies() -> list[str]:
    """Proxy list: the one typed in the app first, then the saved working list."""
    out: list[str] = []
    texts = [os.environ.get("PROXY_IN", "")]
    for p in ("labcfg/lab/working_proxies.txt", "working_proxies.txt"):
        try:
            texts.append(Path(p).read_text(encoding="utf-8"))
        except OSError:
            pass
    for t in texts:
        for ln in t.replace(",", "\n").splitlines():
            p = _norm_proxy(ln)
            if p and p not in out:
                out.append(p)
    return out[:MAX_FALLBACK_ROUTES]


def _run_helper(name: str) -> None:
    try:
        subprocess.run([sys.executable, str(HERE / name)], check=False, timeout=240)
    except Exception as e:  # never fail the workflow because of a helper
        print(f"{name} failed: {type(e).__name__}", flush=True)


def xray_proxies() -> list[str]:
    """Local SOCKS proxies from the v2ray config, else from the saved default configs."""
    out: list[str] = []
    if not os.path.isfile("/tmp/xray_from_config") and os.environ.get("V2RAY_CONFIG", "").strip():
        _run_helper("xray_setup.py")
    if os.path.isfile("/tmp/xray_from_config"):
        out.append("socks5://127.0.0.1:10808")
    if not out:
        if not os.path.isfile("/tmp/xray_default_proxies.txt"):
            _run_helper("xray_default.py")
        try:
            for ln in Path("/tmp/xray_default_proxies.txt").read_text().splitlines():
                if ln.strip():
                    out.append(ln.strip())
        except OSError:
            pass
    return out[:MAX_FALLBACK_ROUTES]


def upgrade_ytdlp_nightly() -> bool:
    print("last chance: installing yt-dlp nightly", flush=True)
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "--pre", "yt-dlp[default]"])
    subprocess.run(["yt-dlp", "--version"])
    return r.returncode == 0


def fallback_routes(page: str, base: str, out_dir: Path, skip: set) -> tuple[Path | None, str]:
    """Order: 1) proxy list  2) v2ray/default configs  3) yt-dlp nightly (then all again)."""
    proxies = [p for p in collect_proxies() if p not in skip]
    for p in proxies:
        print(f"retry via proxy {p}", flush=True)
        path = download_hls(page, referer=page, out_base=base, out_dir=out_dir, proxy=p)
        if path:
            return path, f"proxy {p}"
    xs = [p for p in xray_proxies() if p not in skip]
    for p in xs:
        print(f"retry via config {p}", flush=True)
        path = download_hls(page, referer=page, out_base=base, out_dir=out_dir, proxy=p)
        if path:
            return path, f"config {p}"
    if upgrade_ytdlp_nightly():
        for p in [None] + proxies + xs:
            print(f"nightly retry via {p or 'GitHub IP (no proxy)'}", flush=True)
            path = download_hls(page, referer=page, out_base=base, out_dir=out_dir, proxy=p)
            if path:
                return path, f"nightly + {p or 'GitHub IP (no proxy)'}"
    return None, ""


def main() -> int:
    global TARGET_H
    if os.environ.get("UPLOAD", "true").lower() not in {"1", "true", "yes"}:
        print("UPLOAD disabled")
        return 0

    data_path = Path("xh_links.json")
    if not data_path.is_file():
        print("xh_links.json missing")
        return 1

    results = json.loads(data_path.read_text(encoding="utf-8"))

    try:
        import lab_log  # failure logs: one file per link that failed (lab_scripts/lab_log.py)
        _cap = lab_log.Capture()
        _cap.start()
    except Exception:
        lab_log, _cap = None, None

    def _save_fail(item, page, title, why):
        # a link whose extract step already failed was logged by links.py: no second file
        if lab_log is None or item.get("error"):
            return
        lab_log.save_failure(os.environ.get("LAB_LOG_MODE") or "download", page, title, why,
                             _cap.since_mark() if _cap else "", extra={"quality": quality})
    quality = os.environ.get("QUALITY", "best")
    _qm = re.search(r"(\d{3,4})", quality or "")
    if _qm and (quality or "").strip().lower() not in ("best", "max"):
        TARGET_H = int(_qm.group(1))
    out_dir = Path("downloads")
    out_dir.mkdir(exist_ok=True)

    files: list[Path] = []
    notes = ["Lab download (HLS via yt-dlp, Upload-File style)", f"quality={quality}", ""]

    for i, item in enumerate(results, 1):
        if _cap:
            _cap.mark()
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
            _save_fail(item, page, title, "no media url found for the chosen quality")
            continue

        base = safe_name(title, i)
        # Prefer direct HLS URL with page as referer (works without proxy for many xhcdn links)
        path = download_hls(media, referer=page or media, out_base=base, out_dir=out_dir)
        if not path and page and kind != "page":
            print("retry via page URL")
            path = download_hls(page, referer=page, out_base=base, out_dir=out_dir)
        route = "GitHub IP (no proxy)"
        used_proxy = (item.get("proxy_used") or "").strip()
        if not path and used_proxy:
            print(f"GitHub IP could not download - retrying through the proxy that found the links: {used_proxy}", flush=True)
            path = download_hls(media, referer=page or media, out_base=base, out_dir=out_dir, proxy=used_proxy)
            if not path and page and kind != "page":
                path = download_hls(page, referer=page, out_base=base, out_dir=out_dir, proxy=used_proxy)
            route = f"proxy {used_proxy}"
        if not path and page:
            path, route2 = fallback_routes(page, base, out_dir, {used_proxy})
            if path:
                route = route2
        if path:
            files.append(path)
            notes.append(f"  route: {route}")
            print(f"Downloaded through: {route}", flush=True)
        else:
            print("FAILED this item")
            _save_fail(item, page, title, "download failed on every route")

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
