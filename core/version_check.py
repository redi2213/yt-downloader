"""Comparing the app's version with the one on GitHub (pure text helpers, no Kivy).

Versions look like "2.25"; a build made off the main branch is "2.25-dev.7".
"""
import re


def parse(version):
    """'2.25' / 'v2.25' / '2.25-dev.7' -> (2, 25); None when there is no number."""
    m = re.match(r"\s*v?(\d+)(?:\.(\d+))?", str(version or ""))
    return (int(m.group(1)), int(m.group(2) or 0)) if m else None


def compare(current, latest):
    """What 'latest' is compared with 'current': newer / same / older / unknown."""
    a, b = parse(current), parse(latest)
    if a is None or b is None:
        return "unknown"
    return "newer" if b > a else ("same" if b == a else "older")


def describe(res):
    """One line for the About screen from the update-check result."""
    if not res.get("ok"):
        return res.get("error") or "Could not check for updates."
    cur, latest, state = res["current"], res["latest"], res["state"]
    if state == "newer":
        return f"Version {latest} is on GitHub (you have {cur}). Build the new APK from Settings > App tools."
    if state == "same":
        return f"You have the latest version ({cur})."
    if state == "older":
        return f"This build ({cur}) is newer than main ({latest})."
    return f"Could not compare versions ({cur} / {latest})."
