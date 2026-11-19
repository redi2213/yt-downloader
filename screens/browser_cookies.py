"""In-app browser > Menu > Export cookies: the cookies of the page shown (read from the WebView's CookieManager) as a
Netscape cookies.txt, and the headers (User-Agent, Referer, Cookie) for yt-dlp and curl. Written like
screens/browser_tools.py: English texts, translated by core/i18n.

Steps: the domains found are listed with their number of cookies (never values) and the user switches them on or
off (and may add a sign-in domain) -> the output screen: copy, save cookies.txt on the phone, copy the headers, send
to a GitHub secret -> a confirm screen before anything is sent to GitHub.

No Build needed: this screen, core/browser_cookies.py, services/cookie_secret_service.py. Build needed
(BrowserHelper.exportCookies): reading all the cookies of the site. An older APK is not ready for it and only the
cookies sent with the files the browser found are available (the screen says so).

Cookie values are only in memory (``_S``, emptied when the screen is left) and never in a label, log or message.
"""
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from core import android_downloads, browser_cookies as bc, browser_tabs as bt, browser_tools as tools
from core.async_utils import run_in_background
from screens import browser_pages
from screens.browser import _copy
from screens.browser_tools import _status, _title
from screens.common import BTN_H, wrapped_label
from services import browser_service, cookie_secret_service

_LIMITS = ("Android WebView limits: HttpOnly cookies are included, but the expiry, path and Secure / HttpOnly flags "
           "of a cookie cannot be read, so cookies.txt keeps every cookie as a session cookie for the whole site "
           "(path /). Cookies set only for another path, or for a domain that is not listed here, are not available: "
           "use Add domain for sign-in domains (for example google.com).")

_S = {}         # the screen's state; holds cookie values only in memory


def reset():
    _S.clear()


def _leave(nav):
    reset()
    nav.show_browser()


def _button(nav, text, action):
    btn = Button(text=text, size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: action(btn))
    nav.add(btn)
    return btn


# -- reading the cookies ---------------------------------------------------------------------------------------------
def _collect(nav, extra):
    """Asks the WebView for the cookies of the page (and the extra domains) and fills ``_S``."""
    st = browser_service.state()
    tab = st.tabs.current()
    sess = st.tabs.session_for(tab["id"])
    page = sess.page if bt.is_web(sess.page) else tab.get("url")
    page = bc.page_address(tools.original_url(page)) if bt.is_web(page) else ""
    br = nav.browser
    answer = None
    if page and br is not None and br.cookies_ready():
        answer = br.export_cookies(bc.query_urls(page, bc.candidate_hosts(page, extra)))
    if answer is not None:
        results, ua, full = answer.get("queries") or [], answer.get("ua") or "", True
    else:
        items = list(sess.items.values())
        results, ua, full = bc.results_from_items(items), bc.ua_from_items(items), False
    jar = bc.build_jar(results)
    known, names = _S.get("known", set()), {c["domain"] for c in jar}
    chosen = {d for d in _S.get("selected", set()) if d in names}
    chosen |= {d for d in bc.default_selected(jar, page, extra) if d not in known}
    _S.update(page=page, ua=ua, full=full, extra=list(extra), jar=jar, selected=chosen, known=known | names)


def _chosen():
    return bc.select(_S.get("jar") or [], _S.get("selected") or set())


def _chosen_domains(chosen):
    return sorted({c["domain"] for c in chosen})


# -- step 1: which domains -------------------------------------------------------------------------------------------
def open_export(nav):
    nav.remember(lambda: open_export(nav))
    reset()
    _collect(nav, [])
    build_domains(nav)


def _domain_text(domain, count, on):
    return f"{domain} ({count}): " + ("ON" if on else "OFF")


def build_domains(nav, note=""):
    nav.clear()
    _title(nav, "Export cookies")
    nav.add(wrapped_label("Cookies sign in as you: anyone who gets them can use your accounts. Choose only the "
                          "domains you need. Nothing is sent anywhere without your confirmation."))
    page, jar = _S.get("page") or "", _S.get("jar") or []
    nav.add(wrapped_label(f"Site: {bc.host_of(page)}" if page else "Open a page first"))
    if page and not _S.get("full"):
        nav.add(wrapped_label("Only the cookies sent with the files found on this page are available. All the "
                              "cookies of the site need the latest app update (a new build)."))
    status = _status()
    status.text = note
    nav.add(status)
    domains = bc.domain_counts(jar)
    if page and not domains:
        nav.add(wrapped_label("No cookies were found for this site. Sign in on the page first, then try again."))
    for domain, count in domains:
        def flip(btn, domain=domain, count=count):
            _S["selected"].symmetric_difference_update({domain})
            btn.text = _domain_text(domain, count, domain in _S["selected"])
            status.text = ""
        _button(nav, _domain_text(domain, count, domain in _S["selected"]), flip)

    if page:
        box = TextInput(hint_text="Add another domain (for example google.com)", multiline=False,
                        size_hint_y=None, height=BTN_H)
        nav.add(box)

        def add(_btn):
            domain = bc.clean_domain(box.text)
            if not domain:
                status.text = "Type a domain like google.com"
                return
            extra = _S.get("extra") or []
            _collect(nav, extra if domain in extra else extra + [domain])
            found = any(c["domain"] in bc.host_chain(domain) for c in _S["jar"])
            build_domains(nav, "Domain added" if found else "No cookies were found for this domain")
        _button(nav, "Add domain", add)

    def go(_btn):
        if not _chosen():
            status.text = "Choose at least one domain"
            return
        open_output(nav)
    if domains:
        _button(nav, "Continue", go)
    nav.add(wrapped_label(_LIMITS))
    _button(nav, "Back to the menu", lambda b: (reset(), browser_pages.open_menu(nav)))


