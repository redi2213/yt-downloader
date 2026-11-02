#!/usr/bin/env python3
"""
Find working free public proxies from open lists.
Outputs:
  working_proxies.txt   one proxy URL per line (socks5://ip:port or http://ip:port)
  working_proxies.json  details
"""

import os
import re
import json
import time
import concurrent.futures
from urllib.request import urlopen, Request, build_opener, ProxyHandler
from urllib.error import URLError, HTTPError

SOURCES = [
    ("socks5", "https://raw.githubusercontent.com/proxio-io/proxy-list/main/socks5.txt"),
    ("socks5", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"),
    ("http", "https://raw.githubusercontent.com/proxio-io/proxy-list/main/http.txt"),
    ("http", "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"),
]

# How many candidates to try (keeps Actions under time limit)
MAX_CANDIDATES = int(os.environ.get("MAX_CANDIDATES", "80"))
MAX_WORKERS = int(os.environ.get("MAX_WORKERS", "20"))
TIMEOUT = float(os.environ.get("PROXY_TIMEOUT", "8"))
NEEDED = int(os.environ.get("NEEDED", "5"))  # stop early when we have enough

TEST_URL = os.environ.get("TEST_URL", "https://httpbin.org/ip")
# Optional second check against target site (may still fail on free DCs)
XH_CHECK = os.environ.get("XH_CHECK", "0") == "1"
XH_URL = "https://xhamster.com/"


def fetch_text(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="ignore")


def parse_lines(text: str, proto: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # ip:port
        m = re.match(r"^(\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})$", line)
        if not m:
            continue
        ip, port = m.group(1), m.group(2)
        if proto == "socks5":
            out.append(f"socks5://{ip}:{port}")
        else:
            out.append(f"http://{ip}:{port}")
    return out


def test_proxy(proxy_url: str) -> dict | None:
    """Return dict if proxy can reach TEST_URL, else None."""
    try:
        # urllib ProxyHandler only supports http/https proxies natively.
        # For socks5 we skip urllib and mark protocol; actual socks needs PySocks.
        if proxy_url.startswith("socks5://"):
            return test_socks5(proxy_url)
        opener = build_opener(ProxyHandler({"http": proxy_url, "https": proxy_url}))
        req = Request(TEST_URL, headers={"User-Agent": "Mozilla/5.0"})
        t0 = time.time()
        with opener.open(req, timeout=TIMEOUT) as r:
            body = r.read(500).decode("utf-8", errors="ignore")
        ms = int((time.time() - t0) * 1000)
        if r.status and r.status >= 400:
            return None
        result = {"proxy": proxy_url, "latency_ms": ms, "ok": True, "body_snip": body[:80]}
        if XH_CHECK:
            try:
                req2 = Request(XH_URL, headers={"User-Agent": "Mozilla/5.0"})
                with opener.open(req2, timeout=TIMEOUT) as r2:
                    html = r2.read(2000).decode("utf-8", errors="ignore").lower()
                result["xh_ok"] = ("xhamster" in html) or ("video" in html) or r2.status == 200
            except Exception:
                result["xh_ok"] = False
        return result
    except Exception:
        return None


def test_socks5(proxy_url: str) -> dict | None:
    """Test SOCKS5 using PySocks if available."""
    try:
        import socks  # noqa: F401
        import socket
        from urllib.parse import urlparse

        u = urlparse(proxy_url)
        host, port = u.hostname, u.port

        # quick TCP connect via socks
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, host, port)
        s.settimeout(TIMEOUT)
        t0 = time.time()
        # resolve httpbin through proxy by connecting to 1.1.1.1:443 as reachability probe
        # Better: use requests with socks
        try:
            import requests
            t0 = time.time()
            r = requests.get(
                TEST_URL,
                proxies={"http": proxy_url, "https": proxy_url},
                timeout=TIMEOUT,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            ms = int((time.time() - t0) * 1000)
            if r.status_code >= 400:
                return None
            result = {"proxy": proxy_url, "latency_ms": ms, "ok": True, "body_snip": r.text[:80]}
            if XH_CHECK:
                try:
                    r2 = requests.get(
                        XH_URL,
                        proxies={"http": proxy_url, "https": proxy_url},
                        timeout=TIMEOUT,
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    html = r2.text[:3000].lower()
                    result["xh_ok"] = ("xhamster" in html) or r2.status_code == 200
                except Exception:
                    result["xh_ok"] = False
            return result
        finally:
            try:
                s.close()
            except Exception:
                pass
    except Exception:
        return None


def main():
    print("Downloading free proxy lists...")
    candidates = []
    seen = set()
    for proto, url in SOURCES:
        try:
            text = fetch_text(url)
            items = parse_lines(text, proto)
            print(f"  {url} -> {len(items)} {proto}")
            for p in items:
                if p not in seen:
                    seen.add(p)
                    candidates.append(p)
        except Exception as e:
            print(f"  FAIL {url}: {e}")

    # Prefer socks5 first, then http
    candidates.sort(key=lambda x: (0 if x.startswith("socks5") else 1, x))
    candidates = candidates[:MAX_CANDIDATES]
    print(f"\nTesting {len(candidates)} candidates (timeout={TIMEOUT}s, workers={MAX_WORKERS})...")

    working = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(test_proxy, p): p for p in candidates}
        for fut in concurrent.futures.as_completed(futs):
            res = fut.result()
            if res and res.get("ok"):
                working.append(res)
                tag = ""
                if "xh_ok" in res:
                    tag = " XH=OK" if res["xh_ok"] else " XH=NO"
                print(f"  OK  {res['proxy']}  {res['latency_ms']}ms{tag}")
                if len(working) >= NEEDED:
                    # cancel remaining
                    for f in futs:
                        f.cancel()
                    break

    working.sort(key=lambda x: x.get("latency_ms", 99999))

    with open("working_proxies.txt", "w", encoding="utf-8") as f:
        for w in working:
            f.write(w["proxy"] + "\n")

    with open("working_proxies.json", "w", encoding="utf-8") as f:
        json.dump(working, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 50)
    print(f"Found {len(working)} working proxy(ies)")
    if not working:
        print("None alive. Free lists are flaky — re-run later or use Termux without proxy.")
    else:
        print("Top:")
        for w in working[:10]:
            print(f"  {w['proxy']}  ({w['latency_ms']}ms)")
    print("Saved: working_proxies.txt / working_proxies.json")


if __name__ == "__main__":
    main()
