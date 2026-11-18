"""TV cast (DLNA/UPnP) - Lab test.

Find TVs (SSDP), serve a file from this phone (HTTP + Range) and send it to the TV
(SetAVTransportURI + Play), then Pause / Stop / Seek / Volume. The file is always on the
phone first (scan the phone or download a direct link to the phone), never played straight
from a GitHub Release link. Logic lives in lib/dlna_core.py (module list in lab/index.json).
"""
import os

try:
    from labx import dlna_core as D
except ImportError:  # running outside the app
    import dlna_core as D

S = {"tv": None, "file": None, "server": None, "hotspot": False}


def build(host):
    host.title("TV cast (DLNA)")
    host.text("Test tool. The phone and the TV must be on the same Wi-Fi. The file is played from this phone.")
    tv, f = S["tv"], S["file"]
    host.text("TV: " + ("%s (%s)" % (tv["name"], tv["host"]) if tv else "not chosen"))
    host.text("File: " + (os.path.basename(f) if f else "not chosen"))
    host.text("Network: " + ("Hotspot (TV is connected to this phone's hotspot)" if S["hotspot"] else "Wi-Fi / modem"))
    host.status()

    def go():
        if S["tv"] and S["file"]:
            host.show(player_screen)
        else:
            host.set_status("Choose a TV and a file first")

    host.button("Network: " + ("Hotspot" if S["hotspot"] else "Wi-Fi / modem") + "  [tap to switch]",
                lambda: _toggle_hotspot(host))
    host.button("1) Find TVs", lambda: host.show(find_screen))
    host.button("2) Choose file (phone or link)", lambda: host.show(file_screen))
    host.button("3) Play on TV", go)
    host.button("Show log", host.show_log)
    host.back_button("Back")


# ------------------------------------------------------------------ 1) TVs
def find_screen(host):
    host.title("Finding TVs")
    hot = S["hotspot"]
    host.text("Searching with SSDP on the hotspot (about 8 seconds)." if hot else "Searching with SSDP (about 6 seconds).")
    host.status()
    host.set_status("Searching...")

    def work():
        ok, msg = D.acquire_multicast_lock()
        return ok, msg, D.discover(8.0 if hot else 6.0, hotspot=hot)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            host.log("discover failed:", err)
            return
        ok, msg, found = res
        host.log("multicast lock:", ok, msg, "| found:", len(found))
        host.replace(tv_list_screen, found, "" if ok else msg)

    host.background(work, done=done)
    host.back_button("Back")


def tv_list_screen(host, found, warn):
    host.title("TVs found (%d)" % len(found))
    if warn:
        host.text("Multicast lock problem: " + warn)
    if not found:
        host.text("No TV answered. Check the Wi-Fi (same network, no guest/isolated mode) and that the TV's "
                  "network/DLNA/cast feature is on.")
    if not found and S["hotspot"]:
        host.text("Hotspot mode: turn on this phone's hotspot, connect the TV to it (TV Wi-Fi settings), "
                  "then search again.")
    for tv in found:
        host.button("%s  (%s)" % (tv["name"], tv["host"]), lambda t=tv: _pick_tv(host, t))
    host.status()
    host.button("Search again", lambda: host.replace(find_screen))
    host.back_button("Back")


def _pick_tv(host, tv):
    S["tv"] = tv
    host.replace(build)


def _toggle_hotspot(host):
    S["hotspot"] = not S["hotspot"]
    S["tv"] = None  # the TV list differs between the modem Wi-Fi and the hotspot
    host.replace(build)


# ------------------------------------------------------------------ 2) file
def file_screen(host):
    host.title("Choose file")
    host.text("The TV pulls the file from a small server on this phone, so the file must be on the phone.")
    host.button("Scan phone for videos / audio", lambda: host.show(scan_screen))
    path = host.input("File path on the phone", text=S["file"] or "")
    link = host.input("Direct link (downloaded to the phone first)")
    host.status()

    def use_path():
        p = (path.text or "").strip()
        if os.path.isfile(p):
            S["file"] = p
            host.replace(build)
        else:
            host.set_status("No such file on the phone")

    def use_link():
        u = (link.text or "").strip()
        if not u.lower().startswith(("http://", "https://")):
            host.set_status("Paste a direct http(s) link")
            return
        host.show(download_screen, u)

    host.button("Use this path", use_path)
    host.button("Download link to the phone", use_link)
    host.back_button("Back")


def scan_screen(host):
    host.title("Scanning the phone")
    host.status()
    host.set_status("Looking in Download, Movies, Music...")

    def work():
        return D.scan_media([os.path.join(host.data_dir, "dlna_cache")])

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            host.log("scan failed:", err)
            return
        host.replace(scan_result_screen, res)

    host.background(work, done=done)
    host.back_button("Back")


