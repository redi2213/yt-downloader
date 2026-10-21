"""Persian (fa) texts for the screens. English is what the code writes; when the
language is Persian every text that reaches a label or button goes through
``tr()``: an exact match in core/fa_strings.EXACT, then the PATTERNS (texts with
numbers or names in them), then line by line for texts of several lines. A text
that is not in the tables stays English - add it to core/fa_strings.py, nothing else
needs to change.
"""
import re

_lang = "en"
_compiled = None


def set_language(code):
    global _lang
    _lang = "fa" if code == "fa" else "en"


def language():
    return _lang


def is_fa():
    return _lang == "fa"


def _patterns():
    global _compiled
    if _compiled is None:
        from core.fa_strings import PATTERNS
        _compiled = [(re.compile(p), t) for p, t in PATTERNS]
    return _compiled


def _one(text):
    from core.fa_strings import EXACT
    if text in EXACT:
        return EXACT[text]
    for rx, template in _patterns():
        m = rx.fullmatch(text)
        if m:
            try:
                return template.format(*m.groups())
            except Exception:
                return None
    return None


def tr(text):
    """Persian form of ``text`` or ``text`` itself when there is none."""
    if _lang != "fa" or not isinstance(text, str) or not text.strip():
        return text
    lead = text[:len(text) - len(text.lstrip())]
    tail = text[len(text.rstrip()):]
    core = text.strip()
    hit = _one(core)
    if hit is not None:
        return lead + hit + tail
    if "\n" in core:
        parts, changed = [], False
        for line in core.split("\n"):
            got = _one(line.strip()) if line.strip() else None
            if got is None:
                parts.append(line)
            else:
                parts.append(got)
                changed = True
        if changed:
            return lead + "\n".join(parts) + tail
    return text
