"""Mornye settings: download order, fallback ticks, search note, registry link."""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from api import mornye_prefs
from core.async_utils import run_in_background
from screens import common
from screens.common import BTN_H, GAP, wrapped_label


def build(nav, on_back, registry_text=None):
    prefs = mornye_prefs.load()
    order, enabled = prefs["order"], prefs["enabled"]
    registry = prefs["registry"] if registry_text is None else registry_text
    box = {"registry": registry}

    nav.clear()
    nav.add(Label(text="Mornye settings", size_hint_y=None, height=dp(40)))

    nav.add(wrapped_label(
        "Search: Spotify. Type a song name instead of a link in the Mornye box and "
        "pick the track from the results."))

    nav.add(Label(text="Download order and fallback", size_hint_y=None, height=dp(30)))
    nav.add(wrapped_label(
        "Tick the sources that may be used. They are tried from top to bottom; "
        "if a track is missing on the first, the next one is tried."))

    def _again():
        build(nav, on_back, registry_text=box["registry"])

    def _toggle(p):
        def _h(instance):
            if p in enabled:
                if len(enabled) > 1:
                    enabled.remove(p)
            else:
                enabled.append(p)
            mornye_prefs.save(order, enabled, box["registry"])
            _again()
        return _h

    def _move(i, step):
        def _h(instance):
            j = i + step
            if 0 <= j < len(order):
                order[i], order[j] = order[j], order[i]
                mornye_prefs.save(order, enabled, box["registry"])
                _again()
        return _h

    for i, p in enumerate(order):
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        mark = "[x]" if p in enabled else "[ ]"
        tog = Button(text="%d  %s %s" % (i + 1, mark, mornye_prefs.NAMES[p]))
        tog.bind(on_press=_toggle(p))
        up = Button(text="Up", size_hint_x=None, width=dp(64))
        up.bind(on_press=_move(i, -1))
        down = Button(text="Down", size_hint_x=None, width=dp(72))
        down.bind(on_press=_move(i, 1))
        row.add_widget(tog)
        row.add_widget(up)
        row.add_widget(down)
        nav.add(row)

    nav.add(wrapped_label("Coming soon (not built into the app yet): "
                          + ", ".join(mornye_prefs.SOON)))

    nav.add(Label(text="Extension repo (registry.json)", size_hint_y=None, height=dp(30)))
    reg_input = TextInput(text=registry, hint_text=mornye_prefs.DEFAULT_REGISTRY,
                          multiline=False, size_hint_y=None, height=dp(48))
    reg_input.bind(text=lambda inst, v: box.__setitem__("registry", v))
    nav.add(reg_input)
    nav.add(common.paste_row(reg_input))

    status = Label(text="", size_hint_y=None, height=dp(90))
    nav.add(status)
    nav.set_status_label(status)

    def _check(instance):
        url = box["registry"]
        mornye_prefs.save(order, enabled, url)
        nav.set_status("Checking the repo...")

        def _work():
            try:
                names = mornye_prefs.check_registry(url)
                text = "Saved. %d extensions: %s" % (len(names), ", ".join(names[:8]))
            except ValueError as e:
                text = "Saved, but: %s" % e
            nav.schedule(lambda: nav.set_status(text))
        run_in_background(_work)

    check_btn = Button(text="Save and check repo", size_hint_y=None, height=BTN_H)
    check_btn.bind(on_press=_check)
    nav.add(check_btn)

    def _back(instance):
        mornye_prefs.save(order, enabled, box["registry"])
        on_back()

    back_btn = Button(text="Back", size_hint_y=None, height=BTN_H)
    back_btn.bind(on_press=_back)
    nav.add(back_btn)
