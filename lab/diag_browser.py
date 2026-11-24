"""Lab: Browser capture. Claude's browser job: a real WebView opens a page, tries to start
the video and records what the browser asks for and gets back. Result goes to the repo.

Why: some sites answer plain HTTP clients (yt-dlp, python) with an error but work in a real
browser. This shows what the real browser does (status of the media request, first bytes,
cookie names, user agent) so Claude can copy it.

Job file (written by Claude): config branch, diag-jobs/browser.json
  {"id": "...", "title": "...", "url": "https://...", "wait_s": 40,
   "pattern": "get_stream|\\.mp4|\\.m3u8", "desktop": false, "auto_play": true}
Result: config/diag-results/latest.txt (same place as Diagnostics).
Needs Android (WebView through pyjnius). No build needed to change this file.
"""
import base64
import json
import re
import time
import traceback

try:
    from jnius import PythonJavaClass, java_method
except Exception:  # not running on Android
    PythonJavaClass = None

REPO = "redi2213/yt-downloader"
API = "https://api.github.com/repos/" + REPO
RESULT_BRANCH = "config"
RESULT_DIR = "diag-results"
JOB_PATH = "diag-jobs/browser.json"
KEEP = 20
DEFAULT_RX = r"get_stream|\.mp4|\.m3u8|\.mpd|\.webm"
DESKTOP_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0.0.0 Safari/537.36")

S = {"web": None, "keep": [], "watch": None, "err": None, "job": {}, "data": {}, "t0": 0.0,
     "ending": False, "play": 0, "fetched": False}

_HIDE = [
    (re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "<token>"),
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key)\b\s*[:=]\s*[^\n]+"), r"\1: <hidden>"),
    (re.compile(r"(?i)([?&;][\w-]*(?:token|key|secret|passw|sig|session|auth)[\w-]*)=[^&\s\"']+"), r"\1=<hidden>"),
]

# Runs inside the page every 2 seconds. __RX__ is replaced by a JS string.
POLL_JS = r"""(function(){
  var RX=new RegExp(__RX__,'i'); var out={};
  try{ if(!window.__dg){ window.__dg=1; window.__dgl=[];
    var abs=function(u){try{return new URL(String(u),location.href).href;}catch(e){return String(u);}};
    var f=window.fetch;
    if(f){window.fetch=function(a){try{window.__dgl.push({u:abs((a&&a.url)||a),k:'fetch'});}catch(e){} return f.apply(this,arguments);};}
    var op=XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open=function(m,u){try{window.__dgl.push({u:abs(u),k:'xhr'});}catch(e){} return op.apply(this,arguments);};
  }}catch(e){}
  try{ out.href=location.href; out.ua=navigator.userAgent; }catch(e){}
  try{ out.cookies=document.cookie.split(';').map(function(c){return c.split('=')[0].trim();}).filter(Boolean); }catch(e){}
  var ent=[];
  try{ performance.getEntriesByType('resource').forEach(function(e){ if(RX.test(e.name)) ent.push({n:e.name,i:e.initiatorType,s:e.responseStatus,t:e.transferSize,b:e.encodedBodySize}); }); }catch(e){}
  out.entries=ent.slice(0,60);
  try{ out.hooks=(window.__dgl||[]).filter(function(x){return RX.test(x.u);}).slice(0,40); }catch(e){}
  try{ out.videos=Array.prototype.map.call(document.querySelectorAll('video'),function(v){return {cur:v.currentSrc,src:v.src,ns:v.networkState,rs:v.readyState,err:v.error?v.error.code:null,paused:v.paused,dur:v.duration};}); }catch(e){}
  out.tr=window.__tr||null;
  return JSON.stringify(out);
})()"""

AUTOPLAY_JS = r"""(function(){var r=[];
  try{document.querySelectorAll('video').forEach(function(v){try{v.muted=true;v.play();r.push('video.play');}catch(e){r.push('play error '+e);}});}catch(e){}
  ['.fp-play','.kt-play','.vjs-big-play-button','.jw-icon-display','.plyr__control--overlaid','[class*="play-btn"]','[class*="big-play"]','[class*="PlayButton"]','.fp-ui'].forEach(function(s){
    try{var e=document.querySelector(s);if(e){e.click();r.push('click '+s);}}catch(x){}});
  return JSON.stringify(r);})()"""

