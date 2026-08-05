from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from screens.base import BaseScreen


class HomeScreen(BaseScreen):

    def show(self):
        self.clear()

        app = self.app

        saved_token = app.get_token()

        if saved_token and not getattr(app, "_show_token_field", False):
            app.token_input = None

            btn = Button(
                text="Update GitHub token",
                size_hint_y=None,
                height=44
            )
            btn.bind(on_press=lambda i: app._reveal_token_field())
            self.add(btn)

        else:
            app.token_input = TextInput(
                text=saved_token,
                hint_text="GitHub Token",
                multiline=False,
                size_hint_y=None,
                height=48
            )
            self.add(app.token_input)

            btn = Button(
                text="Save token",
                size_hint_y=None,
                height=40
            )
            btn.bind(
                on_press=lambda i: app._save_token_and_refresh()
            )
            self.add(btn)

        app.url_input = TextInput(
            hint_text="YouTube video or playlist link",
            multiline=False,
            size_hint_y=None,
            height=48
        )
        self.add(app.url_input)


        app.audio_toggle = ToggleButton(
            text="Audio only (MP3): OFF",
            size_hint_y=None,
            height=48
        )

        app.audio_toggle.bind(
            on_press=app.toggle_audio
        )

        self.add(app.audio_toggle)


        buttons = [
            ("Get qualities (single video)", app.on_fetch_single),
            ("This is a playlist", app.on_fetch_playlist),
            ("Upload a file (any link)", lambda x: app.show_upload_screen()),
            ("Download history", lambda x: app.show_live_history()),
            ("About", lambda x: app.show_about()),
        ]


        for text, callback in buttons:
            btn = Button(
                text=text,
                size_hint_y=None,
                height=48
            )
            btn.bind(on_press=callback)
            self.add(btn)


        if app.current_job:
            btn = Button(
                text="Check last job",
                size_hint_y=None,
                height=48
            )
            btn.bind(
                on_press=lambda x: app.resume_job_screen()
            )
            self.add(btn)


        status = Button(
            text="Check GitHub Actions status",
            size_hint_y=None,
            height=48
        )
        status.bind(
            on_press=lambda x: app.show_actions_status()
        )
        self.add(status)
