"""Settings > Appearance and language: language, theme and own colors, font and sizes.

Every choice is saved (api/appearance_prefs.py), applied to the window (screens/style.py)
and the screen is built again, so the change is visible at once.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import appearance
from screens import style
from screens.common import BTN_H, GAP, back_button, fa_text, wrapped_label

_ON = "\u25cf "   # marks the chosen item


def _apply(nav, rebuild):
    style.start()
    rebuild()


def _swatch_button(color, text=""):
    btn = Button(text=text, background_color=color, size_hint_y=None, height=BTN_H)
    normal, down = style._flat
    if normal:
        btn.background_normal = normal
        btn.background_down = down
    return btn


# -- menu ---------------------------------------------------------------------------------------------------------
def build_menu(nav):
    nav.clear()
    nav.add(Label(text="Appearance and language", size_hint_y=None, height=44))
    for text, action in (("Language", nav.show_appearance_language),
                         ("Theme and colors", nav.show_appearance_theme),
                         ("Font and sizes", nav.show_appearance_font)):
        btn = Button(text=text, size_hint_y=None, height=52)
        btn.bind(on_press=lambda i, a=action: a())
        nav.add(btn)
    nav.add(back_button(nav, to=nav.show_settings))


# -- language -----------------------------------------------------------------------------------------------------
def build_language(nav):
    nav.clear()
    nav.add(Label(text="Language", size_hint_y=None, height=44))
    nav.add(Label(text="Choose the language", size_hint_y=None, height=32))
    lang = appearance.prefs().get("lang")

    en_btn = Button(text=("%sEnglish" % _ON) if lang != "fa" else "English", size_hint_y=None, height=52)
    en_btn.bind(on_press=lambda i: _set_language(nav, "en"))
    nav.add(en_btn)
    fa_word = fa_text("فارسی")
    fa_btn = Button(text=(fa_word + " " + _ON.strip()) if lang == "fa" else fa_word, size_hint_y=None, height=52)
    fa_btn.font_name = _fa_font(fa_btn.font_name)
    fa_btn.bind(on_press=lambda i: _set_language(nav, "fa"))
    nav.add(fa_btn)
    nav.add(wrapped_label("Persian turns the whole app Persian and right-to-left. A text that is not translated "
                          "yet stays English."))
    nav.add(back_button(nav, to=nav.show_appearance))


def _fa_font(current):
    from screens.common import FA_FONT
    return FA_FONT or current


def _set_language(nav, code):
    appearance.save(lang=code)
    _apply(nav, nav.show_appearance_language)


# -- theme and colors ---------------------------------------------------------------------------------------------
def build_theme(nav):
    nav.clear()
    nav.add(Label(text="Theme and colors", size_hint_y=None, height=44))
    nav.add(Label(text="Themes", size_hint_y=None, height=32))
    current = appearance.theme_id()
    for theme_id, (label, palette) in appearance.THEMES.items():
        mark = _ON if theme_id == current else ""
        btn = _swatch_button(palette["button"], mark + label)
        btn.color = palette["button_text"]
        btn.bind(on_press=lambda i, t=theme_id: _set_theme(nav, t))
        nav.add(btn)

    nav.add(wrapped_label("Own colors (tap a color, or type a code like #1E88E5)"))
    colors, custom = appearance.colors(), appearance.custom_colors()
    for key in appearance.COLOR_KEYS:
        mark = " *" if key in custom else ""
        nav.add(Label(text=f"{appearance.COLOR_LABELS[key]}{mark}   {appearance.rgba_to_hex(colors[key])}",
                      size_hint_y=None, height=32))
        for start in (0, 6):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
            for hex_code in appearance.PALETTE[start:start + 6]:
                swatch = _swatch_button(appearance.hex_to_rgba(hex_code))
                swatch._ytb_notr = True
                swatch.bind(on_press=lambda i, k=key, h=hex_code: _set_color(nav, k, h))
                row.add_widget(swatch)
            nav.add(row)
        entry = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        code = TextInput(hint_text="#RRGGBB", multiline=False, size_hint_x=0.6)
        apply_btn = Button(text="Apply", size_hint_x=0.4)
        apply_btn.bind(on_press=lambda i, k=key, t=code: _set_color(nav, k, t.text))
        entry.add_widget(code)
        entry.add_widget(apply_btn)
        nav.add(entry)

    if custom:
        reset_btn = Button(text="Reset own colors", size_hint_y=None, height=48)
        reset_btn.bind(on_press=lambda i: _reset_colors(nav))
        nav.add(reset_btn)
    nav.add(back_button(nav, to=nav.show_appearance))


def _set_theme(nav, theme_id):
    appearance.save(theme=theme_id, colors={})     # a theme replaces the own colors
    _apply(nav, nav.show_appearance_theme)


def _set_color(nav, key, hex_code):
    if appearance.hex_to_rgba(hex_code) is None:
        return
    colors = dict(appearance.custom_colors())
    colors[key] = appearance.rgba_to_hex(appearance.hex_to_rgba(hex_code))
    appearance.save(colors=colors)
    _apply(nav, nav.show_appearance_theme)


def _reset_colors(nav):
    appearance.save(colors={})
    _apply(nav, nav.show_appearance_theme)


# -- font and sizes -----------------------------------------------------------------------------------------------
def build_font(nav):
    nav.clear()
    nav.add(Label(text="Font and sizes", size_hint_y=None, height=44))
    nav.add(Label(text="Font", size_hint_y=None, height=32))
    chosen = appearance.chosen_font()
    for label, path, persian_ok in appearance.available_fonts():
        text = ("%s" % _ON if path == chosen else "") + label + ("  (Persian ok)" if persian_ok else "")
        btn = Button(text=text, size_hint_y=None, height=48)
        btn._ytb_notr = True
        if path:
            btn.font_name = path
        btn.bind(on_press=lambda i, p=path: _set_font(nav, p))
        nav.add(btn)
    nav.add(wrapped_label("More fonts: copy .ttf files (for example Vazirmatn-Regular.ttf) into the app's "
                          "assets/fonts folder and build the app again - they appear in this list. "
                          "Persian text needs a font marked Persian ok."))

    nav.add(Label(text="Text size", size_hint_y=None, height=32))
    _step_row(nav, appearance.FONT_SCALES, appearance.font_scale(), _set_font_scale)
    nav.add(Label(text="Box and button size", size_hint_y=None, height=32))
    _step_row(nav, appearance.BOX_SCALES, appearance.box_scale(), _set_box_scale)

    sample = Label(text="Sample text   " + fa_text("متن نمونه"), size_hint_y=None, height=BTN_H)
    sample._ytb_notr = True
    from screens.common import FA_FONT
    if FA_FONT and not appearance.chosen_font():
        sample.font_name = FA_FONT
    nav.add(sample)
    nav.add(back_button(nav, to=nav.show_appearance))


def _step_row(nav, steps, current, on_pick):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for label, value in steps:
        btn = Button(text=(_ON if abs(value - current) < 0.01 else "") + label)
        btn.bind(on_press=lambda i, v=value: on_pick(nav, v))
        row.add_widget(btn)
    nav.add(row)


def _set_font(nav, path):
    appearance.save(font=path)
    _apply(nav, nav.show_appearance_font)


def _set_font_scale(nav, value):
    appearance.save(font_scale=value)
    _apply(nav, nav.show_appearance_font)


def _set_box_scale(nav, value):
    appearance.save(box_scale=value)
    _apply(nav, nav.show_appearance_font)
