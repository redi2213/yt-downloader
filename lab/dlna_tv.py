"""TV cast (DLNA/UPnP) - Lab test.

Find TVs (SSDP), serve a file from this phone (HTTP + Range) and send it to the TV
(SetAVTransportURI + Play), then Pause / Stop / Seek / Volume. The file is always on the
phone first (scan the phone or download a direct link to the phone), never played straight
from a GitHub Release link. Logic lives in lib/dlna_core.py (module list in lab/index.json).
"""
import os
import threading
import time

try:
    from labx import dlna_core as D
except ImportError:  # running outside the app
    import dlna_core as D

S = {"tv": None, "file": None, "server": None, "hotspot": False, "kind": "video", "multi": False,
     "queue": [], "qi": 0, "sel": [], "gen": 0, "seen": False}


def build(host):
    host.title("TV cast (DLNA)")
    host.text("Test tool. The phone and the TV must be on the same Wi-Fi. The file is played from this phone.")
    tv, f = S["tv"], S["file"]
    host.text("TV: " + ("%s (%s)" % (tv["name"], tv["host"]) if tv else "not chosen"))
    host.text("Type: %s | Mode: %s" % (_kind_label(), "Multiple files" if S["multi"] else "Single file"))
    q = S["queue"]
    host.text(("Files: %d selected, first: %s" % (len(q), os.path.basename(q[0]))) if len(q) > 1 else
              "File: " + (os.path.basename(f) if f else "not chosen"))
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
    host.button("2) Type: %s  [tap to switch]" % _kind_label(), lambda: _toggle_kind(host))
    host.button("Mode: %s  [tap to switch]" % ("Multiple files" if S["multi"] else "Single file"),
                lambda: _toggle_multi(host))
    host.button("3) Choose file(s) (phone or link)", lambda: host.show(file_screen))
    host.button("4) Play on TV", go)
    host.row([("Copy log", lambda: _copy_log(host)), ("Clear log", lambda: _clear_log(host))])
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
    host.button("Browse phone folders", lambda: host.show(browse_home_screen))
    host.button("Scan phone for videos / audio", lambda: host.show(scan_screen))
    q = host.input("Search by any part of the name")
    host.button("Search all storage", lambda: _do_search(host, q))
    path = host.input("File path on the phone", text=S["file"] or "")
    link = host.input("Direct link (downloaded to the phone first)")
    host.status()

    def use_path():
        p = (path.text or "").strip()
        if os.path.isfile(p):
            _set_files([p])
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


def _do_search(host, q):
    text = (q.text or "").strip()
    if not text:
        host.set_status("Type part of the file name first")
        return
    host.show(search_screen, text)


def search_screen(host, query):
    host.title("Searching: " + query)
    host.status()
    host.set_status("Looking through all storage...")

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % err)
            host.log("search failed:", err)
            return
        host.replace(scan_result_screen, res)

    host.background(lambda: D.search_media(query, kind=S["kind"]), done=done)
    host.back_button("Back")


def browse_home_screen(host):
    host.title("Browse phone")
    host.text("Pick a folder, then a video or audio file.")
    for name, p in D.shortcuts():
        host.button("[DIR] " + name, lambda x=p: host.show(browse_screen, x))
    host.button("All storage", lambda: host.show(browse_screen, D.storage_root()))
    host.back_button("Back")


def browse_screen(host, path):
    path = path.rstrip("/") or "/"
    host.title(os.path.basename(path) or path)
    host.text(path)
    try:
        dirs, files, cut = D.list_dir(path, kind=S["kind"])
    except D.DlnaError as e:
        host.text(str(e))
        host.back_button("Back")
        return
    _multi_bar(host, lambda: host.replace(browse_screen, path), [p for _n, p, _s in files])
    if path != D.storage_root() and path != "/":
        host.button("[UP] ..", lambda: host.replace(browse_screen, os.path.dirname(path) or "/"))
    for name, p in dirs:
        host.button("[DIR] " + name, lambda x=p: host.show(browse_screen, x))
    for name, p, size in files:
        host.button("%s%s  [%s]" % (_mark(p), name, D.human_size(size)),
                    lambda x=p: _pick_file(host, x, lambda: host.replace(browse_screen, path)))
    if not dirs and not files:
        host.text("No folders or media files here.")
    if cut:
        host.text("Only the first 300 entries are shown.")
    host.status()
    host.back_button("Back")


def scan_screen(host):
    host.title("Scanning the phone")
    host.status()
    host.set_status("Looking in Download, Movies, Music...")

    def work():
        return D.scan_media([os.path.join(host.data_dir, "dlna_cache")], limit=200 if S["multi"] else 40, kind=S["kind"])

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
    _multi_bar(host, lambda: host.replace(scan_result_screen, files), [p for p, _s in files])
    for p, size in files:
        host.button("%s%s  [%s]" % (_mark(p), os.path.basename(p), D.human_size(size)),
                    lambda x=p: _pick_file(host, x, lambda: host.replace(scan_result_screen, files)))
    host.status()
    host.back_button("Back")


