"""Link Lab - any site through yt-dlp (lab copy of the link_downloader repo's tools).

Uses three workflows that are copies of redi2213/link_downloader:
  lab-links.yml         extract the video links (written into the notes of release run-<id>)
  lab-download.yml      extract + download + upload to a release run-<id>
  lab-find-proxies.yml  find free proxies, saved on this repo's lab branch (lab/working_proxies.txt)
The app's own tools and workflows are not touched. Edit this file on the config
branch (lab/link_lab.py) and open the tool again: no build needed.
"""
import re
import time

S = {"urls": "", "quality": "720", "proxy": "", "v2ray": "", "loaded": False}
QUALITIES = [("Best", "best"), ("1080", "1080"), ("720", "720"), ("480", "480")]
PROXY_FILE = "lab/working_proxies.txt"
CONFIG_FILE = "lab/working_configs.txt"


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
              "so most sites work (xHamster and Beeg use their own API first).")
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
    host.text("Both are optional. With both empty, Lab uses its automatic sources: the free "
              "proxies (refreshed every 12 hours) and the best configs of the default "
              "subscription (refreshed every 24 hours). They are tried together and the "
              "first that answers wins. Fill these only to use your own.")
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
    picks = _parse_qualities(body) if conclusion == "success" else []
    if picks:
        host.text("Download one quality (runs lab-download.yml and makes a GitHub release):")
        for title, page, height, link, size in picks[:12]:
            sfx = (" \u2022 " + size) if size else ""
            label = "Download %dp%s" % (height, sfx)
            if len({p[1] for p in picks}) > 1:
                label += " - " + (title[:22] or page[:22])
            host.row([
                (label, lambda p=page, h=height: _run_download(host, p, str(h))),
                ("Copy %dp link%s" % (height, sfx),
                 lambda u=link, h=height: (host.copy(u), host.set_status("Copied %dp link" % h))),
            ])
        if len(picks) > 12:
            host.text("(%d more not shown)" % (len(picks) - 12))
    if links:
        host.button("Copy all links", lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    if body.strip():
        host.button("Copy everything", lambda: (host.copy(body), host.set_status("Copied")))
    host.back_button()


# ---------------------------------------------------------------- download
def _run_download(host, url, quality):
    host.log("download:", quality, url[:200])
    host.show(download_screen, url, quality)


def download_screen(host, url, quality):
    # NOT host.run_action: that always starts the workflow on main, where lab-download.yml
    # is only an empty stub. host.gh.dispatch starts it from the lab branch (the real one).
    label = quality if str(quality) == "best" else "%sp" % quality
    host.title("Downloading (%s)" % label)
    host.text("Runs lab-download.yml from the lab branch and saves the video in a GitHub "
              "release. You can leave this screen; the run keeps going.")
    host.status()
    host.set_status("Starting...")
    inputs = {"url": url, "quality": str(quality), "proxy": S["proxy"], "v2ray_config": S["v2ray"]}

    def work():
        run_id = host.gh.dispatch("lab-download.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-download run", run_id)
        host.set_status("Run %s started..." % run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
        links = []
        if conclusion == "success":
            try:
                links = host.gh.release_links(run_id, attempts=6, delay=2)
            except Exception as e:
                host.log("release links:", e)
        return run_id, conclusion, links

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(download_result, *res)

    host.background(work, done=done)
    host.back_button()


def download_result(host, run_id, conclusion, links):
    if conclusion != "success":
        host.title("Run finished: %s" % conclusion)
        host.text("Open GitHub > Actions > Lab Download Release (run %s) to see the log." % run_id)
    elif not links:
        host.title("No file saved")
        host.text("The run succeeded but no release file was found. Open GitHub > Actions > "
                  "Lab Download Release (run %s) to see the log." % run_id)
    else:
        host.title("Downloaded (%d file%s)" % (len(links), "" if len(links) == 1 else "s"))
        host.text("Saved in release run-%s. Open it from Release History in the app "
                  "(the app downloads with your GitHub token).\n\n%s" % (run_id, "\n".join(links)))
    host.status()
    if links:
        host.button("Copy link%s" % ("" if len(links) == 1 else "s"),
                    lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    host.back_button()


def start_download(host):
    _run_download(host, S["urls"], S["quality"])


def _parse_qualities(body):
    """Read the release notes written by lab_scripts/links.py: (title, page link, height, direct link)."""
    out, seen = [], set()
    title = page = ""
    pending = None
    pending_size = ""
    for raw in (body or "").splitlines():
        ln = raw.strip()
        if not ln:
            continue
        if ln.startswith("# page:"):
            page = ln[7:].strip()
            continue
        if ln.startswith("# method:") or ln.startswith("# ERROR"):
            continue
        if ln.startswith("# quality:"):
            m = re.match(r"#\s*quality:\s*(\d{3,4})p", ln)
            pending = int(m.group(1)) if m else None
            ms = re.search(r"\|\s*size:\s*(.+)$", ln)
            pending_size = ms.group(1).strip() if ms else ""
            continue
        if ln.startswith("# "):
            title = ln[2:].strip()
            pending = None
            continue
        if ln.startswith("http"):
            if pending and page and (page, pending) not in seen:
                seen.add((page, pending))
                out.append((title, page, pending, ln, pending_size))
            pending = None
            pending_size = ""
    return out


# ---------------------------------------------------------------- free proxies
def proxies_screen(host):
    host.title("Free proxies (lab list)")
    host.text("Both lists refresh by themselves: proxies every 12 hours, configs every 24 hours "
              "(GitHub schedule). They are saved on the lab branch (%s, %s) and used by Get "
              "links and Download when no proxy / v2ray config is set. The buttons below "
              "refresh them right now." % (PROXY_FILE, CONFIG_FILE))
    host.button("Find new working proxies", lambda: host.show(find_screen))
    host.button("Show the saved list", lambda: host.show(list_screen))
    host.button("Refresh default configs", lambda: host.show(configs_find_screen))
    host.button("Show default configs", lambda: host.show(configs_list_screen))
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
        text = host.gh.read_file(PROXY_FILE, ref="lab")
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


# ---------------------------------------------------------------- default configs
def _read_configs(host):
    """(updated text, ['vless host:port', ...]) from the saved list. Keys are never shown."""
    from urllib.parse import urlsplit
    try:
        text = host.gh.read_file(CONFIG_FILE, ref="lab")
    except Exception as e:
        host.log("config list read:", e)
        return None
    updated, items = "", []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("# Updated:"):
            updated = ln[10:].strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            u = urlsplit(ln)
            items.append("%s %s:%s" % (u.scheme, u.hostname, u.port))
        except Exception:
            items.append(ln.split("://")[0] + " (config)")
    return updated, items


def configs_find_screen(host):
    host.title("Refreshing configs")
    host.text("Runs lab-refresh-configs.yml: tests the nodes of the default subscription and "
              "keeps the best few. It takes a few minutes; the result is saved on GitHub even "
              "if you leave this screen.")
    host.status()
    host.set_status("Starting...")

    def work():
        run_id = host.gh.dispatch("lab-refresh-configs.yml", {})
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-refresh-configs run", run_id)
        conclusion = host.gh.wait(run_id, on_status=lambda s: host.set_status("%s..." % s))
        return conclusion, _read_configs(host)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        conclusion, info = res
        host.replace(configs_view, "Run finished: %s" % conclusion, info)

    host.background(work, done=done)
    host.back_button()


def configs_list_screen(host):
    host.title("Default configs")
    host.status()
    host.set_status("Reading...")

    def done(info, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            return
        host.replace(configs_view, "Default configs", info)

    host.background(lambda: _read_configs(host), done=done)
    host.back_button()


def configs_view(host, heading, info):
    host.title(heading)
    if info is None:
        host.text("No saved configs yet. Use \"Refresh default configs\".")
    else:
        updated, items = info
        if not items:
            host.text("The list is empty.")
        else:
            host.text("%d configs (updated %s):\n%s" % (len(items), updated or "?", "\n".join(items)))
    host.status()
    host.back_button()
