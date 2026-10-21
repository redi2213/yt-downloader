"""Applies Settings > Appearance to every widget the app creates.

One hook does it all: ``install()`` wraps ``Widget.add_widget`` so each widget that is
put on a screen is styled once (theme colors, font, text size, box size) and, when the
language is Persian, its text is translated (core/i18n.py), shaped and right aligned. A
text that changes later (``label.text = ...``) goes through the same steps. Switching
the language or the theme rebuilds the screen, so nothing has to be updated in place.

Buttons keep their text in ``widget._ytb_src`` (English, as the code wrote it), because
the Back key looks for a button named "Back".
"""
from kivy.core.window import Window
from kivy.metrics import sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.widget import Widget

from core import appearance, i18n
from screens import common

_installed = False
_flat = ("", "")
_DEFAULT_WHITE = (1, 1, 1, 1)


def _is_shaped(text):
    return any("\ufb50" <= c <= "\ufeff" for c in (text or ""))


def start(flat_dir=None):
    """Called once when the app starts and again after a theme / language change."""
    global _flat
    i18n.set_language(appearance.prefs().get("lang"))
    if flat_dir and not any(_flat):
        _flat = appearance.flat_images(flat_dir)
    colors = appearance.colors()
    Window.clearcolor = colors["bg"]
    common.CARD[:] = list(colors["card"])
    common.CARD_ON[:] = list(colors["selected"])


def install(flat_dir=None):
    global _installed
    start(flat_dir)
    if _installed:
        return
    _installed = True
    original = Widget.add_widget

    def add_widget(self, widget, *args, **kwargs):
        result = original(self, widget, *args, **kwargs)
        try:
            style_tree(widget)
        except Exception:
            pass
        return result

    Widget.add_widget = add_widget


def style_tree(widget):
    if getattr(widget, "_ytb_done", False):
        return
    widget._ytb_done = True
    _style_one(widget)
    for child in list(getattr(widget, "children", [])):
        style_tree(child)


# -- one widget ---------------------------------------------------------------------------------------------------
def _style_one(w):
    if isinstance(w, TextInput):
        _style_input(w)
    elif isinstance(w, Label):
        _style_label(w)
    elif isinstance(w, BoxLayout):
        _style_box(w)


def _scale_height(w):
    scale = appearance.box_scale()
    if scale != 1.0 and w.size_hint_y is None:
        w.height = w.height * scale


def _style_box(box):
    if box.orientation != "horizontal":
        return
    if i18n.is_fa() and len(box.children) > 1 and not getattr(box, "_ytb_mirrored", False):
        box._ytb_mirrored = True
        kids = list(box.children)          # last added first
        box.clear_widgets()
        for kid in kids:                   # the first one added now sits on the right
            box.add_widget(kid)
    if box.size_hint_y is None and any(isinstance(c, (Button, TextInput)) for c in box.children):
        _scale_height(box)


def _font_for(w, text):
    """font_name for this widget, or None to leave it as it is."""
    if w.font_name not in ("Roboto", None, "") and w.font_name != getattr(w, "_ytb_font", None):
        return None                        # the code chose a font on purpose
    chosen = appearance.chosen_font()
    if text and common.has_rtl(text):
        ok = any(path == chosen and p_ok for _l, path, p_ok in appearance.available_fonts())
        if ok:
            return chosen
        return common.FA_FONT or (chosen or None)
    return chosen or None


def _apply_font(w, text):
    font = _font_for(w, text)
    if font and w.font_name != font:
        w._ytb_font = font
        w.font_name = font


def _style_label(w):
    scale = appearance.font_scale()
    if scale != 1.0:
        w.font_size = w.font_size * scale
    is_button = isinstance(w, Button)
    if is_button:
        _scale_height(w)
        if not appearance.is_classic():
            _flatten(w)
    else:
        _label_color(w)
    _apply_font(w, w.text)
    if i18n.is_fa() and not isinstance(w, (Spinner, ToggleButton)) and not getattr(w, "_ytb_notr", False):
        w._ytb_src = w.text
        w._ytb_last = None
        w._ytb_busy = False
        w.bind(text=_on_text, text_size=_on_text_size)
        _convert(w, w.text)
    elif i18n.is_fa() and isinstance(w, (Spinner, ToggleButton)):
        _apply_font(w, w.text)


