#!/usr/bin/env python3
"""xHamster leg of the "Any site" workflow.

xh_links.py (the same logic as xh_download.yml in link_downloader: free proxies only for reading the
page, yt-dlp / xhamster_api) writes xh_links.json. This script turns it into exactly what the generic
yt-dlp step of Any-Site-Upload produces, so check / format_id / the site log / the app keep working:
  check mode : formats_<idx>.json + AVAILABLE_HEIGHTS / FORMATS_JSON / FORMATS_SAFE lines + summary
  download   : link.txt (the chosen HLS link), pickmeta.json, step outputs fsel / name / extra
  failure    : reason.txt + ::error:: and exit 1
"""
import json
import os
import re
import sys


def short(msg):
    return (msg or "unknown error")[-300:].replace("\n", " ")


def fail(msg):
    try:
        with open("reason.txt", "w", encoding="utf-8") as fh:
            fh.write(short(msg))
    except Exception:
        pass
    print(f"::error::{short(msg)}")
    sys.exit(1)


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def height_of(link, quality=""):
    base = (link or "").split("?")[0].rsplit("/", 1)[-1]
    for s in (quality, base, link):
        m = re.search(r"(\d{3,4})p", s or "", re.I)
        if m:
            return int(m.group(1))
        m = re.search(r"(\d{3,4})x(\d{3,4})", s or "")
        if m:
            return int(m.group(2))
    return 0


def vcodec_of(link):
    m = re.search(r"\.(av1|h264|h265|hevc|vp9)\.", link or "", re.I)
    return m.group(1).lower() if m else "?"


def is_proxy_bound(url):
    # xhcdn often embeds the extractor IP: data=1.2.3.4-dvp
    return bool(re.search(r"data=\d+\.\d+\.\d+\.\d+", url or ""))


def mb(n):
    return f"{n / 1048576:.0f} MB" if n else "-"


def build_rows(data):
    quals = [q for q in (data.get("qualities") or []) if q.get("link")]
    if not quals and data.get("m3u8"):
        quals = [{"quality": "", "link": data["m3u8"], "ext": "m3u8"}]
    rows, links = [], {}
    for q in quals:
        link = q["link"]
        ext = (q.get("ext") or "").lower()
        hls = ext == "m3u8" or ".m3u8" in link
        h = height_of(link, str(q.get("quality") or ""))
        vc = vcodec_of(link)
        kind = "hls" if hls else (ext or "mp4")
        base = f"{h}p.{vc}.{kind}" if h else f"x.{vc}.{kind}"
        rid, n = base, 2
        while rid in links:
            rid = f"{base}_{n}"
            n += 1
        links[rid] = link
        rows.append({
            "id": rid, "h": h or None, "ext": "mp4" if hls else (ext or "mp4"), "fps": None,
            "vcodec": vc, "acodec": "unknown", "size": None, "tbr": None,
            "proto": "m3u8_native" if hls else "https",
        })
    return rows, links


def main():
    url = os.environ["URL"]
    idx = os.environ.get("IDX", "1")
    q = os.environ.get("QUALITY", "720")
    fid_in = os.environ.get("FORMAT_ID", "").strip()
    check = (q == "check" and not fid_in)
    try:
        target = 0 if q in ("highest", "check") else int(q)
    except ValueError:
        target = 0

    try:
        with open("xh_links.json", encoding="utf-8") as fh:
            results = json.load(fh)
    except Exception as e:
        fail(f"xHamster: the extract step gave no result ({e})")
    data = (results or [{}])[0]
    if data.get("error"):
        fail(f"xHamster: {data['error']}")

    rows, links = build_rows(data)
    if not rows:
        fail("xHamster: no media links found")

    title = data.get("title") or "video"
    meta = {"extractor": "xHamster"}
    with open("pickmeta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    print(f"Title: {title} (method: {data.get('method')}, proxy: {data.get('proxy_used') or 'none'})")

    if check:
        rows.sort(key=lambda r: (r["h"] or 0, r["size"] or 0))
        heights = sorted({r["h"] for r in rows if r["h"]})
        print("AVAILABLE_HEIGHTS: " + (",".join(map(str, heights)) or "none"))
        print(f"{'format_id':<22}{'height':<8}{'ext':<6}{'fps':<5}{'size':<9}{'audio':<7}vcodec")
        for r in rows:
            print(f"{r['id']:<22}{str(r['h'] or '?'):<8}{r['ext']:<6}{str(r['fps'] or '-'):<5}"
                  f"{mb(r['size']):<9}{'yes':<7}{r['vcodec']}")
        payload = {"url": url, "title": title, "heights": heights, "formats": rows}
        with open(f"formats_{idx}.json", "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print("FORMATS_JSON=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        # a secret whose value is "5" would hide every 5: the app turns U+00A4 back into 5
        safe = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace("5", "\u00a4")
        print("FORMATS_SAFE=" + safe)
        summ = os.environ.get("GITHUB_STEP_SUMMARY")
        if summ:
            with open(summ, "a", encoding="utf-8") as fh:
                fh.write(f"### link {idx}: {title}\n\n")
                fh.write("**Heights:** " + (", ".join(f"{h}p" for h in heights) or "none") + "\n\n")
                fh.write("| format_id | height | ext | vcodec |\n|---|---|---|---|\n")
                for r in rows:
                    fh.write(f"| {r['id']} | {r['h'] or '?'} | {r['ext']} | {r['vcodec']} |\n")
                fh.write("\n")
        return

    chosen = None
    if fid_in:
        chosen = next((r for r in rows if r["id"] == fid_in), None)
        if not chosen:
            fail(f"format_id '{fid_in}' not found. Available: " + ", ".join(r["id"] for r in rows))
        print(f"Using the requested format_id: {fid_in}")
    else:
        fmts = [r for r in rows if r["h"]]
        if fmts:
            t = target or max(r["h"] for r in fmts)
            best_h = min({r["h"] for r in fmts}, key=lambda hh: (abs(hh - t), -hh))
            if target and best_h != target:
                print(f"Requested {target}p not available, closest is {best_h}p")
            cands = [r for r in fmts if r["h"] == best_h]
            # like xh_download: HLS first (reliable on Actions), then links not tied to a proxy IP
            cands.sort(key=lambda r: (0 if r["proto"] == "m3u8_native" else 1,
                                      1 if is_proxy_bound(links[r["id"]]) else 0))
            print(f"Candidates at {best_h}p: " + ", ".join(r["id"] for r in cands))
            chosen = cands[0]
        else:
            chosen = rows[0]
            print("No height info, using the first link")

    link = links[chosen["id"]]
    meta["height"] = chosen["h"]
    with open("pickmeta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh)
    print(f"Chosen: {chosen['id']} ({chosen['h'] or '?'}p) -> {link}")
    with open("link.txt", "w", encoding="utf-8") as fh:
        fh.write(link + "\n")

    name = re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("._-")[:120] or "video"
    set_output("fsel", chosen["id"])
    set_output("name", f"{name}.mp4")
    set_output("extra", "")


if __name__ == "__main__":
    main()
