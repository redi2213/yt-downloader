#!/usr/bin/env bash
set -euo pipefail
CFG_RAW="${V2RAY_CONFIG:-}"
[ -z "$CFG_RAW" ] && { echo "No V2RAY_CONFIG \u2014 skip xray"; exit 0; }

echo "Installing Xray..."
VER=$(curl -sL https://api.github.com/repos/XTLS/Xray-core/releases/latest | python3 -c "import sys,json;print(json.load(sys.stdin)['tag_name'])")
curl -sL "https://github.com/XTLS/Xray-core/releases/download/${VER}/Xray-linux-64.zip" -o /tmp/xray.zip
unzip -o /tmp/xray.zip -d /tmp/xray
sudo mv /tmp/xray/xray /usr/local/bin/xray && sudo chmod +x /usr/local/bin/xray

export V2RAY_CONFIG
python3 - <<'PY'
import base64,json,os,re,sys,urllib.parse,urllib.request
raw=os.environ.get("V2RAY_CONFIG","").strip()
raw=re.sub(r"^```(?:json)?\s*","",raw); raw=re.sub(r"\s*```$","",raw).strip()
UA={"User-Agent":"Mozilla/5.0"}

def b64(s):
    s=s.strip().replace("-","+").replace("_","/"); s+="="*((-len(s))%4); return base64.b64decode(s)

def fetch(u):
    with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30) as r:
        return r.read().decode("utf-8","ignore")

def parse_vmess(link):
    d=json.loads(b64(link.split("://",1)[1]).decode())
    host=d.get("add")or d.get("host")or""; port=int(d.get("port")or 443)
    net=(d.get("net")or"tcp").lower(); tls=(d.get("tls")or"").lower(); path=d.get("path")or"/"
    peer=d.get("host")or d.get("sni")or host
    ob={"tag":"proxy","protocol":"vmess","settings":{"vnext":[{"address":host,"port":port,"users":[{"id":d.get("id"),"alterId":int(d.get("aid")or 0),"security":d.get("scy")or"auto"}]}]},"streamSettings":{"network":net}}
    if tls in("tls","reality"):
        ob["streamSettings"]["security"]="tls"; ob["streamSettings"]["tlsSettings"]={"serverName":peer,"allowInsecure":True}
    if net=="ws": ob["streamSettings"]["wsSettings"]={"path":path,"headers":{"Host":peer}}
    if net=="grpc": ob["streamSettings"]["grpcSettings"]={"serviceName":path.lstrip("/")}
    return ob

def parse_vt(link,proto):
    u=urllib.parse.urlparse(link); q=dict(urllib.parse.parse_qsl(u.query))
    user=urllib.parse.unquote(u.username or""); host=u.hostname or""; port=u.port or 443
    sec=(q.get("security")or"none").lower(); net=(q.get("type")or"tcp").lower()
    sni=q.get("sni")or q.get("host")or host; path=urllib.parse.unquote(q.get("path")or"/"); hh=q.get("host")or sni
    if proto=="vless":
        settings={"vnext":[{"address":host,"port":port,"users":[{"id":user,"encryption":q.get("encryption")or"none","flow":q.get("flow")or""}]}]}
    else:
        settings={"servers":[{"address":host,"port":port,"password":user}]}
    stream={"network":net}
    if sec in("tls","xtls","reality"):
        stream["security"]="tls" if sec!="reality" else "reality"
        if stream["security"]=="tls":
            tls={"serverName":sni,"allowInsecure":True,"fingerprint":q.get("fp")or"chrome"}
            if q.get("alpn"): tls["alpn"]=[x.strip() for x in q["alpn"].split(",") if x.strip()]
            stream["tlsSettings"]=tls
        else:
            stream["realitySettings"]={"serverName":sni,"fingerprint":q.get("fp")or"chrome","publicKey":q.get("pbk")or"","shortId":q.get("sid")or"","spiderX":q.get("spx")or""}
    if net=="ws": stream["wsSettings"]={"path":path,"headers":{"Host":hh}}
    if net=="grpc": stream["grpcSettings"]={"serviceName":(q.get("serviceName")or path).lstrip("/")}
    return {"tag":"proxy","protocol":proto,"settings":settings,"streamSettings":stream}

