package org.redi2213.ytbridge;

import android.app.Activity;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebStorage;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.io.ByteArrayInputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * The in-app browser's native half. pyjnius cannot subclass WebViewClient, so this class owns the
 * WebView, the round badge (top right) and the list of media seen by shouldInterceptRequest. Python
 * (core/android_browser.py) only calls the static methods below and polls poll() twice a second.
 * Everything that touches a view runs on the UI thread.
 */
public class BrowserHelper {
    private static Activity activity;
    private static WebView web;
    private static Button badge;
    private static int topPx = 0;
    private static String badgeText = "";
    private static boolean visible = false;

    private static final Object LOCK = new Object();
    private static final List<JSONObject> pending = new ArrayList<JSONObject>();
    private static final Set<String> seen = new HashSet<String>();
    private static volatile String pageUrl = "";
    private static volatile String pageTitle = "";
    private static volatile int epoch = 0;
    private static volatile boolean badgeTapped = false;
    private static volatile boolean canBack = false;
    private static String ua = "";
    private static String baseUa = "";
    private static String desktopUa = "";
    private static volatile boolean desktop = false;
    private static volatile boolean darkOn = false;
    private static volatile boolean noImages = false;
    private static volatile boolean noVideos = false;
    private static volatile int findIdx = 0;
    private static volatile int findCount = 0;

    // The extensions to report. Python tells the list (setExtensions: the file types switched on in Browser
    // settings); until then only video and audio, as before.
    private static final String DEFAULT_EXTS = "mp4|m4v|webm|mkv|mov|m3u8|mpd|mp3|m4a|aac|ogg|opus|flac|wav";
    private static volatile String extAlt = DEFAULT_EXTS;
    private static volatile Pattern extPattern = Pattern.compile("(?i)\\.(" + DEFAULT_EXTS + ")(?:$|[?#&;])");

    private static final String SCAN_HEAD =
        "(function(){var o=[];"
      + "function add(u){if(u&&typeof u==='string'&&u.indexOf('blob:')!==0&&u.indexOf('data:')!==0){try{o.push(new URL(u,location.href).href)}catch(e){}}}"
      + "document.querySelectorAll('video,audio,source').forEach(function(e){add(e.currentSrc||e.src)});"
      + "document.querySelectorAll(\"meta[property='og:video'],meta[property='og:video:url'],meta[property='og:video:secure_url'],meta[property='og:audio']\").forEach(function(m){add(m.content)});";
    private static final String SCAN_TAIL =
        "return JSON.stringify(o.filter(function(x,i){return o.indexOf(x)===i}))})()";

    /** The page scan: media elements, plus links (a[href]) to a file of a switched-on type or with a download attribute. */
    private static String scanJs() {
        String alt = extAlt;
        String links = "document.querySelectorAll('a[download]').forEach(function(a){add(a.href)});";
        if (alt != null && alt.length() > 0) {
            links += "var re=new RegExp('\\\\.(" + alt + ")($|[?#&;])','i');"
                   + "document.querySelectorAll('a[href]').forEach(function(a){var h=a.href;if(h&&re.test(h))add(h)});";
        }
        return SCAN_HEAD + links + SCAN_TAIL;
    }

    private static final Runnable SCAN_LATER = new Runnable() {
        public void run() { scan(); }
    };

    private static void ui(Runnable r) {
        if (activity != null) activity.runOnUiThread(r);
    }

