#!/usr/bin/env python3
"""Lab failure logs: ONE small text file per link that could not be read or downloaded.

Used by lab_scripts/links.py (lab-links.yml and the extract step of lab-download.yml) and by
lab_scripts/download.py (lab-download.yml). The files are written to ./lab_logs_out/ and a later
workflow step (lab_scripts/lab_log_push.py) commits them to the `config` branch, folder `lab-logs/`.

Never raises: a problem in here must not change the result of the workflow.
Secrets are scrubbed (v2ray/proxy configs, tokens) and the link is saved without ?query / #fragment.
"""
import hashlib
import io
import os
import re
import sys
import time
from urllib.parse import urlsplit, urlunsplit

OUT_DIR = "lab_logs_out"
MAX_CONSOLE = 12000  # characters of console output kept per link (the END is kept)

_SECRETS = [
    (re.compile(r"\b(?:vless|vmess|trojan|ssr?|hysteria2?|tuic)://\S+", re.I), "<config hidden>"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}"), "<token hidden>"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "<token hidden>"),
    (re.compile(r"x-access-token:[^@\s]+@"), "x-access-token:<hidden>@"),
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1<hidden>@"),
]


def scrub(text):
    text = text or ""
    for rx, repl in _SECRETS:
        text = rx.sub(repl, text)
    return text


def clean_url(url):
    try:
        p = urlsplit((url or "").strip())
        return urlunsplit((p.scheme, p.netloc, p.path, "", ""))
    except Exception:
        return (url or "").split("?", 1)[0].split("#", 1)[0]


class _Tee:
    def __init__(self, real, buf):
        self._real = real
        self._buf = buf

    def write(self, s):
        try:
            self._buf.write(s)
        except Exception:
            pass
        return self._real.write(s)

    def flush(self):
        try:
            self._real.flush()
        except Exception:
            pass

    def __getattr__(self, name):
        return getattr(self._real, name)


class Capture:
    """Copies everything printed (stdout + stderr) into memory while it still shows in the Actions log."""

    def __init__(self):
        self._buf = io.StringIO()
        self._old = None
        self._mark = 0

    def start(self):
        if self._old is None:
            self._old = (sys.stdout, sys.stderr)
            sys.stdout = _Tee(self._old[0], self._buf)
            sys.stderr = _Tee(self._old[1], self._buf)

    def stop(self):
        if self._old is not None:
            sys.stdout, sys.stderr = self._old
            self._old = None

    def mark(self):
        """Next since_mark() starts here (call at the start of each link)."""
        self._mark = len(self._buf.getvalue())

    def text(self):
        return self._buf.getvalue()

    def since_mark(self):
        return self._buf.getvalue()[self._mark:]


def _file_name(mode, url):
    try:
        host = (urlsplit(url or "").netloc or "site").lower()
    except Exception:
        host = "site"
    host = re.sub(r"[^a-z0-9.-]", "", host.replace("www.", ""))[:40] or "site"
    short = hashlib.sha1((url or "").encode("utf-8", "ignore")).hexdigest()[:6]
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    return "%s-%s-%s-%s.txt" % (stamp, mode, host, short)


def save_failure(mode, url, title="", error="", console="", extra=None):
    """Writes lab_logs_out/<time>-<mode>-<domain>-<hash>.txt for ONE link."""
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        lines = [
            "Lab link failure log",
            "mode: %s" % mode,
            "time (UTC): %s" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
            "workflow: %s" % os.environ.get("GITHUB_WORKFLOW", ""),
            "run: %s" % (("https://github.com/%s/actions/runs/%s" % (repo, run_id)) if run_id else ""),
            "commit: %s" % (os.environ.get("GITHUB_SHA", "")[:7]),
            "url: %s" % clean_url(url),
            "title: %s" % (title or ""),
            "error: %s" % (error or ""),
        ]
        for k, v in (extra or {}).items():
            if v not in (None, "", [], {}):
                lines.append("%s: %s" % (k, v))
        tail = (console or "")[-MAX_CONSOLE:]
        lines += ["", "---- console output for this link (the end) ----", tail]
        name = _file_name(mode, url)
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(scrub("\n".join(lines)) + "\n")
        print("[lab-log] failure log written: %s" % name, flush=True)
        return name
    except Exception as e:  # never break the workflow
        try:
            print("[lab-log] could not write the log: %s" % e, flush=True)
        except Exception:
            pass
        return None
