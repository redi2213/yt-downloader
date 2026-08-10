from kivy.core.clipboard import Clipboard
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens.common import back_button, wrapped_label, wrapped_label_height


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))


def build(nav, items):
    nav.clear()
    nav.add(Label(text=f"Download history ({len(items)} found)", size_hint_y=None, height=40))
    if not items:
        nav.add(Label(text="No downloads yet", size_hint_y=None, height=40))
    else:
        bulk_delete_btn = Button(text=f"Delete all {len(items)} shown", size_hint_y=None, height=48)
        bulk_delete_btn.bind(on_press=lambda i: nav.show_bulk_delete_confirm(items))
        nav.add(bulk_delete_btn)

    for item in items:
        size_mb = item.get("size", 0) / (1024 * 1024)
        size_text = f" ({size_mb:.1f} MB)" if size_mb else ""
        title_text = f"{item['date']}\n{item['title']}{size_text}"
        title_height = wrapped_label_height(title_text)
        row_height = title_height + 44 + 6 + 12  # title + link_row + spacing + padding
        row = BoxLayout(orientation="vertical", size_hint_y=None, height=row_height, spacing=6, padding=(0, 6))
        row.add_widget(wrapped_label(title_text, height=title_height))

        link_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4)
        box = TextInput(text=item["link"], readonly=True, multiline=False, size_hint_x=0.55)
        copy_btn = Button(text="Copy", size_hint_x=0.15)
        copy_btn.bind(on_press=lambda i, l=item["link"]: Clipboard.copy(l))
        rename_btn = Button(text="Rename", size_hint_x=0.15)
        rename_btn.bind(on_press=lambda i, it=item: nav.show_rename_prompt(it))
        zip_btn = Button(text="Zip", size_hint_x=0.15)
        zip_btn.bind(on_press=lambda i, it=item: nav.start_zip_release(it))
        delete_btn = Button(text="Delete", size_hint_x=0.15)
        delete_btn.bind(on_press=lambda i, it=item: nav.show_delete_confirm(it))
        link_row.add_widget(box)
        link_row.add_widget(copy_btn)
        link_row.add_widget(rename_btn)
        link_row.add_widget(zip_btn)
        link_row.add_widget(delete_btn)
        row.add_widget(link_row)

        nav.add(row)
    nav.add(back_button(nav))


def build_delete_confirm(nav, item):
    nav.clear()
    nav.add(Label(text=f"Delete this release?\n{item['title']}", size_hint_y=None, height=80))
    confirm_btn = Button(text="Yes, delete", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_delete_release(item))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_job_history())
    nav.add(cancel_btn)


def build_bulk_delete_confirm(nav, items):
    nav.clear()
    nav.add(Label(text=f"Delete all {len(items)} releases shown?\nThis cannot be undone.",
                   size_hint_y=None, height=80))
    confirm_btn = Button(text=f"Yes, delete all {len(items)}", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_bulk_delete(items))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_job_history())
    nav.add(cancel_btn)


def build_deleting(nav):
    nav.clear()
    nav.add(Label(text="Deleting...", size_hint_y=None, height=60))
    nav.add(back_button(nav))


def build_bulk_deleting(nav, count):
    nav.clear()
    status_label = Label(text=f"Deleting 0/{count}...", size_hint_y=None, height=60)
    nav.add(status_label)
    nav.set_status_label(status_label)
    back_btn = Button(text="Back (keeps deleting)", size_hint_y=None, height=48)
    back_btn.bind(on_press=lambda i: nav.show_home())
    nav.add(back_btn)


def build_renaming(nav):
    nav.clear()
    nav.add(Label(text="Renaming...", size_hint_y=None, height=60))
    nav.add(back_button(nav))


def build_rename_prompt(nav, item):
    nav.clear()
    nav.add(Label(text=f"Rename:\n{item['title']}", size_hint_y=None, height=60))
    name_input = TextInput(text=item["title"], multiline=False, size_hint_y=None, height=48)
    nav.add(name_input)
    confirm_btn = Button(text="Save name", size_hint_y=None, height=48)
    confirm_btn.bind(on_press=lambda i: nav.do_rename_release(item, name_input.text.strip()))
    nav.add(confirm_btn)
    cancel_btn = Button(text="Cancel", size_hint_y=None, height=48)
    cancel_btn.bind(on_press=lambda i: nav.show_job_history())
    nav.add(cancel_btn)
