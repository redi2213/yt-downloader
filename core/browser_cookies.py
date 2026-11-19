"""Cookie export of the in-app browser (pure Python: no Kivy, no network; no Build needed).

The WebView's CookieManager (java/.../BrowserHelper.exportCookies, Build) can only answer "which cookies would you
send to this address": a ``name=value; name=value`` header. HttpOnly cookies are in it (only JavaScript cannot see
them) but domain, path, expiry and the Secure / HttpOnly flags are not. This module asks for the page's host and each
parent domain (and the sign-in domains the user adds), works out which domain every cookie belongs to, and writes the
Netscape cookies.txt and the header texts for yt-dlp and curl.

Cookie values never go into a log or an error message: ``redact`` removes them from any text that could carry them.
"""
import re
import shlex
from urllib.parse import urlsplit

NETSCAPE_HEADER = "# Netscape HTTP Cookie File"
MAX_SECRET_LEN = 48000          # the size limit of one GitHub secret
MAX_QUERIES = 30                # addresses asked from the WebView in one go

# two-label public suffixes: the site root of a.example.co.uk is example.co.uk
_SECOND_LEVEL = {"co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au", "co.nz", "co.jp", "or.jp",
                 "co.kr", "co.in", "com.br", "com.tr", "com.mx", "com.ar", "co.za", "com.sg", "com.hk", "com.tw",
                 "com.cn", "com.ua", "co.id", "com.my", "com.sa", "com.eg", "co.il", "org.ir", "co.ir", "ac.ir"}

# sign-in domains a site also uses: they are looked at too but never switched on by themselves
RELATED = {"youtube.com": ("google.com", "accounts.google.com")}


def host_of(url):
    try:
        return (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def _is_ip(host):
    return ":" in host or bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host))


def clean_domain(text):
    """A typed domain ('https://www.Google.com/x', '.google.com') as a plain host name; '' when it is not one."""
    s = str(text or "").strip().lower()
    if "://" in s:
        s = host_of(s)
    s = s.split("/")[0].split(":")[0].strip(".")
    return s if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", s) else ""


def site_root(host):
    if not host or _is_ip(host):
        return host
    labels = host.split(".")
    if len(labels) <= 2:
        return host
    if ".".join(labels[-2:]) in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def host_chain(host):
    """The host and its parent domains down to the site root: a.b.example.com -> a.b.example.com, b.example.com,
    example.com (never the bare suffix)."""
    if not host:
        return []
    if _is_ip(host):
        return [host]
    root = site_root(host)
    chain, cur = [host], host
    while cur != root and "." in cur:
        cur = cur.split(".", 1)[1]
        chain.append(cur)
    return chain


