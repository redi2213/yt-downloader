"""Page Sniffer - get the m3u8 link of a page with YOUR own login, inside the app.

This does by itself what you did by hand in 1DM: it opens the page in an
in-app browser (Android WebView, over the phone's own internet), you log in
with your account and press play, and the tool catches every .m3u8 link the
page asks for. Then you can copy the link or send it to the lab-download
workflow (GitHub downloads it into a release), the same one Link Lab uses.

Lab plugin: edit this file on the lab branch and open the tool again, no build.
Needs Android (WebView through pyjnius). Login/cookies stay in the WebView.
"""
import json
import os
import re
import traceback
from urllib.parse import urlsplit

try:
    from jnius import PythonJavaClass, java_method
except Exception:  # not running on Android
    PythonJavaClass = None

S = {"web": None, "found": [], "keep": [], "watch": None, "btn": None, "err": None, "loaded": False}
QUALITIES = [("Best", "best"), ("1080", "1080"), ("720", "720"), ("480", "480")]
DESKTOP_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

# Runs inside the page every 2 seconds: lists every m3u8 address the page used.
POLL_JS = r"""(function(){
  try{ if(!window.__sn){ window.__sn=1; window.__snl=[];
    try{ performance.setResourceTimingBufferSize(3000); }catch(e){}
    var abs=function(u){ try{ return new URL(String(u),location.href).href; }catch(e){ return String(u); } };
    var f=window.fetch;
    if(f){ window.fetch=function(a){ try{ window.__snl.push(abs((a&&a.url)||a)); }catch(e){} return f.apply(this,arguments); }; }
    var o=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(m,u){ try{ window.__snl.push(abs(u)); }catch(e){} return o.apply(this,arguments); };
  } }catch(e){}
  var out={};
  var add=function(u){ if(u && typeof u==='string' && /m3u8/i.test(u) && /^https?:/i.test(u)) out[u]=1; };
  try{ performance.getEntriesByType('resource').forEach(function(e){ add(e.name); }); }catch(e){}
  try{ (window.__snl||[]).forEach(add); }catch(e){}
  try{ document.querySelectorAll('video,audio,source').forEach(function(v){ add(v.currentSrc); add(v.src); }); }catch(e){}
  return JSON.stringify(Object.keys(out));
})()"""

if PythonJavaClass is not None:
    class _Run(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]
        __javacontext__ = "app"

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        @java_method("()V")
        def run(self):
            try:
                self.fn()
            except Exception:
                S["err"] = traceback.format_exc()

    class _Value(PythonJavaClass):
        __javainterfaces__ = ["android/webkit/ValueCallback"]
        __javacontext__ = "app"

        def __init__(self, fn):
            super().__init__()
            self.fn = fn

        @java_method("(Ljava/lang/Object;)V")
        def onReceiveValue(self, value):
            try:
                self.fn(value)
            except Exception:
                S["err"] = traceback.format_exc()


# ------------------------------------------------------------------ helpers
def _keep(obj):
    S["keep"].append(obj)          # Java calls these later: keep them alive
    del S["keep"][:-60]


def _ui(fn):
    """Run fn on the Android UI thread."""
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    runner = _Run(fn)
    _keep(runner)
    activity.runOnUiThread(runner)


def _first_url(text):
    text = (text or "").strip()
    m = re.search(r"https?://\S+", text)
    if m:
        return m.group(0).rstrip(").,;\"'")
    if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", text):
        return "https://" + text
    return ""


def _short(url):
    p = urlsplit(url)
    tag = " [master]" if "master" in url.lower() else ""
    tail = (p.path or "")[-42:]
    return "%s...%s%s" % (p.netloc, tail, tag)


def _load(host):
    if S["loaded"]:
        return
    S["loaded"] = True
    S["found"] = list(host.store.get("found") or [])


def _top_px(anchor):
    """Pixels from the top of the screen to the bottom of our button bar."""
    from kivy.core.window import Window
    try:
        _x, y = anchor.to_window(anchor.x, anchor.y)
        top = int(Window.height - y) + 4
        if 80 < top < Window.height * 0.7:
            return top
    except Exception:
        pass
    return int(Window.height * 0.30)