def scan_result_screen(host, files):
    host.title("Files (%d)" % len(files))
    if not files:
        host.text("Nothing found in the usual folders. Type the path by hand or download a link.")
    for p, size in files:
        host.button("%s  [%s]" % (os.path.basename(p), D.human_size(size)), lambda x=p: _pick_file(host, x))
    host.status()
    host.back_button("Back")


def _pick_file(host, path):
    S["file"] = path
    host.replace(build)


def download_screen(host, url):
    host.title("Downloading to the phone")
    host.text(url)
    host.status()
    host.set_status("Starting...")
    dest = os.path.join(host.data_dir, "dlna_cache")

    def prog(done, total):
        if total:
            host.set_status("Downloaded %s of %s (%d%%)" % (D.human_size(done), D.human_size(total), done * 100 // total))
        else:
            host.set_status("Downloaded " + D.human_size(done))

    def finished(res, err):
        if err is not None:
            host.set_status("Download failed: %s" % err)
            host.log("download failed:", err)
            return
        S["file"] = res
        host.replace(build)

    host.background(lambda: D.download(url, dest, prog), done=finished)
    host.back_button("Back")


# ------------------------------------------------------------------ 3) player
def player_screen(host):
    tv = S["tv"]
    host.title("TV: " + tv["name"])
    host.text("File: " + os.path.basename(S["file"]))
    host.status()
    host.set_status("Starting the phone server and sending to the TV...")
    host.background(_start_cast, done=lambda res, err: _report(host, "Play", res, err))

    def run(label, fn):
        host.set_status(label + "...")
        host.background(fn, done=lambda res, err: _report(host, label, res, err))

    host.button("Play / Resume", lambda: run("Play", lambda: (D.play(tv), "Playing")[1]))
    host.button("Pause", lambda: run("Pause", lambda: (D.pause(tv), "Paused")[1]))
    host.button("Stop", lambda: run("Stop", lambda: (D.stop(tv), "Stopped")[1]))
    host.button("Back 30 s", lambda: run("Seek", lambda: _seek_rel(tv, -30)))
    host.button("Forward 30 s", lambda: run("Seek", lambda: _seek_rel(tv, 30)))
    at = host.input("Seek to (seconds, mm:ss or h:mm:ss)")

    def seek_to():
        sec = D.parse_user_time(at.text)
        if sec is None:
            host.set_status("Type seconds, mm:ss or h:mm:ss")
            return
        run("Seek", lambda: (D.seek(tv, sec), "Seek to " + D.fmt_time(sec))[1])

    host.button("Seek", seek_to)
    host.button("Volume -5", lambda: run("Volume", lambda: _vol_rel(tv, -5)))
    host.button("Volume +5", lambda: run("Volume", lambda: _vol_rel(tv, 5)))
    host.button("Refresh status", lambda: run("Status", lambda: _status(tv)))
    host.button("Stop TV and close the phone server", lambda: run("Close", _close_all))
    host.button("Show log", host.show_log)
    host.back_button("Back")


def _report(host, label, res, err):
    if err is not None:
        host.log(label, "failed:", err)
        host.set_status("%s failed: %s" % (label, err))
    else:
        host.set_status(res or (label + " ok"))


def _start_cast():
    tv, path = S["tv"], S["file"]
    srv = S.get("server") or D.MediaServer()
    srv.start()
    S["server"] = srv
    ip = D.local_ip_for(tv["host"])
    url = srv.url_for(ip, srv.add(path))
    D.cast(tv, url, path)
    return "Playing. TV pulls from " + url


def _seek_rel(tv, delta):
    pos = D.position(tv)
    target = max(0, pos["rel"] + delta)
    if pos["dur"]:
        target = min(target, max(0, pos["dur"] - 2))
    D.seek(tv, target)
    return "Seek to " + D.fmt_time(target)


def _vol_rel(tv, delta):
    v = max(0, min(100, D.get_volume(tv) + delta))
    D.set_volume(tv, v)
    return "Volume %d" % v


def _status(tv):
    pos = D.position(tv)
    try:
        vol = " | volume %d" % D.get_volume(tv)
    except D.DlnaError:
        vol = ""
    return "%s  %s / %s%s" % (D.state(tv), D.fmt_time(pos["rel"]), D.fmt_time(pos["dur"]), vol)


def _close_all():
    try:
        D.stop(S["tv"])
    except D.DlnaError:
        pass
    srv = S.get("server")
    if srv:
        srv.stop()
        S["server"] = None
    D.release_multicast_lock()
    return "Stopped and closed"
