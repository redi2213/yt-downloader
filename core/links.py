"""Splitting pasted text into links. Pure Python (no Kivy, no network).

The upload box accepts several links at once, one per line; people also paste
them separated by spaces or commas, so every whitespace/comma splits.
"""
import re

_SPLIT_RE = re.compile(r"[\s,]+")


def split_links(text):
    """Every http(s) link in ``text``, in order, without duplicates."""
    seen, links = set(), []
    for token in _SPLIT_RE.split(text or ""):
        token = token.strip()
        if token.lower().startswith(("http://", "https://")) and token not in seen:
            seen.add(token)
            links.append(token)
    return links
