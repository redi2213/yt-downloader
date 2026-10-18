"""Persian -> Finglish file names, for places that cannot keep Persian
(GitHub Release asset names). Same logic as safe_name.py in download.yml:
a word dictionary (if the workflow cloned persian-to-finglish into /tmp/p2f)
with a letter-by-letter fallback, then everything non-ASCII is dropped.

    safe_name("سخت ترین قسمت بازی")  ->  "Sakhtarin ghesmat bazi"
"""
import os
import re
import unicodedata

P2F_DIR = os.environ.get("P2F_DIR", "/tmp/p2f")

# Letter-by-letter fallback (approximate: short vowels are not written in Persian).
M = {
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
    M[chr(0x06F0 + _i)] = str(_i)
    M[chr(0x0660 + _i)] = str(_i)
VOWELISH = {"\u0648": ("v", "o"), "\u06CC": ("y", "i"), "\u064A": ("y", "i"), "\u0649": ("y", "i")}
_MARKS = "\u064E\u0650\u064F\u064B\u064C\u064D\u0651\u0652\u0653\u0640\u200C\u200D"


def _fallback(text):
    out, prev_letter = [], False
    for ch in text:
        if ch in VOWELISH:
            out.append(VOWELISH[ch][0 if not prev_letter else 1])
            prev_letter = True
        elif ch in M:
            out.append(M[ch])
            prev_letter = ch not in _MARKS or prev_letter
        else:
            out.append(ch)
            prev_letter = False
    return "".join(out)


# ---- Word dictionary (correct Finglish with vowels) ----
_FIX = {0x064A: "\u06CC", 0x0649: "\u06CC", 0x0643: "\u06A9"}
_STRIP = re.compile("[\u061F\u060C\u061B\u064B-\u065F\u0640]")


def _key(w):
    return _STRIP.sub("", w.translate(_FIX))


# Your own corrections / missing words. These always win over the dataset.
EXTRA = {
    "\u0633\u062E\u062A": "sakht",
    "\u0648\u06CC\u062F\u06CC\u0648": "video",
    "\u0648\u06CC\u062F\u0626\u0648": "video",
    "\u06CC\u0648\u062A\u06CC\u0648\u0628": "youtube",
}

_D = None


def _dictionary():
    global _D
    if _D is not None:
        return _D
    d = {}
    try:
        with open(os.path.join(P2F_DIR, "farsi-Words-DATASET.txt"), encoding="utf-8") as f, \
             open(os.path.join(P2F_DIR, "english-Words-DATASET.txt"), encoding="utf-8") as e:
            for fa, en in zip(f, e):
                fa, en = _key(fa.strip()), en.strip()
                if fa and en:
                    d.setdefault(fa, en)
    except OSError:
        pass  # dataset not available: everything uses the fallback
    d.update({_key(k): v for k, v in EXTRA.items()})
    _D = d
    return d


_SUFFIX = (
    ("\u062A\u0631\u06CC\u0646", "tarin"),  # ترین
    ("\u0647\u0627\u06CC", "hay"),          # های
    ("\u0647\u0627", "ha"),                 # ها
    ("\u062A\u0631", "tar"),                # تر
)
_SUPERLATIVE = {"\u062A\u0631\u06CC\u0646": "tarin", "\u062A\u0631": "tar"}


def _attach(stem, suf):
    # sakht + tarin -> sakhtarin (merge the doubled letter)
    return stem + (suf[1:] if stem and stem[-1] == suf[0] else suf)


def _tr_part(p):
    D = _dictionary()
    k = _key(p)
    if k in D:
        return D[k], True
    for suf, lat in _SUFFIX:
        if k.endswith(suf) and k[:-len(suf)] in D:
            return _attach(D[k[:-len(suf)]], lat), True
    return _fallback(p), False


def _tr_word(w):
    res = [_tr_part(p) for p in re.split("[\u200C\u200D]+", w) if p]
    return "".join(r[0] for r in res), all(r[1] for r in res)


def finglish(base):
    base = unicodedata.normalize("NFKC", base or "")
    toks = re.split("([\u0600-\u06FF\u200C\u200D]+)", base)
    out, last_p, last_hit = [], -1, False
    for i, t in enumerate(toks):
        if i % 2 == 0:
            out.append(t)
            continue
        sup = _SUPERLATIVE.get(_key(t))
        # "سخت ترین" (separate words) -> "sakhtarin"
        if sup and last_hit and last_p == len(out) - 2 and out[-1] == " ":
            out.pop()
            out[-1] = _attach(out[-1], sup)
            last_p = len(out) - 1
            continue
        text, hit = _tr_word(t)
        out.append(text)
        last_p, last_hit = len(out) - 1, hit
    result = "".join(out)
    if toks[0] == "" and result:
        result = result[0].upper() + result[1:]
    return result


def safe_name(text, fallback="video", max_len=100):
    """File-name-safe ASCII text. ``fallback`` is used when fewer than three
    readable characters are left (e.g. a title in another script)."""
    base = finglish(text)
    base = base.encode("ascii", "ignore").decode("ascii")
    # Characters that break path/files globbing and comma splitting
    base = re.sub(r"[\[\]{},*?!#%&;'\"`$\\<>|:/]+", "_", base)
    base = re.sub(r"\s+_+\s+", " ", base)
    base = re.sub(r"\s+", " ", base)
    base = re.sub(r"_+", "_", base).strip(" _.")
    if len(re.findall(r"[A-Za-z0-9]", base)) < 3:
        base = fallback
    return base[:max_len].strip(" _.") or fallback
