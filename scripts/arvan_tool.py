#!/usr/bin/env python3
"""
Arvan Cloud tool for YT Bridge (independent of every other workflow).

Subcommands
  upload-release  upload release assets (given by asset id) to Arvan
  from-link       download direct link(s) and upload to Arvan
  list            list the whole bucket -> JSON
  delete          delete keys
  rename          rename one key (copy + delete)

Secrets come from the environment: ARVAN_ACCESS_KEY, ARVAN_SECRET_KEY,
ARVAN_BUCKET, ARVAN_ENDPOINT.  Files uploaded by the app go under PREFIX/.
"""
import argparse
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import urllib.parse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

PREFIX = "ytbridge"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def env(name):
    return (os.environ.get(name) or "").strip()


def s3_client():
    ep, ak, sk = env("ARVAN_ENDPOINT"), env("ARVAN_ACCESS_KEY"), env("ARVAN_SECRET_KEY")
    if not (ep and ak and sk and env("ARVAN_BUCKET")):
        print("::error::Arvan secrets are missing (ARVAN_ACCESS_KEY / ARVAN_SECRET_KEY / ARVAN_BUCKET / ARVAN_ENDPOINT)")
        sys.exit(1)
    return boto3.client(
        "s3", endpoint_url=ep, aws_access_key_id=ak, aws_secret_access_key=sk,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      region_name="default", retries={"max_attempts": 5, "mode": "standard"}),
    )


def bucket():
    return env("ARVAN_BUCKET")


def public_url(key):
    return f"{env('ARVAN_ENDPOINT').rstrip('/')}/{bucket()}/{urllib.parse.quote(key, safe='/')}"


def err_text(e):
    if isinstance(e, ClientError):
        c = e.response.get("Error", {})
        return f"{c.get('Code', '')}: {c.get('Message', str(e))}"
    return str(e)


def safe_name(name):
    name = re.sub(r"[\\/\x00-\x1f]", "", name or "").strip().strip(".")
    return name or "downloaded_file"


def unique_key(s3, name):
    base = f"{PREFIX}/{name}"
    try:
        s3.head_object(Bucket=bucket(), Key=base)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return base
        raise
    stem, ext = os.path.splitext(name)
    return f"{PREFIX}/{stem}-{int(time.time())}{ext}"


def upload_one(s3, path):
    name = safe_name(os.path.basename(path))
    key = unique_key(s3, name)
    ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
    s3.upload_file(path, bucket(), key, ExtraArgs={"ContentType": ctype, "ACL": "public-read"})
    return {"name": name, "key": key, "url": public_url(key), "size": os.path.getsize(path)}


def write_result(args, ok, failed):
    res = {"ok": ok, "failed": failed}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    if getattr(args, "notes", None):
        # Hidden block read by the app (same shape as scripts/storage_publish.py): the release has
        # no asset, so Release History shows these files as "kept on Arvan" with their links.
        meta = {"files": [{"name": r["name"], "url": r["url"], "size": r.get("size", 0)}
                          for r in ok if r.get("url")]}
        if failed:
            meta["warn"] = [f"{r['name']}: {r['error']}" for r in failed]
        block = json.dumps(meta, ensure_ascii=False).replace("--", "\\u002d\\u002d")
        lines = [f"<!--ytb-storage:{block}-->", ""]
        for r in ok:
            lines.append(f"Arvan: {r['name']}\n{r['url']}\n")
        for r in failed:
            lines.append(f"FAILED: {r['name']} - {r['error']}\n")
        with open(args.notes, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    print(f"done: {len(ok)} uploaded, {len(failed)} failed")
    return 1 if failed else 0


# ---------------------------------------------------------------- upload-release
def cmd_upload_release(args):
    items = json.loads(env("ITEMS") or "[]")
    if not items:
        print("::error::no items given")
        return 1
    s3 = s3_client()
    repo = os.environ["GITHUB_REPOSITORY"]
    os.makedirs("dl", exist_ok=True)
    ok, failed = [], []
    for it in items:
        name = safe_name(it.get("name", "file"))
        try:
            path = os.path.join("dl", name)
            with open(path, "wb") as out:
                subprocess.run(
                    ["gh", "api", "-H", "Accept: application/octet-stream",
                     f"repos/{repo}/releases/assets/{int(it['asset_id'])}"],
                    stdout=out, check=True)
            ok.append(upload_one(s3, path))
            os.remove(path)
            print("uploaded", name)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::{name}: {err_text(e)}")
            failed.append({"name": name, "error": err_text(e)})
    return write_result(args, ok, failed)


# -------------------------------------------------------------------- from-link
def header_name(url, referer):
    try:
        out = subprocess.run(
            ["curl", "-sIL", "-m", "30", "-A", UA, "-e", referer, url],
            capture_output=True, text=True).stdout
    except Exception:  # noqa: BLE001
        return ""
    m = None
    for line in out.splitlines():
        if line.lower().startswith("content-disposition:"):
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', line, re.I)
    return urllib.parse.unquote(m.group(1).strip()) if m else ""


def cmd_from_link(args):
    urls = [u for u in re.split(r"\s+", env("URLS")) if u.startswith(("http://", "https://"))]
    if not urls:
        print("::error::no valid link (must start with http:// or https://)")
        return 1
    s3 = s3_client()
    referer = env("REFERER")
    os.makedirs("dl", exist_ok=True)
    ok, failed = [], []
    for raw in dict.fromkeys(urls):
        url, hint = raw, ""
        if "#ytb-name=" in raw:
            url, hint = raw.split("#ytb-name=", 1)
            hint = urllib.parse.unquote(hint)
        ref = referer or url
        name = hint or header_name(url, ref) or urllib.parse.unquote(
            os.path.basename(urllib.parse.urlparse(url).path))
        name = safe_name(name)
        try:
            path = os.path.join("dl", name)
            r = subprocess.run(
                ["aria2c", "-x16", "-s16", "-k1M", "--connect-timeout=20", "--max-tries=5",
                 "--retry-wait=5", f"--user-agent={UA}", f"--referer={ref}",
                 "--allow-overwrite=true", "-d", "dl", "-o", name, url])
            if r.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) == 0:
                raise RuntimeError(f"download failed (aria2c exit {r.returncode})")
            with open(path, "rb") as f:
                if f.read(7) == b"#EXTM3U":
                    raise RuntimeError("this is an HLS playlist (.m3u8), not a file")
            ok.append(upload_one(s3, path))
            os.remove(path)
            print("uploaded", name)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::{name}: {err_text(e)}")
            failed.append({"name": name, "error": err_text(e)})
    return write_result(args, ok, failed)


