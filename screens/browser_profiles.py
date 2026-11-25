"""In-app browser: profiles (Browser settings > Profiles). English texts, translated by core/i18n.

Each profile is a separate box (core/browser_profiles.py): its own cookies and logins (a native WebView profile),
settings, speed dial, history, bookmarks and tabs. Switching is only possible here. Not part of the online browser
pack: it needs the profile support of the APK (BrowserHelper.switchProfile, NATIVE_API 2).
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from api import browser_prefs
from core import android_browser, browser_profiles as bpf
from screens.common import BTN_H, GAP, content_width, fa_font_kwargs, fa_text, wrapped_label
from services import browser_service

_WARN = (1, 0.75, 0.4, 1)
_UNSUPPORTED = "This phone's browser engine does not support profiles (update Android System WebView)"
_pf = None


# -- data ----------------------------------------------------------------------------------------------------------
def profiles():
    """The one Profiles object of the app (read from the phone the first time it is asked for)."""
    global _pf
    if _pf is None:
        _pf = bpf.Profiles.from_data(browser_prefs.get_profiles_data())
        browser_prefs.set_active_id(_pf.active_id)
    return _pf


def _save():
    try:
        browser_prefs.set_profiles_data(profiles().to_data())
    except Exception:
        pass


def _switch_data(pf, pid):
    """The saved data (tabs, lists, settings) now belong to profile ``pid``."""
    browser_service.reset_state()           # writes the open tabs / lists of the profile we leave first
    pf.set_active(pid)
    browser_prefs.set_active_id(pf.active_id)
    _save()


def prepare(nav, br):
    """Called by the browser screen before it reads its data: tells the helper which profile its WebView is made with."""
    pf = profiles()
    if pf.active_id and not android_browser.profiles_supported():
        _switch_data(pf, "")                # the WebView of this phone cannot keep profiles apart: the main one is used
    if br is not None and not br.created():
        pid, secure = pf.spec(pf.active_id)
        br.profile = (pid, secure, pf.take_pending())
        _save()


def activate(nav, pid):
    """Makes ``pid`` the active profile (the WebView is made again with it). Returns "" or an error text."""
    pf = profiles()
    if pf.get(pid) is None:
        return "Profile not found"
    if pid == pf.active_id:
        return ""
    if pid and not android_browser.profiles_supported():
        return _UNSUPPORTED
    _switch_data(pf, pid)
    br = nav.browser
    if br is not None:
        native, secure = pf.spec(pid)
        br.switch_profile(native, secure)
    return ""


def fall_back(nav):
    """The WebView could not be put in the active profile: never show it with another profile's cookies."""
    activate(nav, "")
    nav.show_browser()


# -- small widgets -------------------------------------------------------------------------------------------------
def _status(text=""):
    label = Label(text=text, size_hint_y=None, height=BTN_H, color=_WARN, halign="center")
    label.text_size = (content_width(), None)
    return label


def _button(text, action, height=BTN_H):
    btn = Button(text=text, size_hint_y=None, height=height)
    btn.bind(on_press=lambda i: action())
    return btn


def _colored(text, color, name=None, **kw):
    return Button(text=fa_text(text), background_normal="", background_color=bpf.hex_rgba(color, 0.85),
                  color=(1, 1, 1, 1), **fa_font_kwargs(name if name is not None else text), **kw)


def _tag(e, active):
    if active and e["secure"]:
        return f"{e['name']} (active, secure)"
    if active:
        return f"{e['name']} (active)"
    if e["secure"]:
        return f"{e['name']} (secure)"
    return e["name"]


def entry_button(nav, back, back_text):
    """The button of Browser settings that opens this screen."""
    cur = profiles().current()
    btn = _colored(f"Profile: {cur['name']}", cur["color"], cur["name"], size_hint_y=None, height=BTN_H)
    btn.bind(on_press=lambda i: open_profiles(nav, back, back_text))
    return btn


# -- the list ------------------------------------------------------------------------------------------------------
def open_profiles(nav, back, back_text, note=""):
    nav.remember(lambda: open_profiles(nav, back, back_text))
    build_profiles(nav, back, back_text, note)


