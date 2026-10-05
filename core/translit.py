"""ASCII-only text for places that can't show Persian: run titles, labels.
Persian/Arabic letters become Finglish (approximate - short vowels are not
written in Persian, so 'کافه' becomes 'kafh'); anything else that isn't ASCII
is dropped. Same table as the download workflow's safe_name.py.
"""
import re
import unicodedata

_MAP = {
    "\u0627": "a", "\u0622": "a", "\u0623": "a", "\u0625": "e", "\u0621": "", "\u0624": "o", "\u0626": "",
    "\u0628": "b", "\u067E": "p", "\u062A": "t", "\u062B": "s", "\u062C": "j", "\u0686": "ch",
    "\u062D": "h", "\u062E": "kh", "\u062F": "d", "\u0630": "z", "\u0631": "r", "\u0632": "z",
    "\u0698": "zh", "\u0633": "s", "\u0634": "sh", "\u0635": "s", "\u0636": "z", "\u0637": "t",
    "\u0638": "z", "\u0639": "", "\u063A": "gh", "\u0641": "f", "\u0642": "gh", "\u06A9": "k",
    "\u0643": "k", "\u06AF": "g", "\u0644": "l", "\u0645": "m", "\u0646": "n", "\u0647": "h",
    "\u0629": "h", "\u06C0": "h", "\u06D5": "h",
    "\u064E": "a", "\u0650": "e", "\u064F": "o",
    "\u064B": "", "\u064C": "", "\u064D": "", "\u0651": "", "\u0652": "", "\u0653": "", "\u0640": "",
    "\u200C": "", "\u200D": "", "\u061F": "", "\u060C": "", "\u061B": "",
}
for _i in range(10):
    _MAP[chr(0x06F0 + _i)] = str(_i)
    _MAP[chr(0x0660 + _i)] = str(_i)
_VOWELISH = {"\u0648": ("v", "o"), "\u06CC": ("y", "i"), "\u064A": ("y", "i"), "\u0649": ("y", "i")}
_MARKS = "\u064E\u0650\u064F\u064B\u064C\u064D\u0651\u0652\u0653\u0640\u200C\u200D"


def to_finglish(text):
    out, prev_letter = [], False
    for ch in unicodedata.normalize("NFKC", text or ""):
        if ch in _VOWELISH:
            out.append(_VOWELISH[ch][0 if not prev_letter else 1])
            prev_letter = True
        elif ch in _MAP:
            out.append(_MAP[ch])
            prev_letter = ch not in _MARKS or prev_letter
        else:
            out.append(ch)
            prev_letter = False
    return "".join(out)


def ascii_title(text, max_len=48):
    """Short, readable, ASCII-only title ('' if nothing readable is left)."""
    text = to_finglish(text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[\[\]{}\x00-\x1f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" _.-")
    if len(re.findall(r"[A-Za-z0-9]", text)) < 3:
        return ""
    if len(text) > max_len:
        text = text[: max_len - 3].rstrip() + "..."
    return text
