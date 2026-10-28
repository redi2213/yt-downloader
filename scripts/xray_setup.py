#!/usr/bin/env python3
"""Starts a local Xray SOCKS5 proxy (127.0.0.1:10808) from a v2ray config.

Used by the workflows only to read pages (extract step) from another IP than GitHub's.
Input (env V2RAY_CONFIG), any of these, mixed with spaces or new lines:
  * share links      vless:// vmess:// trojan:// ss://   (ws, grpc, tcp, httpupgrade, xhttp, kcp, h2; tls, reality)
  * subscription URL http(s)://...  (base64 or plain list; the nodes are tested, the first working one is used)
  * a full Xray JSON config (ignored, with a warning, when it has no real proxy outbound)

On success it writes /tmp/xray.pid and /tmp/xray_from_config; on any problem it only prints
a warning and exits 0, so the caller carries on without it (free proxy list). Secrets are never printed:
only "protocol host:port" of the node that is used.
"""
import base64
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

PORT = 10808
XRAY_DIR = "/tmp/xray-core"
XRAY_BIN = XRAY_DIR + "/xray"
PROBE = os.environ.get("PROBE_URL", "https://cp.cloudflare.com/generate_204")
MAX_NODES = 30
TEST_WORKERS = 6
SCHEMES = ("vless", "vmess", "trojan", "ss")
UNSUPPORTED = ("hysteria2", "hy2", "hysteria", "tuic", "ssr", "wireguard", "wg")
VALID_FP = {"chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized"}
REAL_OUTBOUNDS = {"vmess", "vless", "trojan", "shadowsocks", "socks", "http", "wireguard", "hysteria", "hysteria2"}
UA = {"User-Agent": "v2rayN/6.60"}


def warn(msg):
    print(f"::warning::{msg}", flush=True)


def b64d(s):
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def one(q, *names):
    for n in names:
        v = q.get(n)
        if v not in (None, ""):
            return v
    return ""


def truthy(v):
    return str(v).lower() in ("1", "true", "yes")


# ------------------------------------------------------------------ stream settings
def stream_settings(net, security, q, host, sni, path, hhost):
    net = (net or "tcp").lower()
    net = {"http": "h2", "websocket": "ws", "splithttp": "xhttp", "raw": "tcp", "mkcp": "kcp"}.get(net, net)
    st = {"network": net}
    sec = (security or "none").lower()
    if sec in ("tls", "xtls"):
        tls = {"serverName": sni or hhost or host, "fingerprint": one(q, "fp") or "chrome"}
        if tls["fingerprint"] not in VALID_FP:
            tls["fingerprint"] = "chrome"
        alpn = [a.strip() for a in urllib.parse.unquote(one(q, "alpn")).split(",") if a.strip()]
        if alpn:
            tls["alpn"] = alpn
        if truthy(one(q, "allowInsecure", "insecure")):
            tls["allowInsecure"] = True
        st["security"] = "tls"
        st["tlsSettings"] = tls
    elif sec == "reality":
        fp = one(q, "fp") or "chrome"
        rs = {"serverName": sni or host, "fingerprint": fp if fp in VALID_FP else "chrome",
              "publicKey": one(q, "pbk"), "shortId": one(q, "sid"), "spiderX": urllib.parse.unquote(one(q, "spx"))}
        if one(q, "pqv"):
            rs["mldsa65Verify"] = one(q, "pqv")
        st["security"] = "reality"
        st["realitySettings"] = rs
    if net == "ws":
        ws = {"path": path or "/"}
        if hhost:
            ws["headers"] = {"Host": hhost}
        st["wsSettings"] = ws
    elif net == "grpc":
        st["grpcSettings"] = {"serviceName": (one(q, "serviceName") or path or "").lstrip("/"),
                              "multiMode": one(q, "mode") == "multi",
                              **({"authority": one(q, "authority")} if one(q, "authority") else {})}
    elif net == "httpupgrade":
        st["httpupgradeSettings"] = {"path": path or "/", **({"host": hhost} if hhost else {})}
    elif net == "xhttp":
        xs = {"path": path or "/", **({"host": hhost} if hhost else {})}
        if one(q, "mode"):
            xs["mode"] = one(q, "mode")
        if one(q, "extra"):
            try:
                xs["extra"] = json.loads(urllib.parse.unquote(one(q, "extra")))
            except ValueError:
                pass
        st["xhttpSettings"] = xs
    elif net == "h2":
        st["httpSettings"] = {"path": path or "/", **({"host": [h for h in hhost.split(",") if h]} if hhost else {})}
    elif net == "kcp":
        ks = {"header": {"type": one(q, "headerType") or "none"}}
        if one(q, "seed"):
            ks["seed"] = one(q, "seed")
        st["kcpSettings"] = ks
    elif net == "tcp" and one(q, "headerType") == "http":
        st["tcpSettings"] = {"header": {"type": "http", "request": {
            "path": [p for p in (path or "/").split(",") if p],
            **({"headers": {"Host": [h for h in hhost.split(",") if h]}} if hhost else {})}}}
    return st


