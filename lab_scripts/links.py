#!/usr/bin/env python3
"""xHamster links: xhamster_api first, yt-dlp fallback. Output + Job Summary."""

from __future__ import annotations

import os
import re
import json
import asyncio
import signal
import subprocess
import sys
from urllib.parse import urljoin, urlparse
from typing import Any


def _compat_base_api() -> None:
    try:
        import base_api.base as b

        if not hasattr(b, "setup_logger") and hasattr(b, "get_logger"):
            b.setup_logger = b.get_logger  # type: ignore[attr-defined]
    except Exception:
        pass


_compat_base_api()


LOCAL_XRAY = "socks5://127.0.0.1:10808"


def _is_local_config(proxy: str) -> bool:
    """SOCKS on this machine: a v2ray/Xray config, not a free proxy."""
    p = (proxy or "").strip().lower()
    return p.startswith(("socks5://127.0.0.1:", "socks5://localhost:", "socks5h://127.0.0.1:", "socks5h://localhost:"))


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _config_xray_up() -> bool:
    return os.path.isfile("/tmp/xray_from_config") or (
        os.path.isfile("/tmp/xray.pid") and bool(os.environ.get("V2RAY_CONFIG", "").strip())
    )


def load_proxies() -> list[str]:
    """Free proxies first, local Xray configs last.

    Direct GitHub IP is tried before this list. A saved v2ray config must not
    hide the runner IP or the free list; it is only the last fallback.
    """
    free: list[str] = []
    configs: list[str] = []

    def take(raw: str) -> None:
        if _is_local_config(raw):
            configs.append(raw)
        else:
            free.append(raw)

    one = (os.environ.get("PROXY") or "").strip()
    if one:
        take(one)

    for path in ("working_proxies.txt", "proxies.txt"):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    take(line)

    if os.path.isfile("/tmp/xray_default_proxies.txt"):
        with open("/tmp/xray_default_proxies.txt", encoding="utf-8") as f:
            configs.extend(ln.strip() for ln in f if ln.strip())

    if _config_xray_up():
        configs.append(LOCAL_XRAY)

    free = _dedupe(free)
    configs = [c for c in _dedupe(configs) if c not in set(free)]
    if configs:
        print(f"Order: GitHub IP, then {len(free)} proxy(ies), then {len(configs)} config(s)")
    elif free:
        print(f"Order: GitHub IP, then {len(free)} proxy(ies)")
    else:
        print("Order: GitHub IP only")
    return free + configs


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


def make_client(proxy: str | None = None, module: str = "xhamster_api"):
    apply_proxy_env(proxy)
    _compat_base_api()
    import importlib

    Client = importlib.import_module(module).Client

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


def is_xhamster(url: str) -> bool:
    return bool(re.search(r"xhamster|//(?:[a-z0-9-]+\.)*xh[a-z]{2,10}\d?\.(?:com|desi)/", url or "", re.I))


_PROCS: list = []


def _kill(p) -> None:
    """Kill a yt-dlp process and anything it started."""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def _run_ytdlp(cmd: list[str], timeout: int):
    """subprocess.run replacement whose process can be killed from another thread."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    _PROCS.append(p)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(p)
        p.communicate()
        raise
    finally:
        if p in _PROCS:
            _PROCS.remove(p)
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def _ok(data: dict | None) -> bool:
    return bool(data) and bool(data.get("qualities") or data.get("m3u8")) and not data.get("error")


def race_proxies(url: str, proxies: list[str], workers: int = 4) -> dict | None:
    """yt-dlp through several proxies at once; the first one that finds links wins."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(via_ytdlp, url, p): p for p in proxies}
    last = None
    try:
        for f in as_completed(futs):
            try:
                data = f.result()
            except Exception as e:
                print(f"  [race] {futs[f]}: {type(e).__name__}: {e}")
                continue
            last = data
            if _ok(data):
                print(f"  [race] winner: {futs[f]}")
                return data
            print(f"  [race] {futs[f]}: {data.get('error')}")
    finally:
        for p in list(_PROCS):
            _kill(p)
        ex.shutdown(wait=False, cancel_futures=True)
    return last


