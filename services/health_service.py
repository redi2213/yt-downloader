"""The Health page: is everything the app needs in place?

Every check returns ``{"title", "status", "detail", "fix"}`` where status is
``ok`` (green), ``warn`` (orange), ``fail`` (red) or ``info`` (grey) and ``fix``
says what to do ('' when nothing). A check never raises: a problem while
checking is itself shown as a result.

Checks: GitHub token (valid, access, expiry) - app version and branch - the
workflows the app needs - the repo's Secrets (names only, GitHub never gives
values) - Actions minutes used this month.
"""
import re
from datetime import datetime, timezone

import requests

from api import storage_prefs
from api.github import client, repo_files, secrets, workflows
from api.github.auth import get_token
from core.async_utils import run_in_background
from core.config import API_BASE, APP_VERSION, GITHUB_BRANCH, REPO_NAME, REPO_OWNER
from core.exceptions import AuthenticationError, NetworkError

# Workflow files the app dispatches
REQUIRED_WORKFLOWS = [
    "download.yml", "list-formats.yml", "list-playlist.yml", "upload-file.yml",
    "Any-Site-Upload.yml", "aparat-download.yml", "telegram-download.yml",
    "filimo-direct-link.yml", "google-play-download.yml", "Series-Links.yml",
    "build-apk.yml", "backup-project.yml", "zip-release.yml",
    "cleanup-releases.yml", "arvan-maintenance.yml",
]

# (secret, needed for) - the ones a missing value only affects one tool
SECRET_SPECS = [
    ("YTDLP_COOKIES", "YouTube downloads (cookies, avoids the bot check)"),
    ("FILIMO_AUTHV1", "Filimo"),
    ("GPLAYDL_API_KEY", "Google Play APK download"),
    ("TDL_SESSION", "Telegram download"),
    ("COOKIES_TXT", "Any site (cookies, optional)"),
    ("PROXY", "Any site (proxy, optional)"),
    ("KEYSTORE_BASE64", "Build APK (signing)"),
    ("KEYSTORE_PASSWORD", "Build APK (signing)"),
    ("KEY_ALIAS", "Build APK (signing)"),
    ("KEY_PASSWORD", "Build APK (signing)"),
]
ARVAN_SECRETS = [("ARVAN_ACCESS_KEY", "Arvan storage"), ("ARVAN_SECRET_KEY", "Arvan storage")]

# Minutes a month included with each GitHub plan (private repos)
PLAN_MINUTES = {"free": 2000, "pro": 3000, "team": 3000, "enterprise": 50000}


def _item(title, status, detail="", fix=""):
    return {"title": title, "status": status, "detail": detail, "fix": fix}


def _http_code(e):
    return getattr(getattr(e, "response", None), "status_code", None)


