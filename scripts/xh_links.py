#!/usr/bin/env python3
"""xHamster links: xhamster_api first, yt-dlp fallback. Output + Job Summary."""

from __future__ import annotations

import os
import re
import json
import asyncio
import subprocess
from typing import Any


def _compat_base_api() -> None:
    try:
        import base_api.base as b

        if not hasattr(b, "setup_logger") and hasattr(b, "get_logger"):
            b.setup_logger = b.get_logger  # type: ignore[attr-defined]
    except Exception:
        pass


_compat_base_api()


def load_proxies() -> list[str]:
    proxies: list[str] = []
    if os.path.isfile("/tmp/xray.pid"):
        proxies.append("socks5://127.0.0.1:10808")
    one = (os.environ.get("PROXY") or "").strip()
    if one:
        proxies.append(one)
    for path in ("working_proxies.txt", "proxies.txt"):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
    seen: set[str] = set()
    out: list[str] = []
    for p in proxies:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def apply_proxy_env(proxy: str | None) -> None:
    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ.pop(k, None)
    if not proxy:
        return
    for k in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        os.environ[k] = proxy


def make_client(proxy: str | None = None):
    apply_proxy_env(proxy)
    _compat_base_api()
    from xhamster_api import Client

    if not proxy:
        return Client()
    try:
        from base_api.modules.config import config as cfg  # type: ignore

        cfg.proxies = {"http": proxy, "https": proxy}
        cfg.trust_env = True
        try:
            cfg.impersonation = os.environ.get("IMPERSONATE", "chrome")
        except Exception:
            pass
        try:
            from base_api import BaseCore  # type: ignore

            return Client(core=BaseCore(config=cfg))
        except Exception:
            return Client()
    except Exception as e:
        print(f"  (base_api config skipped: {type(e).__name__}: {e})")
        return Client()


async def via_api(url: str, proxy: str | None) -> dict:
    client = make_client(proxy)
    video = await client.get_video(url)
    title = getattr(video, "title", None) or "unknown"
    max_res = getattr(video, "max_resolution", None)
    m3u8 = getattr(video, "m3u8_base_url", None) or getattr(video, "m3u8", None)
    result: dict[str, Any] = {
        "url": url,
        "title": title,
        "max_resolution": max_res,
        "m3u8": m3u8,
        "qualities": [],
        "error": None,
        "proxy_used": proxy,
        "method": "xhamster_api",
    }
    if not m3u8:
        result["error"] = "m3u8 not found"
        return result
    for resolution, quality in re.findall(r"(\d+x\d+):(\d+p)", str(m3u8)):
        result["qualities"].append(
            {
                "quality": quality,
                "resolution": resolution,
                "link": str(m3u8).replace("_TPL_", quality),
                "ext": "m3u8",
            }
        )
    return result


def _h(q: dict) -> int:
    m = re.search(r"(\d+)", str(q.get("quality") or ""))
    return int(m.group(1)) if m else 0


def via_ytdlp(url: str, proxy: str | None) -> dict:
    cmd = ["yt-dlp", "--no-warnings", "-J", "--no-download", url]
    if proxy:
        cmd[1:1] = ["--proxy", proxy]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {
            "url": url,
            "title": None,
            "max_resolution": None,
            "m3u8": None,
            "qualities": [],
            "error": f"yt-dlp spawn: {type(e).__name__}: {e}",
            "proxy_used": proxy,
            "method": "yt-dlp",
        }
    if p.returncode != 0:
        err = (p.stderr or p.stdout or "yt-dlp failed").strip().splitlines()[-1:]
        return {
            "url": url,
            "title": None,
            "max_resolution": None,
            "m3u8": None,
            "qualities": [],
            "error": f"yt-dlp: {err[0] if err else 'failed'}",
            "proxy_used": proxy,
            "method": "yt-dlp",
        }
    try:
        info = json.loads(p.stdout)
    except json.JSONDecodeError:
        return {
            "url": url,
            "title": None,
            "max_resolution": None,
            "m3u8": None,
            "qualities": [],
            "error": "yt-dlp: invalid JSON",
            "proxy_used": proxy,
            "method": "yt-dlp",
        }

    title = info.get("title") or "unknown"
    qualities = []
    m3u8 = None
    for f in info.get("formats") or []:
        u = f.get("url") or ""
        if not u:
            continue
        ext = (f.get("ext") or "").lower()
        h = f.get("height")
        proto = (f.get("protocol") or "").lower()
        note = f.get("format_note") or f.get("format_id") or ""
        if "m3u8" in proto or ".m3u8" in u:
            if not m3u8:
                m3u8 = u
            label = f"{h}p" if h else str(note or "hls")
            qualities.append(
                {
                    "quality": label,
                    "resolution": f"{f.get('width')}x{h}" if h else label,
                    "link": u,
                    "ext": "m3u8",
                }
            )
        elif ext in ("mp4", "webm") and h:
            qualities.append(
                {
                    "quality": f"{h}p",
                    "resolution": f"{f.get('width')}x{h}",
                    "link": u,
                    "ext": ext,
                }
            )

    seen_q: set[str] = set()
    uniq = []
    for q in sorted(qualities, key=_h, reverse=True):
        k = f"{q['quality']}|{q.get('ext')}"
        if k in seen_q:
            continue
        seen_q.add(k)
        uniq.append(q)

    err = None if uniq or m3u8 else "yt-dlp: no media urls"
    return {
        "url": url,
        "title": title,
        "max_resolution": uniq[0]["quality"] if uniq else None,
        "m3u8": m3u8,
        "qualities": uniq,
        "error": err,
        "proxy_used": proxy,
        "method": "yt-dlp",
    }


