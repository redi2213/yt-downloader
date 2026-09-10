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


def build_input(nav, action):
    nav.clear()
    nav.add(Label(text=action.get("title", ""), size_hint_y=None, height=48))

    fields = _fields_for(action)
    # key -> current value, kept up to date as the user types/picks
    values = {}
    # key -> list of (button, choice_value) for choice fields, so we can
    # reset/highlight the selected one
    choice_buttons = {}

    for field in fields:
        key = field["key"]
        ftype = field.get("type", "text")
        label_text = field.get("label")

        if label_text:
            nav.add(Label(text=label_text, size_hint_y=None, height=28))

        if ftype == "choice":
            choices = field.get("choices", [])
            default = field.get("default", choices[0]["value"] if choices else None)
            values[key] = default
            row_buttons = []
            for choice in choices:
                btn = Button(text=choice.get("label", str(choice.get("value"))),
                             size_hint_y=None, height=48)

                def _on_choice(instance, k=key, v=choice["value"], buttons=row_buttons):
                    values[k] = v
                    for b in buttons:
                        b.bold = (b is instance)

                btn.bind(on_press=_on_choice)
                btn.bold = (choice["value"] == default)
                nav.add(btn)
                row_buttons.append(btn)
            choice_buttons[key] = row_buttons
        else:
            hint = field.get("hint", "")
            text_input = TextInput(hint_text=hint, multiline=False,
                                    size_hint_y=None, height=48)

            def _on_text(instance, value, k=key):
                values[k] = value

            text_input.bind(text=_on_text)
            values[key] = ""
            nav.add(text_input)

    start_btn = Button(text="Start", size_hint_y=None, height=56)
    start_btn.bind(on_press=lambda i: nav.start_dynamic_action(action, values))
    nav.add(start_btn)

    nav.add(common.back_button(nav, text="Back"))

    status_label = Label(text="", size_hint_y=None, height=40)
    nav.add(status_label)
    nav.set_status_label(status_label)
      
