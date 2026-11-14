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
import android.webkit.ValueCallback;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;

import org.json.JSONArray;
import org.json.JSONObject;
import org.json.JSONTokener;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
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

    private static final Pattern MEDIA = Pattern.compile(
        "(?i)\\.(mp4|m4v|webm|mkv|mov|m3u8|mpd|mp3|m4a|aac|ogg|opus|flac|wav)(?:$|[?#&])");

    private static final String SCAN_JS =
        "(function(){var o=[];"
      + "function add(u){if(u&&typeof u==='string'&&u.indexOf('blob:')!==0&&u.indexOf('data:')!==0){try{o.push(new URL(u,location.href).href)}catch(e){}}}"
      + "document.querySelectorAll('video,audio,source').forEach(function(e){add(e.currentSrc||e.src)});"
      + "document.querySelectorAll(\"meta[property='og:video'],meta[property='og:video:url'],meta[property='og:video:secure_url'],meta[property='og:audio']\").forEach(function(m){add(m.content)});"
      + "return JSON.stringify(o.filter(function(x,i){return o.indexOf(x)===i}))})()";

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
                CookieManager cm = CookieManager.getInstance();
                cm.setAcceptCookie(true);
                cm.setAcceptThirdPartyCookies(web, true);
                web.setWebViewClient(new Client());
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

    // ---- what was found -------------------------------------------------------------
    private static void newPage(String url) {
        synchronized (LOCK) {
            if (url == null || url.equals(pageUrl)) return;
            pageUrl = url;
            pageTitle = "";
            epoch++;
            seen.clear();
            pending.clear();
        }
    }

    private static void record(String u, String src) {
        if (u == null || u.startsWith("blob:") || u.startsWith("data:")) return;
        Uri p = Uri.parse(u);
        String key = (p.getHost() == null ? "" : p.getHost()) + (p.getPath() == null ? "" : p.getPath());
        synchronized (LOCK) {
            if (!seen.add(key)) return;
            try {
                JSONObject o = new JSONObject();
                o.put("url", u);
                o.put("src", src);
                o.put("referer", pageUrl);
                o.put("ua", ua);
                String c = CookieManager.getInstance().getCookie(u);
                o.put("cookie", c == null ? "" : c);
                pending.add(o);
            } catch (Exception e) { }
        }
    }

    static void scan() {
        final WebView w = web;
        if (w == null) return;
        w.evaluateJavascript(SCAN_JS, new ValueCallback<String>() {
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

    /** JSON: {epoch, page, title, tapped, can_back, items:[{url, src, referer, ua, cookie}]} - new items only. */
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
                out.put("items", arr);
            } catch (Exception e) { }
            badgeTapped = false;
        }
        return out.toString();
    }

    static class Client extends WebViewClient {
        @Override
        public void onPageStarted(WebView v, String url, Bitmap favicon) {
            newPage(url);
            canBack = v.canGoBack();
        }

        @Override
        public void onPageFinished(WebView v, String url) {
            String t = v.getTitle();
            pageTitle = t == null ? "" : t;
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
                if ("GET".equalsIgnoreCase(r.getMethod()) && MEDIA.matcher(u).find()) record(u, "net");
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
