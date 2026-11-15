"""In-app browser page tools that need no Build (pure Python: no Kivy, no network): the address of a page
translated by Google Translate and back, and the site name shown when clearing a site's data."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRANSLATE_SUFFIX = ".translate.goog"
_TR_KEYS = ("_x_tr_sl", "_x_tr_tl", "_x_tr_hl", "_x_tr_pto")


def host_of(url):
    try:
        return urlsplit(str(url or "")).hostname or ""
    except ValueError:
        return ""


def is_translated(url):
    return host_of(url).endswith(TRANSLATE_SUFFIX)


def original_url(url):
    """The real address behind a translate.goog address (the address itself when it is not one)."""
    if not is_translated(url):
        return str(url or "")
    parts = urlsplit(url)
    label = host_of(url)[:-len(TRANSLATE_SUFFIX)]
    real = label.replace("--", "\0").replace("-", ".").replace("\0", "-")
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in _TR_KEYS])
    return urlunsplit(("https", real, parts.path, query, parts.fragment))


def translate_url(url, lang="fa"):
    """The same page opened through Google Translate (translate.goog): "" when the address cannot be translated
    (not http(s), no host, or a custom port)."""
    url = original_url(url)
    try:
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in ("http", "https") or not host or parts.port:
            return ""
    except ValueError:
        return ""
    new_host = host.replace("-", "--").replace(".", "-") + TRANSLATE_SUFFIX
    extra = urlencode({"_x_tr_sl": "auto", "_x_tr_tl": lang, "_x_tr_hl": lang, "_x_tr_pto": "wapp"})
    query = parts.query + ("&" if parts.query else "") + extra
    return urlunsplit(("https", new_host, parts.path or "/", query, parts.fragment))
