"""Storage screens (Settings > Storage): where finished files are kept
(GitHub / Arvan / both), the Arvan buckets, the Arvan usage page and the
form to add a bucket. Only builds widgets: the work is done by
services/storage_service.py through the navigator.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from core import storage_format as fmt
from screens import common
from screens.common import BTN_H, GAP, SMALL_BTN_H, back_button, wrapped_label

_ON = (0.35, 0.85, 0.45, 1)      # tint of the selected button
_OFF = (1, 1, 1, 1)
_DANGER = (1.0, 0.55, 0.55, 1)

MODE_BUTTONS = (("github", "GitHub"), ("arvan", "Arvan"), ("both", "Both"))


def build(nav, res, mode=None):
    """The Storage screen. ``res`` is the bucket list result of
    storage_service.start_load_buckets, or None while it is loading."""
    nav.clear()
    mode = mode or nav.storage_mode()
    nav.add(Label(text="Storage", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("Where new files are kept. Arvan files are deleted after 7 days "
                          "(free plan: 5 GB storage, 20 GB traffic)."))

    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for key, text in MODE_BUTTONS:
        btn = Button(text=text)
        if key == mode:
            btn.background_color = _ON
        btn.bind(on_press=lambda i, k=key: nav.set_storage_mode(k))
        row.add_widget(btn)
    nav.add(row)

    nav.add(Label(text="Arvan buckets", size_hint_y=None, height=BTN_H))
    if res is None:
        nav.add(Label(text="Loading...", size_hint_y=None, height=BTN_H))
    elif not res.get("ok"):
        nav.add(wrapped_label(res.get("error", "Could not read the buckets.")))
    elif not res["buckets"]:
        nav.add(wrapped_label("No bucket yet. Add one to use Arvan."))
    else:
        nav.add(wrapped_label("Tap a bucket to make it the preferred one. If it is full, "
                              "the next one is used."))
        for bucket in res["buckets"]:
            nav.add(_bucket_row(nav, bucket))

    add_btn = Button(text="Add a bucket", size_hint_y=None, height=BTN_H)
    add_btn.bind(on_press=lambda i: nav.show_add_bucket())
    nav.add(add_btn)

    info_btn = Button(text="Arvan usage and files", size_hint_y=None, height=BTN_H)
    info_btn.bind(on_press=lambda i: nav.show_storage_info())
    nav.add(info_btn)

    clean_btn = Button(text="Delete expired files now", size_hint_y=None, height=BTN_H)
    clean_btn.bind(on_press=lambda i: nav.start_arvan_cleanup())
    nav.add(clean_btn)

    nav.add(back_button(nav, to=lambda: nav.show_settings_section("downloads")))


def _bucket_row(nav, bucket):
    row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    mark = "(*) " if bucket["active"] else "( ) "
    pick = Button(text=f"{mark}{bucket['label']}  [{bucket['id']}]")
    if bucket["active"]:
        pick.background_color = _ON
    pick.bind(on_press=lambda i, b=bucket["id"]: nav.set_active_bucket(b))
    row.add_widget(pick)
    remove = Button(text="Remove", size_hint_x=None, width=dp(90))
    remove.background_color = _DANGER
    remove.bind(on_press=lambda i, b=bucket: nav.show_remove_bucket_confirm(b))
    row.add_widget(remove)
    return row


def build_remove_confirm(nav, bucket):
    nav.clear()
    nav.add(wrapped_label(f"Remove the bucket \"{bucket['label']}\" from the app?\n"
                          "Its keys are deleted from the GitHub secrets. "
                          "Files already on Arvan stay there until the daily cleanup."))
    yes = Button(text="Remove", size_hint_y=None, height=BTN_H)
    yes.background_color = _DANGER
    yes.bind(on_press=lambda i: nav.start_remove_bucket(bucket["id"]))
    nav.add(yes)
    no = Button(text="Cancel", size_hint_y=None, height=BTN_H)
    no.bind(on_press=lambda i: nav.show_storage())
    nav.add(no)


def build_add(nav):
    """Form for a new bucket: the keys of any Arvan account (a bought plan, an
    account somebody gave you). Saved as GitHub secrets; never kept here."""
    nav.clear()
    nav.add(Label(text="Add an Arvan bucket", size_hint_y=None, height=BTN_H))
    nav.add(wrapped_label("The bucket must already exist in that Arvan account. "
                          "The keys are saved as GitHub secrets and cannot be read back."))

    def field(hint, text="", password=False, paste=True):
        box = TextInput(text=text, hint_text=hint, multiline=False, password=password,
                        size_hint_y=None, height=dp(48))
        nav.add(box)
        if paste:
            nav.add(common.paste_row(box))
        return box

    access = field("Access key")
    secret = field("Secret key", password=True)
    bucket = field("Bucket name", text="my-files-telegram", paste=False)
    endpoint = field("Endpoint (region)", text=fmt.DEFAULT_ENDPOINT, paste=False)
    quota = field("Storage of the plan in GB", text="5", paste=False)

    save = Button(text="Save bucket", size_hint_y=None, height=BTN_H)
    save.bind(on_press=lambda i: nav.start_add_bucket(
        access.text, secret.text, bucket.text, endpoint.text, quota.text))
    nav.add(save)
    nav.add(back_button(nav, to=nav.show_storage))


def build_info(nav, data):
    """Usage of every bucket and the project's files with the time left until
    the daily cleanup deletes them. ``data`` is the info block of
    scripts/arvan_maintenance.py."""
    nav.clear()
    nav.add(Label(text="Arvan usage", size_hint_y=None, height=BTN_H))
    buckets = data.get("buckets", [])
    if not buckets:
        nav.add(wrapped_label("No Arvan bucket is configured. Add one first."))
    for b in buckets:
        name = f"{b.get('bucket')}  [{b.get('id')}]"
        if b.get("error"):
            nav.add(wrapped_label(f"{name}\nCould not read it: {b['error']}"))
            continue
        quota = b.get("quota_bytes") or 0
        used = b.get("used_bytes") or 0
        left = max(0, quota - used)
        lines = [name,
                 f"Used: {fmt.fmt_bytes(used)} of {fmt.fmt_bytes(quota)}",
                 f"Free: {fmt.fmt_bytes(left)}",
                 f"Files in the bucket: {b.get('objects', 0)} (from this app: {b.get('ours', 0)})",
                 "Traffic left: not available from Arvan's storage API - see the Arvan panel"]
        nav.add(wrapped_label("\n".join(lines)))
        for f in b.get("files", []):
            text = f"{f.get('name')}\n{fmt.fmt_bytes(f.get('size'))} - {fmt.fmt_expiry(f.get('expires_in_hours'))}"
            nav.add(wrapped_label(text, halign="left"))
    nav.add(back_button(nav, to=nav.show_storage))
