"""Manual tool picker for a link shared into the app: shown when the link is
not obviously YouTube and no tool's ``domains`` matched it. Lists every tool
the app has (built-in screens + the remote-config actions); tapping one opens
it with the link already filled in.
"""
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens import common


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Link received - loading tools...", size_hint_y=None, height=60))
    nav.add(common.back_button(nav))


def build(nav, url, actions):
    nav.clear()
    nav.add(Label(text="Link received - choose a tool", size_hint_y=None, height=44))
    nav.add(common.wrapped_label(url))

    youtube_btn = Button(text="YouTube Download", size_hint_y=None, height=52)
    youtube_btn.bind(on_press=lambda i: nav.show_youtube_download(video_url=url))
    nav.add(youtube_btn)

    upload_btn = Button(text="Upload a file (any link)", size_hint_y=None, height=52)
    upload_btn.bind(on_press=lambda i: nav.show_upload_screen(url))
    nav.add(upload_btn)

    for action in actions or []:
        btn = Button(text=action.get("title", action.get("id", "?")),
                     size_hint_y=None, height=52)
        btn.bind(on_press=lambda i, a=action: nav.show_action_input(a, prefill=url))
        nav.add(btn)

    nav.add(common.back_button(nav))
