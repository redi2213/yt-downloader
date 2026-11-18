"""DLNA/UPnP core for casting a file to a TV (no Kivy). Used by lab/dlna_tv.py.

Pieces: MulticastLock (Android), SSDP discovery of MediaRenderers, SOAP calls
(AVTransport / RenderingControl), a small HTTP media server with Range support,
download-to-phone helper and a media scanner. Self-test: python dlna_core.py (prints ok).
"""
import mimetypes
import os
import re
import socket
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape

import requests

SSDP_ADDR = ("239.255.255.250", 1900)
ST_RENDERER = "urn:schemas-upnp-org:device:MediaRenderer:1"
ST_AVT = "urn:schemas-upnp-org:service:AVTransport:1"
FEATURES = "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000"
MIME = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm",
    ".avi": "video/x-msvideo", ".mov": "video/quicktime", ".ts": "video/mp2t", ".3gp": "video/3gpp",
    ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg",
    ".opus": "audio/ogg", ".flac": "audio/flac", ".wav": "audio/wav",
}


class DlnaError(Exception):
    pass


# ---------------------------------------------------------------- Android multicast lock
_lock = {"obj": None}


def acquire_multicast_lock():
    """(ok, message). Needs CHANGE_WIFI_MULTICAST_STATE + ACCESS_WIFI_STATE in the APK."""
    if _lock["obj"] is not None:
        return True, ""
    try:
        from jnius import autoclass
    except Exception:
        return True, "not on Android (no lock needed)"
    try:
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        ctx = autoclass("android.content.Context")
        wifi = activity.getApplicationContext().getSystemService(ctx.WIFI_SERVICE)
        lock = wifi.createMulticastLock("ytbridge_dlna")
        lock.setReferenceCounted(False)
        lock.acquire()
        _lock["obj"] = lock
        return True, ""
    except Exception as e:
        text = str(e)
        if "Permission" in text or "permission" in text or "SecurityException" in text:
            text = "permission missing (CHANGE_WIFI_MULTICAST_STATE / ACCESS_WIFI_STATE): a new APK build is needed. " + text
        return False, text


def release_multicast_lock():
    lock, _lock["obj"] = _lock["obj"], None
    try:
        if lock is not None and lock.isHeld():
            lock.release()
    except Exception:
        pass


def local_ip_for(host):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, 9))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


# ---------------------------------------------------------------- XML helpers
def _ln(tag):
    return tag.rsplit("}", 1)[-1]


def _child_text(el, name):
    for c in el:
        if _ln(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_description(content, location):
    """Device description XML -> renderer dict, or None when it is not a MediaRenderer."""
    root = ET.fromstring(content)
    base = location
    for el in root.iter():
        if _ln(el.tag) == "URLBase" and (el.text or "").strip():
            base = el.text.strip()
            break
    dev = None
    for el in root.iter():
        if _ln(el.tag) == "device" and "MediaRenderer" in _child_text(el, "deviceType"):
            dev = el
            break
    if dev is None:
        return None
    services = {}
    for el in dev.iter():
        if _ln(el.tag) == "service":
            stype = _child_text(el, "serviceType")
            ctrl = _child_text(el, "controlURL")
            if stype and ctrl:
                services[stype] = {"type": stype, "url": urllib.parse.urljoin(base, ctrl)}
    avt = next((v for k, v in services.items() if ":service:AVTransport:" in k), None)
    rc = next((v for k, v in services.items() if ":service:RenderingControl:" in k), None)
    return {
        "name": _child_text(dev, "friendlyName") or "TV",
        "udn": _child_text(dev, "UDN"),
        "location": location,
        "host": urllib.parse.urlsplit(location).hostname or "",
        "avt": avt,
        "rc": rc,
    }


def discover(timeout=6.0):
    """SSDP M-SEARCH for MediaRenderers. Returns a list of renderer dicts (needs the multicast lock)."""
    locs = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 4)
        sock.settimeout(0.4)
        end = time.time() + timeout
        next_send = 0.0
        while time.time() < end:
            if time.time() >= next_send:
                for st in (ST_RENDERER, ST_AVT):
                    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
                           "MAN: \"ssdp:discover\"\r\nMX: 2\r\nST: %s\r\n\r\n" % st).encode()
                    try:
                        sock.sendto(msg, SSDP_ADDR)
                    except OSError:
                        pass
                next_send = time.time() + 2.0
            try:
                data, _addr = sock.recvfrom(65507)
            except socket.timeout:
                continue
            except OSError:
                break
            m = re.search(r"(?im)^location:\s*(\S+)", data.decode("utf-8", "replace"))
            if m and m.group(1) not in locs:
                locs.append(m.group(1))
    finally:
        sock.close()

    def one(loc):
        try:
            return parse_description(requests.get(loc, timeout=4).content, loc)
        except Exception:
            return None

    found = {}
    if locs:
        with ThreadPoolExecutor(6) as ex:
            for d in ex.map(one, locs):
                if d and d["avt"]:
                    found.setdefault(d["udn"] or d["location"], d)
    return sorted(found.values(), key=lambda d: d["name"].lower())


