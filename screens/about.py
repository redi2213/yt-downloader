from kivy.uix.button import Button
from kivy.uix.label import Label

from core import version_check
from core.config import APP_VERSION, ABOUT_TEXT_TEMPLATE
from screens import common


def build(nav):
    nav.clear()
    about_text = ABOUT_TEXT_TEMPLATE.format(version=APP_VERSION)
    nav.add(Label(text=about_text, size_hint_y=None, height=220))

    status = Label(text="", size_hint_y=None, height=70, halign="center", valign="middle")
    status.text_size = (common.content_width(), None)

    def show(res):
        status.text = version_check.describe(res)

    def check(_instance):
        status.text = "Checking..."
        from services import update_check_service
        update_check_service.start_check(lambda res: nav.schedule(lambda: show(res)))

    check_btn = Button(text="Check for update", size_hint_y=None, height=48)
    check_btn.bind(on_press=check)
    nav.add(check_btn)
    nav.add(status)

    back_btn = Button(text="Back", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_settings())
    nav.add(back_btn)