# ------------------------------------------------------------------ share links -> outbound
def parse_vmess(link):
    d = json.loads(b64d(link.split("://", 1)[1]).decode("utf-8", "ignore"))
    host, port = d.get("add") or "", int(d.get("port") or 443)
    q = {"fp": d.get("fp") or "", "alpn": d.get("alpn") or "", "headerType": d.get("type") or ""}
    st = stream_settings(d.get("net"), (d.get("tls") or "none") or "none", q, host,
                         d.get("sni") or "", d.get("path") or "/", d.get("host") or "")
    ob = {"protocol": "vmess", "settings": {"vnext": [{"address": host, "port": port, "users": [
        {"id": d.get("id"), "alterId": int(d.get("aid") or 0), "security": d.get("scy") or "auto"}]}]},
        "streamSettings": st}
    return ob, host, port


def parse_url_link(link, proto):
    u = urllib.parse.urlsplit(link)
    q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
    user = urllib.parse.unquote(u.username or "")
    host, port = u.hostname or "", u.port or 443
    sec = (q.get("security") or ("tls" if proto == "trojan" else "none")).lower()
    path = urllib.parse.unquote(q.get("path") or "")
    st = stream_settings(q.get("type") or "tcp", sec, q, host, q.get("sni") or "", path, q.get("host") or "")
    if proto == "vless":
        usr = {"id": user, "encryption": q.get("encryption") or "none"}
        if q.get("flow"):
            usr["flow"] = q["flow"]
        settings = {"vnext": [{"address": host, "port": port, "users": [usr]}]}
    else:
        settings = {"servers": [{"address": host, "port": port, "password": user}]}
    return {"protocol": proto, "settings": settings, "streamSettings": st}, host, port


def parse_ss(link):
    body = link[5:]
    frag = ""
    if "#" in body:
        body, frag = body.split("#", 1)
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    q = dict(urllib.parse.parse_qsl(query))
    body = body.rstrip("/")
    if "@" in body:
        ui, hp = body.rsplit("@", 1)
        try:
            ui = b64d(ui).decode()
        except Exception:
            ui = urllib.parse.unquote(ui)
    else:
        dec = b64d(urllib.parse.unquote(body)).decode()
        ui, hp = dec.rsplit("@", 1)
    method, password = ui.split(":", 1)
    host, port = hp.rsplit(":", 1)
    ob = {"protocol": "shadowsocks", "settings": {"servers": [{"address": host.strip("[]"), "port": int(port),
          "method": method, "password": password}]}}
    plugin = urllib.parse.unquote(q.get("plugin", ""))
    if plugin:
        parts = plugin.split(";")
        kv = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
        if parts[0] not in ("v2ray-plugin", "xray-plugin"):
            raise ValueError(f"ss plugin {parts[0]} not supported")
        sec = "tls" if "tls" in parts[1:] else "none"
        ob["streamSettings"] = stream_settings("ws", sec, {}, host, kv.get("host", ""), kv.get("path", "/"), kv.get("host", ""))
    return ob, host.strip("[]"), int(port)


