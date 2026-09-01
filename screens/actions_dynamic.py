"""Dynamic actions screen: renders buttons from the remote config (fetched
via services/remote_config_service.py) instead of hardcoded ones, so new
download sources can appear without a rebuild - only a config.json edit on
the 'config' branch.

Two sub-screens, both built by this module:
  - build_loading / build: the list of available actions
  - build_input: the URL-entry form for one chosen action, which on submit
    hands off to generic_action_service via the Navigator
"""
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens import common


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Loading available actions...", size_hint_y=None, height=60))
    nav.add(common.back_button(nav))


def build(nav, actions):
    nav.clear()
    nav.add(Label(text="Download Anything", size_hint_y=None, height=48))

    if not actions:
        nav.add(Label(text="No actions available right now.", size_hint_y=None, height=48))
    else:
        for action in actions:
            btn = Button(text=action.get("title", action.get("id", "?")),
                         size_hint_y=None, height=52)
            btn.bind(on_press=lambda instance, a=action: nav.show_action_input(a))
            nav.add(btn)

    nav.add(common.back_button(nav))


def build_input(nav, action):
    nav.clear()
    nav.add(Label(text=action.get("title", ""), size_hint_y=None, height=48))

    hint = action.get("input_hint", "Enter a link")
    url_input = TextInput(hint_text=hint, multiline=False, size_hint_y=None, height=48)
    nav.add(url_input)

    start_btn = Button(text="Start", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.start_dynamic_action(action, url_input.text))
    nav.add(start_btn)

    nav.add(common.back_button(nav, text="Back"))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)
