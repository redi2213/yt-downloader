"""Link Lab - any site through yt-dlp (lab copy of the link_downloader repo's tools).

Uses three workflows that are copies of redi2213/link_downloader:
  lab-links.yml         extract the video links (written into the notes of release run-<id>)
  lab-download.yml      extract + download + upload to a release run-<id>
  lab-find-proxies.yml  find free proxies, saved on this repo's config branch (lab/working_proxies.txt)
The app's own tools and workflows are not touched. Edit this file on the config
branch (lab/link_lab.py) and open the tool again: no build needed.
"""
import time

S = {"urls": "", "quality": "720", "proxy": "", "v2ray": "", "loaded": False}
QUALITIES = [("Best", "best"), ("1080", "1080"), ("720", "720"), ("480", "480")]
PROXY_FILE = "lab/working_proxies.txt"


def _load(host):
    if S["loaded"]:
        return
    S["loaded"] = True
    for key in ("proxy", "v2ray", "quality"):
        value = host.store.get(key)
        if value:
            S[key] = value


# ---------------------------------------------------------------- first screen
def build(host):
    _load(host)
    if host.prefill and not S["urls"]:
        S["urls"] = host.prefill
    host.title("Link Lab (any site)")
    host.text("Paste one or more video page links, one per line. yt-dlp reads the page, "
              "so most sites work.")
    urls = host.input("Links, one per line", text=S["urls"], multiline=True)
    host.text("Quality (for the download)")
    quality = host.choice(QUALITIES, default=S["quality"])
    host.status()

    def grab():
        S["urls"] = urls.text.strip()
        S["quality"] = quality.value
        host.store.set("quality", S["quality"])
        return S["urls"]

    def need():
        if not grab():
            host.set_status("Paste a link first")
            return False
        return True

    host.button("Get links only", lambda: need() and host.show(links_screen))
    host.button("Download to a GitHub release", lambda: need() and start_download(host))
    host.button("Options (proxy / v2ray)", lambda: (grab(), host.show(options_screen)))
    host.button("Free proxies", lambda: (grab(), host.show(proxies_screen)))
    host.button("Show log", host.show_log)
    host.back_button("Back")


# ---------------------------------------------------------------- options
def options_screen(host):
    host.title("Options")
    host.text("Both are optional. With both empty, the saved free proxy list is tried first "
              "(Free proxies button), then the plain GitHub IP.")
    host.text("Proxy (socks5://ip:port or http://ip:port)")
    proxy = host.input("Proxy override", text=S["proxy"])
    host.text("v2ray / Xray config: vless://, vmess://, trojan://, ss:// link, "
              "subscription link or JSON. When set, free proxies are ignored.")
    v2 = host.input("Config", text=S["v2ray"], multiline=True)
    host.status()

    def save():
        S["proxy"] = proxy.text.strip()
        S["v2ray"] = v2.text.strip()
        host.store.set("proxy", S["proxy"])
        host.store.set("v2ray", S["v2ray"])
        host.set_status("Saved")

    def clear():
        proxy.text = ""
        v2.text = ""
        S["proxy"] = S["v2ray"] = ""
        host.store.delete("proxy")
        host.store.delete("v2ray")
        host.set_status("Cleared")

    host.button("Save", save)
    host.button("Clear both", clear)
    host.back_button()


# ---------------------------------------------------------------- get links
def links_screen(host):
    host.title("Getting links")
    host.text("Runs lab-links.yml on GitHub (about a minute). You can leave this screen; "
              "the run keeps going.")
    host.status()
    host.set_status("Starting...")
    inputs = {"url": S["urls"], "proxy": S["proxy"], "v2ray_config": S["v2ray"]}

    def work():
        run_id = host.gh.dispatch("lab-links.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-links run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
        body = ""
        if conclusion == "success":
            for _ in range(6):
                try:
                    body = host.gh.request("GET", "/releases/tags/run-%s" % run_id).json().get("body") or ""
                except Exception as e:
                    host.log("release read:", e)
                    body = ""
                if body:
                    break
                time.sleep(2)
        return run_id, conclusion, body

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(links_result, *res)

    host.background(work, done=done)
    host.back_button()


def links_result(host, run_id, conclusion, body):
    links = [ln.strip() for ln in body.splitlines() if ln.strip().startswith("http")]
    if conclusion != "success":
        host.title("Run finished: %s" % conclusion)
        host.text("Open GitHub > Actions > Lab Links (run %s) to see the log." % run_id)
    elif not body.strip():
        host.title("No links saved")
        host.text("The run succeeded but saved nothing. Open GitHub > Actions > Lab Links "
                  "(run %s) to see the log." % run_id)
    else:
        host.title("Links (%d)" % len(links))
        host.text(body.strip())
    host.status()
    if links:
        host.button("Copy all links", lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    if body.strip():
        host.button("Copy everything", lambda: (host.copy(body), host.set_status("Copied")))
    host.back_button()


# ---------------------------------------------------------------- download
def start_download(host):
    action = {
        "workflow": "lab-download.yml",
        "workflow_inputs": {"url": "{url}", "quality": "{quality}",
                            "proxy": "{proxy}", "v2ray_config": "{v2ray_config}"},
    }
    host.log("download:", S["quality"], S["urls"][:200])
    host.run_action(action, {"url": S["urls"], "quality": S["quality"],
                             "proxy": S["proxy"], "v2ray_config": S["v2ray"]})


# ---------------------------------------------------------------- free proxies
def proxies_screen(host):
    host.title("Free proxies (lab list)")
    host.text("The list is saved on the config branch (%s) and used by Get links and "
              "Download when no proxy / v2ray config is set." % PROXY_FILE)
    host.button("Find new working proxies", lambda: host.show(find_screen))
    host.button("Show the saved list", lambda: host.show(list_screen))
    host.back_button()


def find_screen(host):
    host.title("Finding proxies")
    host.text("Runs lab-find-proxies.yml. This can take several minutes; the result is saved on "
              "GitHub even if you leave this screen.")
    host.status()
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-find-proxies.yml",
                                  {"needed": "8", "max_candidates": "100", "xh_check": "0"})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-find-proxies run", run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
        return conclusion, _read_list(host)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        conclusion, lines = res
        host.replace(list_view, "Run finished: %s" % conclusion, lines)

    host.background(work, done=done)
    host.back_button()


def list_screen(host):
    host.title("Saved proxy list")
    host.status()
    host.set_status("Reading...")

    def done(lines, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(list_view, "Saved proxy list", lines)

    host.background(lambda: _read_list(host), done=done)
    host.back_button()


def _read_list(host):
    try:
        text = host.gh.read_file(PROXY_FILE, ref="config")
    except Exception as e:
        host.log("proxy list read:", e)
        return None
    return [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]


def list_view(host, heading, lines):
    host.title(heading)
    if lines is None:
        host.text("No saved list yet. Use \"Find new working proxies\".")
    elif not lines:
        host.text("The list is empty.")
    else:
        host.text("%d proxies:\n%s" % (len(lines), "\n".join(lines)))
    host.status()
    if lines:
        host.button("Copy the list", lambda: (host.copy("\n".join(lines)), host.set_status("Copied")))
    host.back_button()