def to_outbound(link):
    low = link.lower()
    if low.startswith("vmess://"):
        return parse_vmess(link)
    if low.startswith("vless://"):
        return parse_url_link(link, "vless")
    if low.startswith("trojan://"):
        return parse_url_link(link, "trojan")
    if low.startswith("ss://"):
        return parse_ss(link)
    raise ValueError("unsupported link type")


def wrap(ob, port):
    ob = dict(ob)
    ob["tag"] = "proxy"
    return {"log": {"loglevel": "warning"},
            "inbounds": [{"tag": "ytb-socks-in", "listen": "127.0.0.1", "port": port, "protocol": "socks",
                          "settings": {"udp": True, "auth": "noauth"}}],
            "outbounds": [ob, {"tag": "direct", "protocol": "freedom"}, {"tag": "block", "protocol": "blackhole"}],
            "routing": {"domainStrategy": "AsIs", "rules": [{"type": "field", "network": "tcp,udp", "outboundTag": "proxy"}]}}


# ------------------------------------------------------------------ full JSON
def from_json(raw, port):
    cfg = json.loads(raw)
    if isinstance(cfg, list):
        cfg = cfg[0] if cfg else {}
    if "outbounds" not in cfg and "protocol" in cfg:
        return wrap(cfg, port), "json outbound"
    obs = cfg.get("outbounds") or []
    if not any((o.get("protocol") or "").lower() in REAL_OUTBOUNDS for o in obs):
        return None, "the JSON has no proxy outbound (only direct/fragment/dns), so it would not change the IP"
    ibs = [i for i in (cfg.get("inbounds") or []) if (i.get("protocol") or "").lower() != "tun"]
    ibs = [i for i in ibs if int(i.get("port") or 0) != port or (i.get("protocol") or "").lower() in ("socks", "mixed")]
    if not any((i.get("protocol") or "").lower() in ("socks", "mixed") and int(i.get("port") or 0) == port for i in ibs):
        ibs.insert(0, {"tag": "ytb-socks-in", "listen": "127.0.0.1", "port": port, "protocol": "socks",
                       "settings": {"udp": True, "auth": "noauth"}})
    cfg["inbounds"] = ibs
    return cfg, "json config"


# ------------------------------------------------------------------ collecting nodes
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read().decode("utf-8", "ignore")


def links_from_text(text):
    text = text.strip()
    if "://" not in text[:200]:
        try:
            dec = b64d(text).decode("utf-8", "ignore")
            if "://" in dec:
                text = dec
        except Exception:
            pass
    out, skipped = [], set()
    for line in text.replace("\r", "\n").split("\n"):
        for tok in line.split():
            m = re.match(r"^([a-z0-9]+)://", tok, re.I)
            if not m:
                continue
            sch = m.group(1).lower()
            if sch in SCHEMES:
                out.append(tok)
            elif sch in UNSUPPORTED:
                skipped.add(sch)
    return out, skipped


def collect(raw):
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw).strip()
    if raw[:1] in "{[":
        return "json", raw, set()
    links, skipped = [], set()
    for tok in raw.split():
        if re.match(r"^https?://", tok, re.I):
            try:
                print("Fetching the subscription...", flush=True)
                got, sk = links_from_text(fetch(tok))
                print(f"  {len(got)} supported nodes in the subscription", flush=True)
                links += got
                skipped |= sk
            except Exception as e:
                warn(f"could not read the subscription ({type(e).__name__})")
    got, sk = links_from_text(raw)
    links += got
    skipped |= sk
    seen, uniq = set(), []
    for l in links:
        if l not in seen:
            seen.add(l)
            uniq.append(l)
    return "links", uniq[:MAX_NODES], skipped