# -- step 2: what to do with them ------------------------------------------------------------------------------------
def open_output(nav):
    nav.remember(lambda: open_export(nav))
    build_output(nav)


def build_output(nav):
    chosen = _chosen()
    if not chosen:
        build_domains(nav)
        return
    text, header = bc.to_netscape(chosen), bc.cookie_header(chosen)
    page, ua = _S.get("page") or "", _S.get("ua") or ""
    nav.clear()
    _title(nav, "Export cookies")
    nav.add(wrapped_label(f"Cookies: {len(chosen)}"))
    nav.add(wrapped_label(f"Domains: {', '.join(_chosen_domains(chosen))}"))
    status = _status()
    nav.add(status)

    def copy(value, done):
        def run(_btn):
            if value:
                _copy(value)
            status.text = done if value else "Nothing to copy"
        return run

    def save(_btn):
        status.text = "Saving..."

        def work():
            try:
                saved = android_downloads.save_text_file(text, "cookies.txt", category="Browser")
                msg = f"Saved: {saved}\nThis file signs in as you: delete it when you are done."
            except Exception:
                msg = "Could not save the file"
            Clock.schedule_once(lambda dt: setattr(status, "text", msg))
        run_in_background(work)

    _title(nav, "Cookies")
    _button(nav, "Copy cookies (Netscape format)", copy(text, "Cookies copied"))
    _button(nav, "Save cookies.txt on the phone", save)
    _button(nav, "Send to a GitHub secret", lambda b: open_send(nav))
    _title(nav, "Headers for yt-dlp and curl")
    _button(nav, "Copy yt-dlp options", copy(bc.ytdlp_options(ua, page), "Copied"))
    _button(nav, "Copy curl command (cookies.txt)", copy(bc.curl_command("", ua, page), "Copied"))
    _button(nav, "Copy curl command (Cookie header)", copy(bc.curl_command("", ua, page, header), "Copied"))
    _button(nav, "Copy Cookie header", copy(header, "Copied"))
    _button(nav, "Copy User-Agent", copy(ua, "Copied"))
    _button(nav, "Copy Referer", copy(page, "Copied"))
    nav.add(wrapped_label("The Cookie header and the curl command with it hold the cookie values: share them with care."))
    nav.add(wrapped_label(_LIMITS))
    _button(nav, "Back to domains", lambda b: build_domains(nav))
    _button(nav, "Back to browser", lambda b: _leave(nav))


# -- step 3: sending to GitHub (always asks first) -------------------------------------------------------------------
def open_send(nav):
    nav.remember(lambda: open_export(nav))
    build_send(nav)


def build_send(nav):
    nav.clear()
    _title(nav, "Send to a GitHub secret")
    nav.add(wrapped_label("The workflows read cookies from a GitHub secret of your repository. The secret is "
                          "replaced by these cookies; what is saved now cannot be read back. Choose where they go:"))
    state = wrapped_label("Checking what is saved...")
    nav.add(state)

    def show(res):
        if res.get("ok"):
            names = ", ".join(res.get("saved") or [])
            state.text = f"Saved now: {names}" if names else "Saved now: none"
        else:
            state.text = res.get("error") or "Could not read what is saved."
    cookie_secret_service.start_status(lambda res: Clock.schedule_once(lambda dt: show(res)))
    for name, label in cookie_secret_service.TARGETS:
        _button(nav, label, lambda b, name=name, label=label: build_confirm(nav, name, label))
    _button(nav, "Back to the cookies", lambda b: build_output(nav))


