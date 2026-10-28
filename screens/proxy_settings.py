"""Settings > Downloads and storage > Proxy / v2ray config.

One saved config (a GitHub secret) that the Any site workflow uses to read pages from another IP
than GitHub's. It can be replaced or deleted here; the box in Any site overrides it for one run."""
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens import common
from screens.common import BTN_H, back_button, wrapped_label


def build(nav, state=None):
    """``state``: None while the saved state is being read, else {'ok': True, 'saved': bool}
    or {'ok': False, 'error': str}."""
    nav.clear()
    nav.add(Label(text="Proxy / v2ray config", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label(
        "Many sites block GitHub's IP. With a config saved here, Any site reads the page through it "
        "(only the page; the video itself is downloaded directly). Supported: vless / vmess / trojan / ss "
        "links (one per line), a subscription link, or a full Xray JSON. When a config is set, the free "
        "proxy list is not used. The config is saved as a GitHub secret and cannot be read back."))
    if state is None:
        status = "Checking what is saved..."
    elif not state.get("ok"):
        status = state.get("error") or "Could not read what is saved."
    elif state.get("saved"):
        status = "A v2ray config is saved."
    else:
        status = "No v2ray config is saved."
    nav.add(wrapped_label(status))

    box = TextInput(hint_text="Paste vless:// vmess:// trojan:// ss:// links, a subscription link or Xray JSON",
                    multiline=True, size_hint_y=None, height=dp(150))
    nav.add(box)
    nav.add(common.paste_row(box, append=True))

    saved = bool(state and state.get("ok") and state.get("saved"))
    save_btn = Button(text="Replace the saved config" if saved else "Save config", size_hint_y=None, height=BTN_H)
    save_btn.bind(on_press=lambda i: nav.start_save_proxy_config(box.text))
    nav.add(save_btn)
    if saved:
        delete_btn = Button(text="Delete the saved config", size_hint_y=None, height=BTN_H)
        delete_btn.bind(on_press=lambda i: nav.start_delete_proxy_config())
        nav.add(delete_btn)

    info = Label(text="", size_hint_y=None, height=40, color=(1, 0.75, 0.4, 1))
    nav.add(info)
    nav.set_status_label(info)
    nav.add(back_button(nav, to=lambda: nav.show_settings_section("downloads")))
