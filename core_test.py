import time
import re
import requests

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

TOKEN = ""


def headers():
    return {
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def dispatch_workflow(workflow_file, inputs):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    print(f"[dispatch] POST {url} inputs={inputs}")
    r = requests.post(url, headers=headers(), json={"ref": "main", "inputs": inputs})
    print(f"[dispatch] status={r.status_code} body={r.text[:500]}")
    r.raise_for_status()


def get_latest_run_id(workflow_file):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=1"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    runs = r.json()["workflow_runs"]
    run_id = runs[0]["id"] if runs else None
    print(f"[latest_run] {workflow_file} -> {run_id}")
    return run_id


def wait_for_run(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}"
    while True:
        r = requests.get(url, headers=headers())
        r.raise_for_status()
        data = r.json()
        status = data["status"]
        print(f"[wait] status={status}")
        if status == "completed":
            print(f"[wait] conclusion={data['conclusion']}")
            return data["conclusion"]
        time.sleep(2)


def get_run_log_text(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}/jobs"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    jobs = r.json()["jobs"]
    print(f"[jobs] found {len(jobs)} job(s)")
    job_id = jobs[0]["id"]
    log_url = f"{API_BASE}/actions/jobs/{job_id}/logs"
    r = requests.get(log_url, headers=headers())
    print(f"[log] status={r.status_code} length={len(r.text)}")
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
        label = m.group(0)
        results.append((fmt_id, label))
    return results


def get_release_link(run_id):
    tag = f"run-{run_id}"
    url = f"{API_BASE}/releases/tags/{tag}"
    for i in range(10):
        r = requests.get(url, headers=headers())
        print(f"[release] attempt={i} status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            assets = data.get("assets", [])
            print(f"[release] assets={len(assets)}")
            if assets:
                return assets[0]["browser_download_url"]
        time.sleep(3)
    return None


def test_list_formats(url):
    print("\n===== TEST: list-formats =====")
    dispatch_workflow("list-formats.yml", {"video_url": url})
    time.sleep(2)
    run_id = get_latest_run_id("list-formats.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        print(f"[FAIL] list-formats run did not succeed: {conclusion}")
        return None
    log_text = get_run_log_text(run_id)
    formats = parse_formats(log_text)
    print(f"[RESULT] parsed {len(formats)} formats")
    for fmt_id, label in formats[:10]:
        print(f"   {fmt_id}: {label}")
    return formats


def test_download(url, format_id, audio_only, mode):
    print("\n===== TEST: download =====")
    inputs = {
        "video_url": url,
        "format_id": format_id,
        "audio_only": "true" if audio_only else "false",
    }
    dispatch_workflow("download.yml", inputs)
    time.sleep(2)
    run_id = get_latest_run_id("download.yml")
    conclusion = wait_for_run(run_id)
    if conclusion != "success":
        print(f"[FAIL] download run did not succeed: {conclusion}")
        print("[HINT] fetching log to inspect failure...")
        try:
            log_text = get_run_log_text(run_id)
            print(log_text[-3000:])
        except Exception as e:
            print(f"[ERROR] could not fetch log: {e}")
        return
    if mode == "link":
        link = get_release_link(run_id)
        print(f"[RESULT] link = {link}")
    else:
        print("[RESULT] would download artifact here (skipped in CLI test)")


if __name__ == "__main__":
    TOKEN = input("GitHub token: ").strip()
    globals()["TOKEN"] = TOKEN

    url = input("YouTube link: ").strip()
    formats = test_list_formats(url)

    if formats:
        print("\nPick a format id to test download (or press Enter to test audio-only):")
        choice = input("format id: ").strip()
        if choice:
            test_download(url, choice, audio_only=False, mode="link")
        else:
            test_download(url, "bestaudio", audio_only=True, mode="link")
