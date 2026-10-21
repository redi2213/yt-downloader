"""Themes, colors, fonts and size steps of the app (pure data, no widgets).

``classic`` is the look the app always had (Kivy's own black background and
grey button images): while it is the theme and no own color is set, the app
does not restyle anything. Every other theme (or an own color) draws flat
buttons in the theme colors - see screens/style.py.
"""
import os
from collections import OrderedDict

from api import appearance_prefs

COLOR_KEYS = ("bg", "text", "button", "button_text", "card", "selected")
COLOR_LABELS = {
    "bg": "Background", "text": "Text", "button": "Buttons and menus",
    "button_text": "Button text", "card": "List items (cards)", "selected": "Selected item",
}

# What "classic" looks like in the flat model (used when only some colors are changed).
CLASSIC = {
    "bg": (0.0, 0.0, 0.0, 1), "text": (1.0, 1.0, 1.0, 1), "button": (0.27, 0.27, 0.30, 1),
    "button_text": (1.0, 1.0, 1.0, 1), "card": (0.14, 0.14, 0.17, 1), "selected": (0.12, 0.40, 0.22, 1),
}

THEMES = OrderedDict([
    ("classic",  ("Classic (default)", dict(CLASSIC))),
    ("midnight", ("Midnight", {"bg": (0.05, 0.07, 0.12, 1), "text": (0.92, 0.94, 1.0, 1), "button": (0.16, 0.22, 0.36, 1),
                               "button_text": (1, 1, 1, 1), "card": (0.10, 0.13, 0.22, 1), "selected": (0.15, 0.40, 0.65, 1)})),
    ("light",    ("Light", {"bg": (0.95, 0.96, 0.98, 1), "text": (0.10, 0.10, 0.15, 1), "button": (0.20, 0.45, 0.85, 1),
                            "button_text": (1, 1, 1, 1), "card": (0.86, 0.89, 0.94, 1), "selected": (0.62, 0.85, 0.68, 1)})),
    ("ocean",    ("Ocean", {"bg": (0.03, 0.10, 0.15, 1), "text": (0.88, 0.97, 1.0, 1), "button": (0.05, 0.45, 0.62, 1),
                            "button_text": (1, 1, 1, 1), "card": (0.06, 0.18, 0.25, 1), "selected": (0.10, 0.45, 0.40, 1)})),
    ("forest",   ("Forest", {"bg": (0.05, 0.11, 0.07, 1), "text": (0.90, 0.97, 0.90, 1), "button": (0.15, 0.50, 0.25, 1),
                             "button_text": (1, 1, 1, 1), "card": (0.09, 0.18, 0.11, 1), "selected": (0.30, 0.55, 0.20, 1)})),
    ("sunset",   ("Sunset", {"bg": (0.14, 0.08, 0.06, 1), "text": (1.0, 0.95, 0.90, 1), "button": (0.85, 0.40, 0.15, 1),
                             "button_text": (1, 1, 1, 1), "card": (0.22, 0.13, 0.09, 1), "selected": (0.60, 0.45, 0.10, 1)})),
    ("purple",   ("Purple", {"bg": (0.09, 0.06, 0.14, 1), "text": (0.95, 0.92, 1.0, 1), "button": (0.45, 0.28, 0.80, 1),
                             "button_text": (1, 1, 1, 1), "card": (0.16, 0.11, 0.24, 1), "selected": (0.35, 0.30, 0.65, 1)})),
])

# Swatches offered for every own color (no pure white: (1,1,1,1) means "default" to Kivy buttons).
PALETTE = ["#000000", "#1B1B22", "#3A3A44", "#7A7A86", "#FAFAFA", "#E53935",
           "#FB8C00", "#FDD835", "#43A047", "#00897B", "#1E88E5", "#8E24AA"]

FONT_SCALES = [("Small", 0.85), ("Normal", 1.0), ("Large", 1.15), ("Extra large", 1.3)]
BOX_SCALES = [("Compact", 0.85), ("Normal", 1.0), ("Roomy", 1.15), ("Large", 1.3)]

_prefs = None


def prefs():
    global _prefs
    if _prefs is None:
        _prefs = appearance_prefs.load()
    return _prefs


def save(**changes):
    global _prefs
    _prefs = appearance_prefs.save(**changes)
    return _prefs


