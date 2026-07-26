import time
import json
import os
import re
import threading
import queue
import requests

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"
HISTORY_FILE = os.path.expanduser("~/.yt_history_v2.json")

TOKEN = ""
job_queue = queue.Queue()
history_lock = threading.Lock()

QUALITY_PRESETS = {
    "1": ("480p", 480, False),
    "2": ("720p", 720, False),
    "3": ("1080p", 1080, False),
    "4": ("2160p", 2160, False),
    "5": ("Best", 99999, False),
    "6": ("Best HDR", 99999, True),
}


def headers():
    return {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}


def dispatch_workflow(workflow_file, inputs):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    r = requests.post(url, headers=headers(), json={"ref": "dev", "inputs": inputs})
    r.raise_for_status()


def get_latest_run_id(workflow_file):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=1"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    runs = r.json()["workflow_runs"]
    return runs[0]["id"] if runs else None


def get_run_steps(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    jobs = r.json()["jobs"]
    if not jobs:
        return None, []
    job = jobs[0]
    return job["status"], job.get("steps", [])


def wait_for_run_with_steps(run_id, on_step=None):
    url = f"{API_BASE}/actions/runs/{run_id}"
    last_step_name = None
    while True:
        r = requests.get(url, headers=headers())
        r.raise_for_status()
        data = r.json()
        status = data["status"]

        _, steps = get_run_steps(run_id)
        current_step = None
        for s in steps:
            if s["status"] == "in_progress":
                current_step = s["name"]
                break
        if current_step and current_step != last_step_name and on_step:
            on_step(current_step)
            last_step_name = current_step

        if status == "completed":
            return data["conclusion"]
        time.sleep(2)


def get_run_log_text(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    job_id = r.json()["jobs"][0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = requests.get(log_url, headers=headers())
    r.raise_for_status()
    return r.text


def parse_formats(log_text):
    results = []
    for line in log_text.splitlines():
        if "video only" not in line or "storyboard" in line:
            continue
        clean = re.sub(r"^.*Z ", "", line)
        parts = clean.split()
        if not parts:
            continue
        fmt_id = parts[0]
        m = re.search(r"(\d+p\d*)( HDR)?", clean)
        if not m:
            continue
        results.append((fmt_id, m.group(0)))
    return results


def pick_format(formats, target_height, want_hdr):
    candidates = []
    for fmt_id, label in formats:
        is_hdr = "HDR" in label
        digits = "".join(ch for ch in label.split("p")[0] if ch.isdigit())
        if not digits:
            continue
        candidates.append((fmt_id, label, int(digits), is_hdr))
    if not candidates:
        return None
    if want_hdr:
        pool = [c for c in candidates if c[3]] or candidates
    else:
        pool = [c for c in candidates if not c[3]] or candidates
    if target_height >= 99999:
        best = max(pool, key=lambda c: c[2])
    else:
        best = sorted(pool, key=lambda c: abs(c[2] - target_height))[0]
    return best[0], best[1]


def get_release_link(run_id):
    tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for _ in range(10):
        r = requests.get(url, headers=headers())
        if r.status_code == 200:
            assets = r.json().get("assets", [])
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(3)
    return None


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def add_history(entry):
    with history_lock:
        items = load_history()
        items.insert(0, entry)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)


def print_history():
    items = load_history()
    if not items:
        print("(history empty)")
        return
    for i, item in enumerate(items, 1):
        print(f"{i}. [{item['time']}] {item['title']} ({item['quality']})")
        print(f"   LINK: {item['result']}")


def process_job(url, height, hdr):
    tag = f"[{url[-11:]}]"

    def step_report(step_name):
        print(f"{tag} STEP: {step_name}")

    dispatch_workflow("list-formats.yml", {"video_url": url})
    time.sleep(2)
    run_id = get_latest_run_id("list-formats.yml")
    conclusion = wait_for_run_with_steps(run_id, on_step=step_report)
    if conclusion != "success":
        print(f"{tag} FAILED at list-formats")
        return

    log_text = get_run_log_text(run_id)
    formats = parse_formats(log_text)
    picked = pick_format(formats, height, hdr)
    if not picked:
        print(f"{tag} no format matched")
        return
    fmt_id, label = picked
    print(f"{tag} picked {label}")

    dispatch_workflow("download.yml", {"video_url": url, "format_id": fmt_id, "audio_only": "false"})
    time.sleep(2)
    dl_run_id = get_latest_run_id("download.yml")
    conclusion = wait_for_run_with_steps(dl_run_id, on_step=step_report)
    if conclusion != "success":
        print(f"{tag} FAILED at download")
        return

    link = get_release_link(dl_run_id)
    if link:
        title = link.split("/")[-1].rsplit(".", 1)[0]
        add_history({
            "time": time.strftime("%Y-%m-%d %H:%M"),
            "title": title,
            "quality": label,
            "source_url": url,
            "result": link,
        })
        print(f"{tag} DONE -> {link}")


def worker():
    while True:
        job = job_queue.get()
        if job is None:
            break
        url, height, hdr = job
        try:
            process_job(url, height, hdr)
        except Exception as e:
            print(f"[ERROR] {e}")
        job_queue.task_done()


if __name__ == "__main__":
    TOKEN = input("GitHub token: ").strip()

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    print("\nChoose default quality:")
    for k, (name, _, _) in QUALITY_PRESETS.items():
        print(f"  {k}) {name}")
    choice = input("Choice: ").strip()
    name, height, hdr = QUALITY_PRESETS.get(choice, QUALITY_PRESETS["3"])
    print(f"Using: {name}\n")

    print("Paste links quickly, one per line. Empty line = show history. 'quit' = exit.\n")
    while True:
        line = input("> ").strip()
        if line == "quit":
            break
        elif line == "":
            print("\n--- HISTORY ---")
            print_history()
            print("---------------\n")
        else:
            job_queue.put((line, height, hdr))
            print(f"Queued! (queue size: {job_queue.qsize()}) You can paste another link now.\n")

    print("\nWaiting for queue to finish...")
    job_queue.join()
    print("\n=== FINAL HISTORY ===")
    print_history()
