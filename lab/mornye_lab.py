"""Mornye from link - lab copy of the app's Mornye tool.

The Mornye in Download Anything is NOT touched. This copy keeps all its logic in
lab/lib/ (copies of api/mornye.py, api/mornye_prefs.py, core/mornye_download.py and
services/mornye_link_service.py), so changing it needs no build.

Shared with the app's own Mornye: the saved sessions (so no new browser check) and
the "mornye-from-links.yml" workflow. Separate: the settings (order, ticks, registry),
kept under "mornye_lab_prefs"; logs go to logs/mornye-lab-*.txt on the lab branch.

Differs from the app's version on purpose: a song name typed in the link box is
searched. (The app tests `not parse_spotify(...)`, but that returns the tuple
(None, None) for plain text, which is never "falsy", so it never searches there.)
"""
import time

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from labx import mornye, mornye_link_service, mornye_prefs

QUALITIES = [("Lossless (FLAC 16-bit)", "LOSSLESS"), ("Hi-Res (best available)", "HI_RES_LOSSLESS")]
TARGETS = (("Download with the app (save on this phone)", "phone"),
           ("Give the direct links", "links"),
           ("Upload to a GitHub release", "github"))
NAMES = {"tidal": "Tidal", "qobuz": "Qobuz", "deezer": "Deezer"}
WAYS = {"github": "Upload to a GitHub release instead",
        "phone": "Download with the app instead",
        "links": "Give the direct links instead"}

# what the screens share while the plugin is open
S = {"url": "", "quality": "LOSSLESS", "registry": None, "verify": None}


def _kind(url):
    """'track' / 'album' / 'playlist' / 'artist', or None when it is not a Spotify link."""
    return (mornye.parse_spotify(url) or (None, None))[0]


def _ui(host, fn):
    """Runs fn on the UI thread (the service threads call this)."""
    host.nav.schedule(lambda: host._safe(fn))


def _draw(host, fn, *args):
    """Draws a screen without changing where Back goes (the Back of the working
    screen that may follow still returns to the screen before this one)."""
    host._epoch += 1
    host._cancel_timers()
    host.nav.clear()
    try:
        fn(host, *args)
    except Exception as e:
        host._fail(e)


def _to_form(host):
    """Back to the first screen, forgetting the steps in between."""
    host._stack = []
    host.replace(build)


def _safe_buttons(host, buttons):
    """Buttons for a result screen: the given ones, then Back to the form."""
    buttons = list(buttons) + [("Back to the form", lambda: _to_form(host))]
    return [(text, (lambda f=f: host._safe(f))) for text, f in buttons]


# ---------------------------------------------------------------- form
def build(host):
    if host.prefill and not S["url"]:
        S["url"] = host.prefill
    w = {}

    def grab():
        S["url"] = w["url"].text.strip()
        S["quality"] = w["quality"].value
        return {"url": S["url"], "quality": S["quality"]}

    host.title("Mornye (lab copy)")
    host.text("Search Spotify (song or artist name)")
    search = host.input("e.g. Shakira Waka Waka", paste=False)
    host.button("Search", lambda: start_search(host, search.text, grab()))
    host.text("Spotify link or song name")
    w["url"] = host.input("Link, or a song name (e.g. Shakira Waka Waka)", text=S["url"])
    host.text("Quality")
    w["quality"] = host.choice(QUALITIES, default=S["quality"])
    host.button("Settings (sources, order, repo)", lambda: (grab(), host.show(settings_screen)))
    host.status()

    def start():
        values = grab()
        if not values["url"]:
            host.set_status("Enter spotify link or song name")
            return
        host.log("start:", values["url"], values["quality"])
        if not _kind(values["url"]):
            return start_search(host, values["url"], values)
        start_flow(host, values)

    host.button("Start", start)
    host.back_button("Back")


# ---------------------------------------------------------------- search
def start_search(host, query, values):
    query = (query or "").strip()
    if not query:
        host.set_status("Type a song or artist name")
        return
    values = dict(values, url=query)
    host.log("search:", query)
    host.nav.show_working("Searching Spotify...")

    def work():
        return mornye.search_spotify(query)

    def done(found, err):
        message = ""
        if isinstance(err, mornye.MornyeError):
            found, message = [], str(err)
        elif err is not None:
            raise err
        elif not found:
            message = "Nothing found - try another name or paste the link"
        host.show(results_screen, values, found, message)

    host.background(work, done=done)


def results_screen(host, values, found, message):
    host.title("Pick the track" if found else (message or "Nothing found"))
    for item in found:
        link = "https://open.spotify.com/track/" + item["id"]
        host.button("%s - %s" % (item["title"], item["artist"]),
                    lambda link=link: start_flow(host, dict(values, url=link)))
    host.back_button()