def build_confirm(nav, name, label):
    chosen = _chosen()
    if not chosen:
        build_domains(nav)
        return
    text = bc.to_netscape(chosen)
    nav.clear()
    _title(nav, "Send cookies to GitHub?")
    nav.add(wrapped_label(f"Secret: {name}"))
    nav.add(wrapped_label(label))
    nav.add(wrapped_label(f"Cookies: {len(chosen)}"))
    nav.add(wrapped_label(f"Domains: {', '.join(_chosen_domains(chosen))}"))
    nav.add(wrapped_label("Sent to GitHub encrypted; only your workflows can read them. This replaces the cookies "
                          "saved in this secret now, and they cannot be read back."))
    status = _status()
    nav.add(status)
    yes = Button(text="Yes, send to GitHub", size_hint_y=None, height=BTN_H)

    def run(_btn):
        yes.disabled = True
        status.text = "Sending..."

        def show(res):
            if res.get("ok"):
                status.text = "Sent. The workflows will use these cookies."
            else:
                yes.disabled = False
                status.text = res.get("error") or "Could not send"
        cookie_secret_service.start_save(name, text, lambda res: Clock.schedule_once(lambda dt: show(res)))
    yes.bind(on_press=run)
    nav.add(yes)
    _button(nav, "Cancel", lambda b: build_send(nav))
    _button(nav, "Back to browser", lambda b: _leave(nav))


# -- Network requests (Fetch / XHR of the page): Copy as cURL ---------------------------------------------------------
# Build needed (BrowserHelper.netLog): an older APK is not ready for it and the screen says so. The requests hold
# cookie values (only in memory, like ``_S``): the cURL with the Cookie header is the only text that carries them.
def open_netlog(nav):
    nav.remember(lambda: open_netlog(nav))
    reset()
    build_netlog(nav)


def build_netlog(nav, note="", query=None):
    if query is not None:
        _S["net_q"] = str(query or "").strip()
    br = nav.browser
    data = br.net_log() if br is not None and br.netlog_ready() else None
    nav.clear()
    _title(nav, "Network requests (Fetch / XHR)")
    status = _status()
    status.text = note
    if data is None:
        nav.add(wrapped_label("This needs the latest app update (a new build)."))
        nav.add(status)
        _button(nav, "Back to the menu", lambda b: (reset(), browser_pages.open_menu(nav)))
        _button(nav, "Back to browser", lambda b: _leave(nav))
        return
    items = data.get("items") or []
    nav.add(wrapped_label("The Fetch and XHR requests the page made, like the Network tab of a desktop browser. "
                          "Open the page, do what gives the result (for example press its button), come back here "
                          "and pick the request. Requests made before the page finished starting may be missing."))
    nav.add(status)
    box = TextInput(hint_text="Filter (part of the address or body)", text=_S.get("net_q", ""), multiline=False,
                    size_hint_y=None, height=BTN_H)
    nav.add(box)
    _button(nav, "Apply filter", lambda b: build_netlog(nav, query=box.text))
    _button(nav, "Refresh", lambda b: build_netlog(nav))

    def clear(_btn):
        br.clear_net_log()
        build_netlog(nav, "List cleared")
    rows = bc.net_filter(items, _S.get("net_q"))
    nav.add(wrapped_label(f"Requests: {len(rows)} of {len(items)}" + (" (newest first, first %d shown)" % bc.MAX_NET_SHOWN
                                                                       if len(rows) > bc.MAX_NET_SHOWN else "")))
    for req in rows[:bc.MAX_NET_SHOWN]:
        _button(nav, bc.net_title(req), lambda b, req=req: build_request(nav, req))
    if items:
        _button(nav, "Clear the list", clear)
    _button(nav, "Back to the menu", lambda b: (reset(), browser_pages.open_menu(nav)))
    _button(nav, "Back to browser", lambda b: _leave(nav))


def build_request(nav, req):
    nav.clear()
    _title(nav, "Request")
    nav.add(wrapped_label(f"{str(req.get('method') or 'GET').upper()} ({req.get('k') or 'fetch'})"))
    nav.add(wrapped_label(str(req.get("url") or "")))
    body = str(req.get("body") or "")
    form = req.get("form") or []
    if bc.net_body_unknown(req):
        nav.add(wrapped_label("This request sends a body (a file or binary data) that could not be read: the cURL "
                              "has no body."))
    status = _status()
    nav.add(status)

    def copy(value, done):
        def run(_btn):
            if value:
                _copy(value)
            status.text = done if value else "Nothing to copy"
        return run

    _button(nav, "Copy as cURL", copy(bc.net_curl(req, True), "Copied (it holds the Cookie header: share with care)"))
    _button(nav, "Copy as cURL (without Cookie)", copy(bc.net_curl(req, False), "Copied"))
    _button(nav, "Copy address", copy(str(req.get("url") or ""), "Copied"))
    if body:
        _button(nav, "Copy body", copy(body, "Copied"))
    elif form:
        _button(nav, "Copy form fields", copy("&".join(f"{p[0]}={p[1]}" for p in form if len(p) == 2), "Copied"))
    nav.add(wrapped_label("The cURL with the Cookie header holds the cookie values: share it with care."))
    _button(nav, "Back to the list", lambda b: build_netlog(nav))
    _button(nav, "Back to browser", lambda b: _leave(nav))
