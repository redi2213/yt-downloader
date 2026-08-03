import time
import re
import requests

REPO_OWNER = "redi2213"
REPO_NAME = "yt-downloader"
API_BASE = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}"

TOKEN = ""


def headers():
    return {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github+json"}


def dispatch_workflow(workflow_file, inputs, ref="v1.3"):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/dispatches"
    r = requests.post(url, headers=headers(), json={"ref": ref, "inputs": inputs})
    print(f"[dispatch] status={r.status_code} {r.text[:200]}")
    r.raise_for_status()


def get_latest_run_id(workflow_file):
    url = f"{API_BASE}/actions/workflows/{workflow_file}/runs?per_page=1"
    r = requests.get(url, headers=headers())
    r.raise_for_status()
    runs = r.json()["workflow_runs"]
    return runs[0]["id"] if runs else None


def wait_for_run(run_id):
    url = f"{API_BASE}/actions/runs/{run_id}"
    while True:
        r = requests.get(url, headers=headers())
        r.raise_for_status()
        data = r.json()
        status = data["status"]
        print(f"[wait] {status}")
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
        clean = re.sub(r"^.*Z ", "", line)
        m = re.match(r"^(\S+)\s+(\S+)\s+(\d+x\d+|\w+)\s", clean)
        if not m:
            continue
        fmt_id, ext, res = m.groups()
        if fmt_id in ("ID", "format"):
            continue
        results.append((fmt_id, f"{res} ({ext})"))
    return results


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


def test_any_site_formats(url):
    print(f"\n===== Testing generic site: {url} =====")
    dispatch_workflow("list-formats.yml", {"video_url": url})
    time.sleep(2)
    run_id = get_latest_run_id("list-formats.yml")
    conclusion = wait_for_run(run_id)
    print(f"conclusion={conclusion}")
    if conclusion != "success":
        print("[FAIL] list-formats did not succeed")
        return None
    log_text = get_run_log_text(run_id)
    formats = parse_formats(log_text)
    print(f"[RESULT] {len(formats)} formats found:")
    for fmt_id, label in formats[:20]:
        print(f"   {fmt_id}: {label}")
    return formats


def test_any_site_download(url, format_id):
    print(f"\n===== Testing generic download: {url} format={format_id} =====")
    dispatch_workflow("download.yml", {
        "video_url": url, "format_id": format_id, "audio_only": "false"
    })
    time.sleep(2)
    run_id = get_latest_run_id("download.yml")
    conclusion = wait_for_run(run_id)
    print(f"conclusion={conclusion}")
    if conclusion != "success":
        print("[FAIL] download did not succeed")
        return None
    link = get_release_link(run_id)
    print(f"[RESULT] link = {link}")
    return link


if __name__ == "__main__":
    TOKEN = input("GitHub token: ").strip()

    print("\nPaste ANY video URL (not just YouTube - Instagram, Twitter/X, TikTok, Vimeo, etc.)")
    url = input("URL: ").strip()

    formats = test_any_site_formats(url)

    if formats:
        print("\nPick a format id to test full download (or press Enter to skip):")
        choice = input("format id: ").strip()
        if choice:
            test_any_site_download(url, choice)
