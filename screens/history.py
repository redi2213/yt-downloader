import threading
import uuid

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout

from screens.base import BaseScreen

from backend.github_api import (
    delete_release,
    rename_release_asset,
    dispatch_workflow,
    get_run_id_by_job_id,
    wait_for_run,
    GitHubAuthError,
    notify,
)


class HistoryScreen(BaseScreen):

    def show(self):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=f"Recent jobs ({len(app.job_history)})",
                size_hint_y=None,
                height=40
            )
        )

        if not app.job_history:
            self.add(
                Label(
                    text="No jobs yet",
                    size_hint_y=None,
                    height=40
                )
            )

        back = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back.bind(
            on_press=lambda x: app.show_home()
        )

        self.add(back)


    def show_live(self):
        self.clear()

        app = self.app

        self.add(
            Label(
                text="Loading...",
                size_hint_y=None,
                height=40
            )
        )

        threading.Thread(
            target=app._load_live_history_thread,
            daemon=True
        ).start()


    def render(self, items):
        self.clear()

        app = self.app

        self.add(
            Label(
                text=f"Download history ({len(items)} found)",
                size_hint_y=None,
                height=40
            )
        )

        if not items:
            self.add(
                Label(
                    text="No downloads yet",
                    size_hint_y=None,
                    height=40
                )
            )

        for item in items:

            row = BoxLayout(
                orientation="vertical",
                size_hint_y=None,
                height=180
            )

            row.add_widget(
                Label(
                    text=item["title"],
                    size_hint_y=None,
                    height=40
                )
            )

            link = TextInput(
                text=item["link"],
                readonly=True,
                multiline=False
            )

            row.add_widget(link)

            copy_btn = Button(
                text="Copy",
                size_hint_y=None,
                height=40
            )

            copy_btn.bind(
                on_press=lambda x, l=item["link"]: Clipboard.copy(l)
            )

            row.add_widget(copy_btn)


            delete_btn = Button(
                text="Delete",
                size_hint_y=None,
                height=40
            )

            delete_btn.bind(
                on_press=lambda x, i=item: self.show_delete_confirm(i)
            )

            row.add_widget(delete_btn)


            rename_btn = Button(
                text="Rename",
                size_hint_y=None,
                height=40
            )

            rename_btn.bind(
                on_press=lambda x, i=item: self.show_rename_prompt(i)
            )

            row.add_widget(rename_btn)


            zip_btn = Button(
                text="Zip",
                size_hint_y=None,
                height=40
            )

            zip_btn.bind(
                on_press=lambda x, i=item: self.start_zip_release(i)
            )

            row.add_widget(zip_btn)

            self.add(row)


        back = Button(
            text="Back",
            size_hint_y=None,
            height=48
        )

        back.bind(
            on_press=lambda x: app.show_home()
        )

        self.add(back)



    def show_delete_confirm(self, item):
        self.clear()

        self.add(
            Label(
                text=f"Delete this release?\n{item['title']}",
                size_hint_y=None,
                height=80
            )
        )

        btn = Button(
            text="Yes, delete",
            size_hint_y=None,
            height=48
        )

        btn.bind(
            on_press=lambda x: self.do_delete_release(item)
        )

        self.add(btn)


        cancel = Button(
            text="Cancel",
            size_hint_y=None,
            height=48
        )

        cancel.bind(
            on_press=lambda x: self.show_live()
        )

        self.add(cancel)



    def do_delete_release(self, item):

        app = self.app

        self.clear()

        self.add(
            Label(
                text="Deleting...",
                size_hint_y=None,
                height=60
            )
        )


        def worker():
            try:
                delete_release(
                    item["release_id"],
                    item["tag_name"]
                )

                Clock.schedule_once(
                    lambda dt: self.show_live()
                )

            except GitHubAuthError:
                Clock.schedule_once(
                    lambda dt: app.show_result(
                        "GitHub token invalid or expired."
                    )
                )

            except Exception as e:
                Clock.schedule_once(
                    lambda dt: app.show_result(
                        f"Delete failed: {str(e)[:60]}"
                    )
                )


        threading.Thread(
            target=worker,
            daemon=True
        ).start()



    def show_rename_prompt(self, item):

        self.clear()

        box = TextInput(
            text=item["title"],
            multiline=False,
            size_hint_y=None,
            height=48
        )

        self.add(box)


        btn = Button(
            text="Save name",
            size_hint_y=None,
            height=48
        )

        btn.bind(
            on_press=lambda x: self.do_rename_release(
                item,
                box.text.strip()
            )
        )

        self.add(btn)



    def do_rename_release(self, item, new_name):

        app = self.app

        if not new_name:
            self.show_live()
            return


        def worker():

            try:

                rename_release_asset(
                    item["release_id"],
                    item["asset_id"],
                    new_name
                )


                Clock.schedule_once(
                    lambda dt: self.show_live()
                )


            except Exception as e:

                Clock.schedule_once(
                    lambda dt: app.show_result(
                        f"Rename failed: {str(e)[:60]}"
                    )
                )


        threading.Thread(
            target=worker,
            daemon=True
        ).start()



    def start_zip_release(self, item):

        app = self.app

        self.clear()

        self.add(
            Label(
                text=f"Zipping:\n{item['title']}",
                size_hint_y=None,
                height=60
            )
        )


        job_id = uuid.uuid4().hex[:12]


        def worker():

            try:

                dispatch_workflow(
                    "zip-release.yml",
                    {
                        "asset_url": item["link"],
                        "asset_name": item["title"],
                        "release_id": str(item["release_id"]),
                        "job_id": job_id,
                    }
                )


                run_id = get_run_id_by_job_id(
                    "zip-release.yml",
                    job_id
                )


                if run_id is None:
                    Clock.schedule_once(
                        lambda dt: app.show_result(
                            "Could not find zip workflow."
                        )
                    )
                    return


                result = wait_for_run(run_id)


                Clock.schedule_once(
                    lambda dt: self.show_live()
                )


            except Exception as e:

                Clock.schedule_once(
                    lambda dt: app.show_result(
                        f"Zip failed: {str(e)[:60]}"
                    )
                )


        threading.Thread(
            target=worker,
            daemon=True
        ).start()