# -- colors -------------------------------------------------------------------------------------------------------
def hex_to_rgba(text):
    s = str(text or "").strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return tuple(int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)) + (1,)
    except ValueError:
        return None


def rgba_to_hex(rgba):
    return "#" + "".join(f"{max(0, min(255, int(round(c * 255)))):02X}" for c in tuple(rgba)[:3])


def luminance(rgba):
    r, g, b = tuple(rgba)[:3]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def mix(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3)) + (1,)


def custom_colors():
    return {k: v for k, v in (prefs().get("colors") or {}).items() if k in COLOR_KEYS and hex_to_rgba(v)}


def theme_id():
    t = prefs().get("theme")
    return t if t in THEMES else "classic"


def is_classic():
    """True = the app looks exactly as it always did (nothing is restyled)."""
    return theme_id() == "classic" and not custom_colors()


def colors():
    """The six colors in use: the theme with the own colors on top."""
    base = dict(THEMES[theme_id()][1])
    for key, value in custom_colors().items():
        base[key] = hex_to_rgba(value)
    return base


def input_background():
    c = colors()
    return (1, 1, 1, 1) if luminance(c["bg"]) > 0.5 else mix(c["card"], (1, 1, 1), 0.12)


def dark_text_on_light():
    return luminance(colors()["bg"]) > 0.5


# -- sizes --------------------------------------------------------------------------------------------------------
def font_scale():
    try:
        return float(prefs().get("font_scale") or 1.0)
    except (TypeError, ValueError):
        return 1.0


def box_scale():
    try:
        return float(prefs().get("box_scale") or 1.0)
    except (TypeError, ValueError):
        return 1.0


# -- fonts --------------------------------------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_DIR = os.path.join(_HERE, "assets", "fonts")
# Name parts of fonts known to hold the Persian letters.
_PERSIAN_HINTS = ("vazir", "sahel", "samim", "shabnam", "yekan", "iransans", "estedad", "tanha", "parastoo",
                  "lalezar", "nastaliq", "naskh", "arab", "kufi", "dejavu", "gandom", "mikhak", "noto")
_SYSTEM_FONTS = [("Roboto", "Roboto-Regular.ttf"), ("Noto Naskh Arabic", "NotoNaskhArabic-Regular.ttf"),
                 ("Noto Sans Arabic", "NotoSansArabic-Regular.ttf"), ("Noto Serif", "NotoSerif-Regular.ttf"),
                 ("Droid Sans Mono", "DroidSansMono.ttf"), ("Cutive Mono", "CutiveMono.ttf")]


def persian_ok(path):
    name = os.path.basename(path or "").lower()
    return any(h in name for h in _PERSIAN_HINTS)


def available_fonts():
    """[(label, path or '', handles Persian)] - the app's own default first, then the
    ttf files in assets/fonts (drop e.g. Vazirmatn-Regular.ttf there and rebuild), then a few
    Android system fonts that exist on this phone."""
    out = [("Default (Roboto)", "", False)]
    seen = set()
    if os.path.isdir(_FONT_DIR):
        for name in sorted(os.listdir(_FONT_DIR)):
            if name.lower().endswith((".ttf", ".otf")):
                path = os.path.join(_FONT_DIR, name)
                out.append((os.path.splitext(name)[0], path, persian_ok(path)))
                seen.add(name.lower())
    for label, file_name in _SYSTEM_FONTS:
        path = os.path.join("/system/fonts", file_name)
        if os.path.exists(path) and file_name.lower() not in seen and label != "Roboto":
            out.append((label, path, persian_ok(path)))
    return out


def chosen_font():
    path = prefs().get("font") or ""
    return path if path and os.path.exists(path) else ""


# -- flat button images (written once; a flat color needs a plain white texture) -------------------------------------
def _png(path, gray):
    import struct
    import zlib
    raw = b"\x00" + bytes([gray, gray, gray, 255]) * 4
    rows = raw * 4

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 4, 4, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(data)


def flat_images(folder):
    """(normal, pressed) png paths for flat buttons; ('', '') when they cannot be written."""
    try:
        os.makedirs(folder, exist_ok=True)
        normal, down = os.path.join(folder, "flat_n.png"), os.path.join(folder, "flat_d.png")
        if not os.path.exists(normal):
            _png(normal, 255)
        if not os.path.exists(down):
            _png(down, 200)
        return normal, down
    except Exception:
        return "", ""