# ------------------------------------------------------------------ xray
def install_xray():
    if os.path.isfile(XRAY_BIN):
        return True
    os.makedirs(XRAY_DIR, exist_ok=True)
    zp = "/tmp/xray.zip"
    r = subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", zp,
                        "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip"])
    if r.returncode:
        return False
    with zipfile.ZipFile(zp) as z:
        z.extractall(XRAY_DIR)
    os.chmod(XRAY_BIN, 0o755)
    return True


def start(cfg, port, name):
    path = f"/tmp/xray-{name}.json"
    with open(path, "w") as fh:
        json.dump(cfg, fh)
    env = dict(os.environ, XRAY_LOCATION_ASSET=XRAY_DIR)
    log = open(f"/tmp/xray-{name}.log", "w")
    p = subprocess.Popen([XRAY_BIN, "run", "-c", path], stdout=log, stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(30):
        time.sleep(0.2)
        if p.poll() is not None:
            return None
        r = subprocess.run(["bash", "-c", f"exec 3<>/dev/tcp/127.0.0.1/{port}"], capture_output=True)
        if r.returncode == 0:
            return p
    return p


def probe(port):
    t = time.time()
    r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", "12",
                        "-x", f"socks5h://127.0.0.1:{port}", PROBE], capture_output=True, text=True)
    return r.stdout.strip() in ("200", "204", "301", "302"), time.time() - t


def test_node(i, ob, port, stop):
    if stop.is_set():
        return False
    p = start(wrap(ob, port), port, f"t{i}")
    if p is None:
        return False
    try:
        ok, _ = probe(port)
        return ok
    finally:
        p.kill()


def main():
    raw = os.environ.get("V2RAY_CONFIG", "").strip()
    if not raw:
        print("No v2ray config - skipped")
        return 0
    kind, data, skipped = collect(raw)
    if skipped:
        warn("not supported here (needs another engine), skipped: " + ", ".join(sorted(skipped)))
    if not install_xray():
        warn("could not download Xray - continuing without the v2ray config")
        return 0

    cfg, label = None, ""
    if kind == "json":
        try:
            cfg, label = from_json(data, PORT)
        except Exception as e:
            warn(f"the JSON could not be used ({type(e).__name__}: {str(e)[:80]})")
            return 0
        if cfg is None:
            warn(label + " - ignoring it, free proxies will be used")
            return 0
    else:
        nodes = []
        for l in data:
            try:
                ob, host, port = to_outbound(l)
                nodes.append((ob, f"{ob['protocol']} {host}:{port}"))
            except Exception as e:
                print(f"skip a node: {str(e)[:60]}", flush=True)
        if not nodes:
            warn("no usable node in the v2ray config - continuing without it")
            return 0
        chosen = nodes[0]
        if len(nodes) > 1:
            print(f"Testing {len(nodes)} nodes...", flush=True)
            stop = threading.Event()
            ex = ThreadPoolExecutor(max_workers=TEST_WORKERS)
            futs = [ex.submit(test_node, i, ob, 20000 + i, stop) for i, (ob, _n) in enumerate(nodes)]
            chosen = None
            for i, f in enumerate(futs):
                ok = f.result()
                print(f"  node {i + 1}: {nodes[i][1]} -> {'OK' if ok else 'fail'}", flush=True)
                if ok:
                    chosen = nodes[i]
                    break
            stop.set()
            ex.shutdown(wait=False, cancel_futures=True)
            if not chosen:
                warn("none of the nodes worked - continuing without the v2ray config")
                return 0
        cfg, label = wrap(chosen[0], PORT), chosen[1]

    p = start(cfg, PORT, "main")
    if p is None:
        warn("Xray did not start: " + open("/tmp/xray-main.log").read()[-300:].replace("\n", " "))
        return 0
    ok, secs = probe(PORT)
    if not ok:
        p.kill()
        warn(f"the v2ray config does not connect ({label}) - continuing without it")
        return 0
    open("/tmp/xray.pid", "w").write(str(p.pid))
    open("/tmp/xray_from_config", "w").write("1")
    print(f"Xray is up on socks5://127.0.0.1:{PORT} via {label} ({secs:.1f}s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
