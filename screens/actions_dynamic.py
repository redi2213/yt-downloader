"""Dynamic actions screen: renders buttons from the remote config (fetched
via services/remote_config_service.py) instead of hardcoded ones, so new
download sources can appear without a rebuild - only a config.json edit on
the 'config' branch.

Two sub-screens, both built by this module:
  - build_loading / build: the list of available actions
  - build_input: the input form for one chosen action, which on submit
    hands off to generic_action_service via the Navigator

Each action in config.json can describe its inputs in one of two ways:

  - New style, "fields" (supports multiple inputs, e.g. a link *and* a
    quality picker):
        "fields": [
            {"key": "url", "type": "text", "label": "Video link",
             "hint": "Paste the link"},
            {"key": "format_id", "type": "choice", "label": "Quality",
             "choices": [{"label": "Best", "value": "bestvideo"},
                         {"label": "720p", "value": "bestvideo[height<=720]"}],
             "default": "bestvideo"}
        ]
    "workflow_inputs" values can then reference "{url}", "{format_id}", etc.

  - Old style, single "input_hint" (unchanged, still supported so existing
    config.json entries keep working with no edits):
        "input_hint": "Enter the Mediafire link"
    "workflow_inputs" values reference "{input}".

A "choice" field can also accept a typed amount next to its ready-made
choices. Its choices have values like "count:5" / "days:7" and the field adds:
        "custom": {"units": [{"label": "Videos", "value": "count", "max": 200},
                             {"label": "Days", "value": "days", "max": 365}]}
The screen then shows the choices as quick buttons, a Videos/Days switch and a
number box; the value sent is "<unit>:<number>". Older app versions ignore
"custom" and just show the choices.

The selected option of a choice field is shown in green.
"""
import re

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput

from screens import common
from screens.common import BTN_H, GAP

# Option buttons: normal / selected (the button's grey is multiplied by these)
OPTION_OFF = (1, 1, 1, 1)
OPTION_ON = (0.35, 0.85, 0.45, 1)

_AMOUNT_RE = re.compile(r"^([A-Za-z_]+):(\d+)$")


def parse_amount(value):
    """'days:7' -> ('days', 7); anything else -> None."""
    m = _AMOUNT_RE.match(str(value or ""))
    return (m.group(1), int(m.group(2))) if m else None


def validate_custom(field, value):
    """Error text for a field with a typed amount, or None when it is fine
    (also None for fields without "custom")."""
    custom = field.get("custom")
    if not custom:
        return None
    label = field.get("label") or "the amount"
    parsed = parse_amount(value)
    units = {u["value"]: u for u in custom.get("units", [])}
    if parsed is None or parsed[0] not in units:
        return f"{label}: enter a whole number"
    unit, number = parsed
    maximum = units[unit].get("max", 10 ** 6)
    if number < 1 or number > maximum:
        return f"{label}: {units[unit].get('label', unit)} must be from 1 to {maximum}"
    return None


def _per_row(labels):
    """How many option buttons fit on one line, by the longest label."""
    longest = max((len(l) for l in labels), default=0)
    return 3 if longest <= 10 else (2 if longest <= 20 else 1)


def _option_rows(nav, labels, on_press_for):
    """Lays option buttons out in rows, returns the buttons in order."""
    per_row = _per_row(labels)
    width = (common.content_width() - GAP * (per_row - 1)) / per_row
    buttons = []
    for start in range(0, len(labels), per_row):
        chunk = labels[start:start + per_row]
        height = max([BTN_H] + [common.wrapped_label_height(l, extra_padding=dp(18), width=width - dp(16)) for l in chunk])
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=height, spacing=GAP)
        for offset, label in enumerate(chunk):
            btn = Button(text=label, halign="center", valign="middle", background_color=OPTION_OFF)
            btn.text_size = (width - dp(16), None)
            btn.bind(on_press=on_press_for(start + offset))
            row.add_widget(btn)
            buttons.append(btn)
        nav.add(row)
    return buttons


def _mark(btn, selected):
    btn.bold = selected
    btn.background_color = OPTION_ON if selected else OPTION_OFF


def build_loading(nav):
    nav.clear()
    nav.add(Label(text="Loading available actions...", size_hint_y=None, height=60))
    nav.add(common.back_button(nav))


def build(nav, actions):
    nav.clear()
    nav.add(Label(text="Download Anything", size_hint_y=None, height=48))

    upload_btn = Button(text="Upload a file (any link)", size_hint_y=None, height=48)
    upload_btn.bind(on_press=lambda i: nav.show_upload_screen())
    nav.add(upload_btn)

    if not actions:
        nav.add(Label(text="No actions available right now.", size_hint_y=None, height=48))
    else:
        for action in actions:
            btn = Button(text=action.get("title", action.get("id", "?")),
                         size_hint_y=None, height=52)
            btn.bind(on_press=lambda instance, a=action: nav.show_action_input(a))
            nav.add(btn)

    nav.add(common.back_button(nav))