# ------------------------------------------------------------------------- list
def cmd_list(args):
    s3 = s3_client()
    objs, token = [], None
    while True:
        kw = {"Bucket": bucket(), "MaxKeys": 1000}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        for o in resp.get("Contents", []):
            if o["Key"].endswith("/"):
                continue
            objs.append({"key": o["Key"], "size": o["Size"],
                         "modified": o["LastModified"].isoformat(), "url": public_url(o["Key"])})
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    objs.sort(key=lambda x: x["modified"], reverse=True)
    res = {"bucket": bucket(), "count": len(objs), "total_size": sum(o["size"] for o in objs),
           "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "objects": objs}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    print(f"listed {len(objs)} objects, {res['total_size']} bytes")
    return 0


# ----------------------------------------------------------------------- delete
def cmd_delete(args):
    keys = json.loads(env("KEYS") or "[]")
    if not keys:
        print("::error::no keys given")
        return 1
    s3 = s3_client()
    ok, failed = [], []
    for k in keys:
        try:
            s3.delete_object(Bucket=bucket(), Key=k)
            ok.append({"name": k, "key": k})
            print("deleted", k)
        except Exception as e:  # noqa: BLE001
            failed.append({"name": k, "error": err_text(e)})
    return write_result(args, ok, failed)


# ----------------------------------------------------------------------- rename
def cmd_rename(args):
    old, new = env("OLD_KEY"), env("NEW_KEY")
    if not old or not new:
        print("::error::old and new key are required")
        return 1
    new = new.lstrip("/")
    s3 = s3_client()
    try:
        try:
            s3.head_object(Bucket=bucket(), Key=new)
            raise RuntimeError("a file with the new name already exists")
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") not in ("404", "NoSuchKey", "NotFound"):
                raise
        s3.copy_object(Bucket=bucket(), Key=new, ACL="public-read",
                       CopySource={"Bucket": bucket(), "Key": old},
                       MetadataDirective="COPY")
        s3.delete_object(Bucket=bucket(), Key=old)
        print("renamed", old, "->", new)
        return write_result(args, [{"name": new, "key": new, "url": public_url(new)}], [])
    except Exception as e:  # noqa: BLE001
        return write_result(args, [], [{"name": old, "error": err_text(e)}])


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("upload-release", cmd_upload_release), ("from-link", cmd_from_link),
                     ("list", cmd_list), ("delete", cmd_delete), ("rename", cmd_rename)):
        sp = sub.add_parser(name)
        sp.add_argument("--out", required=True)
        sp.add_argument("--notes")
        sp.set_defaults(fn=fn)
    a = p.parse_args()
    try:
        sys.exit(a.fn(a))
    except (BotoCoreError, ClientError) as e:
        print(f"::error::{err_text(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