# ---------------------------------------------------------------- one track: ask each service first
def start_flow(host, values):
    if _kind(values.get("url", "")) != "track" or values.get("providers"):
        return ask_target(host, values)
    host.log("probe:", values["url"])
    host.nav.show_working("Checking what each service offers...",
                          extra_buttons=[("Cancel", mornye_link_service.cancel)])
    mornye_link_service.start_probe(
        values["url"], values.get("quality", "LOSSLESS"), mornye_prefs.providers_string(),
        host.set_status,
        lambda link, provider="": _ui(host, lambda: show_verify(host, link, provider)),
        lambda res: _ui(host, lambda: host.show(probe_screen, values, res)))


def probe_screen(host, values, res):
    S["verify"] = None
    if not res.get("ok"):
        host.text(res.get("error", "Failed"))
    else:
        secs = int(res.get("duration") or 0)
        head = "%s - %s" % (res.get("title", ""), res.get("artist", ""))
        if secs:
            head += "  (%d:%02d)" % (secs // 60, secs % 60)
        host.text(head)
        usable = 0
        for row in res.get("providers") or []:
            name = NAMES.get(row["provider"], row["provider"])
            if row["ok"]:
                usable += 1
                parts = [row["info"] or "FLAC"]
                if row["size"]:
                    parts.append("%.1f MB" % (row["size"] / 1048576.0))
                if row["kbps"]:
                    parts.append("~%d kbps" % row["kbps"])
                if row["note"]:
                    parts.append(row["note"])
                btn = host.button("%s\n%s" % (name, "  |  ".join(parts)),
                                  lambda p=row["provider"]: ask_target(host, dict(values, providers=p)),
                                  height=dp(84))
                btn.halign = "center"
                btn.bind(width=lambda w, v: setattr(w, "text_size", (v - dp(16), None)))
            else:
                host.text("%s: %s" % (name, row["note"] or "not available"))
        if not usable:
            host.text("Nothing can be downloaded from these services right now")
    host.button("Show log", lambda: host.show(log_screen, res.get("log") or res.get("error") or ""))
    host.back_button()


def ask_target(host, values):
    if values.get("target") in ("phone", "links", "github"):
        return begin_download(host, values)
    host.show(target_screen, values)


def target_screen(host, values):
    host.title("What should be done with the music?")
    for label, target in TARGETS:
        host.button(label, lambda t=target: begin_download(host, dict(values, target=t)))
    host.back_button()


# ---------------------------------------------------------------- download
def begin_download(host, values, message="Downloading music on this phone..."):
    host.log("download:", values.get("url"), "| target", values.get("target"),
             "| providers", values.get("providers") or mornye_prefs.providers_string())
    host.nav.show_working(message, extra_buttons=[("Cancel", mornye_link_service.cancel)])
    mornye_link_service.start_download(
        values.get("url", ""), values.get("quality", "LOSSLESS"),
        values.get("providers") or mornye_prefs.providers_string(),
        host.set_status,
        lambda link, provider="": _ui(host, lambda: show_verify(host, link, provider)),
        lambda res: _ui(host, lambda: finish(host, values, res)),
        target=values.get("target", "phone"))


def finish(host, values, res):
    S["verify"] = None
    log = str(res.get("log") or res.get("error") or "(empty log)")
    buttons = [("Show log", lambda: host.replace(log_screen, log, lambda: finish(host, values, res))),
               ("Copy log", lambda: host.copy(res.get("log", "")))]
    note = ("\nLog saved in the repo: " + res["log_path"]) if res.get("log_path") else ""
    again = lambda: begin_download(host, values)
    if not res.get("ok"):
        buttons = _other_ways(host, values) + [("Try again", again)] + buttons
        host.nav.show_result(res.get("error", "Failed") + note, extra_buttons=_safe_buttons(host, buttons))
        return
    failed = res.get("failed") or []
    saved = res.get("saved") or []
    links = res.get("links") or []
    verb = "uploaded to" if links else "saved in"
    count = len(links) if links else len(saved)
    msg = "%s: %d file(s) %s %s" % (res.get("title") or "Done", count, verb, res.get("folder", ""))
    if res.get("mode") == "links":
        msg = "%s: %d direct link(s) - they expire soon, copy or open them now" % (
            res.get("title") or "Done", count)
    if failed:
        msg += "\n%d failed:\n%s" % (len(failed), "\n".join(failed[:6]))
        buttons.insert(0, ("Copy failed tracks", lambda: host.copy("\n".join(failed))))
        buttons.append(("Try again", again))
        if values.get("target") == "links":      # some tracks have no single direct link
            buttons = _other_ways(host, values) + buttons
    if links:
        host.nav.show_result(msg + note, links=links, extra_buttons=_safe_buttons(host, buttons),
                             category="Mornye")
    else:
        host.nav.show_result(msg + note, extra_buttons=_safe_buttons(host, buttons))


def _other_ways(host, values):
    """The other ways to get the music, shown when a run fails, so a failure does
    not mean starting from the beginning."""
    now = values.get("target") or "phone"
    ways = [(WAYS[t], (lambda t=t: begin_download(host, dict(values, target=t))))
            for t in ("github", "phone", "links") if t != now]
    if values.get("providers") and values["providers"] != mornye_prefs.providers_string():
        # a source was picked on the probe screen: let every ticked source try
        ways.append(("Try all ticked sources", lambda: begin_download(
            host, {k: v for k, v in values.items() if k != "providers"})))
    return ways


def log_screen(host, text, back=None):
    host.title("Mornye log")
    label = Label(text=text, size_hint_y=None, halign="left", valign="top")
    label.bind(width=lambda w, v: setattr(w, "text_size", (v, None)))
    label.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))
    scroll = ScrollView(size_hint=(1, None), height=dp(420))
    scroll.add_widget(label)
    host.add(scroll)
    host.button("Copy log", lambda: host.copy(text))
    host.back_button(to=back)


