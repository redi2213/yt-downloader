import time
import threading
import history_patch as hp
from core_test import (
    dispatch_workflow, get_latest_run_id, wait_for_run,
    get_run_log_text, parse_formats, get_release_link
)
import core_test

QUALITY_PRESETS = {
    "1": ("480p", 480, False),
    "2": ("720p", 720, False),
    "3": ("1080p", 1080, False),
    "4": ("2160p", 2160, False),
    "5": ("Best", 99999, False),
    "6": ("Best HDR", 99999, True),
}

history_lock = threading.Lock()


def pick_format(formats, target_height, want_hdr):
    candidates = []
    for fmt_id, label in formats:
        is_hdr = "HDR" in label
        digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
        if not digits:
            continue
        height = int(digits)
        candidates.append((fmt_id, label, height, is_hdr))

    if not candidates:
        return None

    if want_hdr:
        hdr_candidates = [c for c in candidates if c[3]]
        pool = hdr_candidates if hdr_candidates else candidates
    else:
        pool = [c for c in candidates if not c[3]] or candidates

    if target_height >= 99999:
        best = max(pool, key=lambda c: c[2])
        return best[0], best[1]

    pool_sorted = sorted(pool, key=lambda c: abs(c[2] - target_height))
    best = pool_sorted[0]
    return best[0], best[1]


def process_link(url, target_height, want_hdr, index):
    tag = f"[link {index}]"
    print(f"{tag} dispatching list-formats for {url}")
    dispatch_workflow("list-formats.yml", {"video_url": url})
    time.sleep(2)
    run_id = get_latest_run_id("list-formats.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        print(f"{tag} FAIL: could not list formats")
        return
    log_text = get_run_log_text(run_id)
    formats = parse_formats(log_text)
    if not formats:
        print(f"{tag} FAIL: no formats found")
        return

    picked = pick_format(formats, target_height, want_hdr)
    if not picked:
        print(f"{tag} FAIL: could not pick a format")
        return
    fmt_id, label = picked
    print(f"{tag} picked {label} (id={fmt_id}), dispatching download")

    dispatch_workflow("download.yml", {
        "video_url": url, "format_id": fmt_id, "audio_only": "false"
    })
    time.sleep(2)
    dl_run_id = get_latest_run_id("download.yml")
    conclusion = wait_for_run(dl_run_id)
    if conclusion != "success":
        print(f"{tag} FAIL: download failed")
        return

    link = get_release_link(dl_run_id)
    print(f"{tag} DONE: {link}")
    if link:
        with history_lock:
            hp.add_history_entry({
                "time": time.strftime("%Y-%m-%d %H:%M"),
                "title": hp.title_from_link(link),
                "quality": label,
                "mode": "link",
                "source_url": url,
                "result": link,
            })


if __name__ == "__main__":
    core_test.TOKEN = input("GitHub token: ").strip()

    print("Paste YouTube links, one per line. Empty line to finish:")
    links = []
    while True:
        line = input().strip()
        if not line:
            break
        links.append(line)

    print("\nChoose default quality for ALL links:")
    for k, (name, _, _) in QUALITY_PRESETS.items():
        print(f"  {k}) {name}")
    choice = input("Choice: ").strip()
    name, height, hdr = QUALITY_PRESETS.get(choice, QUALITY_PRESETS["3"])
    print(f"Using: {name}\n")

    threads = []
    for i, url in enumerate(links, 1):
        t = threading.Thread(target=process_link, args=(url, height, hdr, i), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(0.5)

    for t in threads:
        t.join()

    print("\n===== ALL DONE =====")
    hp.print_history()