def _label_color(w):
    colors = appearance.colors()
    if tuple(w.color) == _DEFAULT_WHITE:
        if not appearance.is_classic():
            w.color = colors["text"]
    elif appearance.dark_text_on_light() and appearance.luminance(w.color) > 0.55:
        w.color = colors["text"]          # pale hint colors would vanish on a light background


def _flatten(btn):
    """Flat button in the theme color (the grey image of Kivy cannot be made lighter)."""
    normal, down = _flat
    colors = appearance.colors()
    btn.color = colors["button_text"] if tuple(btn.color) == _DEFAULT_WHITE else btn.color
    if not normal:
        btn.background_color = colors["button"] if tuple(btn.background_color) == _DEFAULT_WHITE else btn.background_color
        return
    btn.background_normal = normal
    btn.background_down = down
    btn.border = (0, 0, 0, 0)          # the picture is a plain 4x4 color, nothing to slice
    if tuple(btn.background_color) == _DEFAULT_WHITE:
        btn.background_color = colors["button"]
    btn._ytb_flat = True
    btn.bind(background_color=_remap_default)


def _remap_default(btn, value):
    """Code that sets a button back to "no tint" (1,1,1,1) means the normal button color."""
    if tuple(value) == _DEFAULT_WHITE and not getattr(btn, "_ytb_busy_bg", False):
        btn._ytb_busy_bg = True
        btn.background_color = appearance.colors()["button"]
        btn._ytb_busy_bg = False


def _style_input(w):
    scale = appearance.font_scale()
    if scale != 1.0:
        w.font_size = w.font_size * scale
    _scale_height(w)
    chosen = appearance.chosen_font()
    if chosen and w.font_name in ("Roboto", None, ""):
        w.font_name = chosen
    if not appearance.is_classic():
        colors = appearance.colors()
        w.background_color = appearance.input_background()
        w.foreground_color = colors["text"] if appearance.luminance(appearance.input_background()) < 0.5 else (0.1, 0.1, 0.12, 1)
        w.cursor_color = w.foreground_color
        w.hint_text_color = tuple(w.foreground_color[:3]) + (0.5,)
    if i18n.is_fa() and w.hint_text:
        hint = i18n.tr(w.hint_text)
        if hint != w.hint_text and common.has_rtl(hint) and not _is_shaped(hint):
            hint = common.fa_text(hint, w.width if w.width > 50 else None)
        w.hint_text = hint
        if common.has_rtl(hint) and common.FA_FONT:
            w.font_name = common.FA_FONT


# -- Persian text -------------------------------------------------------------------------------------------------
def _width_of(w):
    """Pixels a text may take: only a label the code gave a ``text_size`` is cut into lines for it.
    (A button's own width is no limit - a new widget is 100 px wide and would cut every word.)"""
    ts = getattr(w, "text_size", None)
    return ts[0] if ts and ts[0] else None


def _convert(w, raw):
    if getattr(w, "_ytb_busy", False):
        return
    w._ytb_src = raw
    out = i18n.tr(raw)
    if common.has_rtl(out) and not _is_shaped(out):
        out = common.fa_text(out, _width_of(w))
    if out != raw:
        w._ytb_last = out
        w._ytb_busy = True
        try:
            w.text = out
        finally:
            w._ytb_busy = False
    if common.has_rtl(out):
        _apply_font(w, out)
        if getattr(w, "halign", "") == "left" and not isinstance(w, Button):
            w.halign = "right"


def _on_text(w, value):
    if getattr(w, "_ytb_busy", False) or value == getattr(w, "_ytb_last", None):
        return
    _convert(w, value)


def _on_text_size(w, value):
    """A wrapped Persian label is cut into lines for its text_size: redo it when that changes."""
    src = getattr(w, "_ytb_src", None)
    if src and value and value[0] and not getattr(w, "_ytb_busy", False) and len(src) > 24:
        _convert(w, src)
