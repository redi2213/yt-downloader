"""InstaMod - check the SamMods site (instamod.app) for new app versions, with no ads.

The phone reads the page itself (plain HTTP, no browser, no ad scripts), drops the ad redirects that are
glued before every real link (ad, ad, real file), and shows each app version with its real links.
MediaFire pages are opened in the background to get the direct file link. Versions seen before are
remembered, so a new one is marked NEW.
"""
import re

SITE = "https://www.instamod.app/?m=1"
UA = ("Mozilla/5.0 (Linux; Android 13; M2101K6G Build/TKQ1.221013.002) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
GOOD = ("mediafire.com", "drive.usercontent.google.com", "drive.google.com", "mega.nz", "github.com", "dropbox.com")
NOISE = {"install", "old", "mediafire", "googledrive", "version", "servers", "download", "senders"}

A_RE = re.compile(r"<a\b[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
VER_RE = re.compile(r"(\S+)\s+[vV](\d[\d.]*)")
ARCH_RE = re.compile(r"arm64-v8a?|armeabi-v7a?", re.I)
MF_SCRAMBLED = re.compile(r'data-scrambled-url="([^"]+)"')
MF_HREF = re.compile(r'href="(https?://download[0-9a-z.-]*\.mediafire\.com/[^"]+)"', re.I)


def _text(html):
    t = TAG_RE.sub(" ", html or "")
    t = t.replace("&amp;", "&").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", t).strip()


def _host(url):
    m = re.match(r"https?://([^/?#]+)", url or "", re.I)
    return m.group(1).lower() if m else ""


def _tag(url):
    h = _host(url)
    for key, name in (("mediafire", "MediaFire"), ("google", "Drive"), ("mega.nz", "Mega"),
                      ("github", "GitHub"), ("dropbox", "Dropbox")):
        if key in h:
            return name
    return h


def clean_links(href):
    """A button address can hold several addresses joined by commas: ad, ad, real file (sometimes two real
    files). Keep only the ones on a known file host, in order."""
    href = (href or "").replace("&amp;", "&")
    parts = [p for p in re.split(r",(?=https?://)", href) if p.lower().startswith("http")]
    return [p for p in parts if any(_host(p) == g or _host(p).endswith("." + g) for g in GOOD)]


def parse(html):
    """-> {"new": [group, ...], "old": [group, ...]}; group = {"title", "links": [(label, url)]}"""
    out = {"new": [], "old": []}
    pos, cur, old = 0, None, False
    for m in A_RE.finditer(html or ""):
        urls = clean_links(m.group(1))
        if not urls:
            continue
        between = _text(html[pos:m.start()])
        pos = m.end()
        if "old version" in between.lower():
            old = True
        vers = list(VER_RE.finditer(between))
        if vers:
            v = vers[-1]
            name = v.group(1).strip("*")
            if name.lower() == "thunder":
                before = between[:v.start()].split()
                name = (before[-1] + " Thunder") if before else "Thunder"
            arch = ARCH_RE.findall(between[v.end():])
            title = "%s v%s%s" % (name, v.group(2), " " + arch[-1] if arch else "")
            bucket = out["old" if old else "new"]
            cur = next((g for g in bucket if g["title"] == title), None)
            if cur is None:
                cur = {"title": title, "links": []}
                bucket.append(cur)
        if cur is None:
            continue
        label = _text(m.group(2)) or "File"
        for u in urls:
            if all(u != x[1] for x in cur["links"]):
                cur["links"].append(("%s [%s]" % (label, _tag(u)), u))
    return out


def mediafire_direct(html):
    import base64
    m = MF_SCRAMBLED.search(html or "")
    if m:
        try:
            raw = m.group(1)
            link = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8", "ignore").strip()
            if link.startswith("http"):
                return link
        except Exception:
            pass
    m = MF_HREF.search(html or "")
    return m.group(1).replace("&amp;", "&") if m else ""


def build(host):
    host.title("InstaMod - app updates")
    host.text("Reads instamod.app on this phone without ads and shows the real file links of the newest "
              "versions. Versions you have seen before are not marked NEW.")
    host.button("Check for updates", lambda: host.show(check))
    host.status()
    host.back_button("Back")


def check(host):
    host.title("InstaMod - app updates")
    host.status()
    host.set_status("Reading the site...")

    def work():
        r = host.get(SITE, headers={"User-Agent": UA})
        data = parse(r.text)
        if not data["new"] and not data["old"]:
            raise RuntimeError("No download links found on the page")
        return data

    def done(result, error):
        if error:
            host.set_status("Failed: %s" % str(error)[:120])
            return
        host.replace(show_list, result)

    host.background(work, done=done)
    host.back_button()


def show_list(host, data):
    seen = set(host.store.get("seen", []))
    host.title("Newest versions")
    for g in data["new"]:
        mark = "NEW  " if seen and g["title"] not in seen else ""
        host.button("%s%s  (%d files)" % (mark, g["title"], len(g["links"])),
                    lambda g=g: host.show(show_group, g))
    host.store.set("seen", sorted(seen | {g["title"] for g in data["new"]}))
    if data["old"]:
        host.button("Old versions (%d)" % len(data["old"]), lambda: host.show(show_old, data["old"]))
    host.back_button()


def show_old(host, groups):
    host.title("Old versions")
    for g in groups:
        host.button("%s  (%d files)" % (g["title"], len(g["links"])), lambda g=g: host.show(show_group, g))
    host.back_button()


def show_group(host, g):
    host.title(g["title"])
    host.text("Tap a file: the direct link is found, then you can copy or open it.")
    host.status()
    for label, url in g["links"]:
        host.button(label, lambda label=label, url=url: _resolve(host, label, url))
    host.back_button()


def _resolve(host, label, url):
    host.set_status("Getting the direct link...")

    def work():
        if "mediafire.com" in _host(url) and "download" not in _host(url):
            r = host.get(url, headers={"User-Agent": UA})
            link = mediafire_direct(r.text)
            if not link:
                raise RuntimeError("No direct link on the MediaFire page")
            return link
        if "drive.usercontent.google.com" in _host(url) and "confirm=" not in url:
            return url + "&confirm=t"
        return url

    def done(result, error):
        if error:
            host.set_status("Failed: %s" % str(error)[:120])
            return
        host.log("direct:", label, result)
        host.show(show_result, label, result)

    host.background(work, done=done)


def show_result(host, label, url):
    host.title(label)
    host.text(url)
    host.status()
    host.row([("Copy link", lambda: (host.copy(url), host.set_status("Copied"))),
              ("Open", lambda: host.open_url(url))])
    host.back_button()