# ---------------------------------------------------------------- the one-time browser check
def show_verify(host, link, provider=""):
    S["verify"] = {"link": link, "auto": True}
    host.open_url(link)
    _draw(host, verify_screen, link, provider)


def verify_screen(host, link, provider):
    host.title("One-time check" + (" - " + provider if provider else ""))
    host.text("1. In the browser, pass the check. The page closes by itself - that is normal.\n"
              "2. Back in the app, the page opens once more by itself. Tap Copy on the box "
              "with the code (if it does not open, use the button below).\n"
              "3. Come back here, tap Paste, then Continue.")
    host.status()
    host.button("Open the page again", lambda: host.open_url(link))
    code = host.input("Pasted code")

    def submit():
        if mornye_link_service.submit_grant(code.text):
            S["verify"] = None
            host.nav.show_working("Starting the session...",
                                  extra_buttons=[("Cancel", mornye_link_service.cancel)])
        else:
            host.set_status("That is not the verification code")

    def cancel():
        S["verify"] = None
        mornye_link_service.cancel()

    host.button("Continue", submit)
    host.button("Cancel", cancel)

    # The check page closes itself. While the app is in the background Kivy's clock
    # stands still, so a long gap between two ticks means "the app is back": open
    # the page once more, it then shows the code (what the app's own Mornye does
    # from main.py on_resume).
    last = {"t": time.monotonic()}

    def tick():
        now = time.monotonic()
        gap, last["t"] = now - last["t"], now
        state = S.get("verify")
        if gap > 4 and state and state.get("auto"):
            state["auto"] = False
            host.after(0.8, lambda: host.open_url(state["link"]))

    host.every(1.0, tick)


# ---------------------------------------------------------------- settings
def settings_screen(host):
    prefs = mornye_prefs.load()
    order, enabled = prefs["order"], prefs["enabled"]
    if S["registry"] is None:
        S["registry"] = prefs["registry"]
    w = {}

    def save():
        S["registry"] = w["reg"].text
        mornye_prefs.save(order, enabled, S["registry"])

    def toggle(p):
        if p in enabled:
            if len(enabled) > 1:
                enabled.remove(p)
        else:
            enabled.append(p)
        save()
        host.replace(settings_screen)

    def move(i, step):
        j = i + step
        if 0 <= j < len(order):
            order[i], order[j] = order[j], order[i]
            save()
            host.replace(settings_screen)

    host.title("Mornye settings (lab copy)")
    host.text("Search: Spotify. Type a song name instead of a link and pick the track "
              "from the results.")
    host.text("Download order and fallback: tick the sources that may be used. They are "
              "tried from top to bottom; if a track is missing on the first, the next one is tried.")
    for i, p in enumerate(order):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=46, spacing=10)
        tog = Button(text="%d  %s %s" % (i + 1, "[x]" if p in enabled else "[ ]", mornye_prefs.NAMES[p]))
        tog.bind(on_press=lambda inst, p=p: host._safe(toggle, p))
        up = Button(text="Up", size_hint_x=None, width=dp(64))
        up.bind(on_press=lambda inst, i=i: host._safe(move, i, -1))
        down = Button(text="Down", size_hint_x=None, width=dp(72))
        down.bind(on_press=lambda inst, i=i: host._safe(move, i, 1))
        for b in (tog, up, down):
            row.add_widget(b)
        host.add(row)
    host.text("Coming soon (not built in yet): " + ", ".join(mornye_prefs.SOON))
    host.text("Extension repo (registry.json)")
    w["reg"] = host.input(mornye_prefs.DEFAULT_REGISTRY, text=S["registry"])
    host.status(height=90)

    def check():
        save()
        host.set_status("Checking the repo...")

        def work():
            try:
                names = mornye_prefs.check_registry(S["registry"])
                return "Saved. %d extensions: %s" % (len(names), ", ".join(names[:8]))
            except ValueError as e:
                return "Saved, but: %s" % e

        host.background(work, done=lambda text, err: host.set_status(text if err is None else "Error: %s" % err))

    def forget():
        mornye.clear_session()
        host.set_status("Sessions removed: the next download asks for the browser check again")

    host.button("Save and check repo", check)
    host.button("Forget saved sessions (also used by the app's own Mornye)", forget)
    host.back_button(to=lambda: (save(), host.back()))
