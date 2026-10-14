"""Arvan Cloud (S3-compatible) storage helpers shared by the workflows.

Runs only on GitHub Actions - never inside the app. Credentials come from
repository Secrets (the workflow passes ``toJSON(secrets)`` in ALL_SECRETS):

    main bucket     ARVAN_ACCESS_KEY, ARVAN_SECRET_KEY, ARVAN_BUCKET,
                    ARVAN_ENDPOINT (optional), ARVAN_QUOTA_GB (optional)
    extra buckets   ARVAN_2_ACCESS_KEY, ARVAN_2_SECRET_KEY, ARVAN_2_BUCKET, ...
                    (id = the number; the app creates them from Settings)

Every object this project uploads lives under ``ytbridge/run-<id>/`` so the
daily cleanup never touches other files in a shared bucket (for example the
Telegram bot's files). Free-space checks do count the WHOLE bucket, because
the plan's quota is per bucket/account.
"""
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

DEFAULT_ENDPOINT = "https://s3.ir-thr-at1.arvanstorage.ir"
DEFAULT_MAIN_BUCKET = "my-files-telegram"
DEFAULT_QUOTA_GB = 5.0
KEY_PREFIX = "ytbridge"
RETENTION_DAYS = 7
GIB = 1024 ** 3

_NUMBERED = re.compile(r"^ARVAN_(\d+)_ACCESS_KEY$")


@dataclass
class Bucket:
    id: str            # "main", "2", "3", ...
    access_key: str
    secret_key: str
    bucket: str
    endpoint: str
    quota_bytes: int

    @property
    def label(self) -> str:
        return f"{self.bucket} ({self.id})"


# ------------------------------------------------------------- secrets ---
def load_secrets(env=None) -> dict:
    """The secrets dict: ALL_SECRETS (JSON) merged over the plain environment."""
    env = os.environ if env is None else env
    data = {}
    raw = env.get("ALL_SECRETS", "")
    if raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                data = {str(k): str(v) for k, v in parsed.items() if v not in (None, "")}
        except ValueError:
            pass
    for k, v in env.items():
        if k.startswith("ARVAN_") and v and k not in data:
            data[k] = v
    return data


def _quota_bytes(raw) -> int:
    try:
        gb = float(str(raw).strip())
        if gb <= 0:
            raise ValueError
    except (TypeError, ValueError):
        gb = DEFAULT_QUOTA_GB
    return int(gb * GIB)


def _one(secrets, prefix, bucket_id, default_bucket):
    access = secrets.get(f"{prefix}_ACCESS_KEY", "").strip()
    secret = secrets.get(f"{prefix}_SECRET_KEY", "").strip()
    name = secrets.get(f"{prefix}_BUCKET", "").strip() or default_bucket
    if not (access and secret and name):
        return None
    return Bucket(
        id=bucket_id, access_key=access, secret_key=secret, bucket=name,
        endpoint=(secrets.get(f"{prefix}_ENDPOINT", "").strip() or DEFAULT_ENDPOINT).rstrip("/"),
        quota_bytes=_quota_bytes(secrets.get(f"{prefix}_QUOTA_GB")),
    )


def discover_buckets(secrets: dict) -> list:
    """Every complete bucket configuration found in the secrets: main first,
    then the numbered ones in ascending order."""
    found = []
    main = _one(secrets, "ARVAN", "main", DEFAULT_MAIN_BUCKET)
    if main:
        found.append(main)
    numbers = sorted(int(m.group(1)) for k in secrets for m in [_NUMBERED.match(k)] if m)
    for n in numbers:
        b = _one(secrets, f"ARVAN_{n}", str(n), "")
        if b:
            found.append(b)
    return found


def order_buckets(buckets: list, preferred: str = "") -> list:
    """The preferred bucket first, the others after it in their normal order
    (so a full bucket falls over to the next one)."""
    preferred = (preferred or "").strip()
    first = [b for b in buckets if b.id == preferred]
    return first + [b for b in buckets if b.id != preferred]


# ---------------------------------------------------------------- S3 ---
def make_client(b: Bucket):
    import boto3
    from botocore.client import Config
    return boto3.client(
        "s3",
        endpoint_url=b.endpoint,
        aws_access_key_id=b.access_key,
        aws_secret_access_key=b.secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      retries={"max_attempts": 5, "mode": "standard"}),
        region_name="default",
    )


def _iter_objects(client, bucket, prefix=""):
    paginator = client.get_paginator("list_objects_v2")
    kwargs = {"Bucket": bucket}
    if prefix:
        kwargs["Prefix"] = prefix
    for page in paginator.paginate(**kwargs):
        for obj in page.get("Contents", []) or []:
            yield obj