# Reads only the first chunk of each candidate (never the whole file).
FETCH_JS = r"""(function(){ var list=__LIST__; window.__tr=[];
 list.forEach(function(u){
  var rec=function(o){ o.u=u; window.__tr.push(o); };
  fetch(u,{headers:{'Range':'bytes=0-1023'},credentials:'include'}).then(function(r){
    var h=r.headers; var base={status:r.status,type:h.get('content-type'),len:h.get('content-length'),range:h.get('content-range')};
    var rd=(r.body&&r.body.getReader)?r.body.getReader():null;
    if(!rd){ base.note='no stream reader'; rec(base); return; }
    return rd.read().then(function(x){ try{rd.cancel();}catch(e){}
      var b=(x&&x.value)?x.value:new Uint8Array(0); var a=b.slice(0,12);
      base.bytes=b.length;
      base.hex=Array.prototype.map.call(a,function(v){return ('0'+v.toString(16)).slice(-2);}).join('');
      var t=''; try{t=new TextDecoder().decode(b.slice(0,60));}catch(e){}
      base.text=t.replace(/[^\x20-\x7e]/g,'.'); rec(base); });
  }).catch(function(e){ rec({error:String(e)}); });
 });
 return 'started';})()"""

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
def _hide(text):
    text = str(text)
    for rx, rep in _HIDE:
        text = rx.sub(rep, text)
    return text


def _keep(obj):
    S["keep"].append(obj)          # Java calls these later: keep them alive
    del S["keep"][:-60]


def _ui(fn):
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    runner = _Run(fn)
    _keep(runner)
    activity.runOnUiThread(runner)


def _top_px(anchor):
    from kivy.core.window import Window
    try:
        _x, y = anchor.to_window(anchor.x, anchor.y)
        top = int(Window.height - y) + 4
        if 80 < top < Window.height * 0.7:
            return top
    except Exception:
        pass
    return int(Window.height * 0.30)


def _fresh():
    return {"href": "", "ua": "", "cookies": [], "videos": [], "entries": {}, "hooks": {}, "tr": None, "actions": []}


def _read_job(host):
    r = host.gh.request("GET", API + "/contents/" + JOB_PATH + "?ref=" + RESULT_BRANCH).json()
    job = json.loads(base64.b64decode(r["content"]).decode("utf-8"))
    if not str(job.get("url", "")).startswith("http"):
        raise RuntimeError("the job has no valid url")
    return job


