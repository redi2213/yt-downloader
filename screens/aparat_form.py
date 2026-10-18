"""The Aparat form (Download Anything > Download from Aparat).

Instead of one long page with everything on it, the form looks at the link and
shows only what belongs to it:

  * video    - Quality, What to do
  * playlist - + "Choose videos"
  * channel  - + how many videos / days, + "Choose videos"

"What to do" is two steps: Upload to GitHub (Separate files / One zip) or Get
links (On GitHub / On this phone). They are the same four ``output`` values as
before (upload_separate, upload_zip, links, links_phone), so the config.json
entry and the workflow do not change. Nothing was removed, only regrouped.
"""
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens import actions_dynamic, common
from screens.common import GAP
from scripts import aparat_core

_UPLOAD = ("upload_separate", "upload_zip")
_LINKS = ("links", "links_phone")
_TYPE_TEXT = {
    None: "Paste an Aparat link to see the options",
    "video": "A video",
    "playlist": "A playlist",
    "channel": "A channel",
}


class _Slot:
    """Lets the helpers of actions_dynamic (which call ``nav.add``) fill a box
    that can be emptied and refilled when the link type changes."""

    def __init__(self, box):
        self.box = box

    def add(self, widget):
        common.fit_height(widget)
        self.box.add_widget(widget)

    def clear(self):
        self.box.clear_widgets()


def _detect(link):
    link = (link or "").strip()
    if not link:
        return None
    return aparat_core.parse_link(link)[0]


def build(nav, action, prefill=None, share_url=None, initial=None):
    initial = initial or {}
    nav.clear()
    nav.add(Label(text=action.get("title", ""), size_hint_y=None, height=48))

    if share_url:
        nav.add(Label(text="Link received - tool chosen automatically", size_hint_y=None, height=32))
        other_btn = Button(text="Choose another tool", size_hint_y=None, height=44)
        other_btn.bind(on_press=lambda i, u=share_url: nav.show_share_chooser(u))
        nav.add(other_btn)

    fields = {f["key"]: f for f in action.get("fields") or []}

    def default_of(key, fallback):
        field = fields.get(key) or {}
        choices = field.get("choices") or []
        return initial.get(key) or field.get("default") or (choices[0]["value"] if choices else fallback)

    values = {
        "url": initial.get("url") or prefill or "",
        "quality": default_of("quality", "best"),
        "output": default_of("output", "upload_separate"),
        "channel_limit": default_of("channel_limit", "count:5"),
    }

    link_label = fields.get("url", {}).get("label") or "Aparat link"
    nav.add(Label(text=link_label, size_hint_y=None, height=28))
    url_input = TextInput(text=values["url"], hint_text=fields.get("url", {}).get("hint", "Video, playlist or channel link"),
                          multiline=False, size_hint_y=None, height=48)
    nav.add(url_input)
    nav.add(common.paste_row(url_input))

    type_label = Label(text=_TYPE_TEXT[None], size_hint_y=None, height=32)
    nav.add(type_label)

    box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    box.height = 0
    box.bind(minimum_height=box.setter("height"))
    nav.add(box)
    slot = _Slot(box)
    state = {"kind": "unset", "event": None}

    def render():
        kind = _detect(values["url"])
        state["kind"] = kind
        type_label.text = _TYPE_TEXT.get(kind, _TYPE_TEXT["channel"])
        slot.clear()
        if kind is None:
            return
        _quality_section(slot, fields, values)
        _output_section(slot, fields, values, render)
        if kind == "channel" and fields.get("channel_limit"):
            slot.add(Label(text=fields["channel_limit"].get("label", "How many"), size_hint_y=None, height=28))
            actions_dynamic._build_amount_field(slot, fields["channel_limit"], values, values)
        if kind in ("playlist", "channel"):
            pick_btn = Button(text="Choose videos", size_hint_y=None, height=56)
            pick_btn.bind(on_press=lambda i: nav.start_aparat_pick(action, values))
            slot.add(pick_btn)

    def on_link(_instance, text):
        values["url"] = text

        def later(_dt):
            if _detect(values["url"]) != state["kind"] and box.parent is not None:
                render()

        if state["event"] is not None:
            state["event"].cancel()
        state["event"] = Clock.schedule_once(later, 0.4)

    url_input.bind(text=on_link)
    render()

    start_btn = Button(text="Start", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.start_dynamic_action(action, values))
    nav.add(start_btn)

    parent = nav.show_home if share_url else nav.show_dynamic_actions
    nav.add(common.back_button(nav, text="Back", to=parent))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)


def _quality_section(slot, fields, values):
    field = fields.get("quality") or {}
    choices = field.get("choices") or []
    if not choices:
        return
    slot.add(Label(text=field.get("label", "Quality"), size_hint_y=None, height=28))
    buttons = []

    def press_for(index):
        def _handler(_instance):
            values["quality"] = choices[index]["value"]
            for btn, choice in zip(buttons, choices):
                actions_dynamic._mark(btn, choice["value"] == values["quality"])
        return _handler

    labels = [c.get("label", str(c.get("value"))) for c in choices]
    buttons.extend(actions_dynamic._option_rows(slot, labels, press_for))
    for btn, choice in zip(buttons, choices):
        actions_dynamic._mark(btn, choice["value"] == values["quality"])


def _output_section(slot, fields, values, render):
    """Step 1: Upload to GitHub / Get links. Step 2: the two ways of each."""
    available = {c["value"] for c in (fields.get("output") or {}).get("choices", [])}
    if not available:
        return
    slot.add(Label(text="What to do", size_hint_y=None, height=28))

    modes = []
    if available & set(_UPLOAD):
        modes.append(("Upload to GitHub", "upload"))
    if available & set(_LINKS):
        modes.append(("Get links", "links"))
    current = "upload" if values["output"] in _UPLOAD else "links"

    def mode_press(index):
        def _handler(_instance):
            wanted = modes[index][1]
            if wanted != current:
                group = [v for v in (_UPLOAD if wanted == "upload" else _LINKS) if v in available]
                values["output"] = group[0]
                render()
        return _handler

    mode_buttons = actions_dynamic._option_rows(slot, [m[0] for m in modes], mode_press)
    for btn, (_label, key) in zip(mode_buttons, modes):
        actions_dynamic._mark(btn, key == current)

    way_labels = {"upload_separate": "Separate files", "upload_zip": "One zip",
                  "links": "On GitHub", "links_phone": "On this phone"}
    ways = [v for v in (_UPLOAD if current == "upload" else _LINKS) if v in available]
    if len(ways) < 2:
        return

    def way_press(index):
        def _handler(_instance):
            values["output"] = ways[index]
            for btn, way in zip(way_buttons, ways):
                actions_dynamic._mark(btn, way == values["output"])
        return _handler

    way_buttons = actions_dynamic._option_rows(slot, [way_labels[w] for w in ways], way_press)
    for btn, way in zip(way_buttons, ways):
        actions_dynamic._mark(btn, way == values["output"])