async def try_one(url: str, proxy: str | None) -> dict:
    print("  [api] ...")
    try:
        data = await via_api(url, proxy)
        if (data.get("m3u8") or data.get("qualities")) and not data.get("error"):
            return data
        print(f"  [api] fail: {data.get('error')}")
    except Exception as e:
        print(f"  [api] exception: {type(e).__name__}: {e}")
    print("  [yt-dlp] ...")
    data = via_ytdlp(url, proxy)
    if data.get("error"):
        print(f"  [yt-dlp] fail: {data.get('error')}")
    return data


async def try_with_proxies(url: str, proxies: list[str]) -> dict:
    chain: list[str | None] = list(proxies) if proxies else [None]
    last: dict | None = None
    for proxy in chain:
        print(f"\n>>> Trying {proxy or '(direct)'}")
        data = await try_one(url, proxy)
        last = data
        if (data.get("qualities") or data.get("m3u8")) and not data.get("error"):
            return data
    return last or {
        "url": url,
        "title": None,
        "max_resolution": None,
        "m3u8": None,
        "qualities": [],
        "error": "all methods/proxies failed",
        "proxy_used": None,
        "method": None,
    }


def print_result(data: dict, index: int | None = None) -> None:
    prefix = f"[{index}] " if index is not None else ""
    print("=" * 55)
    print(f"{prefix}{data.get('title') or 'unknown'}")
    print("=" * 55)
    print(f"URL    : {data['url']}")
    print(f"Method : {data.get('method')}")
    if data.get("proxy_used"):
        print(f"Proxy  : {data['proxy_used']}")
    if data.get("error"):
        print(f"ERROR  : {data['error']}")
        return
    if data.get("m3u8"):
        print(f"\nMaster/HLS:\n{data['m3u8']}")
    for i, q in enumerate(data.get("qualities") or [], 1):
        print(
            f"\n  {i}. [{q.get('quality')}] {q.get('resolution')} ({q.get('ext', '')})"
        )
        print(f"     {q['link']}")
    print("=" * 55)


def write_summary(results: list[dict]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines: list[str] = ["# XHamster Links", ""]
    ok = 0
    all_links: list[str] = []
    for i, item in enumerate(results, 1):
        lines.append(f"## {i}. {item.get('title') or '(no title)'}")
        lines.append(f"- URL: `{item.get('url')}`")
        lines.append(f"- Method: `{item.get('method')}`")
        if item.get("proxy_used"):
            lines.append(f"- Proxy: `{item['proxy_used']}`")
        if item.get("error"):
            lines.append(f"- **ERROR:** `{item['error']}`")
            lines.append("")
            continue
        ok += 1
        if item.get("m3u8"):
            lines.append("- HLS:")
            lines.append("```")
            lines.append(str(item["m3u8"]))
            lines.append("```")
            all_links.append("# HLS")
            all_links.append(str(item["m3u8"]))
        for q in item.get("qualities") or []:
            lines.append(f"- **{q.get('quality')}** ({q.get('ext', '')})")
            lines.append("```")
            lines.append(q["link"])
            lines.append("```")
            all_links.append(f"# {q.get('quality')} ({q.get('ext', '')})")
            all_links.append(q["link"])
        lines.append("")
    lines.append("---")
    lines.append(f"**Success:** {ok}/{len(results)}")
    lines.append("")
    lines.append("### All links (select box to copy)")
    lines.append("```")
    lines.extend(all_links if all_links else ["(no links)"])
    lines.append("```")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


async def main() -> None:
    raw = os.environ.get("URL") or os.environ.get("LINKS") or ""
    urls = [x.strip() for x in raw.splitlines() if x.strip()]
    if not urls:
        try:
            u = input("\nVideo URL:\n> ").strip()
            if u:
                urls = [u]
        except EOFError:
            pass
    if not urls:
        print("No URL")
        return

    proxies = load_proxies()
    print(f"Proxies: {len(proxies)}")
    for p in proxies[:10]:
        print(" ", p)

    results = []
    for i, url in enumerate(urls, 1):
        data = await try_with_proxies(url, proxies)
        print_result(data, index=i if len(urls) > 1 else None)
        results.append(data)

    with open("xh_links.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    txt: list[str] = []
    for item in results:
        txt.append(f"# {item.get('title') or item['url']}")
        txt.append(f"# method: {item.get('method')} proxy: {item.get('proxy_used')}")
        if item.get("error"):
            txt.append(f"# ERROR: {item['error']}")
            txt.append("")
            continue
        if item.get("m3u8"):
            txt.append(str(item["m3u8"]))
        for q in item.get("qualities") or []:
            txt.append(q["link"])
        txt.append("")
    text = "\n".join(txt) + "\n"
    with open("xh_links.txt", "w", encoding="utf-8") as f:
        f.write(text)

    write_summary(results)
    print("\n" + "#" * 60)
    print(text)


if __name__ == "__main__":
    asyncio.run(main())