def _put(host, path, text, msg):
    url = API + "/contents/" + path
    sha = None
    try:
        sha = host.gh.request("GET", url + "?ref=" + RESULT_BRANCH).json().get("sha")
    except Exception:
        sha = None
    body = {"message": msg, "branch": RESULT_BRANCH,
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    host.gh.request("PUT", url, json=body)


def _prune(host):
    try:
        items = host.gh.request("GET", API + "/contents/" + RESULT_DIR + "?ref=" + RESULT_BRANCH).json()
        old = sorted((i for i in items if i.get("name", "").endswith(".txt") and i.get("name") != "latest.txt"),
                     key=lambda i: i["name"])
        for i in old[:-KEEP]:
            host.gh.request("DELETE", API + "/contents/" + i["path"],
                            json={"message": "diag: prune", "sha": i["sha"], "branch": RESULT_BRANCH})
    except Exception:
        pass


def _save(host, report):
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    try:
        _put(host, RESULT_DIR + "/latest.txt", report, "diag: browser")
        _put(host, "%s/%s-browser.txt" % (RESULT_DIR, stamp), report, "diag: browser")
    except Exception as e:
        return "NOT saved to repo: %s" % str(e)[:120]
    _prune(host)
    return "Saved: %s branch, %s/latest.txt" % (RESULT_BRANCH, RESULT_DIR)


# ------------------------------------------------------------------ screens
def build(host):
    host.title("Browser capture")
    host.text("Opens the page Claude prepared in an in-app browser, tries to start the video, "
              "watches what the browser requests and saves the result to the repo. "
              "If the video does not start by itself, tap play once.")
    host.status()

    def go():
        host.set_status("Reading Claude's browser job...")

        def done(job, err):
            if err is not None:
                host.set_status("Failed: %s" % str(err)[:120])
                return
            host.show(capture_screen, job)

        host.background(lambda: _read_job(host), done=done)

    host.button("Start Claude's browser job", go)
    host.back_button("Back")


def capture_screen(host, job):
    if PythonJavaClass is None or host.android() is None:
        host.title("Not available")
        host.text("This tool needs the Android WebView, so it only works on the phone.")
        host.back_button()
        return
    S.update({"job": job, "data": _fresh(), "t0": time.time(), "ending": False, "play": 0,
              "fetched": False, "err": None})
    host.status()
    host.set_status("Loading... tap play if the video does not start.")
    host.row([
        ("< Page", lambda: _web_do("back")),
        ("Reload", lambda: _web_do("reload")),
        ("Finish now", lambda: _end(host)),
    ])
    anchor = host.back_button("Back (close page)", to=lambda: _leave(host))
    _watch(host)
    host.after(0.4, lambda: _open(host, job, anchor))
    host.every(2.0, lambda: _tick(host))


def report_screen(host, report, saved):
    host.title("Browser result")
    host.status()
    host.set_status(saved)
    shown = report[:2500]
    if len(report) > 2500:
        shown += "\n... (cut here; Copy gives everything)"
    host.text(shown)
    host.button("Copy all", lambda: host.copy(report or "(empty)"))
    host.back_button()


# ------------------------------------------------------------------ browser
def _watch(host):
    from kivy.clock import Clock
    if S["watch"] is not None:
        S["watch"].cancel()
    epoch = host._epoch

    def check(dt):
        if S["web"] is None or host._epoch != epoch:
            _close_web()
            return False
    S["watch"] = Clock.schedule_interval(check, 0.4)


def _open(host, job, anchor):
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
    desktop = bool(job.get("desktop"))
    url = str(job["url"])

    def make():
        wv = WebView(activity)
        st = wv.getSettings()
        st.setJavaScriptEnabled(True)
        st.setDomStorageEnabled(True)
        st.setUseWideViewPort(True)
        st.setLoadWithOverviewMode(True)
        try:
            st.setMediaPlaybackRequiresUserGesture(False)
        except Exception:
            pass
        agent = str(st.getUserAgentString() or "")
        st.setUserAgentString(DESKTOP_UA if desktop else agent.replace("; wv", "").replace("Version/4.0 ", ""))
        cookies = CookieManager.getInstance()
        cookies.setAcceptCookie(True)
        try:
            cookies.setAcceptThirdPartyCookies(wv, True)
        except Exception:
            pass
        wv.setWebViewClient(WebViewClient())
        params = LP(-1, height, 48)
        params.topMargin = top
        activity.addContentView(wv, params)
        wv.loadUrl(url)
        S["web"] = wv

    host.log("browser job", url[:120], "desktop" if desktop else "phone")
    _ui(make)


def _web_do(what):
    wv = S["web"]
    if wv is None:
        return
    if what == "back":
        _ui(lambda: wv.goBack() if wv.canGoBack() else None)
    else:
        _ui(lambda: wv.reload())


def _eval(js, tag=None):
    wv = S["web"]
    if wv is None:
        return
    cb = None
    if tag:
        def got(raw, tag=tag):
            S["data"]["actions"].append("%s: %s" % (tag, str(raw)[:240]))
        cb = _Value(got)
        _keep(cb)
    _ui(lambda: wv.evaluateJavascript(js, cb))


def _rx():
    return str(S["job"].get("pattern") or DEFAULT_RX)


def _poll(host):
    wv = S["web"]
    if wv is None:
        return
    callback = _Value(lambda raw: _on_value(host, raw))
    _keep(callback)
    js = POLL_JS.replace("__RX__", json.dumps(_rx()))
    _ui(lambda: wv.evaluateJavascript(js, callback))


def _on_value(host, raw):
    text = raw if isinstance(raw, str) else (raw.toString() if raw is not None else "")
    if not text or text == "null":
        return
    value = json.loads(text)
    obj = json.loads(value) if isinstance(value, str) else value
    host.nav.schedule(lambda: _merge(obj))


def _merge(obj):
    d = S["data"]
    for k in ("href", "ua", "cookies", "videos"):
        if k in obj and obj[k] is not None:
            d[k] = obj[k]
    for e in obj.get("entries") or []:
        d["entries"][e.get("n")] = e
    for h in obj.get("hooks") or []:
        d["hooks"][h.get("u")] = h.get("k")
    if obj.get("tr"):
        d["tr"] = obj["tr"]


def _fetch_test():
    d = S["data"]
    cands = []
    for u in list(d["entries"].keys()) + list(d["hooks"].keys()) + [v.get("cur") or v.get("src") for v in d["videos"]]:
        if u and u.startswith("http") and u not in cands:
            cands.append(u)
    cands = cands[:3]
    if not cands:
        d["actions"].append("in-page fetch test: no candidate url seen yet")
        return
    _eval(FETCH_JS.replace("__LIST__", json.dumps(cands)), "fetch test started")


def _tick(host):
    if S["err"]:
        host.log("ERROR\n" + S["err"])
        host.set_status("Browser error: " + S["err"].strip().splitlines()[-1][:110])
        S["err"] = None
    if S["web"] is None or S["ending"]:
        return
    el = time.time() - S["t0"]
    wait = float(S["job"].get("wait_s", 40))
    _poll(host)
    if S["job"].get("auto_play", True):
        if el > 4 and S["play"] == 0:
            S["play"] = 1
            _eval(AUTOPLAY_JS, "autoplay 1")
        elif el > 14 and S["play"] == 1:
            S["play"] = 2
            _eval(AUTOPLAY_JS, "autoplay 2")
    if el > wait * 0.6 and not S["fetched"]:
        S["fetched"] = True
        _fetch_test()
    try:
        host.set_status("Watching... %d of %d s. Tap play if nothing starts." % (el, wait))
    except Exception:
        pass
    if el >= wait:
        _end(host)


def _end(host):
    if S["ending"] or S["web"] is None:
        return
    S["ending"] = True
    try:
        host.set_status("Collecting the result...")
    except Exception:
        pass
    if not S["fetched"]:
        S["fetched"] = True
        _fetch_test()
        host.after(3.0, lambda: _poll(host))
        host.after(4.5, lambda: _finish(host))
    else:
        _poll(host)
        host.after(2.5, lambda: _finish(host))


def _leave(host):
    S["ending"] = True
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


# ------------------------------------------------------------------ report
def _report():
    d, job = S["data"], S["job"]
    L = ["# Diagnostics (browser) %s UTC" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
         "", "job: %s" % job.get("id"), "title: %s" % job.get("title"), "",
         "## Browser capture (browser)",
         "start_url: %s" % job.get("url"),
         "final_url: %s" % d["href"],
         "user_agent: %s" % d["ua"],
         "cookie names (%d): %s" % (len(d["cookies"]), ", ".join(d["cookies"]) or "none"),
         "pattern: %s" % _rx()]
    L.append("actions:")
    L.extend("  " + a for a in d["actions"]) if d["actions"] else L.append("  none")
    L.append("videos (%d):" % len(d["videos"]))
    for v in d["videos"]:
        L.append("  cur=%s src=%s networkState=%s readyState=%s error=%s paused=%s duration=%s"
                 % (str(v.get("cur"))[:160], str(v.get("src"))[:160], v.get("ns"), v.get("rs"),
                    v.get("err"), v.get("paused"), v.get("dur")))
    L.append("resource entries matching (%d): status | initiator | transfer | body | name" % len(d["entries"]))
    for e in list(d["entries"].values())[:30]:
        L.append("  %s | %s | %s | %s | %s" % (e.get("s"), e.get("i"), e.get("t"), e.get("b"), str(e.get("n"))[:200]))
    L.append("fetch/xhr calls matching (%d):" % len(d["hooks"]))
    for u, k in list(d["hooks"].items())[:20]:
        L.append("  %s %s" % (k, str(u)[:200]))
    L.append("in-page fetch test (first chunk, same cookies as the page):")
    if d["tr"]:
        for t in d["tr"]:
            L.append("  " + json.dumps(t, ensure_ascii=False)[:400])
    else:
        L.append("  no result")
    return _hide("\n".join(L))[:24000]


def _finish(host):
    if S.get("done_once") == S["t0"]:
        return
    S["done_once"] = S["t0"]
    report = _report()
    _close_web()

    def work():
        return report, _save(host, report)

    def done(res, err):
        if err is not None:
            host.set_status("Failed: %s" % str(err)[:120])
            return
        host.replace(report_screen, res[0], res[1])

    host.background(work, done=done)