def bucket_usage(client, b: Bucket):
    """(bytes used, object count) of the WHOLE bucket."""
    total = count = 0
    for obj in _iter_objects(client, b.bucket):
        total += int(obj.get("Size", 0))
        count += 1
    return total, count


def _ts(value) -> float:
    if hasattr(value, "timestamp"):
        return value.timestamp()
    return float(value or 0)


def list_ours(client, b: Bucket) -> list:
    """Objects uploaded by this project (under KEY_PREFIX), newest first."""
    items = []
    for obj in _iter_objects(client, b.bucket, KEY_PREFIX + "/"):
        items.append({"key": obj["Key"], "size": int(obj.get("Size", 0)),
                      "modified": _ts(obj.get("LastModified"))})
    items.sort(key=lambda i: i["modified"], reverse=True)
    return items


def public_url(b: Bucket, key: str) -> str:
    """Path-style public URL. The key is URL-encoded (spaces etc. would cut
    the link in chat apps) while the path separators stay literal."""
    return f"{b.endpoint}/{b.bucket}/{quote(key, safe='/')}"


def iso_utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cleanup_expired(client, b: Bucket, now: float = None, days: int = RETENTION_DAYS):
    """Deletes this project's objects older than ``days``. Returns
    (deleted count, freed bytes)."""
    now = time.time() if now is None else now
    limit = now - days * 86400
    old = [i for i in list_ours(client, b) if i["modified"] < limit]
    freed = 0
    for start in range(0, len(old), 1000):
        chunk = old[start:start + 1000]
        client.delete_objects(
            Bucket=b.bucket,
            Delete={"Objects": [{"Key": i["key"]} for i in chunk], "Quiet": True})
        freed += sum(i["size"] for i in chunk)
    return len(old), freed


def _friendly_error(e: Exception) -> str:
    resp = getattr(e, "response", None)
    if isinstance(resp, dict):
        err = resp.get("Error", {})
        code, msg = err.get("Code", ""), err.get("Message", "")
        if code:
            return f"{code}: {msg}"[:200]
    return str(e)[:200]


def upload_to_arvan(path: str, buckets: list, preferred: str, run_tag: str,
                    client_factory=make_client, now: float = None):
    """Uploads one file to the first bucket (preferred first, then the rest)
    that has room and accepts it.

    Returns (info, warnings): ``info`` is a dict (name, url, size, expires,
    bucket) or None when no bucket worked; ``warnings`` lists what went wrong
    on the way (full bucket, rejected upload...).
    """
    now = time.time() if now is None else now
    name = os.path.basename(path)
    size = os.path.getsize(path)
    key = f"{KEY_PREFIX}/{run_tag}/{name}"
    warnings = []
    if not buckets:
        return None, ["No Arvan bucket is configured (add the ARVAN_* secrets)"]
    for b in order_buckets(buckets, preferred):
        try:
            client = client_factory(b)
            used, _count = bucket_usage(client, b)
            if used + size > b.quota_bytes:
                warnings.append(
                    f"Bucket {b.label} is full ({used / GIB:.2f} of {b.quota_bytes / GIB:.2f} GB used)")
                continue
            client.upload_file(path, b.bucket, key,
                               ExtraArgs={"ACL": "public-read",
                                          "ContentType": _content_type(name)})
            return {
                "name": name, "url": public_url(b, key), "size": size,
                "expires": iso_utc(now + RETENTION_DAYS * 86400),
                "bucket": b.bucket, "bucket_id": b.id,
            }, warnings
        except Exception as e:  # noqa: BLE001 - any failure moves on to the next bucket
            warnings.append(f"Bucket {b.label}: {_friendly_error(e)}")
    return None, warnings


def _content_type(name: str) -> str:
    import mimetypes
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


# ------------------------------------------------- release body (meta) ---
META_OPEN = "<!--ytb-storage:"
META_CLOSE = "-->"


def build_body(mode: str, files: list, warnings: list, notes: str = "") -> str:
    """Release description: a hidden JSON block the app reads, then plain
    text for people reading the release on GitHub."""
    meta = {"v": 1, "mode": mode, "files": files, "warn": warnings}
    raw = json.dumps(meta, ensure_ascii=True, separators=(",", ":")).replace(">", "\\u003e")
    lines = [META_OPEN + raw + META_CLOSE]
    if notes:
        lines.append(notes)
    if files:
        lines.append(f"Arvan links (deleted after {RETENTION_DAYS} days):")
        lines += [f"- {f['name']}: {f['url']}" for f in files]
    if warnings:
        lines.append("Warnings:")
        lines += [f"- {w}" for w in warnings]
    return "\n".join(lines) + "\n"