# ---------------------------------------------------------------- SOAP
_ERR = re.compile(r"<errorCode>\s*(\d+)\s*</errorCode>.*?<errorDescription>(.*?)</errorDescription>", re.S)


def soap(url, stype, action, args, timeout=8):
    inner = "".join("<%s>%s</%s>" % (k, escape(str(v)), k) for k, v in args)
    body = ('<?xml version="1.0" encoding="utf-8"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            '<u:%s xmlns:u="%s">%s</u:%s></s:Body></s:Envelope>') % (action, stype, inner, action)
    headers = {"Content-Type": 'text/xml; charset="utf-8"', "SOAPACTION": '"%s#%s"' % (stype, action)}
    try:
        r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise DlnaError("%s: %s" % (action, e))
    if r.status_code >= 300:
        m = _ERR.search(r.text or "")
        raise DlnaError("%s failed: %s" % (action, ("UPnP %s %s" % (m.group(1), m.group(2).strip())) if m else "HTTP %d" % r.status_code))
    out = {}
    try:
        root = ET.fromstring(r.content)
        for el in root.iter():
            if _ln(el.tag) == "Body" and len(el):
                for c in el[0]:
                    out[_ln(c.tag)] = (c.text or "").strip()
                break
    except ET.ParseError:
        pass
    return out


def _avt(tv, action, args):
    return soap(tv["avt"]["url"], tv["avt"]["type"], action, args)


def _rc(tv, action, args):
    if not tv.get("rc"):
        raise DlnaError("this TV has no volume control")
    return soap(tv["rc"]["url"], tv["rc"]["type"], action, args)


def fmt_time(sec):
    sec = int(max(0, sec))
    return "%d:%02d:%02d" % (sec // 3600, sec % 3600 // 60, sec % 60)


def parse_time(text):
    """'H:MM:SS(.f)' -> seconds; anything else (NOT_IMPLEMENTED ...) -> 0."""
    try:
        total = 0.0
        for part in (text or "").strip().split(":"):
            total = total * 60 + float(part)
        return int(total)
    except ValueError:
        return 0


def parse_user_time(text):
    """What the user types: seconds, mm:ss or h:mm:ss -> seconds (None if invalid)."""
    t = (text or "").strip()
    if not re.fullmatch(r"\d+(:\d{1,2}){0,2}", t):
        return None
    return parse_time(t)


def mime_of(path):
    ext = os.path.splitext(path)[1].lower()
    return MIME.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream"


def didl(url, title, mime, size):
    kind = "object.item.audioItem.musicTrack" if mime.startswith("audio/") else "object.item.videoItem"
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/">'
            '<item id="0" parentID="-1" restricted="1"><dc:title>%s</dc:title><upnp:class>%s</upnp:class>'
            '<res protocolInfo="http-get:*:%s:%s" size="%d">%s</res></item></DIDL-Lite>'
            ) % (escape(title), kind, mime, FEATURES, size, escape(url))


def cast(tv, url, path):
    """Stop, SetAVTransportURI, Play."""
    mime = mime_of(path)
    title = os.path.splitext(os.path.basename(path))[0]
    meta = didl(url, title, mime, os.path.getsize(path))
    try:
        _avt(tv, "Stop", [("InstanceID", 0)])
    except DlnaError:
        pass
    try:
        _avt(tv, "SetAVTransportURI", [("InstanceID", 0), ("CurrentURI", url), ("CurrentURIMetaData", meta)])
    except DlnaError:
        _avt(tv, "SetAVTransportURI", [("InstanceID", 0), ("CurrentURI", url), ("CurrentURIMetaData", "")])
    time.sleep(0.5)
    play(tv)


def play(tv):
    _avt(tv, "Play", [("InstanceID", 0), ("Speed", "1")])


def pause(tv):
    _avt(tv, "Pause", [("InstanceID", 0)])


def stop(tv):
    _avt(tv, "Stop", [("InstanceID", 0)])


def seek(tv, seconds):
    target = fmt_time(seconds)
    try:
        _avt(tv, "Seek", [("InstanceID", 0), ("Unit", "REL_TIME"), ("Target", target)])
    except DlnaError:
        _avt(tv, "Seek", [("InstanceID", 0), ("Unit", "ABS_TIME"), ("Target", target)])


def position(tv):
    d = _avt(tv, "GetPositionInfo", [("InstanceID", 0)])
    return {"rel": parse_time(d.get("RelTime")), "dur": parse_time(d.get("TrackDuration"))}


def state(tv):
    return _avt(tv, "GetTransportInfo", [("InstanceID", 0)]).get("CurrentTransportState", "?")


def get_volume(tv):
    d = _rc(tv, "GetVolume", [("InstanceID", 0), ("Channel", "Master")])
    return int(d.get("CurrentVolume") or 0)


def set_volume(tv, value):
    _rc(tv, "SetVolume", [("InstanceID", 0), ("Channel", "Master"), ("DesiredVolume", int(max(0, min(100, value))))])


# ---------------------------------------------------------------- media server (Range)
class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "YTBridgeDLNA/1"

    def log_message(self, *args):
        pass

    def do_HEAD(self):
        self._safe(False)

    def do_GET(self):
        self._safe(True)

    def _safe(self, body):
        try:
            self._serve(body)
        except Exception:
            self.close_connection = True

    def _plain(self, code, extra=None):
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _serve(self, body):
        parts = urllib.parse.urlsplit(self.path).path.split("/")
        path = self.server.items.get(parts[2]) if len(parts) >= 3 and parts[1] == "media" else None
        if not path or not os.path.isfile(path):
            self._plain(404)
            return
        size = os.path.getsize(path)
        start, end, status = 0, size - 1, 200
        m = re.match(r"\s*bytes\s*=\s*(\d*)\s*-\s*(\d*)", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            a, b = m.groups()
            if not a:
                start = max(0, size - int(b))
            else:
                start = int(a)
                end = min(int(b), size - 1) if b else size - 1
            if start >= size or start > end:
                self._plain(416, {"Content-Range": "bytes */%d" % size})
                return
            status = 206
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", mime_of(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("transferMode.dlna.org", "Streaming")
        self.send_header("contentFeatures.dlna.org", FEATURES)
        self.end_headers()
        if not body:
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


class MediaServer:
    def __init__(self):
        self.items = {}
        self.httpd = None
        self.port = 0

    @property
    def running(self):
        return self.httpd is not None

    def start(self, port=0):
        if self.httpd:
            return self.port
        httpd = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
        httpd.daemon_threads = True
        httpd.items = self.items
        self.httpd = httpd
        self.port = httpd.server_address[1]
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        return self.port

    def stop(self):
        httpd, self.httpd = self.httpd, None
        if httpd:
            httpd.shutdown()
            httpd.server_close()

    def add(self, path):
        key = "%x" % (abs(hash(os.path.abspath(path))) % (1 << 40))
        self.items[key] = path
        return key

    def url_for(self, ip, key):
        name = os.path.basename(self.items[key])
        return "http://%s:%d/media/%s/%s" % (ip, self.port, key, urllib.parse.quote(name, safe=""))


# ---------------------------------------------------------------- files
def _filename(resp, url):
    cd = resp.headers.get("Content-Disposition") or ""
    name = ""
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", cd)
    if m:
        name = urllib.parse.unquote(m.group(1).strip())
    else:
        m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd)
        if m:
            name = m.group(1).strip()
    if not name:
        name = urllib.parse.unquote(os.path.basename(urllib.parse.urlsplit(url).path))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "video"
    if not os.path.splitext(name)[1]:
        ext = mimetypes.guess_extension((resp.headers.get("Content-Type") or "").split(";")[0].strip()) or ".mp4"
        name += ext
    return name


def download(url, dest_dir, on_progress=None):
    """Download a direct link to this phone first. Returns the local path."""
    os.makedirs(dest_dir, exist_ok=True)
    with requests.get(url, stream=True, timeout=30, allow_redirects=True) as r:
        r.raise_for_status()
        name = _filename(r, url)
        dest = os.path.join(dest_dir, name)
        base, ext = os.path.splitext(dest)
        n = 1
        while os.path.exists(dest):
            n += 1
            dest = "%s (%d)%s" % (base, n, ext)
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                done += len(chunk)
                now = time.time()
                if on_progress and now - last > 0.7:
                    last = now
                    on_progress(done, total)
        os.replace(tmp, dest)
    return dest


def scan_media(extra_roots=(), limit=40):
    roots = list(extra_roots) + ["/storage/emulated/0/Download", "/storage/emulated/0/Movies",
                                 "/storage/emulated/0/Music", "/sdcard/Download"]
    seen, rows = set(), []
    for root in roots:
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirs, files in os.walk(root):
            if dirpath.count(os.sep) - base_depth >= 4:
                dirs[:] = []
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in MIME:
                    continue
                p = os.path.join(dirpath, fn)
                real = os.path.realpath(p)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                rows.append((st.st_mtime, p, st.st_size))
    rows.sort(reverse=True)
    return [(p, s) for _m, p, s in rows[:limit]]


def human_size(n):
    v = float(n)
    for u in ("B", "KB", "MB", "GB"):
        if v < 1024 or u == "GB":
            return "%d B" % v if u == "B" else "%.1f %s" % (v, u)
        v /= 1024.0


# ---------------------------------------------------------------- self-test
def _selftest():
    import tempfile

    assert fmt_time(3725) == "1:02:05" and parse_time("1:02:05.500") == 3725 and parse_time("NOT_IMPLEMENTED") == 0
    assert parse_user_time("90") == 90 and parse_user_time("1:30") == 90 and parse_user_time("x") is None
    xml = ('<root xmlns="urn:schemas-upnp-org:device-1-0"><device><deviceType>urn:schemas-upnp-org:device:MediaRenderer:1'
           '</deviceType><friendlyName>Living TV</friendlyName><UDN>uuid:1</UDN><serviceList>'
           '<service><serviceType>urn:schemas-upnp-org:service:AVTransport:1</serviceType><controlURL>/avt</controlURL></service>'
           '<service><serviceType>urn:schemas-upnp-org:service:RenderingControl:1</serviceType><controlURL>rc</controlURL></service>'
           '</serviceList></device></root>')
    d = parse_description(xml.encode(), "http://192.168.1.5:8080/desc.xml")
    assert d["name"] == "Living TV" and d["avt"]["url"] == "http://192.168.1.5:8080/avt" and d["rc"]["url"].endswith("/rc")
    assert parse_description(b"<root><device><deviceType>x:Router</deviceType></device></root>", "http://a/b") is None
    assert "&lt;DIDL-Lite" in escape(didl("http://x/y&z", "\u0641\u06cc\u0644\u0645", "video/mp4", 5))

    # media server: Range, HEAD, Persian name
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "\u0641\u06cc\u0644\u0645 \u062a\u0633\u062a.mp4")
    data = bytes(range(256)) * 4
    open(path, "wb").write(data)
    srv = MediaServer()
    srv.start()
    url = srv.url_for("127.0.0.1", srv.add(path))
    assert "%D9%81" in url
    r = requests.get(url, headers={"Range": "bytes=100-199"})
    assert r.status_code == 206 and r.content == data[100:200] and r.headers["Content-Range"] == "bytes 100-199/1024"
    r = requests.get(url, headers={"Range": "bytes=1000-"})
    assert r.status_code == 206 and r.content == data[1000:]
    r = requests.get(url, headers={"Range": "bytes=-24"})
    assert r.content == data[-24:]
    assert requests.get(url, headers={"Range": "bytes=5000-"}).status_code == 416
    assert requests.get(url).content == data and requests.head(url).headers["Content-Length"] == "1024"
    assert requests.get(url.replace("/media/", "/nope/")).status_code == 404

    # fake TV: SOAP headers / escaping / response parsing
    class Fake(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            self.server.log.append((self.headers["SOAPACTION"], body))
            out = ('<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:R xmlns:u="x">'
                   '<CurrentVolume>17</CurrentVolume><RelTime>0:01:30</RelTime><TrackDuration>1:00:00</TrackDuration>'
                   '</u:R></s:Body></s:Envelope>').encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

    fake = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    fake.log = []
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    u = "http://127.0.0.1:%d/c" % fake.server_address[1]
    tv = {"avt": {"url": u, "type": "urn:schemas-upnp-org:service:AVTransport:1"},
          "rc": {"url": u, "type": "urn:schemas-upnp-org:service:RenderingControl:1"}}
    assert get_volume(tv) == 17 and position(tv) == {"rel": 90, "dur": 3600}
    cast(tv, url, path)
    seek(tv, 125)
    set_volume(tv, 250)
    actions = [a for a, _b in fake.log]
    assert '"urn:schemas-upnp-org:service:AVTransport:1#SetAVTransportURI"' in actions
    assert any("<Target>0:02:05</Target>" in b for _a, b in fake.log)
    assert any("<DesiredVolume>100</DesiredVolume>" in b for _a, b in fake.log)
    assert any("&lt;DIDL-Lite" in b and "%D9%81" in b for _a, b in fake.log)
    fake.shutdown()
    srv.stop()
    print("ok")


if __name__ == "__main__":
    _selftest()