def is_beeg(url: str) -> bool:
    return bool(re.search(r"(^|//|\.)beeg\.com(/|$)", url or "", re.I))


async def via_beeg(url: str, proxy: str | None) -> dict:
    """Beeg through unofficial-api-for-beeg: the HLS master + one playlist per height."""
    client = make_client(proxy, "beeg_api")
    video = await client.get_video(url)
    title = getattr(video, "title", None) or "unknown"
    m3u8 = getattr(video, "m3u8_base_url", None)
    result: dict[str, Any] = {
        "url": url,
        "title": title,
        "max_resolution": None,
        "m3u8": m3u8,
        "qualities": [],
        "error": None,
        "proxy_used": proxy,
        "method": "beeg_api",
    }
    if not m3u8:
        result["error"] = "m3u8 not found"
        return result
    try:
        heights = await client.core.list_available_qualities(m3u8)
    except Exception as e:
        print(f"  [beeg_api] quality list failed: {type(e).__name__}: {e}")
        heights = []
    for h in sorted({int(x) for x in heights}, reverse=True):
        try:
            link = await client.core.get_m3u8_by_quality(m3u8, h)
        except Exception as e:
            print(f"  [beeg_api] {h}p skipped: {type(e).__name__}: {e}")
            continue
        result["qualities"].append(
            {"quality": f"{h}p", "resolution": f"{h}p", "link": str(link), "ext": "m3u8"}
        )
    if result["qualities"]:
        result["max_resolution"] = result["qualities"][0]["quality"]
    return result


def _h(q: dict) -> int:
    m = re.search(r"(\d+)", str(q.get("quality") or ""))
    return int(m.group(1)) if m else 0


PEEK_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def is_peekvids(url: str) -> bool:
    return bool(re.search(r"(^|//|\.)peekvids\.com(/|$)", url or "", re.I))


def via_ytdlp(url: str, proxy: str | None) -> dict:
    cmd = ["yt-dlp", "--no-warnings", "--socket-timeout", "15", "-J", "--no-download", url]
    if is_peekvids(url):
        # PeekVids has no own extractor: Generic + HTML5 with a browser UA and the page as referer
        url = url.split("?", 1)[0].split("#", 1)[0]
        cmd = ["yt-dlp", "--no-warnings", "--socket-timeout", "15", "-J", "--no-download",
               "--no-playlist", "--retries", "3", "--ies", "Generic,HTML5",
               "--user-agent", PEEK_UA, "--referer", url, url]
    if proxy:
        cmd[1:1] = ["--proxy", proxy]
    try:
        p = _run_ytdlp(cmd, timeout=90)
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
                    "size": f.get("filesize") or f.get("filesize_approx"),
                    "size_exact": bool(f.get("filesize")),
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


# ---------------------------------------------------------------- site adapters
# A site adapter is a small module written with LINKLAB_SITE_GUIDE.md:
#   SITE_ID = "x"; DOMAINS = ["x.com"]; def extract(url, proxy) -> {"title", "qualities": [...]} or {"error"}
# Registered sites live in lab_scripts/sites/<id>.py and lab_scripts/sites/index.json (added with
# Lab > Add workflow > "Add a tested site to Link Lab"). One under test is registered by
# lab_scripts/site_runner.py. For such a site the adapter is tried first (GitHub IP, then every proxy and
# config, like any other source); when it finds nothing, yt-dlp is the fallback as before.
ADAPTERS: list[Any] = []


def _adapter_id(mod: Any) -> str:
    return str(getattr(mod, "SITE_ID", None) or getattr(mod, "__name__", "site"))