# -- token -----------------------------------------------------------------------
def _check_token(ctx):
    if not get_token():
        return _item("GitHub token", "fail", "No token is saved on this phone.",
                     "Settings: paste a token, or use Sign in with GitHub.")
    try:
        r = client.get(API_BASE)
    except AuthenticationError:
        return _item("GitHub token", "fail", "The token is invalid, expired, or has no access to this repo.",
                     "Settings: save a new token (or sign in with GitHub again).")
    except NetworkError:
        return _item("GitHub token", "warn", "Could not reach GitHub (no connection?).",
                     "Check the internet connection and press Refresh.")
    except requests.exceptions.HTTPError as e:
        if _http_code(e) == 404:
            return _item("GitHub token", "fail", f"The repo {REPO_OWNER}/{REPO_NAME} was not found with this token.",
                         "The token must belong to (or be allowed on) this repo.")
        return _item("GitHub token", "warn", f"GitHub answered HTTP {_http_code(e)}.", "Press Refresh in a minute.")
    data = r.json()
    ctx["repo"] = data
    perms = data.get("permissions") or {}
    detail = f"Valid. Repo: {REPO_OWNER}/{REPO_NAME}"
    status, fix = "ok", ""
    if perms and not perms.get("push"):
        status, fix = "warn", "The token can read the repo but not write to it: running workflows and updates need write access."
        detail += " (read-only)"
    expires = r.headers.get("github-authentication-token-expiration")
    if expires:
        try:
            when = datetime.strptime(expires[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            days = (when - datetime.now(timezone.utc)).days
            if days < 0:
                return _item("GitHub token", "fail", "The token has expired.", "Settings: save a new token.")
            detail += f"\nExpires in {days} day{'s' if days != 1 else ''}"
            if days < 7:
                status = "warn" if status == "ok" else status
                fix = fix or "It expires soon: create a new token and save it in Settings."
        except ValueError:
            pass
    return _item("GitHub token", status, detail, fix)


# -- app version / branches -----------------------------------------------------------
def _check_build(ctx):
    items = []
    detail = f"Version {APP_VERSION}   Branch: {GITHUB_BRANCH}"
    try:
        branches = repo_files.list_branches()
    except Exception:
        items.append(_item("App build", "info", detail, ""))
        return items
    if GITHUB_BRANCH not in branches:
        items.append(_item("App build", "fail", detail + "\nThis branch does not exist in the repo.",
                           f"Every workflow runs on '{GITHUB_BRANCH}': build the app from an existing branch, "
                           "or re-create the branch."))
    else:
        items.append(_item("App build", "ok", detail))
    if "config" not in branches:
        items.append(_item("Config branch", "fail", "The branch 'config' does not exist.",
                           "It holds config.json (buttons, error help) and ntfy.json. Create it from the Settings update."))
    return items


# -- workflows -----------------------------------------------------------------------------
def _check_workflows(ctx):
    try:
        have = {w["file"] for w in workflows.list_workflows()}
    except AuthenticationError:
        return _item("Workflows", "warn", "Could not read the workflow list (token).", "See the token check above.")
    except Exception as e:
        return _item("Workflows", "warn", f"Could not read the workflow list: {str(e)[:50]}", "Press Refresh.")
    missing = [f for f in REQUIRED_WORKFLOWS if f not in have]
    if missing:
        return _item("Workflows", "fail", f"{len(REQUIRED_WORKFLOWS) - len(missing)} of {len(REQUIRED_WORKFLOWS)} found.\nMissing: "
                     + ", ".join(missing),
                     "Settings > Update project: send the update zip again, or add the missing file(s) to .github/workflows.")
    return _item("Workflows", "ok", f"All {len(REQUIRED_WORKFLOWS)} workflows the app uses are in the repo.")


# -- secrets -----------------------------------------------------------------------------------
def _check_secrets(ctx):
    try:
        names = set(secrets.list_secret_names())
    except AuthenticationError:
        return _item("Secrets", "warn", "This token cannot read the repo's Secrets.",
                     "Use a classic token with the 'repo' scope (or a GitHub App with 'Secrets: Read').")
    except Exception as e:
        return _item("Secrets", "warn", f"Could not read the Secrets: {str(e)[:50]}", "Press Refresh.")
    uses_arvan = storage_prefs.get_mode() in ("arvan", "both")
    lines, status, fix = [], "ok", []
    specs = [(n, why, "fail" if uses_arvan else "warn") for n, why in ARVAN_SECRETS] \
        + [(n, why, "warn") for n, why in SECRET_SPECS]
    for name, why, level in specs:
        if name in names:
            lines.append(f"[OK] {name}")
        else:
            lines.append(f"[missing] {name} - {why}")
            if level == "fail":
                status = "fail"
                fix.append(f"{name} is needed because Storage is set to use Arvan")
            elif status == "ok":
                status = "warn"
    known = {n for n, _w in ARVAN_SECRETS + SECRET_SPECS}
    other = sorted(n for n in names if n not in known)
    if other:
        lines.append("Other Secrets: " + ", ".join(other))
    have = sum(1 for n, _w, _l in specs if n in names)
    detail = f"{have} of {len(specs)} known Secrets are set.\n" + "\n".join(lines)
    advice = "; ".join(fix) or ("Add the missing Secrets only for the tools you use: "
                                "repo Settings > Secrets and variables > Actions." if status == "warn" else "")
    return _item("Secrets", status, detail, advice)


# -- Actions minutes ---------------------------------------------------------------------------------
def _minutes_used(owner, now):
    """Minutes of Actions used this month, or None. Tries GitHub's newer billing
    endpoint first, then the older one."""
    try:
        r = client.get(f"https://api.github.com/users/{owner}/settings/billing/usage",
                       params={"year": now.year, "month": now.month})
        total = 0.0
        for row in r.json().get("usageItems", []):
            if str(row.get("product", "")).lower() == "actions" and str(row.get("unitType", "")).lower().startswith("minute"):
                total += float(row.get("quantity") or 0)
        return total, None
    except Exception:
        pass
    try:
        data = client.get(f"https://api.github.com/users/{owner}/settings/billing/actions").json()
        return float(data.get("total_minutes_used") or 0), data.get("included_minutes")
    except Exception:
        return None, None


def _check_minutes(ctx):
    repo = ctx.get("repo") or {}
    if repo and not repo.get("private", True):
        return _item("Actions minutes", "ok", "The repo is public: Actions minutes are free and not counted.")
    now = datetime.now(timezone.utc)
    used, included = _minutes_used(REPO_OWNER, now)
    if used is None:
        return _item("Actions minutes", "info", "Not available with this token.",
                     "It needs a classic token with the 'user' scope. You can also see it at github.com/settings/billing.")
    if not included:
        try:
            plan = str((client.get("https://api.github.com/user").json().get("plan") or {}).get("name", "")).lower()
            included = PLAN_MINUTES.get(plan)
        except Exception:
            included = None
    detail = f"{used:.0f} minutes used this month"
    if not included:
        return _item("Actions minutes", "info", detail)
    pct = used / included * 100
    detail += f" of about {included} included ({pct:.0f}%)"
    if pct >= 95:
        return _item("Actions minutes", "fail", detail,
                     "Almost out: runs will stop or cost money. Wait for the new month, or make the repo public.")
    if pct >= 80:
        return _item("Actions minutes", "warn", detail, "Getting close to the monthly limit: avoid big downloads for now.")
    return _item("Actions minutes", "ok", detail)


_CHECKS = (_check_token, _check_build, _check_workflows, _check_secrets, _check_minutes)


def run_checks():
    ctx, results = {}, []
    for check in _CHECKS:
        try:
            out = check(ctx)
        except Exception as e:   # a check must never break the page
            out = _item(re.sub(r"^_check_", "", check.__name__).title(), "warn", f"Could not check: {str(e)[:60]}")
        results.extend(out if isinstance(out, list) else [out])
    return results


def start_health(on_done):
    def work():
        try:
            on_done({"ok": True, "items": run_checks()})
        except Exception as e:
            on_done({"ok": False, "error": f"Health check failed: {str(e)[:60]}"})
    run_in_background(work)