def page_address(url):
    """The page address without #fragment; '' when it is not an http(s) page."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ""
    return parts._replace(fragment="").geturl()


def candidate_hosts(page, extra=()):
    """[{'host', 'kind'}] to ask the WebView about. kind: 'site' (the page's host and its parent domains),
    'related' (sign-in domains the site uses) or 'extra' (added by the user)."""
    out, seen = [], set()

    def put(host, kind):
        if host and host not in seen:
            seen.add(host)
            out.append({"host": host, "kind": kind})

    site = host_of(page)
    for h in host_chain(site):
        put(h, "site")
    for rel in RELATED.get(site_root(site), ()):
        for h in host_chain(rel):
            put(h, "related")
    for typed in extra or ():
        for h in host_chain(clean_domain(typed)):
            put(h, "extra")
    return out[:MAX_QUERIES]


def query_urls(page, hosts):
    """The addresses given to the WebView: the page itself (cookies of its path) and the root of every host."""
    urls = []
    addr = page_address(page)
    if addr:
        urls.append(addr)
    for h in hosts:
        u = f"https://{h['host']}/"
        if u not in urls:
            urls.append(u)
    return urls[:MAX_QUERIES]


def parse_header(text):
    """'a=1; b=2' -> [('a', '1'), ('b', '2')]."""
    pairs = []
    for part in str(text or "").split(";"):
        name, eq, value = part.strip().partition("=")
        if name and eq:
            pairs.append((name, value))
    return pairs


def _under(child, parent):
    return child != parent and child.endswith("." + parent)


def build_jar(results):
    """results: [{'url', 'cookie'}] as the WebView answered -> [{'domain', 'sub', 'name', 'value'}].

    A cookie that every asked subdomain of a host also gets is a domain cookie of that host (``sub`` True, written
    as '.host'). One that only a deeper host gets is host-only. A cookie found on a two-label root nothing below it
    was asked about is taken as a domain cookie (that is what sites almost always set)."""
    by_host = {}
    for r in results or []:
        host = host_of((r or {}).get("url"))
        if not host:
            continue
        pairs = by_host.setdefault(host, [])
        for p in parse_header(r.get("cookie")):
            if p not in pairs:
                pairs.append(p)
    holders = {}
    for host, pairs in by_host.items():
        for p in pairs:
            holders.setdefault(p, set()).add(host)
    jar = []
    for (name, value), hosts in holders.items():
        for root in (h for h in hosts if not any(_under(h, o) for o in hosts)):
            kids = [h for h in by_host if _under(h, root)]
            if kids:
                sub = all((name, value) in by_host[k] for k in kids)
            else:
                sub = root == site_root(root) and not _is_ip(root)
            jar.append({"domain": root, "sub": sub, "name": name, "value": value})
    jar.sort(key=lambda c: (c["domain"], c["name"], c["value"]))
    return jar


def domain_counts(jar):
    """[(domain, number of cookies)]: what the user sees before anything leaves the screen (never values)."""
    counts = {}
    for c in jar:
        counts[c["domain"]] = counts.get(c["domain"], 0) + 1
    return sorted(counts.items())


def default_selected(jar, page, extra=()):
    """The domains switched on at first: the page's own site and the domains the user added."""
    wanted = set(host_chain(host_of(page)))
    for typed in extra or ():
        wanted.update(host_chain(clean_domain(typed)))
    return {c["domain"] for c in jar if c["domain"] in wanted}


def select(jar, domains):
    return [c for c in jar if c["domain"] in domains]


def _field(text):
    return re.sub(r"[\t\r\n]", " ", str(text))


def to_netscape(cookies):
    """The cookies.txt text (Netscape format: yt-dlp --cookies, curl -b). Expiry 0 = session cookie, path /."""
    lines = [NETSCAPE_HEADER]
    for c in cookies:
        domain = ("." if c["sub"] else "") + c["domain"]
        lines.append("\t".join([domain, "TRUE" if c["sub"] else "FALSE", "/", "FALSE", "0",
                                _field(c["name"]), _field(c["value"])]))
    return "\n".join(lines) + "\n"


def cookie_header(cookies):
    """One 'name=value; name=value' header; a name found on several domains keeps the most specific one."""
    seen, parts = set(), []
    for c in sorted(cookies, key=lambda c: -len(c["domain"].split("."))):
        if c["name"] not in seen:
            seen.add(c["name"])
            parts.append(f"{c['name']}={c['value']}")
    return "; ".join(parts)


def ytdlp_options(ua="", referer=""):
    """yt-dlp options that go with cookies.txt (no cookie value in it)."""
    parts = ["--cookies cookies.txt"]
    if ua:
        parts.append("--user-agent " + shlex.quote(ua))
    if referer:
        parts.append("--referer " + shlex.quote(referer))
    return " ".join(parts)


def curl_command(url="", ua="", referer="", header=""):
    """A curl command: with the Cookie ``header`` (it holds the cookie values) or, when empty, with -b cookies.txt."""
    parts = ["curl", "-L"]
    parts += ["-H", shlex.quote("Cookie: " + header)] if header else ["-b", "cookies.txt"]
    if ua:
        parts += ["-A", shlex.quote(ua)]
    if referer:
        parts += ["-e", shlex.quote(referer)]
    parts.append(shlex.quote(url) if url else "'URL'")
    return " ".join(parts)


def results_from_items(items):
    """Without the new native method (an older build) only the cookies the browser sent with the files it found
    are known: [{'url', 'cookie'}] from the items of the browser session."""
    out = []
    for it in items or []:
        cookie = ((it or {}).get("headers") or {}).get("Cookie") or ""
        if cookie and it.get("url"):
            out.append({"url": it["url"], "cookie": cookie})
    return out


def ua_from_items(items):
    for it in items or []:
        ua = ((it or {}).get("headers") or {}).get("User-Agent")
        if ua:
            return ua
    return ""


def valid_cookies_txt(text):
    """(text, error) for a cookies.txt that may go into a secret."""
    value = str(text or "").strip("\n") + "\n"
    lines = value.split("\n")
    if lines[0].strip() != NETSCAPE_HEADER or not any(l and not l.startswith("#") for l in lines[1:]):
        return "", "There are no cookies to save."
    if len(value) > MAX_SECRET_LEN:
        return "", "These cookies are too long for a GitHub secret. Choose fewer domains."
    return value, ""


def redact(text, secret_text):
    """``text`` with every piece of ``secret_text`` (cookies.txt or a Cookie header) replaced by ***: for any
    message that could carry a cookie."""
    out = str(text or "")
    pieces = set()
    for chunk in re.split(r"[\t\r\n;]+", str(secret_text or "")):
        chunk = chunk.strip()
        if len(chunk) >= 6:
            pieces.add(chunk)
        value = chunk.partition("=")[2]
        if len(value) >= 6:
            pieces.add(value)
    for piece in sorted(pieces, key=len, reverse=True):
        out = out.replace(piece, "***")
    return out


# -- Network log: the Fetch / XHR requests of the page (headers, body, answer) and "Copy as cURL" ------------------------
# The WebView helper (java/.../BrowserHelper.netLog, Build) wraps fetch and XMLHttpRequest in the page and reports
# every request: {id, k, url, method, headers, body, form, ctype, bin, page, cookie, ua} and, when the answer comes,
# {status, resp (text, cut at 100000 characters) or rbin (the type of a non-text answer)}.
# ``cookie`` holds cookie values: only net_curl(with_cookie=True) writes them out.
MAX_NET_SHOWN = 100
_SKIP_HEADERS = {"host", "content-length", "cookie", "user-agent", "referer", "origin", "connection"}


def net_title(req, limit=400):
    """One line for the list: 'POST host/path?query' (the whole address up to ``limit`` characters)."""
    req = req or {}
    parts = urlsplit(str(req.get("url") or ""))
    path = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
    text = f"{str(req.get('method') or 'GET').upper()} {parts.netloc}{path}"
    return text if len(text) <= limit else text[:max(limit - 3, 1)] + "..."


def net_host(req):
    return host_of((req or {}).get("url"))


def net_domains(items):
    """[(host, number of requests)], the busiest first: the domain filter buttons."""
    counts = {}
    for r in items or []:
        h = net_host(r) if isinstance(r, dict) else ""
        if h:
            counts[h] = counts.get(h, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


def _in_domain(host, domain):
    return host == domain or host.endswith("." + domain)


def net_filter(items, text="", domain=""):
    """The requests newest first. ``domain``: only that host and its subdomains (api.example.com, example.com).
    ``text``: only those whose address or body holds it (not case sensitive)."""
    t = str(text or "").strip().lower()
    d = str(domain or "").strip().lower()
    out = [r for r in (items or []) if isinstance(r, dict) and r.get("url")]
    if d:
        out = [r for r in out if _in_domain(net_host(r), d)]
    if t:
        out = [r for r in out if t in str(r["url"]).lower() or t in str(r.get("body") or "").lower()]
    return list(reversed(out))


def net_body_unknown(req):
    """True when the page sent a body this log could not read (a file, Blob, Request object ...)."""
    req = req or {}
    return bool(req.get("bin")) and not req.get("body") and not req.get("form")


def net_response(req):
    """(text, note) of the answer: the text when it was logged, else why there is none."""
    req = req or {}
    if req.get("resp"):
        return str(req["resp"]), ""
    if "rbin" in req:
        return "", f"The answer is not text ({req.get('rbin') or 'binary'}): it is not logged."
    if "status" in req:
        return "", "The answer was empty."
    return "", "No answer yet (the request may still be running, or it failed)."


def _origin_of(url):
    p = urlsplit(str(url or ""))
    return f"{p.scheme}://{p.netloc}" if p.scheme and p.netloc else ""


def net_headers(req, with_cookie=True):
    """[(name, value)] of the request as the browser sent it: its own headers (User-Agent, Referer, Origin, Cookie)
    from what the helper knows, then the ones the page set. ``with_cookie`` False leaves the Cookie header out."""
    req = req or {}
    method = str(req.get("method") or "GET").upper()
    sent = {}
    for k, v in (req.get("headers") or {}).items():
        sent[str(k).lower()] = (str(k), str(v))
    heads = []
    ua, page = str(req.get("ua") or ""), str(req.get("page") or "")
    if ua:
        heads.append(("User-Agent", ua))
    if page:
        heads.append(("Referer", page))
    if method not in ("GET", "HEAD") and _origin_of(page):
        heads.append(("Origin", _origin_of(page)))
    for low, (k, v) in sent.items():
        if low not in _SKIP_HEADERS:
            heads.append((k, v))
    if (req.get("body") or req.get("form")) and "content-type" not in sent and not req.get("form"):
        heads.append(("Content-Type", str(req.get("ctype") or "text/plain;charset=UTF-8")))
    cookie = str(req.get("cookie") or "")
    if with_cookie and cookie:
        heads.append(("Cookie", cookie))
    return heads


def net_headers_text(req):
    """The request headers to show on screen: every line, the Cookie one without its values."""
    lines = [f"{k}: {v}" for k, v in net_headers(req, False)]
    if (req or {}).get("cookie"):
        lines.append("Cookie: *** (hidden here; the cURL with Cookie has it)")
    return "\n".join(lines)


def net_curl(req, with_cookie=True):
    """'Copy as cURL' of one logged request; ``with_cookie`` False leaves the Cookie header out."""
    req = req or {}
    url = str(req.get("url") or "")
    method = str(req.get("method") or "GET").upper()
    body = str(req.get("body") or "")
    form = [p for p in (req.get("form") or []) if isinstance(p, (list, tuple)) and len(p) == 2]
    parts = ["curl", shlex.quote(url)]
    if method == "HEAD":
        parts.append("-I")
    elif method != "GET" and not (method == "POST" and (body or form)):
        parts += ["-X", shlex.quote(method)]
    for k, v in net_headers(req, with_cookie):
        parts += ["-H", shlex.quote(f"{k}: {v}")]
    if form:
        for k, v in form:
            parts += ["-F", shlex.quote(f"{k}={v}")]
    elif body:
        parts += ["--data-raw", shlex.quote(body)]
    parts.append("--compressed")
    return " ".join(parts)
