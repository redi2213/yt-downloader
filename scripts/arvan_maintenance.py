"""Arvan bucket maintenance run by two workflows.

    arvan_maintenance.py cleanup [--tag run-1]   delete this project's files older than 7 days
    arvan_maintenance.py info    --tag run-1     usage + file list of every bucket

With --tag the result is written as the description of a release with that
tag (no files), which is where the app reads it. Both need ALL_SECRETS.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import storage_core as core  # noqa: E402

INFO_OPEN = "<!--ytb-arvan:"
MAX_FILES_PER_BUCKET = 100


def gh(*args, check=True):
    return subprocess.run(["gh", *args], check=check)


def _buckets():
    return core.discover_buckets(core.load_secrets())


def build_info(buckets, client_factory=core.make_client, now=None) -> dict:
    now = time.time() if now is None else now
    out = []
    for b in buckets:
        entry = {"id": b.id, "bucket": b.bucket, "endpoint": b.endpoint,
                 "quota_bytes": b.quota_bytes}
        try:
            client = client_factory(b)
            used, count = core.bucket_usage(client, b)
            ours = core.list_ours(client, b)
            entry.update({
                "used_bytes": used, "objects": count, "ours": len(ours),
                "files": [{
                    "name": i["key"].split("/")[-1], "size": i["size"],
                    "expires_in_hours": round((i["modified"] + core.RETENTION_DAYS * 86400 - now) / 3600, 1),
                    "url": core.public_url(b, i["key"]),
                } for i in ours[:MAX_FILES_PER_BUCKET]],
                # Arvan gives no traffic figure through the S3 API
                "traffic_left_bytes": None,
            })
        except Exception as e:  # noqa: BLE001
            entry["error"] = core._friendly_error(e)
        out.append(entry)
    return {"v": 1, "kind": "info", "retention_days": core.RETENTION_DAYS, "buckets": out}


def run_cleanup(buckets, client_factory=core.make_client, now=None) -> dict:
    results = []
    for b in buckets:
        entry = {"id": b.id, "bucket": b.bucket}
        try:
            deleted, freed = core.cleanup_expired(client_factory(b), b, now=now)
            entry.update({"deleted": deleted, "freed_bytes": freed})
        except Exception as e:  # noqa: BLE001
            entry["error"] = core._friendly_error(e)
        results.append(entry)
    return {"v": 1, "kind": "cleanup", "buckets": results}


def _publish_result(tag: str, title: str, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).replace(">", "\\u003e")
    fd, path = tempfile.mkstemp(suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(INFO_OPEN + raw + "-->\n")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    gh("release", "create", tag, *(["--repo", repo] if repo else []),
       "--prerelease", "--title", title, "--notes-file", path)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["cleanup", "info"])
    p.add_argument("--tag", default="")
    args = p.parse_args(argv)
    buckets = _buckets()
    if not buckets:
        print("::warning::No Arvan bucket is configured")
    payload = build_info(buckets) if args.cmd == "info" else run_cleanup(buckets)
    print(json.dumps(payload, indent=2)[:4000])
    if args.tag:
        _publish_result(args.tag, f"Arvan {args.cmd}", payload)
    failed = [b for b in payload["buckets"] if b.get("error")]
    return 1 if buckets and len(failed) == len(buckets) else 0


if __name__ == "__main__":
    sys.exit(main())