def register_adapter(mod: Any) -> None:
    """Adds (or replaces, same SITE_ID) one adapter module."""
    sid = _adapter_id(mod)
    ADAPTERS[:] = [a for a in ADAPTERS if _adapter_id(a) != sid] + [mod]


def load_adapters(base: str | None = None) -> None:
    """Loads the sites listed in lab_scripts/sites/index.json. An id that is already registered
    (the one under test) is kept as it is."""
    import importlib.util

    here = os.path.dirname(os.path.abspath(__file__))
    base = base or os.path.join(here, "sites")
    try:
        with open(os.path.join(base, "index.json"), encoding="utf-8") as fh:
            entries = (json.load(fh) or {}).get("sites", [])
    except Exception:
        entries = []
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("enabled") is False or not entry.get("file"):
            continue
        sid = str(entry.get("id") or "")
        if any(_adapter_id(a) == sid for a in ADAPTERS):
            continue
        path = os.path.join(base, os.path.basename(str(entry["file"])))
        try:
            spec = importlib.util.spec_from_file_location("linklab_site_" + sid, path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if not callable(getattr(mod, "extract", None)):
                raise RuntimeError("no extract() function")
            register_adapter(mod)
            print(f"Site adapter loaded: {sid}")
        except Exception as e:
            print(f"::warning::site adapter {sid} not loaded: {type(e).__name__}: {e}")


def find_adapter(url: str) -> Any | None:
    if not ADAPTERS:
        return None
    host = (urlparse(url or "").hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for mod in ADAPTERS:
        try:
            matcher = getattr(mod, "matches", None)
            if callable(matcher):
                if matcher(url):
                    return mod
                continue
            for d in getattr(mod, "DOMAINS", None) or []:
                d = str(d).lower().lstrip(".")
                if d.startswith("www."):
                    d = d[4:]
                if host == d or host.endswith("." + d):
                    return mod
        except Exception:
            continue
    return None


def via_adapter(mod: Any, url: str, proxy: str | None) -> dict:
    """Runs adapter.extract(url, proxy) and turns the answer into the same dict as via_api / via_ytdlp."""
    out: dict[str, Any] = {
        "url": url, "title": None, "max_resolution": None, "m3u8": None, "qualities": [],
        "error": None, "proxy_used": proxy, "method": "adapter:" + _adapter_id(mod),
    }
    try:
        res = mod.extract(url, proxy)
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
        return out
    if not isinstance(res, dict):
        out["error"] = "the adapter returned no dict"
        return out
    out["title"] = res.get("title")
    if res.get("error"):
        out["error"] = str(res["error"])[:300]
        return out
    quals: list[dict] = []
    for q in res.get("qualities") or []:
        if not isinstance(q, dict):
            continue
        link = str(q.get("link") or q.get("url") or "")
        if not link.startswith("http"):
            continue
        name = str(q.get("quality") or q.get("resolution") or "")
        if not name and q.get("height"):
            name = f"{int(q['height'])}p"
        quals.append({
            "quality": name or "unknown", "resolution": str(q.get("resolution") or name or ""),
            "link": link, "ext": str(q.get("ext") or ("m3u8" if ".m3u8" in link else "mp4")),
        })
    quals.sort(key=_h, reverse=True)
    out["qualities"] = quals
    out["m3u8"] = res.get("m3u8")
    if quals:
        out["max_resolution"] = quals[0]["quality"]
    elif not out["m3u8"]:
        out["error"] = "the adapter found no quality"
    return out


async def try_one(url: str, proxy: str | None) -> dict:
    adapter = find_adapter(url)
    if adapter is not None:
        label = "adapter:" + _adapter_id(adapter)
        print(f"  [{label}] ...")
        loop = asyncio.get_running_loop()
        data = await loop.run_in_executor(None, via_adapter, adapter, url, proxy)
        if _ok(data):
            return data
        print(f"  [{label}] fail: {data.get('error')}")
    beeg = is_beeg(url)
    if beeg or is_xhamster(url):
        label = "beeg_api" if beeg else "api"
        print(f"  [{label}] ...")
        try:
            data = await (via_beeg(url, proxy) if beeg else via_api(url, proxy))
            if _ok(data):
                return data
            print(f"  [{label}] fail: {data.get('error')}")
        except Exception as e:
            print(f"  [{label}] exception: {type(e).__name__}: {e}")
    print("  [yt-dlp] ...")
    data = via_ytdlp(url, proxy)
    if data.get("error"):
        print(f"  [yt-dlp] fail: {data.get('error')}")
    return data


async def try_with_proxies(url: str, proxies: list[str]) -> dict:
    """GitHub IP, then free proxies, then local Xray configs. Stop at the first success."""
    free = [p for p in proxies if p and not _is_local_config(p)][:10]
    configs = [p for p in proxies if p and _is_local_config(p)]

    print("\n>>> Trying (direct, GitHub IP)")
    data = await try_one(url, None)
    if _ok(data):
        return data
    last: dict = data

    # beeg_api / xhamster_api keep proxy settings on a process-wide client, so one at a time.
    # Other sites can race yt-dlp. Configs stay out of the race and run only if those fail.
    if free and not is_beeg(url) and not is_xhamster(url) and find_adapter(url) is None:
        print(f"\n>>> Racing {len(free)} proxies (the first that works wins)")
        loop = asyncio.get_running_loop()
        raced = await loop.run_in_executor(None, race_proxies, url, free)
        if raced and _ok(raced):
            return raced
        if raced:
            last = raced
    else:
        for proxy in free:
            print(f"\n>>> Trying proxy {proxy}")
            data = await try_one(url, proxy)
            last = data
            if _ok(data):
                return data

    for proxy in configs:
        print(f"\n>>> Trying config {proxy}")
        data = await try_one(url, proxy)
        last = data
        if _ok(data):
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


# ---------------------------------------------------------------- file sizes
def fmt_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.1f} MB"


def size_label(q: dict) -> str:
    n = q.get("size")
    if not n:
        return "Unknown size"
    return ("" if q.get("size_exact") else "~") + fmt_size(int(n))


def _curl(args: list[str], proxy: str | None, timeout: int = 20, head: bool = False) -> str:
    cmd = ["curl", "-sL", "--max-time", str(timeout), "-A", "Mozilla/5.0"]
    if proxy:
        cmd += ["-x", proxy.replace("socks5://", "socks5h://", 1)]
    try:
        p = subprocess.run(cmd + args, capture_output=True, timeout=timeout + 5)
        return p.stdout.decode("utf-8", "replace")
    except Exception:
        return ""


def _range_size(url: str, proxy: str | None) -> int | None:
    """Total size of a file/segment: ask for byte 0 only and read Content-Range."""
    out = _curl(["-o", "/dev/null", "-D", "-", "-r", "0-0", url], proxy, 15)
    blocks = [b for b in re.split(r"\r?\n\r?\n", out) if b.strip().upper().startswith("HTTP/")]
    if not blocks:
        return None
    head = blocks[-1].lower()
    m = re.search(r"content-range:\s*bytes\s+[^/]*/(\d+)", head)
    if m:
        return int(m.group(1))
    status = re.match(r"http/\S+\s+(\d+)", head)
    m = re.search(r"content-length:\s*(\d+)", head)
    if status and status.group(1) == "200" and m:
        return int(m.group(1))
    return None


def _hls_estimate(url: str, proxy: str | None) -> int | None:
    """HLS has no total size: measure a few segments and multiply by the segment count."""
    text = _curl([url], proxy, 20)
    if "#EXTM3U" not in text:
        return None
    if "#EXT-X-STREAM-INF" in text:
        lines = text.splitlines()
        for i, ln in enumerate(lines):
            if ln.startswith("#EXT-X-STREAM-INF"):
                for nxt in lines[i + 1:]:
                    if nxt.strip() and not nxt.startswith("#"):
                        url = urljoin(url, nxt.strip())
                        break
                break
        text = _curl([url], proxy, 20)
        if "#EXTM3U" not in text:
            return None
    segs = [urljoin(url, ln.strip()) for ln in text.splitlines()
            if ln.strip() and not ln.startswith("#")]
    if not segs:
        return None
    n = len(segs)
    idx = sorted({0, n // 3, (2 * n) // 3})
    sizes = [s for s in (_range_size(segs[i], proxy) for i in idx) if s]
    if not sizes:
        return None
    return int(sum(sizes) / len(sizes) * n)


def _probe(q: dict, proxy: str | None) -> None:
    link = str(q.get("link") or "")
    try:
        if q.get("ext") == "m3u8" or ".m3u8" in link:
            n = _hls_estimate(link, proxy)
            if n:
                q["size"], q["size_exact"] = n, False
        elif not q.get("size_exact"):
            n = _range_size(link, proxy)
            if n:
                q["size"], q["size_exact"] = n, True
    except Exception as e:
        print(f"  [size] {q.get('quality')}: {type(e).__name__}: {e}")


def add_sizes(data: dict) -> None:
    """Fill q['size'] / q['size_exact'] for every quality (same proxy that found the links)."""
    from concurrent.futures import ThreadPoolExecutor

    quals = data.get("qualities") or []
    if not quals or data.get("error"):
        return
    proxy = data.get("proxy_used")
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda q: _probe(q, proxy), quals))
    for q in quals:
        print(f"  size {q.get('quality')}: {size_label(q)}")


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
            f"\n  {i}. [{q.get('quality')}] {q.get('resolution')} ({q.get('ext', '')}) {size_label(q)}"
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
    try:
        sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    except Exception:
        pass
    raw = os.environ.get("URL") or os.environ.get("LINKS") or ""
    urls = [x.strip() for x in raw.splitlines() if x.strip()]
    # a link pasted without "https://" is fixed here (xhamster_api needs the full address)
    urls = [u if re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I) else "https://" + u.lstrip("/") for u in urls]
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

    load_adapters()
    proxies = load_proxies()
    print(f"Proxies: {len(proxies)}")
    for p in proxies[:10]:
        print(" ", p)

    try:
        import lab_log  # failure logs: one file per link that could not be read (lab_scripts/lab_log.py)
    except Exception:
        lab_log = None
    log_mode = os.environ.get("LAB_LOG_MODE") or "links"

    results = []
    for i, url in enumerate(urls, 1):
        cap = lab_log.Capture() if lab_log else None
        if cap:
            cap.start()
        try:
            data = await try_with_proxies(url, proxies)
            add_sizes(data)
            print_result(data, index=i if len(urls) > 1 else None)
        except Exception as e:
            if cap:
                cap.stop()
                import traceback
                lab_log.save_failure(log_mode, url, "", "crashed: %s: %s" % (type(e).__name__, e),
                                     cap.text() + "\n" + traceback.format_exc())
            raise
        if cap:
            cap.stop()
        results.append(data)
        if cap and (data.get("error") or not (data.get("qualities") or data.get("m3u8"))):
            lab_log.save_failure(log_mode, url, data.get("title") or "", data.get("error") or "no video link found",
                                 cap.text(), extra={"method": data.get("method"), "proxy": data.get("proxy_used")})

    with open("xh_links.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    txt: list[str] = []
    for item in results:
        txt.append(f"# {item.get('title') or item['url']}")
        txt.append(f"# method: {item.get('method')} proxy: {item.get('proxy_used')}")
        txt.append(f"# page: {item.get('url')}")
        if item.get("error"):
            txt.append(f"# ERROR: {item['error']}")
            txt.append("")
            continue
        if item.get("m3u8"):
            txt.append(str(item["m3u8"]))
        for q in item.get("qualities") or []:
            txt.append(f"# quality: {q.get('quality')} ({q.get('ext', '')}) | size: {size_label(q)}")
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
