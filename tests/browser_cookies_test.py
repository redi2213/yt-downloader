"""Cookie export of the in-app browser (plain Python, no Kivy needed):
    python3 tests/browser_cookies_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import browser_cookies as bc  # noqa: E402

# -- hosts
assert bc.host_chain("a.b.example.com") == ["a.b.example.com", "b.example.com", "example.com"]
assert bc.host_chain("www.example.co.uk") == ["www.example.co.uk", "example.co.uk"]
assert bc.host_chain("example.com") == ["example.com"] and bc.host_chain("10.0.0.5") == ["10.0.0.5"]
assert bc.clean_domain("https://www.Google.com/x") == "www.google.com" and bc.clean_domain(".google.com") == "google.com"
assert bc.clean_domain("localhost") == "" and bc.clean_domain("a b.com") == "" and bc.clean_domain("") == ""
assert bc.page_address("https://x.test/a?b=1#top") == "https://x.test/a?b=1"
assert bc.page_address("about:blank") == "" and bc.page_address("") == ""
hosts = bc.candidate_hosts("https://www.youtube.com/watch?v=1", ["accounts.google.com", "bad domain"])
assert [h["host"] for h in hosts] == ["www.youtube.com", "youtube.com", "google.com", "accounts.google.com"]
assert [h["kind"] for h in hosts] == ["site", "site", "related", "related"]
urls = bc.query_urls("https://www.youtube.com/watch?v=1#t", hosts)
assert urls[0] == "https://www.youtube.com/watch?v=1" and "https://google.com/" in urls and len(urls) == 5

# -- which domain a cookie belongs to
res = [
    {"url": "https://www.example.com/a", "cookie": "sid=1; pref=x; path_only=9"},
    {"url": "https://www.example.com/", "cookie": "sid=1; pref=x"},
    {"url": "https://example.com/", "cookie": "sid=1"},
]
jar = bc.build_jar(res)
by = {c["name"]: c for c in jar}
assert by["sid"] == {"domain": "example.com", "sub": True, "name": "sid", "value": "1"}
assert by["pref"]["domain"] == "www.example.com" and by["pref"]["sub"] is False
assert by["path_only"]["domain"] == "www.example.com"
assert bc.domain_counts(jar) == [("example.com", 1), ("www.example.com", 2)]
assert bc.default_selected(jar, "https://www.example.com/a") == {"example.com", "www.example.com"}
# a root nothing below was asked about: a domain cookie; a host below that does not get it: host-only
jar2 = bc.build_jar([{"url": "https://example.com/", "cookie": "a=1"}])
assert [(c["domain"], c["sub"]) for c in jar2] == [("example.com", True)]
jar3 = bc.build_jar([{"url": "https://example.com/", "cookie": "a=1"}, {"url": "https://x.y.example.com/", "cookie": "b=2"}])
assert {c["name"]: c["sub"] for c in jar3} == {"a": False, "b": False}
assert bc.build_jar([]) == [] and bc.build_jar([{"url": "junk", "cookie": "a=1"}]) == []
# values with = and ; parts
assert bc.parse_header("a=b=c; ; novalue; d=") == [("a", "b=c"), ("d", "")]

# -- selection and Netscape text
chosen = bc.select(jar, {"example.com"})
txt = bc.to_netscape(chosen)
assert txt == "# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t0\tsid\t1\n"
host_txt = bc.to_netscape(bc.select(jar, {"www.example.com"}))
assert "\nwww.example.com\tFALSE\t/\tFALSE\t0\tpref\tx\n" in host_txt
assert bc.to_netscape([{"domain": "a.test", "sub": False, "name": "n\t1", "value": "v\n2"}]).splitlines()[1].count("\t") == 6
assert bc.valid_cookies_txt(txt)[1] == "" and bc.valid_cookies_txt(bc.NETSCAPE_HEADER)[1] != ""
assert bc.valid_cookies_txt("junk")[1] != "" and bc.valid_cookies_txt("")[1] != ""
assert bc.valid_cookies_txt(bc.to_netscape([{"domain": "a.test", "sub": False, "name": "n", "value": "v" * 50000}]))[1] != ""

# -- headers for the tools
mixed = [{"domain": "example.com", "sub": True, "name": "k", "value": "wide"},
         {"domain": "www.example.com", "sub": False, "name": "k", "value": "narrow"},
         {"domain": "example.com", "sub": True, "name": "z", "value": "2"}]
assert bc.cookie_header(mixed) == "k=narrow; z=2"
ua, ref = "Mozilla/5.0 (X11; it's)", "https://www.example.com/a?x=1&y=2"
opts = bc.ytdlp_options(ua, ref)
assert opts.startswith("--cookies cookies.txt --user-agent ") and "secret" not in opts
assert bc.ytdlp_options() == "--cookies cookies.txt"
c1 = bc.curl_command("https://x.test/f.mp4", ua, ref)
assert c1.startswith("curl -L -b cookies.txt -A ") and c1.endswith("https://x.test/f.mp4")
c2 = bc.curl_command("", ua, ref, "k=narrow; z=2")
assert "-H 'Cookie: k=narrow; z=2'" in c2 and c2.endswith("'URL'")
assert "'\"'\"'" in c1                      # the apostrophe of the user agent is quoted safely

# -- older build: only cookies sent with found files
items = [{"url": "https://cdn.example.com/a.mp4", "headers": {"Cookie": "t=1", "User-Agent": "UA1"}},
         {"url": "https://x/b.mp4", "headers": {}}]
assert bc.results_from_items(items) == [{"url": "https://cdn.example.com/a.mp4", "cookie": "t=1"}]
assert bc.ua_from_items(items) == "UA1" and bc.ua_from_items([]) == ""

# -- redact: no cookie value survives in a message
secret = bc.to_netscape([{"domain": "a.test", "sub": True, "name": "session", "value": "SUPERSECRETVALUE"}])
for msg in ("bad request: SUPERSECRETVALUE", "failed for session\tSUPERSECRETVALUE end", "x session=SUPERSECRETVALUE"):
    assert "SUPERSECRETVALUE" not in bc.redact(msg, secret), msg
assert "SUPERSECRETVALUE" not in bc.redact("Cookie: session=SUPERSECRETVALUE", "session=SUPERSECRETVALUE")
assert bc.redact("plain message", secret) == "plain message" and bc.redact("", "") == ""
# -- network log: Copy as cURL
req = {"k": "xhr", "url": "https://dl6.irweb.top/get?id=1", "method": "POST", "headers": {"X-Test": "1", "Cookie": "no"},
       "body": "a=1&b='2'", "page": "https://linkirani.ir/?url=x", "cookie": "s=SECRET", "ua": "UA/1"}
cmd = bc.net_curl(req, True)
assert cmd.startswith("curl 'https://dl6.irweb.top/get?id=1'") and "-X" not in cmd
assert "-H 'X-Test: 1'" in cmd and "-H 'Cookie: s=SECRET'" in cmd and "-H 'Cookie: no'" not in cmd
assert "-H 'Origin: https://linkirani.ir'" in cmd and "-H 'Referer: https://linkirani.ir/?url=x'" in cmd
assert "-H 'Content-Type: text/plain;charset=UTF-8'" in cmd and "--data-raw" in cmd and cmd.endswith("--compressed")
assert "SECRET" not in bc.net_curl(req, False)
get = {"url": "https://a.test/x", "method": "GET", "page": "https://a.test/", "ua": "UA"}
cmd = bc.net_curl(get, False)
assert "Origin" not in cmd and "-X" not in cmd and "--data-raw" not in cmd
assert "-X PUT" in bc.net_curl({"url": "https://a.test/x", "method": "PUT", "body": "z"}, False)
assert "-F k=v" in bc.net_curl({"url": "https://a.test/x", "method": "POST", "form": [["k", "v"]]}, False)
assert "application/x-www-form-urlencoded" in bc.net_curl({"url": "https://a.test/x", "method": "POST", "body": "a=1",
                                                          "ctype": "application/x-www-form-urlencoded;charset=UTF-8"}, False)
assert bc.net_body_unknown({"bin": 1}) and not bc.net_body_unknown({"bin": 1, "body": "x"})
items = [{"url": "https://a.test/one", "method": "GET"}, {"url": "https://a.test/two", "method": "POST", "body": "needle"}, {"x": 1}]
assert [r["url"] for r in bc.net_filter(items)] == ["https://a.test/two", "https://a.test/one"]
assert [r["url"] for r in bc.net_filter(items, "NEEDLE")] == ["https://a.test/two"] and bc.net_filter(None) == []
assert bc.net_title({"url": "https://a.test/p?q=1", "method": "post"}) == "POST a.test/p?q=1"
assert len(bc.net_title({"url": "https://a.test/" + "x" * 200, "method": "GET"})) == 56

print("browser cookies tests: ok")