    // ---- view set-up ----------------------------------------------------------------
    public static void create(final Activity act, final int top) {
        activity = act;
        topPx = top;
        ui(new Runnable() {
            public void run() {
                if (web != null) return;
                web = new WebView(act);
                WebSettings s = web.getSettings();
                s.setJavaScriptEnabled(true);
                s.setDomStorageEnabled(true);
                s.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
                s.setBuiltInZoomControls(true);
                s.setDisplayZoomControls(false);
                s.setUseWideViewPort(true);
                s.setLoadWithOverviewMode(true);
                // a "wv" WebView user agent is refused by some sites (Google, YouTube)
                ua = s.getUserAgentString().replace("; wv", "");
                s.setUserAgentString(ua);
                baseUa = ua;
                desktopUa = makeDesktopUa(ua);
                CookieManager cm = CookieManager.getInstance();
                cm.setAcceptCookie(true);
                cm.setAcceptThirdPartyCookies(web, true);
                web.setWebViewClient(new Client());
                web.addJavascriptInterface(new NetBridge(), "YtbNet");
                web.setFindListener(new WebView.FindListener() {
                    public void onFindResultReceived(int active, int total, boolean done) {
                        findCount = total;
                        findIdx = total > 0 ? active + 1 : 0;
                    }
                });
                // a download the page starts (a clicked link, an attachment) is reported to the list with the
                // server's headers (type, name, size)
                web.setDownloadListener(new DownloadListener() {
                    public void onDownloadStart(String url, String userAgent, String contentDisposition,
                                                String mimetype, long contentLength) {
                        recordDownload(url, contentDisposition, mimetype, contentLength);
                    }
                });
                web.setVisibility(View.GONE);
                FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT);
                lp.topMargin = topPx;
                act.addContentView(web, lp);

                float d = act.getResources().getDisplayMetrics().density;
                badge = new Button(act);
                badge.setAllCaps(false);
                badge.setTextColor(Color.WHITE);
                badge.setTextSize(15);
                badge.setPadding(0, 0, 0, 0);
                GradientDrawable g = new GradientDrawable();
                g.setShape(GradientDrawable.OVAL);
                g.setColor(Color.parseColor("#E53935"));
                badge.setBackground(g);
                badge.setVisibility(View.GONE);
                badge.setOnClickListener(new View.OnClickListener() {
                    public void onClick(View v) { badgeTapped = true; }
                });
                int size = (int) (52 * d);
                FrameLayout.LayoutParams bl = new FrameLayout.LayoutParams(size, size);
                bl.gravity = Gravity.TOP | Gravity.END;
                bl.topMargin = topPx + (int) (12 * d);
                bl.rightMargin = (int) (12 * d);
                act.addContentView(badge, bl);
            }
        });
    }

    public static void setTop(final int top) {
        topPx = top;
        ui(new Runnable() {
            public void run() {
                if (web != null && web.getLayoutParams() instanceof FrameLayout.LayoutParams) {
                    FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) web.getLayoutParams();
                    lp.topMargin = topPx;
                    web.setLayoutParams(lp);
                }
                if (badge != null && badge.getLayoutParams() instanceof FrameLayout.LayoutParams) {
                    float d = activity.getResources().getDisplayMetrics().density;
                    FrameLayout.LayoutParams bl = (FrameLayout.LayoutParams) badge.getLayoutParams();
                    bl.topMargin = topPx + (int) (12 * d);
                    badge.setLayoutParams(bl);
                }
            }
        });
    }

    private static void applyBadge() {
        if (badge == null) return;
        badge.setText(badgeText);
        badge.setVisibility(visible && badgeText.length() > 0 ? View.VISIBLE : View.GONE);
    }

    public static void setVisible(final boolean v) {
        ui(new Runnable() {
            public void run() {
                visible = v;
                if (web != null) web.setVisibility(v ? View.VISIBLE : View.GONE);
                applyBadge();
            }
        });
    }

    public static void setBadge(final String text) {
        ui(new Runnable() {
            public void run() {
                badgeText = text == null ? "" : text;
                applyBadge();
            }
        });
    }

    // ---- navigation -----------------------------------------------------------------
    public static void load(final String url) {
        ui(new Runnable() { public void run() { if (web != null) web.loadUrl(url); } });
    }

    public static void goBack() {
        ui(new Runnable() { public void run() { if (web != null && web.canGoBack()) web.goBack(); } });
    }

    public static void goForward() {
        ui(new Runnable() { public void run() { if (web != null && web.canGoForward()) web.goForward(); } });
    }

    public static void reload() {
        ui(new Runnable() { public void run() { if (web != null) web.reload(); } });
    }

    public static boolean canBack() { return canBack; }

    /** The list's Refresh: forget what was seen and load the page again, so every file is reported once more. */
    public static void rescan() {
        synchronized (LOCK) {
            seen.clear();
            pending.clear();
        }
        ui(new Runnable() { public void run() { if (web != null) web.reload(); } });
    }

    // ---- what was found -------------------------------------------------------------
    private static void newPage(String url) {
        synchronized (LOCK) {
            if (url == null || url.equals(pageUrl)) return;
            pageUrl = url;
            pageTitle = "";
            epoch++;
            netLog.clear();
            seen.clear();
            pending.clear();
        }
    }

    private static void record(String u, String src) {
        add(u, src, null, null, -1, false);
    }

    private static void recordDownload(String u, String disp, String mime, long len) {
        add(u, "download", mime, disp, len, true);
    }

    /** Remembers one link for poll(). A download event (force) is reported even when the link was seen before:
     *  it carries the server's headers, and the list moves the file to the top. */
    private static void add(String u, String src, String mime, String disp, long len, boolean force) {
        if (u == null || !(u.startsWith("http://") || u.startsWith("https://"))) return;
        Uri p = Uri.parse(u);
        String key = (p.getHost() == null ? "" : p.getHost()) + (p.getPath() == null ? "" : p.getPath());
        synchronized (LOCK) {
            if (!seen.add(key) && !force) return;
            try {
                JSONObject o = new JSONObject();
                o.put("url", u);
                o.put("src", src);
                o.put("referer", pageUrl);
                o.put("ua", ua);
                String c = CookieManager.getInstance().getCookie(u);
                o.put("cookie", c == null ? "" : c);
                o.put("mime", mime == null ? "" : mime);
                o.put("disp", disp == null ? "" : disp);
                o.put("len", len);
                pending.add(o);
            } catch (Exception e) { }
        }
    }

    /** The file types to report, as extensions without dots ("zip,pdf,mp4"): see core/browser_media.Rules.csv(). */
    public static void setExtensions(String csv) {
        StringBuilder alt = new StringBuilder();
        if (csv != null) {
            for (String s : csv.split(",")) {
                s = s.trim().toLowerCase();
                if (s.startsWith(".")) s = s.substring(1);
                if (s.matches("[a-z0-9]{1,8}")) {
                    if (alt.length() > 0) alt.append('|');
                    alt.append(s);
                }
            }
        }
        extAlt = alt.toString();
        extPattern = alt.length() == 0 ? null : Pattern.compile("(?i)\\.(" + alt + ")(?:$|[?#&;])");
    }

    static void scan() {
        final WebView w = web;
        if (w == null) return;
        w.evaluateJavascript(scanJs(), new ValueCallback<String>() {
            public void onReceiveValue(String value) {
                try {
                    if (value == null || value.equals("null")) return;
                    Object v = new JSONTokener(value).nextValue();
                    if (!(v instanceof String)) return;
                    JSONArray arr = new JSONArray((String) v);
                    for (int i = 0; i < arr.length(); i++) record(arr.getString(i), "page");
                } catch (Exception e) { }
            }
        });
    }

    /** JSON: {epoch, page, title, tapped, can_back, items:[{url, src, referer, ua, cookie, mime, disp, len}]} - new items only. */
    public static String poll() {
        JSONObject out = new JSONObject();
        synchronized (LOCK) {
            JSONArray arr = new JSONArray();
            for (JSONObject o : pending) arr.put(o);
            pending.clear();
            try {
                out.put("epoch", epoch);
                out.put("page", pageUrl);
                out.put("title", pageTitle);
                out.put("tapped", badgeTapped);
                out.put("can_back", canBack);
                out.put("find_idx", findIdx);
                out.put("find_n", findCount);
                out.put("items", arr);
            } catch (Exception e) { }
            badgeTapped = false;
        }
        return out.toString();
    }

    // ---- network log: Fetch / XHR requests of the page (headers and body) for "Copy as cURL" -----------------
    // A small script (NET_JS) wraps fetch and XMLHttpRequest in the page and reports every request to NetBridge.
    // Requests made before the script runs (very early in a page load) are not seen. Python reads netLog().
    private static final List<String> netLog = new ArrayList<String>();
    private static final int NET_MAX = 150;
    private static final int NET_IN_MAX = 600000;
    private static final String NET_JS =
        "(function(){try{if(window.__ytbNetHook)return;var P=window.YtbNet;if(!P)return;window.__ytbNetHook=1;var CAP=100000;"
      + "function send(o){try{P.push(JSON.stringify(o))}catch(e){}}"
      + "function nid(){window.__ytbN=(window.__ytbN||0)+1;return Date.now().toString(36)+window.__ytbN}"
      + "function hd(h,r){try{if(!h)return;if(typeof Headers!=='undefined'&&h instanceof Headers){h.forEach(function(v,k){r[k]=v})}else if(Array.isArray(h)){h.forEach(function(p){r[p[0]]=p[1]})}else{for(var k in h)r[k]=String(h[k])}}catch(e){}}"
      + "function bd(b,o){try{if(b==null)return;if(typeof b==='string'){o.body=b;return}"
      + "if(typeof URLSearchParams!=='undefined'&&b instanceof URLSearchParams){o.body=b.toString();o.ctype='application/x-www-form-urlencoded;charset=UTF-8';return}"
      + "if(typeof FormData!=='undefined'&&b instanceof FormData){o.form=[];b.forEach(function(v,k){o.form.push([k,typeof v==='string'?v:'[file]'])});return}"
      + "o.bin=1}catch(e){o.bin=1}}"
      + "var of=window.fetch;if(of){window.fetch=function(i,init){var o=null;try{var rq=(typeof Request!=='undefined'&&i instanceof Request);o={id:nid(),k:'fetch',url:new URL(rq?i.url:String(i),location.href).href,method:String((init&&init.method)||(rq&&i.method)||'GET').toUpperCase(),headers:{},page:location.href,ts:Date.now()};if(rq)hd(i.headers,o.headers);if(init)hd(init.headers,o.headers);if(init&&init.body!=null)bd(init.body,o);else if(rq&&o.method!=='GET'&&o.method!=='HEAD')o.bin=1;send(o)}catch(e){o=null}var p=of.apply(this,arguments);try{if(o&&p&&p.then)p.then(function(r){try{var ct=r.headers.get('content-type')||'';if(ct===''||/text|json|xml|javascript|html|urlencoded/i.test(ct)){r.clone().text().then(function(t){send({id:o.id,status:r.status,resp:String(t).slice(0,CAP)})},function(){send({id:o.id,status:r.status})})}else{send({id:o.id,status:r.status,rbin:ct})}}catch(e){}},function(){})}catch(e){}return p}}"
      + "var X=XMLHttpRequest.prototype,oo=X.open,os=X.send,oh=X.setRequestHeader;"
      + "X.open=function(m,u){try{this.__y={method:String(m).toUpperCase(),url:String(u),headers:{}}}catch(e){}return oo.apply(this,arguments)};"
      + "X.setRequestHeader=function(k,v){try{if(this.__y)this.__y.headers[k]=v}catch(e){}return oh.apply(this,arguments)};"
      + "X.send=function(b){try{var y=this.__y;if(y){var o={id:nid(),k:'xhr',url:new URL(y.url,location.href).href,method:y.method,headers:y.headers,page:location.href,ts:Date.now()};if(b!=null)bd(b,o);send(o);this.addEventListener('loadend',function(){try{var t=this.responseType,r={id:o.id,status:this.status};if(t===''||t==='text'){r.resp=String(this.responseText||'').slice(0,CAP)}else if(t==='json'){r.resp=JSON.stringify(this.response).slice(0,CAP)}else{r.rbin=t}send(r)}catch(e){}})}}catch(e){}return os.apply(this,arguments)};"
      + "}catch(e){}})()";

    public static class NetBridge {
        @JavascriptInterface
        public void push(String s) {
            try {
                if (s == null || s.length() > NET_IN_MAX) return;
                JSONObject o = new JSONObject(s);
                if (!o.has("url") && o.has("id")) {         // the answer to a request logged before: status, body
                    String id = o.optString("id");
                    synchronized (LOCK) {
                        for (int i = netLog.size() - 1; i >= 0; i--) {
                            String cur = netLog.get(i);
                            if (cur.indexOf("\"id\":\"" + id + "\"") < 0) continue;
                            JSONObject e = new JSONObject(cur);
                            if (!id.equals(e.optString("id"))) continue;
                            if (o.has("status")) e.put("status", o.optInt("status"));
                            if (o.has("resp")) e.put("resp", o.optString("resp"));
                            if (o.has("rbin")) e.put("rbin", o.optString("rbin"));
                            netLog.set(i, e.toString());
                            break;
                        }
                    }
                    return;
                }
                String u = o.optString("url");
                if (!(u.startsWith("http://") || u.startsWith("https://"))) return;
                String c = CookieManager.getInstance().getCookie(u);
                o.put("cookie", c == null ? "" : c);
                o.put("ua", ua);
                synchronized (LOCK) {
                    netLog.add(o.toString());
                    while (netLog.size() > NET_MAX) netLog.remove(0);
                }
            } catch (Exception e) { }
        }
    }

    /** JSON: {page, ua, items:[{id, k, url, method, headers, body, form, ctype, bin, page, cookie, ua, status, resp, rbin}]} - oldest first. */
    public static String netLog() {
        JSONObject out = new JSONObject();
        try {
            JSONArray arr = new JSONArray();
            synchronized (LOCK) {
                for (String s : netLog) arr.put(new JSONObject(s));
            }
            out.put("page", pageUrl);
            out.put("ua", ua);
            out.put("items", arr);
        } catch (Exception e) { }
        return out.toString();
    }

    public static void clearNetLog() {
        synchronized (LOCK) { netLog.clear(); }
    }

    // ---- page tools: desktop view, dark mode, find, blocking images / videos, cleaning ------------------
    private static final String DARK_ON =
        "(function(){try{var d=document;if(d.getElementById('ytb-dark'))return;var s=d.createElement('style');s.id='ytb-dark';"
      + "s.textContent='html{background:#fff!important;filter:invert(1) hue-rotate(180deg)!important}"
      + "img,video,canvas,iframe{filter:invert(1) hue-rotate(180deg)!important}';"
      + "(d.head||d.documentElement).appendChild(s)}catch(e){}})()";
    private static final String DARK_OFF =
        "(function(){try{var s=document.getElementById('ytb-dark');if(s)s.remove()}catch(e){}})()";
    private static final String DESKTOP_JS =
        "(function(){try{var m=document.querySelector('meta[name=viewport]');"
      + "if(!m){m=document.createElement('meta');m.name='viewport';(document.head||document.documentElement).appendChild(m)}"
      + "m.setAttribute('content','width=1280')}catch(e){}})()";
    private static final String NOVIDEO_JS =
        "(function(){try{function k(v){try{v.autoplay=false;v.removeAttribute('autoplay');v.preload='none';if(!v.paused)v.pause()}catch(e){}}"
      + "function all(){document.querySelectorAll('video').forEach(k)}all();"
      + "if(!window.__ytbNoVid){window.__ytbNoVid=true;"
      + "document.addEventListener('play',function(e){var t=e.target;if(t&&t.tagName==='VIDEO')t.pause()},true);"
      + "new MutationObserver(all).observe(document.documentElement,{childList:true,subtree:true})}}catch(e){}})()";
    private static final String CLEAR_STORAGE_JS =
        "(function(){try{localStorage.clear()}catch(e){}try{sessionStorage.clear()}catch(e){}"
      + "try{if(indexedDB.databases)indexedDB.databases().then(function(l){l.forEach(function(d){indexedDB.deleteDatabase(d.name)})})}catch(e){}"
      + "try{if(window.caches)caches.keys().then(function(k){k.forEach(function(n){caches.delete(n)})})}catch(e){}})()";

    private static String makeDesktopUa(String phone) {
        return phone.replaceAll("\\(Linux; Android[^)]*\\)", "(X11; Linux x86_64)")
                    .replace(" Version/4.0", "").replace(" Mobile Safari", " Safari");
    }

    /** Desktop version of sites: desktop user agent + a wide viewport (set again after the page loads). */
    public static void setDesktop(final boolean on, final boolean doReload) {
        ui(new Runnable() {
            public void run() {
                if (web == null) return;
                boolean changed = desktop != on;
                desktop = on;
                ua = on ? desktopUa : baseUa;
                WebSettings s = web.getSettings();
                s.setUserAgentString(ua);
                s.setUseWideViewPort(true);
                s.setLoadWithOverviewMode(true);
                if (changed && doReload) web.reload();
            }
        });
    }

    /** Dark pages: the page is inverted by CSS (images, video and frames are inverted back). Works on any Android version. */
    public static void setDark(final boolean on) {
        darkOn = on;
        ui(new Runnable() {
            public void run() {
                if (web != null) web.evaluateJavascript(on ? DARK_ON : DARK_OFF, null);
            }
        });
    }

    /** Images / videos are not requested at all (see shouldInterceptRequest); the page should be loaded again. */
    public static void setBlock(final boolean images, final boolean videos) {
        noImages = images;
        noVideos = videos;
        ui(new Runnable() {
            public void run() {
                if (web == null) return;
                WebSettings s = web.getSettings();
                s.setBlockNetworkImage(images);
                if (videos) s.setMediaPlaybackRequiresUserGesture(true);
            }
        });
    }

    static void applyPageTools(WebView v) {
        v.evaluateJavascript(NET_JS, null);
        if (darkOn) v.evaluateJavascript(DARK_ON, null);
        if (desktop) v.evaluateJavascript(DESKTOP_JS, null);
        if (noVideos) v.evaluateJavascript(NOVIDEO_JS, null);
    }

    private static WebResourceResponse blockedResponse() {
        return new WebResourceResponse("text/plain", "utf-8", 204, "No Content",
            new HashMap<String, String>(), new ByteArrayInputStream(new byte[0]));
    }

    private static boolean isImageRequest(WebResourceRequest r, String u) {
        if (r.isForMainFrame()) return false;
        Map<String, String> h = r.getRequestHeaders();
        String a = h == null ? null : h.get("Accept");
        if (a != null && a.startsWith("image/")) return true;
        String p = Uri.parse(u).getPath();
        return p != null && p.toLowerCase().matches(".*\\.(jpe?g|png|gif|webp|avif|bmp|ico)$");
    }

    private static boolean isVideoRequest(WebResourceRequest r, String u) {
        if (r.isForMainFrame()) return false;
        Uri p = Uri.parse(u);
        String path = p.getPath() == null ? "" : p.getPath().toLowerCase();
        if (path.matches(".*\\.(mp4|m4v|webm|mkv|mov|avi|flv|3gp|m3u8|mpd|m4s)$")) return true;
        if (path.contains("/videoplayback")) return true;
        String q = p.getQuery();
        return q != null && q.contains("mime=video");
    }

    // find in page: the counter goes to Python with poll()
    public static void find(final String q) {
        ui(new Runnable() {
            public void run() {
                if (web == null) return;
                if (q == null || q.trim().length() == 0) {
                    web.clearMatches();
                    findIdx = 0;
                    findCount = 0;
                } else {
                    web.findAllAsync(q.trim());
                }
            }
        });
    }

    public static void findNext(final boolean forward) {
        ui(new Runnable() { public void run() { if (web != null) web.findNext(forward); } });
    }

    public static void clearFind() {
        ui(new Runnable() {
            public void run() {
                if (web != null) web.clearMatches();
                findIdx = 0;
                findCount = 0;
            }
        });
    }

    public static void clearCache() {
        ui(new Runnable() { public void run() { if (web != null) web.clearCache(true); } });
    }

    /** All cookies and saved site data (local storage...) of every site; the page loads again. */
    public static void clearAllSiteData() {
        ui(new Runnable() {
            public void run() {
                CookieManager cm = CookieManager.getInstance();
                cm.removeAllCookies(null);
                cm.flush();
                WebStorage.getInstance().deleteAllData();
                if (web != null) {
                    web.clearFormData();
                    web.reload();
                }
            }
        });
    }

    /** Cookies of one site (its host and parent domains, any path of the page address) and, when that site is the
     *  page shown, its local storage / IndexedDB / cache storage; the page loads again. */
    public static void clearSiteData(final String url) {
        ui(new Runnable() {
            public void run() {
                Uri u = Uri.parse(url == null ? "" : url);
                String host = u.getHost();
                if (host == null || host.length() == 0) return;
                CookieManager cm = CookieManager.getInstance();
                List<String> domains = new ArrayList<String>();
                String d = host;
                domains.add(d);
                if (!host.matches("[0-9.]+")) {
                    while (true) {
                        int dot = d.indexOf('.');
                        if (dot < 0) break;
                        String rest = d.substring(dot + 1);
                        if (rest.indexOf('.') < 0) break;      // never the bare suffix (com)
                        d = rest;
                        domains.add(d);
                    }
                }
                Set<String> names = new HashSet<String>();
                List<String> asked = new ArrayList<String>();
                asked.add(url);
                for (String dm : domains) {
                    asked.add("https://" + dm + "/");
                    asked.add("http://" + dm + "/");
                }
                for (String a : asked) {
                    String cs = cm.getCookie(a);
                    if (cs == null) continue;
                    for (String part : cs.split(";")) {
                        int eq = part.indexOf('=');
                        String n = (eq < 0 ? part : part.substring(0, eq)).trim();
                        if (n.length() > 0) names.add(n);
                    }
                }
                List<String> paths = new ArrayList<String>();
                paths.add("/");
                String path = u.getPath();
                if (path != null) {
                    StringBuilder sb = new StringBuilder();
                    for (String seg : path.split("/")) {
                        if (seg.length() == 0) continue;
                        sb.append('/').append(seg);
                        paths.add(sb.toString());
                    }
                }
                String exp = "=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=";
                for (String n : names) {
                    for (String pa : paths) {
                        String base = n + exp + pa;
                        cm.setCookie("https://" + host + "/", base);
                        cm.setCookie("https://" + host + "/", base + "; Secure");
                        cm.setCookie("http://" + host + "/", base);
                        for (String dm : domains) cm.setCookie("https://" + host + "/", base + "; Domain=" + dm);
                    }
                }
                cm.flush();
                if (web == null) return;
                String cur = web.getUrl();
                String curHost = cur == null ? null : Uri.parse(cur).getHost();
                if (host.equals(curHost)) web.evaluateJavascript(CLEAR_STORAGE_JS, null);
                web.postDelayed(new Runnable() {
                    public void run() { if (web != null) web.reload(); }
                }, 500);
            }
        });
    }

    /** Cookie export (core/browser_cookies.py): the cookies the WebView would send to each address (one per line):
     *  {ua, page, queries:[{url, cookie}]}. HttpOnly cookies are included; CookieManager does not tell the domain,
     *  path, expiry or flags of a cookie, so Python works the domain out from the addresses it asked about. */
    public static String exportCookies(String urls) {
        JSONObject out = new JSONObject();
        try {
            JSONArray arr = new JSONArray();
            CookieManager cm = CookieManager.getInstance();
            String[] list = urls == null ? new String[0] : urls.split("\n");
            for (int i = 0; i < list.length && i < 40; i++) {
                String u = list[i].trim();
                if (!(u.startsWith("https://") || u.startsWith("http://"))) continue;
                String c = cm.getCookie(u);
                JSONObject o = new JSONObject();
                o.put("url", u);
                o.put("cookie", c == null ? "" : c);
                arr.put(o);
            }
            out.put("ua", ua);
            out.put("page", pageUrl);
            out.put("queries", arr);
        } catch (Exception e) { }
        return out.toString();
    }

    // ---- tabs: one WebView; the page state (history, scroll) of every other tab is kept as a small Bundle ----
    private static final java.util.Map<String, android.os.Bundle> tabStates =
        new java.util.HashMap<String, android.os.Bundle>();
    private static boolean clearPending = false;   // UI thread only: the next finished page empties the back stack

    /** Leaves tab `from` (its page state is kept) and shows tab `to`: its saved state, else a fresh load of `url`. */
    public static void switchTab(final String from, final String to, final String url) {
        synchronized (LOCK) {
            seen.clear();
            pending.clear();
            pageUrl = "";
            pageTitle = "";
            epoch++;
            netLog.clear();
        }
        ui(new Runnable() {
            public void run() {
                if (web == null) return;
                web.stopLoading();
                if (from != null && from.length() > 0) {
                    android.os.Bundle b = new android.os.Bundle();
                    web.saveState(b);
                    tabStates.put(from, b);
                }
                android.os.Bundle saved = tabStates.get(to);
                if (saved != null && web.restoreState(saved) != null) {
                    canBack = web.canGoBack();
                    return;
                }
                clearPending = true;
                web.loadUrl(url);
            }
        });
    }

    /** A tab was closed (all tabs when `id` is empty): its saved page state goes. */
    public static void forgetTab(final String id) {
        ui(new Runnable() {
            public void run() {
                if (id == null || id.length() == 0) tabStates.clear();
                else tabStates.remove(id);
            }
        });
    }

    static class Client extends WebViewClient {
        @Override
        public void onPageStarted(WebView v, String url, Bitmap favicon) {
            newPage(url);
            canBack = v.canGoBack();
            v.evaluateJavascript(NET_JS, null);
            if (darkOn) v.evaluateJavascript(DARK_ON, null);
        }

        @Override
        public void onPageCommitVisible(WebView v, String url) {
            applyPageTools(v);
        }

        @Override
        public void onPageFinished(WebView v, String url) {
            applyPageTools(v);
            String t = v.getTitle();
            pageTitle = t == null ? "" : t;
            if (clearPending) {
                clearPending = false;
                v.clearHistory();   // a tab opened fresh starts with its own back stack
            }
            canBack = v.canGoBack();
            scan();
            v.postDelayed(SCAN_LATER, 2500);
        }

        @Override
        public void doUpdateVisitedHistory(WebView v, String url, boolean isReload) {
            newPage(url);   // also single-page sites (YouTube) that change the address without a reload
            canBack = v.canGoBack();
        }

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
            try {
                String u = r.getUrl().toString();
                Pattern pt = extPattern;
                if (pt != null && "GET".equalsIgnoreCase(r.getMethod()) && pt.matcher(u).find()) record(u, "net");
                if (noVideos && isVideoRequest(r, u)) return blockedResponse();      // seen above, so still listed
                if (noImages && isImageRequest(r, u)) return blockedResponse();
            } catch (Exception e) { }
            return null;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
            String s = r.getUrl().getScheme();
            return !("http".equals(s) || "https".equals(s));   // intent:, market: ... are not opened
        }
    }
}