def _pick_file(host, path, refresh=None):
    if S["multi"] and refresh:
        if path in S["sel"]:
            S["sel"].remove(path)
        else:
            S["sel"].append(path)
        refresh()
        return
    _set_files([path])
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
        _set_files((S["queue"] + [res]) if S["multi"] else [res])
        host.replace(build)

    host.background(lambda: D.download(url, dest, prog), done=finished)
    host.back_button("Back")


# ------------------------------------------------------------------ 3) player
def player_screen(host):
    tv = S["tv"]
    host.title("TV: " + tv["name"])
    host.text(_track_text())
    host.status()
    host.set_status("Starting the phone server and sending to the TV...")
    host.background(_start_cast, done=lambda res, err: _report(host, "Play", res, err))

    def run(label, fn):
        host.set_status(label + "...")
        host.background(fn, done=lambda res, err: _report(host, label, res, err))

    host.button("Play / Resume", lambda: run("Play", lambda: _resume(tv)))
    host.button("Pause", lambda: run("Pause", lambda: (D.pause(tv), "Paused")[1]))
    host.button("Stop", lambda: run("Stop", lambda: _stop_tv(tv)))
    if len(S["queue"]) > 1:
        host.button("Previous track", lambda: run("Previous", lambda: _go(-1)))
        host.button("Next track", lambda: run("Next", lambda: _go(1)))
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
    host.row([("Copy log", lambda: _copy_log(host)), ("Clear log", lambda: _clear_log(host))])
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
    S["seen"] = False
    _ensure_watch()
    return _track_prefix() + "Playing. TV pulls from " + url


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
    return "%s%s  %s / %s%s" % (_track_prefix(), D.state(tv), D.fmt_time(pos["rel"]), D.fmt_time(pos["dur"]), vol)


def _close_all():
    S["gen"] += 1
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


# ------------------------------------------------------------------ type / multiple files / queue
def _kind_label():
    return "Music" if S["kind"] == "audio" else "Video"


def _toggle_kind(host):
    S["kind"] = "video" if S["kind"] == "audio" else "audio"
    S["queue"], S["file"], S["sel"], S["qi"] = [], None, [], 0  # the old files are the other type
    host.replace(build)


def _toggle_multi(host):
    S["multi"] = not S["multi"]
    S["sel"] = []
    host.replace(build)


def _set_files(paths):
    S["queue"] = list(paths)
    S["qi"] = 0
    S["file"] = paths[0] if paths else None
    S["sel"] = []


def _mark(path):
    if not S["multi"]:
        return ""
    return "[x] " if path in S["sel"] else "[ ] "


def _multi_bar(host, refresh, paths=None):
    if not S["multi"]:
        return

    def use():
        if S["sel"]:
            _set_files(list(S["sel"]))
            host.replace(build)

    def all_here():
        for p in paths:
            if p not in S["sel"]:
                S["sel"].append(p)
        refresh()

    def clear():
        S["sel"] = []
        refresh()

    host.button("Use selected (%d)" % len(S["sel"]), use)
    if paths:
        host.button("Select all here (%d)" % len(paths), all_here)
    host.button("Clear selection", clear)


def _track_prefix():
    n = len(S["queue"])
    return "[%d/%d] " % (S["qi"] + 1, n) if n > 1 else ""


def _track_text():
    n = len(S["queue"])
    name = os.path.basename(S["file"])
    return "Track %d/%d: %s" % (S["qi"] + 1, n, name) if n > 1 else "File: " + name


def _resume(tv):
    D.play(tv)
    _ensure_watch()
    return "Playing"


def _stop_tv(tv):
    S["gen"] += 1  # a stopped queue must not jump to the next track
    D.stop(tv)
    return "Stopped"


def _go(step):
    i = S["qi"] + step
    if i < 0 or i >= len(S["queue"]):
        return "No more tracks that way"
    S["qi"] = i
    S["file"] = S["queue"][i]
    return _start_cast()


def _ensure_watch():
    """Start the watcher that sends the next track when the TV finishes the current one."""
    S["gen"] += 1
    if len(S["queue"]) < 2:
        return
    threading.Thread(target=_watch, args=(S["gen"],), daemon=True).start()


def _watch(gen):
    while S["gen"] == gen:
        time.sleep(3)
        if S["gen"] != gen:
            return
        try:
            state = D.state(S["tv"])
        except D.DlnaError:
            continue
        S["seen"], advance = D.autoplay_step(state, S["seen"])
        if advance:
            if S["qi"] + 1 >= len(S["queue"]):
                return
            S["qi"] += 1
            S["file"] = S["queue"][S["qi"]]
            try:
                _start_cast()  # starts a new watcher, so this one ends
            except (D.DlnaError, OSError):
                return
            return


def _copy_log(host):
    """Copies only the END of the log (the newest lines, at most 60 lines / 7000 characters): the whole
    log is kept on the phone (400 lines) and is too long to paste."""
    try:
        text = host._log.text()
    except Exception:
        host.show_log()
        return
    lines = (text or "").splitlines()[-60:]
    out = "\n".join(lines)[-7000:]
    host.copy(out or "(empty)")
    host.set_status("Copied the last %d lines" % len(lines) if lines else "The log is empty")


def _clear_log(host):
    try:
        host._log.clear()
        host.set_status("Log cleared")
    except Exception as e:
        host.set_status("Could not clear: %s" % str(e)[:60])
