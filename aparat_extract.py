import os
import sys
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

API_BASE_URL = "https://www.aparat.com/api/fa/v1"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "https://www.aparat.com/"
}


def get_video(uid, playlist=None):
    q = f"?playlist={playlist}&pr=1&mf=1" if playlist else ""
    r = requests.get(
        f"{API_BASE_URL}/video/video/show/videohash/{uid}{q}",
        headers=headers
    )
    r.raise_for_status()
    j = r.json()

    a = j["data"]["attributes"]

    return [
        {
            "title": a["title"],
            "profile": x["profile"],
            "url": x["urls"][0]
        }
        for x in a["file_link_all"]
    ]


def main():
    parser = argparse.ArgumentParser(description="Extract direct Aparat video links")
    parser.add_argument("--url", required=True, help="Aparat video or playlist link")
    parser.add_argument("--quality", default=None,
                         help="Quality label to select (e.g. 480p). If omitted, available qualities are listed and the script exits.")
    parser.add_argument("--outfile", default="Aparat.txt", help="Output file path")
    args = parser.parse_args()

    url = args.url.strip().rstrip("/")

    if "/playlist/" in url:
        mode = "playlist"
        pid = url.split("/")[-1]
    elif "/v/" in url:
        mode = "video"
        vid = url.split("/")[-1]
    else:
        print("Invalid link", file=sys.stderr)
        sys.exit(1)

    videos = []

    if mode == "video":
        videos.append(get_video(vid))
    else:
        r = requests.get(
            f"{API_BASE_URL}/video/playlist/one/playlist_id/{pid}",
            headers=headers
        )
        r.raise_for_status()
        j = r.json()

        ids = [
            x["attributes"]["uid"]
            for x in j["included"]
            if x["type"] == "Video"
        ]

        with ThreadPoolExecutor(max_workers=10) as ex:
            fs = [ex.submit(get_video, i, pid) for i in ids]
            for f in as_completed(fs):
                videos.append(f.result())

    qualities = sorted(
        {q["profile"] for v in videos for q in v},
        key=lambda x: int(x[:-1])
    )

    if not qualities:
        print("No qualities found (empty video list?)", file=sys.stderr)
        sys.exit(1)

    print("Available qualities:")
    for i, q in enumerate(qualities, 1):
        print(f"{i}) {q}")

    selected = args.quality

    if not selected:
        print("\nNo --quality given. Re-run with one of the qualities above, e.g. --quality " + qualities[-1],
              file=sys.stderr)
        sys.exit(2)

    if selected not in qualities:
        print(f"\nError: quality '{selected}' not available. Choose from: {', '.join(qualities)}", file=sys.stderr)
        sys.exit(1)

    print("Selected:", selected)

    written = 0
    with open(args.outfile, "w", encoding="utf-8") as f:
        for video in videos:
            match = None
            for q in video:
                if q["profile"] == selected:
                    match = q
                    break
            if match:
                f.write(match["url"] + "\n")
                written += 1

    print(f"\nDone. Wrote {written} link(s) to {args.outfile}")


if __name__ == "__main__":
    main()
