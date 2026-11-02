"""Instagram Downloader - Download Anything plugin (no APK build needed).

Runs .github/workflows/instagram-downloader.yml, follows the run, then reads the
files of the release tagged run-{run_id} (so they also show in Release History).
Proxy / V2Ray boxes are optional; when filled they are sent to the workflow
(which then prefers them over its own saved proxies).
"""
import re
import threading
import time

WORKFLOW = "instagram-downloader.yml"
LINKS_ASSET = "download-links.txt"
_URL_RE = re.compile(r"https?://(?:www\.)?instagram\.com/\S+", re.I)
_COUNT_RE = re.compile(r"Complete files:\s*(\d+)\s*/\s*(\d+)")
_STATUS_TEXT = {"queued": "Queued on GitHub", "in_progress": "Running", "completed": "Finishing"}


def _find_url(text):
    m = _URL_RE.search(text or "")
    return m.group(0).rstrip(").,;") if m else ""


def build(host):
    host.title("Instagram Downloader")
    host.text("Post, Reel or Story link")
    url = host.input("https://www.instagram.com/...", text=_find_url(host.prefill))
    host.text("Proxy (optional)")
    proxy = host.input("socks5h://ip:port or http://ip:port", paste=False)
    host.text("V2Ray config (optional)")
    v2ray = host.input("vless:// vmess:// trojan:// ss://, subscription link or JSON",
                       multiline=True, height=110)
    host.button("Download", lambda: _start(host, url, proxy, v2ray))
    host.status()
    host.back_button("Back")


def _start(host, url_box, proxy_box, v2ray_box):
    url = _find_url(url_box.text)
    if not url:
        host.set_status("Enter an Instagram link (https://www.instagram.com/...)")
        return
    if not url.lower().startswith(("https://www.instagram.com/", "https://instagram.com/")):
        url = "https://" + url.split("://", 1)[1]
        if not url.lower().startswith(("https://www.instagram.com/", "https://instagram.com/")):
            host.set_status("The link must start with https://www.instagram.com/")
            return
    host.show(_run_screen, url, proxy_box.text.strip(), v2ray_box.text.strip())


def _run_screen(host, url, proxy, v2ray):
    state = {"run_id": None, "stop": threading.Event()}
    host.title("Instagram Downloader")
    host.text("Link: " + url[:90])
    host.status()
    host.set_status("Starting workflow...")

    def cancel():
        state["stop"].set()
        if state["run_id"]:
            host.background(host.gh.cancel, state["run_id"])
        host.back()

    host.button("Cancel", cancel)
    host.back_button("Back")
    host.log("start", url, "proxy" if proxy else "", "v2ray" if v2ray else "")
    host.background(_work, host, url, proxy, v2ray, state,
                    done=lambda res, err: _done(host, url, proxy, v2ray, res, err))


def _work(host, url, proxy, v2ray, state):
    inputs = {"instagram_url": url}
    if proxy:
        inputs["proxy"] = proxy
    if v2ray:
        inputs["v2ray_config"] = v2ray
    run_id = host.gh.dispatch(WORKFLOW, inputs)
    if not run_id:
        return {"error": "Could not detect the workflow run. It may still be running on GitHub Actions."}
    state["run_id"] = run_id
    host.log("run", run_id)
    host.set_status("Workflow started (run %s)" % run_id)

    conclusion = host.gh.wait(
        run_id,
        on_status=lambda s: host.set_status(_STATUS_TEXT.get(s, str(s)) + "..."),
        stop_event=state["stop"])
    if conclusion == "cancelled_locally":
        return {"cancelled": True}
    if conclusion != "success":
        return {"error": "Download failed (%s). %s" % (conclusion, _failed_step(host, run_id)),
                "run_id": run_id}

    host.set_status("Checking the files...")
    return _read_release(host, "run-%s" % run_id)


def _failed_step(host, run_id):
    try:
        jobs = host.gh.request("GET", "/actions/runs/%s/jobs" % run_id).json().get("jobs", [])
        for job in jobs:
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    return "Failed step: " + str(step.get("name"))
    except Exception:
        pass
    return "Open the run log on GitHub for details."


def _read_release(host, tag):
    from api.github.auth import auth_headers
    release = None
    for _ in range(10):
        try:
            release = host.gh.request("GET", "/releases/tags/" + tag).json()
            if release.get("assets"):
                break
        except Exception:
            release = None
        time.sleep(2)
    if not release or not release.get("assets"):
        return {"error": "The release %s is not ready or has no files." % tag}

    assets = release["assets"]
    files = [a for a in assets if a.get("name") != LINKS_ASSET]
    bad = [a.get("name") for a in files if not a.get("size") or a.get("state") != "uploaded"]
    if not files or bad:
        return {"error": "Incomplete files in the release, not shown: %s" % (", ".join(bad) or "none found")}

    expected = None
    m = _COUNT_RE.search(release.get("body") or "")
    if m:
        expected = int(m.group(2))
    manifest = next((a for a in assets if a.get("name") == LINKS_ASSET), None)
    if manifest and expected is None:
        try:
            headers = dict(auth_headers())
            headers["Accept"] = "application/octet-stream"
            text = host.gh.request("GET", manifest["url"], headers=headers).text
            m = _COUNT_RE.search(text)
            if m:
                expected = int(m.group(2))
        except Exception:
            expected = None
    if expected is not None and expected != len(files):
        return {"error": "Expected %d complete file(s) but the release has %d." % (expected, len(files))}

    files.sort(key=lambda a: a.get("id", 0))
    return {"links": [a["browser_download_url"] for a in files],
            "names": [a.get("name") for a in files]}


def _done(host, url, proxy, v2ray, result, error):
    if error is not None:
        return _failed(host, url, proxy, v2ray, "Error: %s" % str(error)[:200])
    if result.get("cancelled"):
        return None
    if result.get("error"):
        return _failed(host, url, proxy, v2ray, result["error"])
    links = result["links"]
    host.log("done", len(links), "file(s)")
    host.notify("Instagram Downloader", "%d file(s) ready" % len(links))
    host.result("Done: %d file(s)" % len(links), link=links[0], links=links if len(links) > 1 else None)
    return None


def _failed(host, url, proxy, v2ray, message):
    host.log("failed", message)
    host.notify("Instagram Downloader", "Failed")
    host.replace(_error_screen, url, proxy, v2ray, message)


def _error_screen(host, url, proxy, v2ray, message):
    host.title("Instagram Downloader: failed")
    host.text(message)
    host.button("Copy error", lambda: (host.copy(message), host.set_status("Copied")))
    host.button("Try again", lambda: host.replace(_run_screen, url, proxy, v2ray))
    host.status()
    host.back_button("Back")