def build_profiles(nav, back, back_text, note=""):
    from screens import browser
    pf = profiles()
    nav.clear()
    nav.add(Label(text="Browser profiles", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("Each profile is a separate box: its own cookies and logins, settings, speed dial, history, "
                          "bookmarks and tabs. Export cookies uses the active profile. Profiles are switched only "
                          "here, in the browser settings."))
    if not android_browser.profiles_supported():
        nav.add(wrapped_label("This phone's browser engine (Android System WebView) is too old for profiles. "
                              "Update it from Google Play."))
    status = _status(note)
    nav.add(status)

    def switch(pid):
        err = activate(nav, pid)
        if err:
            status.text = err
            return
        nav.show_browser()

    for e in pf.entries():
        active = e["id"] == pf.active_id
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        body = _colored(_tag(e, active), e["color"], e["name"], size_hint_x=0.74)
        body.bind(on_press=lambda i, pid=e["id"]: switch(pid))
        side = Button(text="Edit", size_hint_x=0.26)
        side.bind(on_press=lambda i, pid=e["id"]: open_edit(nav, pid, back, back_text))
        row.add_widget(body)
        row.add_widget(side)
        nav.add(row)

    nav.add(Label(text="New profile", size_hint_y=None, height=BTN_H))
    name_box = TextInput(hint_text="Profile name", multiline=False, size_hint_y=None, height=BTN_H)
    nav.add(name_box)
    pick = {"i": len(pf.entries()) % len(bpf.COLORS)}
    color_btn = Button(text="", size_hint_y=None, height=BTN_H, background_normal="", color=(1, 1, 1, 1))

    def draw_color():
        cname, chex = bpf.COLORS[pick["i"]]
        color_btn.text = f"Color: {cname}"
        color_btn.background_color = bpf.hex_rgba(chex, 0.85)

    def next_color(_i=None):
        pick["i"] = (pick["i"] + 1) % len(bpf.COLORS)
        draw_color()

    color_btn.bind(on_press=next_color)
    draw_color()
    nav.add(color_btn)
    secure = {"on": False}
    secure_btn = Button(text="Secure profile: OFF", size_hint_y=None, height=BTN_H)

    def flip_secure(_i=None):
        secure["on"] = not secure["on"]
        secure_btn.text = "Secure profile: ON" if secure["on"] else "Secure profile: OFF"

    secure_btn.bind(on_press=flip_secure)
    nav.add(secure_btn)
    nav.add(wrapped_label("Secure profile: cookies, logins and tabs stay saved; third-party trackers and cookies are "
                          "blocked; WebRTC cannot leak your IP; location, camera and microphone are closed and ask "
                          "every time. No proxy. It cannot be changed after the profile is made."))

    def create(_i=None):
        if not android_browser.profiles_supported():
            status.text = _UNSUPPORTED
            return
        entry, err = pf.add(name_box.text, bpf.COLORS[pick["i"]][1], secure["on"])
        if err:
            status.text = err
            return
        _save()
        build_profiles(nav, back, back_text, "Profile created")

    name_box.bind(on_text_validate=create)
    nav.add(_button("Create profile", create))
    nav.add(_button("Open the browser", nav.show_browser))
    nav.add(_button(back_text, lambda: browser.open_settings(nav, back, back_text)))


# -- one profile ---------------------------------------------------------------------------------------------------
def open_edit(nav, pid, back, back_text, note=""):
    nav.remember(lambda: open_edit(nav, pid, back, back_text))
    build_edit(nav, pid, back, back_text, note)


def build_edit(nav, pid, back, back_text, note=""):
    pf = profiles()
    e = pf.get(pid)
    if e is None:
        build_profiles(nav, back, back_text)
        return
    nav.clear()
    nav.add(Label(text="Edit profile", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("Secure profile" if e["secure"] else "Normal profile"))
    status = _status(note)
    nav.add(status)
    name_box = TextInput(text=e["name"], hint_text="Profile name", multiline=False, size_hint_x=0.7)
    save_btn = Button(text="Save", size_hint_x=0.3)

    def save(_i=None):
        err = pf.rename(pid, name_box.text)
        if err:
            status.text = err
            return
        _save()
        status.text = "Saved"

    save_btn.bind(on_press=save)
    name_box.bind(on_text_validate=save)
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    row.add_widget(name_box)
    row.add_widget(save_btn)
    nav.add(row)
    idx = {"i": next((n for n, (_c, h) in enumerate(bpf.COLORS) if h == e["color"].upper()), 0)}
    color_btn = Button(text="", size_hint_y=None, height=BTN_H, background_normal="", color=(1, 1, 1, 1))

    def draw_color():
        cname, chex = bpf.COLORS[idx["i"]]
        color_btn.text = f"Color: {cname}"
        color_btn.background_color = bpf.hex_rgba(chex, 0.85)

    def next_color(_i=None):
        idx["i"] = (idx["i"] + 1) % len(bpf.COLORS)
        pf.recolor(pid, bpf.COLORS[idx["i"]][1])
        _save()
        draw_color()

    color_btn.bind(on_press=next_color)
    draw_color()
    nav.add(color_btn)

    def switch():
        err = activate(nav, pid)
        if err:
            status.text = err
            return
        nav.show_browser()

    if pid == pf.active_id:
        nav.add(_button("Already the active profile", lambda: None))
    else:
        nav.add(_button("Switch to this profile", switch))
    if pid:
        confirm = {"armed": False}
        del_btn = Button(text="Delete profile", size_hint_y=None, height=BTN_H)

        def delete(_i=None):
            if not confirm["armed"]:
                confirm["armed"] = True
                del_btn.text = "Tap again to delete this profile and all its data"
                return
            err = pf.delete(pid)
            if err:
                status.text = err
                confirm["armed"] = False
                del_btn.text = "Delete profile"
                return
            browser_prefs.drop_profile_data(pid)
            br = nav.browser
            if br is not None and br.created():
                br.wipe_profile(pid)        # the WebView removes the profile itself the next time the app starts
            _save()
            build_profiles(nav, back, back_text, "Profile deleted")

        del_btn.bind(on_press=delete)
        nav.add(del_btn)
    nav.add(_button("Back to the profiles", lambda: build_profiles(nav, back, back_text)))