# ------------------------------------------------------------------ first screen
def build(host):
    _load(host)
    host.title("Page Sniffer (m3u8)")
    host.text("Open the series / movie page here, log in with your own account and press play. "
              "The tool catches the .m3u8 link the page uses (like opening it in 1DM). "
              "It uses the phone's own internet, so turn any VPN off if the site needs "
              "your local connection.")
    start = _first_url(host.prefill) or _first_url(host.paste()) or host.store.get("last_url", "")
    field = host.input("Page link", text=start)
    host.text("Browser type (try Desktop if the page does not play)")
    ua = host.choice([("Phone", "phone"), ("Desktop", "desktop")], default=host.store.get("ua", "phone"))
    host.status()

    def go():
        url = _first_url(field.text)
        if not url:
            host.set_status("Paste a page link first")
            return
        host.store.set("last_url", url)
        host.store.set("ua", ua.value)
        host.show(sniff_screen, url, ua.value == "desktop")

    host.button("Open page and watch for m3u8", go)
    if S["found"]:
        host.button("Found links (%d)" % len(S["found"]), lambda: host.show(found_screen))
    host.button("Log out of all sites (clear cookies)", lambda: _clear_cookies(host))
    host.row([("Copy log", lambda: _copy_log(host)), ("Clear log", lambda: _clear_log(host))])
    host.back_button("Back")


def _clear_cookies(host):
    a = host.android()
    if a is None:
        host.set_status("Needs Android")
        return
    CookieManager = a.autoclass("android.webkit.CookieManager")
    _ui(lambda: CookieManager.getInstance().removeAllCookies(None))
    host.set_status("Cookies cleared")


# ------------------------------------------------------------------ browser screen
def sniff_screen(host, url, desktop):
    if PythonJavaClass is None or host.android() is None:
        host.title("Not available")
        host.text("This tool needs the Android WebView, so it only works on the phone.")
        host.back_button()
        return
    host.status()
    host.set_status("Loading... log in, then press play.")
    page_back, reload_btn, links_btn = host.row([
        ("< Page", lambda: _web_do(host, "back")),
        ("Reload", lambda: _web_do(host, "reload")),
        ("Links (%d)" % len(S["found"]), lambda: _to_links(host)),
    ])
    S["btn"] = links_btn
    anchor = host.back_button("Back (close page)", to=lambda: _leave(host))
    _watch(host)
    host.after(0.4, lambda: _open(host, url, desktop, anchor))
    host.every(2.0, lambda: _poll(host))


def _watch(host):
    """Closes the browser if the user leaves this screen in any other way."""
    from kivy.clock import Clock
    if S["watch"] is not None:
        S["watch"].cancel()
    epoch = host._epoch

    def check(dt):
        if S["web"] is None or host._epoch != epoch:
            _close_web()
            return False
    S["watch"] = Clock.schedule_interval(check, 0.4)


def _open(host, url, desktop, anchor):
    from kivy.core.window import Window
    a = host.android()
    _close_web(keep_watch=True)
    top = _top_px(anchor)
    height = max(200, int(Window.height) - top)
    WebView = a.autoclass("android.webkit.WebView")
    WebViewClient = a.autoclass("android.webkit.WebViewClient")
    CookieManager = a.autoclass("android.webkit.CookieManager")
    LP = a.autoclass("android.widget.FrameLayout$LayoutParams")
    activity = a.activity

    def make():
        wv = WebView(activity)
        st = wv.getSettings()
        st.setJavaScriptEnabled(True)
        st.setDomStorageEnabled(True)
        st.setUseWideViewPort(True)
        st.setLoadWithOverviewMode(True)
        agent = str(st.getUserAgentString() or "")
        st.setUserAgentString(DESKTOP_UA if desktop else agent.replace("; wv", "").replace("Version/4.0 ", ""))
        cookies = CookieManager.getInstance()
        cookies.setAcceptCookie(True)
        try:
            cookies.setAcceptThirdPartyCookies(wv, True)
        except Exception:
            pass
        wv.setWebViewClient(WebViewClient())   # keeps links inside this view
        params = LP(-1, height, 48)            # match width, fixed height, gravity top
        params.topMargin = top
        activity.addContentView(wv, params)
        wv.loadUrl(url)
        S["web"] = wv

    host.log("open", url[:120], "desktop" if desktop else "phone")
    _ui(make)


def _poll(host):
    if S["err"]:
        host.log("ERROR\n" + S["err"])
        host.set_status("Browser error: " + S["err"].strip().splitlines()[-1][:110])
        S["err"] = None
    wv = S["web"]
    if wv is None:
        return
    callback = _Value(lambda raw: _on_value(host, raw))
    _keep(callback)
    _ui(lambda: wv.evaluateJavascript(POLL_JS, callback))


