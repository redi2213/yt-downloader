#!/usr/bin/env python3
"""Starts the saved default configs (lab/working_configs.txt) as local SOCKS proxies.

One Xray per config on 127.0.0.1:10811, 10812, ... The addresses are written to
/tmp/xray_default_proxies.txt; links.py adds them to the proxy race next to the free
proxies, so whichever answers first wins. Never fails the workflow: on any problem it only
prints a warning. Only "protocol host:port" is printed.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xray_setup as xs  # noqa: E402

BASE = 10811
MAX_RUN = 6


def main():
    path = next((p for p in ("labcfg/lab/working_configs.txt", "lab/working_configs.txt")
                 if os.path.isfile(p)), None)
    if not path:
        print("No default configs saved yet - skipped")
        return 0
    links = [l.strip() for l in open(path, encoding="utf-8")
             if l.strip() and not l.startswith("#")][:MAX_RUN]
    if not links:
        print("Default config list is empty - skipped")
        return 0
    if not xs.install_xray():
        xs.warn("could not download Xray - default configs skipped")
        return 0
    started = []
    for i, l in enumerate(links):
        try:
            ob, host, port = xs.to_outbound(l)
        except Exception as e:
            print(f"  config {i + 1}: skipped ({str(e)[:50]})")
            continue
        p = xs.start(xs.wrap(ob, BASE + i), BASE + i, f"d{i}")
        label = f"{ob['protocol']} {host}:{port}"
        if p is None:
            print(f"  config {i + 1}: {label} did not start")
            continue
        started.append(f"socks5://127.0.0.1:{BASE + i}")
        print(f"  config {i + 1}: {label} -> 127.0.0.1:{BASE + i}")
    if started:
        with open("/tmp/xray_default_proxies.txt", "w") as f:
            f.write("\n".join(started) + "\n")
        print(f"{len(started)} default config(s) ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