def parse_ss(link):
    body=link[5:].split("#",1)[0]
    try:
        if "@" not in body: decoded=b64(body).decode()
        else:
            ui,hp=body.rsplit("@",1)
            try: ui=b64(ui).decode()
            except Exception: ui=urllib.parse.unquote(ui)
            decoded=f"{ui}@{hp}"
    except Exception: decoded=urllib.parse.unquote(body)
    m=re.match(r"^([^:]+):(.+)@([^:]+):(\d+)$",decoded)
    if not m: raise ValueError("bad ss")
    return {"tag":"proxy","protocol":"shadowsocks","settings":{"servers":[{"address":m.group(3),"port":int(m.group(4)),"method":m.group(1),"password":m.group(2)}]}}

def to_ob(link):
    low=link.strip().lower()
    if low.startswith("vmess://"): return parse_vmess(link.strip())
    if low.startswith("vless://"): return parse_vt(link.strip(),"vless")
    if low.startswith("trojan://"): return parse_vt(link.strip(),"trojan")
    if low.startswith("ss://"): return parse_ss(link.strip())
    raise ValueError("unsupported")

def sub_links(text):
    try:
        dec=b64(text.strip()).decode("utf-8","ignore")
        if "://" in dec: text=dec
    except Exception: pass
    out=[]
    for line in text.replace("\r","\n").split("\n"):
        line=line.strip()
        if line and "://" in line and not line.startswith("#"): out.append(line.split()[0])
    if not out:
        out=re.findall(r"(?:vmess|vless|trojan|ss)://\S+",text,re.I)
    return out

def wrap(ob):
    return {"log":{"loglevel":"warning"},"inbounds":[{"tag":"socks-in","port":10808,"listen":"127.0.0.1","protocol":"socks","settings":{"udp":True,"auth":"noauth"},"sniffing":{"enabled":True,"destOverride":["http","tls"]}}],"outbounds":[ob,{"tag":"direct","protocol":"freedom"},{"tag":"block","protocol":"blackhole"}],"routing":{"domainStrategy":"AsIs","rules":[{"type":"field","outboundTag":"proxy","network":"tcp,udp"}]}}

def ensure_socks(cfg):
    ibs=cfg.get("inbounds")or[]
    if not any(i.get("protocol") in("socks","mixed") and int(i.get("port")or 0)==10808 for i in ibs):
        ibs.insert(0,{"tag":"socks-in","port":10808,"listen":"127.0.0.1","protocol":"socks","settings":{"udp":True,"auth":"noauth"},"sniffing":{"enabled":True,"destOverride":["http","tls"]}})
        cfg["inbounds"]=ibs
    return cfg

cfg=None
if re.match(r"^https?://",raw,re.I):
    print("Fetching subscription...")
    links=sub_links(fetch(raw)); print("nodes:",len(links))
    for link in links[:20]:
        try: cfg=wrap(to_ob(link)); print("Using:",link[:70]); break
        except Exception as e: print("skip",e)
    if not cfg: sys.exit("no parseable nodes")
elif re.match(r"^(vmess|vless|trojan|ss)://",raw,re.I):
    line=next((l.strip() for l in raw.splitlines() if re.match(r"^(vmess|vless|trojan|ss)://",l.strip(),re.I)), raw.strip())
    cfg=wrap(to_ob(line)); print("share OK",cfg["outbounds"][0]["protocol"])
else:
    cfg=json.loads(raw); cfg=ensure_socks(cfg)
    if not any(o.get("protocol") in("vmess","vless","trojan","shadowsocks","socks","http") for o in (cfg.get("outbounds")or[])):
        print("WARNING: no real proxy outbound in JSON")
    if not cfg.get("outbounds"): sys.exit("no outbounds")

open("/tmp/xray-config.json","w").write(json.dumps(cfg,indent=2))
print("Wrote /tmp/xray-config.json")
PY

nohup xray run -c /tmp/xray-config.json >/tmp/xray.log 2>&1 &
echo $! >/tmp/xray.pid
sleep 2
kill -0 "$(cat /tmp/xray.pid)" 2>/dev/null || { echo "Xray failed:"; cat /tmp/xray.log; exit 1; }
echo 1 >/tmp/xray_from_config
echo "Xray up PID $(cat /tmp/xray.pid)"
curl -sS --max-time 20 -x socks5h://127.0.0.1:10808 https://httpbin.org/ip && echo || { echo "WARN self-test failed"; tail -20 /tmp/xray.log; }