def _fields_for(action: dict) -> list:
    """Normalizes an action's input description into a list of field dicts,
    so build_input only ever has to deal with one shape. Old-style actions
    (just "input_hint") become a single implicit text field keyed "input",
    matching generic_action_service's "{input}" substitution."""
    fields = action.get("fields")
    if fields:
        return fields
    return [{
        "key": "input",
        "type": "text",
        "label": "",
        "hint": action.get("input_hint", "Enter a link"),
    }]


def _build_amount_field(nav, field, values):
    """Choices as quick buttons + a unit switch + a number box. The value is
    always "<unit>:<number>" and is kept in values[field key]."""
    key = field["key"]
    choices = field.get("choices", [])
    units = field["custom"]["units"]
    default = parse_amount(field.get("default") or (choices[0]["value"] if choices else ""))
    state = {"unit": default[0] if default else units[0]["value"],
             "number": str(default[1]) if default else ""}

    def current_value():
        return f"{state['unit']}:{state['number']}"

    preset_buttons, unit_buttons = [], []
    number_input = TextInput(text=state["number"], hint_text="How many", multiline=False,
                             input_filter="int", size_hint_y=None, height=BTN_H)

    def refresh():
        values[key] = current_value()
        for btn, choice in zip(preset_buttons, choices):
            _mark(btn, choice["value"] == current_value())
        for btn, unit in zip(unit_buttons, units):
            _mark(btn, unit["value"] == state["unit"])

    def preset_for(index):
        def _handler(instance):
            parsed = parse_amount(choices[index]["value"])
            if parsed:
                state["unit"], state["number"] = parsed[0], str(parsed[1])
                number_input.text = state["number"]
            refresh()
        return _handler

    def unit_for(index):
        def _handler(instance):
            state["unit"] = units[index]["value"]
            refresh()
        return _handler

    labels = [c.get("label", str(c.get("value"))) for c in choices]
    preset_buttons.extend(_option_rows(nav, labels, preset_for))

    unit_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
    for index, unit in enumerate(units):
        btn = Button(text=unit.get("label", unit["value"]), background_color=OPTION_OFF)
        btn.bind(on_press=unit_for(index))
        unit_row.add_widget(btn)
        unit_buttons.append(btn)
    nav.add(unit_row)

    def _on_number(instance, value):
        state["number"] = value.strip()
        refresh()

    number_input.bind(text=_on_number)
    nav.add(number_input)
    refresh()


def build_input(nav, action, prefill=None, share_url=None):
    """``prefill`` (a link shared into the app) goes into the first text
    field. ``share_url`` additionally shows a note and a "Choose another
    tool" button, for when the tool was picked automatically."""
    nav.clear()
    nav.add(Label(text=action.get("title", ""), size_hint_y=None, height=48))

    if share_url:
        nav.add(Label(text="Link received - tool chosen automatically",
                      size_hint_y=None, height=32))
        other_btn = Button(text="Choose another tool", size_hint_y=None, height=44)
        other_btn.bind(on_press=lambda i, u=share_url: nav.show_share_chooser(u))
        nav.add(other_btn)

    fields = _fields_for(action)
    # key -> current value, kept up to date as the user types/picks
    values = {}
    # key -> list of (button, choice_value) for choice fields, so we can
    # reset/highlight the selected one
    choice_buttons = {}
    prefill_pending = bool(prefill)

    for field in fields:
        key = field["key"]
        ftype = field.get("type", "text")
        label_text = field.get("label")

        if label_text:
            nav.add(Label(text=label_text, size_hint_y=None, height=28))

        if ftype == "choice" and field.get("custom"):
            _build_amount_field(nav, field, values)
        elif ftype == "choice":
            choices = field.get("choices", [])
            default = field.get("default", choices[0]["value"] if choices else None)
            values[key] = default
            buttons = []

            def _press_for(index, k=key, ch=choices, bs=buttons):
                def _handler(instance):
                    values[k] = ch[index]["value"]
                    for b2, c2 in zip(bs, ch):
                        _mark(b2, c2["value"] == values[k])
                return _handler

            labels = [c.get("label", str(c.get("value"))) for c in choices]
            buttons.extend(_option_rows(nav, labels, lambda i, f=_press_for: f(i)))
            for btn, choice in zip(buttons, choices):
                _mark(btn, choice["value"] == default)
            choice_buttons[key] = buttons
        else:
            hint = field.get("hint", "")
            text_input = TextInput(hint_text=hint, multiline=False,
                                    size_hint_y=None, height=48)

            def _on_text(instance, value, k=key):
                values[k] = value

            text_input.bind(text=_on_text)
            values[key] = ""
            if prefill_pending:
                text_input.text = prefill
                values[key] = prefill
                prefill_pending = False
            nav.add(text_input)

    start_btn = Button(text="Start", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.start_dynamic_action(action, values))
    nav.add(start_btn)

    nav.add(common.back_button(nav, text="Back"))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)
      
