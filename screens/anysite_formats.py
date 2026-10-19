"""Any site: the formats a site offers (from the "Check formats" run), one
button each. Tapping a button downloads that exact format of that link.

For every height that has several formats (e.g. normal and AV1) the smallest
one is marked, so the choice is easy."""
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common
from screens.common import BTN_H


def _size_text(size):
    if not size:
        return "size ?"
    mib = size / 1048576
    return f"{mib / 1024:.2f} GB" if mib >= 1024 else f"{mib:.0f} MB"


def _label(fmt, smallest):
    height = f"{fmt['h']}p" if fmt.get("h") else "?p"
    parts = [height, fmt.get("ext") or "", fmt.get("vcodec") or "", _size_text(fmt.get("size"))]
    text = "  ·  ".join(p for p in parts if p)
    if smallest:
        text += "  (smallest)"
    return text


def _smallest_ids(formats):
    """format ids that are the smallest of their height (only where a height
    has more than one format and the sizes are known)."""
    by_height = {}
    for fmt in formats:
        by_height.setdefault(fmt.get("h"), []).append(fmt)
    marked = set()
    for group in by_height.values():
        sized = [f for f in group if f.get("size")]
        if len(group) > 1 and sized:
            marked.add(min(sized, key=lambda f: f["size"])["id"])
    return marked


def build(nav, links, on_pick, on_back):
    """``links``: [{url, title, formats: [{id, h, ext, vcodec, size, ...}]}].
    ``on_pick(url, format_id)`` starts the download; ``on_back()`` returns to
    the form."""
    nav.clear()
    nav.add(Label(text="Available formats", size_hint_y=None, height=BTN_H))
    nav.add(common.wrapped_label("Tap a format to download it.", valign="middle"))

    for link in links:
        title = link.get("title") or link.get("url")
        text = common.fa_text(title, common.content_width())
        nav.add(common.wrapped_label(text, valign="middle"))

        formats = sorted(link.get("formats") or [],
                         key=lambda f: (-(f.get("h") or 0), f.get("size") or 0))
        if not formats:
            nav.add(common.wrapped_label("The site listed no video formats for this link."))
            continue
        smallest = _smallest_ids(formats)
        for fmt in formats:
            btn = Button(text=_label(fmt, fmt["id"] in smallest),
                         size_hint_y=None, height=BTN_H + dp(4))
            btn.bind(on_press=lambda i, u=link["url"], f=fmt["id"]: on_pick(u, f))
            nav.add(btn)

    nav.add(common.back_button(nav, text="Back to form", to=on_back))