def _on_value(host, raw):
    """Called on the Java UI thread with the JSON the page script returned."""
    text = raw if isinstance(raw, str) else (raw.toString() if raw is not None else "")
    if not text or text == "null":
        return
    value = json.loads(text)
    urls = json.loads(value) if isinstance(value, str) else value
    host.nav.schedule(lambda: _merge(host, urls))


def _merge(host, urls):
    new = [u for u in urls if u not in S["found"]]
    if not new:
        return
    S["found"].extend(new)
    host.store.set("found", S["found"][-30:])
    for u in new:
        host.log("found", u[:100])
    try:
        if S["btn"] is not None:
            S["btn"].text = "Links (%d)" % len(S["found"])
        host.set_status("Found %d new m3u8 link(s). Open Links." % len(new))
    except Exception:
        pass


def _web_do(host, what):
    wv = S["web"]
    if wv is None:
        return
    if what == "back":
        _ui(lambda: wv.goBack() if wv.canGoBack() else None)
    else:
        _ui(lambda: wv.reload())


def _to_links(host):
    _close_web()
    host.replace(found_screen)


def _leave(host):
    _close_web()
    host.back()


def _close_web(keep_watch=False):
    wv, S["web"] = S["web"], None
    if not keep_watch and S["watch"] is not None:
        try:
            S["watch"].cancel()
        except Exception:
            pass
        S["watch"] = None
    if wv is None:
        return

    def kill():
        try:
            from jnius import cast
            parent = wv.getParent()
            if parent is not None:
                cast("android.view.ViewGroup", parent).removeView(wv)
        except Exception:
            pass
        try:
            wv.destroy()
        except Exception:
            pass
    try:
        _ui(kill)
    except Exception:
        pass


# ------------------------------------------------------------------ found links
def found_screen(host):
    _close_web()
    links = list(S["found"])
    host.title("Stream links (%d)" % len(links))
    if not links:
        host.text("Nothing found yet. Open a page, press play, and wait a few seconds.")
        host.back_button()
        return
    host.text("Quality for the download (used when the link is a master playlist; "
              "a single-quality link ignores it).")
    quality = host.choice(QUALITIES, default=host.store.get("quality", "720"),
                          on_change=lambda v: host.store.set("quality", v))
    host.status()
    for url in reversed(links[-10:]):
        host.text(_short(url))
        host.row([
            ("Download", lambda u=url: host.show(download_screen, u, quality.value)),
            ("Copy", lambda u=url: (host.copy(u), host.set_status("Copied"))),
        ])
    host.button("Copy all", lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    host.button("Share", lambda: host.share_text("\n".join(links)))
    host.button("Clear list", lambda: (S["found"].clear(), host.store.delete("found"),
                                       host.replace(found_screen)))
    host.back_button()


def _link_lab_options(host):
    """proxy / v2ray the user saved in Link Lab (same keys), empty if none."""
    try:
        with open(os.path.join(host.data_dir, "link_lab.json"), encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("proxy") or ""), str(data.get("v2ray") or "")
    except Exception:
        return "", ""


def download_screen(host, url, quality):
    label = quality if str(quality) == "best" else "%sp" % quality
    host.title("Downloading (%s)" % label)
    host.text("Runs lab-download.yml from the lab branch and saves the video in a GitHub "
              "release. You can leave this screen; the run keeps going.")
    host.status(height=560)
    host.set_status("Starting...")
    proxy, v2ray = _link_lab_options(host)
    inputs = {"url": url, "quality": str(quality), "proxy": proxy, "v2ray_config": v2ray}

    def work():
        run_id = host.gh.dispatch("lab-download.yml", inputs)
        if not run_id:
            raise RuntimeError("Could not find the workflow run on GitHub")
        host.log("lab-download run", run_id)
        host.set_status("Run %s started..." % run_id)
        try:
            from labx import lab_jobs
        except Exception:
            lab_jobs = None
        if lab_jobs is not None:
            conclusion = lab_jobs.wait(host, run_id, host.set_status)   # the jobs of the run
        else:
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
        host.text("The run succeeded but no release file was found (run %s)." % run_id)
    else:
        host.title("Downloaded (%d file%s)" % (len(links), "" if len(links) == 1 else "s"))
        host.text("Saved in release run-%s. Open it from Release History in the app.\n\n%s"
                  % (run_id, "\n".join(links)))
    host.status()
    if links:
        host.button("Copy link%s" % ("" if len(links) == 1 else "s"),
                    lambda: (host.copy("\n".join(links)), host.set_status("Copied")))
    host.back_button()


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
