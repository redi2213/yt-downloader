import time
import re
import core_test
from core_test import dispatch_workflow, get_latest_run_id, wait_for_run, get_run_log_text
from multi_test_parallel import process_link, QUALITY_PRESETS
import threading
import history_patch as hp

URL_PATTERN = re.compile(r"https://(www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+")


def get_playlist_links(playlist_url):
    dispatch_workflow("list-playlist.yml", {"playlist_url": playlist_url})
    time.sleep(2)
    run_id = get_latest_run_id("list-playlist.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        print("[FAIL] could not list playlist")
        return []
    log_text = get_run_log_text(run_id)
    links = URL_PATTERN.findall(log_text)
    # findall with groups returns tuples sometimes; re-extract properly
    links = URL_PATTERN.findall(log_text)
    urls = re.findall(r"https://(?:www\.)?youtube\.com/watch\?v=[\w-]+|https://youtu\.be/[\w-]+", log_text)
    return list(dict.fromkeys(urls))  # dedupe, keep order


if __name__ == "__main__":
    core_test.TOKEN = input("GitHub token: ").strip()
    playlist_url = input("Playlist URL: ").strip()

    print("Fetching playlist entries...")
    urls = get_playlist_links(playlist_url)
    print(f"Found {len(urls)} videos:")
    for u in urls:
        print(f"  {u}")

    if not urls:
        exit()

    print("\nChoose default quality for ALL videos:")
    for k, (name, _, _) in QUALITY_PRESETS.items():
        print(f"  {k}) {name}")
    choice = input("Choice: ").strip()
    name, height, hdr = QUALITY_PRESETS.get(choice, QUALITY_PRESETS["3"])
    print(f"Using: {name}\n")

    threads = []
    for i, url in enumerate(urls, 1):
        t = threading.Thread(target=process_link, args=(url, height, hdr, i), daemon=True)
        threads.append(t)
        t.start()
        time.sleep(1.5)

    for t in threads:
        t.join()

    print("\n===== ALL DONE =====")
    hp.print_history()
