import time
import threading
import queue
import history_patch as hp
import core_test
from core_test import dispatch_workflow, get_latest_run_id, wait_for_run, get_release_link
from multi_test_parallel import pick_format, QUALITY_PRESETS
from core_test import get_run_log_text, parse_formats

job_queue = queue.Queue()
history_lock = threading.Lock()
running = True


def worker():
    while running:
        try:
            job = job_queue.get(timeout=1)
        except queue.Empty:
            continue

        url, target_height, want_hdr = job
        print(f"\n[QUEUE] Now processing: {url}")
        try:
            handle_job(url, target_height, want_hdr)
        except Exception as e:
            print(f"[QUEUE] ERROR processing {url}: {e}")
        job_queue.task_done()


def handle_job(url, target_height, want_hdr):
    dispatch_workflow("list-formats.yml", {"video_url": url})
    time.sleep(2)
    run_id = get_latest_run_id("list-formats.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        print(f"[QUEUE] FAIL: could not list formats for {url}")
        return

    log_text = get_run_log_text(run_id)
    formats = parse_formats(log_text)
    if not formats:
        print(f"[QUEUE] FAIL: no formats for {url}")
        return

    picked = pick_format(formats, target_height, want_hdr)
    if not picked:
        print(f"[QUEUE] FAIL: could not pick format for {url}")
        return
    fmt_id, label = picked
    print(f"[QUEUE] picked {label} for {url}")

    dispatch_workflow("download.yml", {
        "video_url": url, "format_id": fmt_id, "audio_only": "false"
    })
    time.sleep(2)
    dl_run_id = get_latest_run_id("download.yml")
    conclusion = wait_for_run(dl_run_id)
    if conclusion != "success":
        print(f"[QUEUE] FAIL: download failed for {url}")
        return

    link = get_release_link(dl_run_id)
    print(f"[QUEUE] DONE: {link}")
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
        print(f"[NOTIFY] Download ready: {hp.title_from_link(link)}")


def add_to_queue(url, target_height, want_hdr):
    job_queue.put((url, target_height, want_hdr))
    print(f"[QUEUE] Added to queue: {url} (queue size now: {job_queue.qsize()})")


if __name__ == "__main__":
    core_test.TOKEN = input("GitHub token: ").strip()

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    print("\nSimulating the app: you can add links one at a time.")
    print("The download happens in the BACKGROUND — you get control back immediately.")
    print("Type 'history' to see progress, 'quit' to stop.\n")

    print("Choose default quality for links you add:")
    for k, (name, _, _) in QUALITY_PRESETS.items():
        print(f"  {k}) {name}")
    choice = input("Choice: ").strip()
    name, height, hdr = QUALITY_PRESETS.get(choice, QUALITY_PRESETS["3"])
    print(f"Using: {name}\n")

    while True:
        line = input("Paste a link (or 'history'/'quit'): ").strip()
        if line == "quit":
            break
        elif line == "history":
            hp.print_history()
        elif line:
            add_to_queue(line, height, hdr)
            print("[APP] Back to home screen — you can add another link now!\n")

    print("\nWaiting for remaining queue items to finish...")
    job_queue.join()
    running = False
    print("\n===== FINAL HISTORY =====")
    hp.print_history()
