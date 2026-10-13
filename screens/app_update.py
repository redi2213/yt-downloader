"""Settings > Update: the confirmation screens.

* ``build_zip_confirm``  - a zip with main/ and config/ folders (as before).
* ``build_review``       - loose files: one summary with tick boxes for the
  files whose place is certain, and a card for each file that needs a
  decision (similar name, same name in several folders, brand new file).
* ``build_folder_picker``- choose the folder of a new file.

The plan (list of dicts from core/file_router.py) is edited in place by the
buttons; "Update" hands it to the service.
"""
from itertools import count

from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from core import file_router as fr
from core import zip_tools
from screens import common
from services import repo_update_service

_builds = count(1)  # makes toggle-group names unique for every drawn screen
MAX_CANDIDATES_SHOWN = 8


def _label(nav, text, height):
    label = Label(text=text, size_hint_y=None, height=height, halign="center", valign="middle")
    label.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
    nav.add(label)


def build_zip_confirm(nav, data):
    nav.clear()
    try:
        summary = repo_update_service.summarize_zip(data)
    except zip_tools.ZipError as e:
        nav.show_result(str(e))
        return
    nav.add(Label(text="Update from zip", size_hint_y=None, height=44))
    lines = "\n".join(f"{branch}: {count_} file(s)" for branch, count_ in sorted(summary.items()))
    _label(nav, lines, 40 + 28 * len(summary))
    _label(nav, "Only changed files are uploaded, one commit per branch. A backup of the "
                "branch is saved first (not for config; last 5 kept). Folders missing "
                "from the zip are left untouched.", 150)
    go = Button(text="Update", size_hint_y=None, height=56)
    go.bind(on_press=lambda i: nav.start_repo_update(data))
    nav.add(go)
    cancel = Button(text="Cancel", size_hint_y=None, height=48)
    cancel.bind(on_press=lambda i: nav.show_settings())
    nav.add(cancel)


# -- small helpers ---------------------------------------------------------
def _where(ref) -> str:
    branch, path = ref
    return path if branch == fr.MAIN_BRANCH else f"{branch}: {path}"


def _folder_text(folder: str) -> str:
    return (folder + "/") if folder else "project root"


def _stats_text(item, ref) -> str:
    if ref not in item["stats"]:
        return " (new file)" if item.get("creates") and ref == item["choice"] else ""
    stats = item["stats"][ref]
    if stats is None:
        return " (binary or large)"
    added, removed = stats
    if not added and not removed:
        return " (only spaces / line endings differ)"
    return f" (+{added} -{removed})"


def _toggle(text, down, group=None):
    btn = ToggleButton(
        text=text, size_hint_y=None, height=common.BTN_H, group=group,
        allow_no_selection=group is None, state="down" if down else "normal",
        halign="left", valign="middle",
    )
    btn.text_size = (common.content_width() - dp(16), None)
    return btn


def _button(text, on_press):
    btn = Button(text=text, size_hint_y=None, height=common.SMALL_BTN_H)
    btn.bind(on_press=lambda i: on_press())
    return btn


def _choose(item, ref):
    item["choice"], item["skip"] = ref, False


def _skip(item):
    item["choice"], item["skip"] = None, True


# -- the review screen -----------------------------------------------------
def build_review(nav, plan, folders, skipped=()):
    nav.clear()
    build_id = next(_builds)

    def redraw():
        build_review(nav, plan, folders, skipped)

    nav.add(Label(text="Update files", size_hint_y=None, height=44))
    nav.add(common.wrapped_label(
        "Untick a file to leave it out. Only changed files are uploaded, one commit per "
        "branch; the branch is backed up first (not config)."))

    matched = [it for it in plan if it["status"] == fr.EXACT]
    unchanged = [it for it in plan if it["status"] == fr.SAME]
    undecided = [it for it in plan if it["status"] in fr.NEEDS_CHOICE]

    refresh_refs = {}

    def refresh(*_args):
        pend = fr.pending(plan)
        problem = fr.conflicts(plan)
        total = sum(1 for it in plan if fr.included(it))
        apply_btn, info = refresh_refs["apply"], refresh_refs["info"]
        apply_btn.disabled = bool(pend or problem or not total)
        apply_btn.text = f"Update {total} file(s)"
        if problem:
            info.text = problem
        elif pend:
            info.text = f"{pend} file(s) below still need a choice."
        elif not total:
            info.text = "Nothing is selected."
        else:
            info.text = ""

    # 1. files whose place is certain: one list with tick boxes
    if matched:
        nav.add(Label(text=f"Will replace ({len(matched)})", size_hint_y=None, height=32))
        for it in matched:
            ref = it["choice"]

            def line(item=it):
                mark = "[x]" if item["selected"] else "[ ]"
                return f"{mark} {_where(item['choice'])}{_stats_text(item, item['choice'])}"

            btn = _toggle(line(), it["selected"])

            def on_state(button, state, item=it, line=line):
                item["selected"] = state == "down"
                button.text = line()
                refresh()

            btn.bind(state=on_state)
            nav.add(btn)

    # 2. identical files: nothing to do
    if unchanged:
        names = ", ".join(_where(it["choice"]) for it in unchanged)
        nav.add(common.wrapped_label(f"Same as the repo, nothing to do ({len(unchanged)}): {names}"))

    if skipped:
        nav.add(common.wrapped_label("Ignored (not sent to the repo): " + ", ".join(skipped)))

    # 3. files that need a decision
    for n, it in enumerate(undecided):
        group = f"upd{build_id}_{n}"
        _decision_card(nav, it, group, folders, refresh, redraw, plan, skipped)

    refresh_refs["info"] = Label(text="", size_hint_y=None, height=common.line_height(2) + 12,
                                 halign="center", valign="middle", color=(1, 0.75, 0.4, 1))
    refresh_refs["info"].bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
    nav.add(refresh_refs["info"])

    apply_btn = Button(text="Update", size_hint_y=None, height=56)
    apply_btn.bind(on_press=lambda i: nav.start_apply_update(plan))
    refresh_refs["apply"] = apply_btn
    nav.add(apply_btn)

    cancel = Button(text="Cancel", size_hint_y=None, height=48)
    cancel.bind(on_press=lambda i: nav.show_settings())
    nav.add(cancel)
    refresh()


def _decision_card(nav, item, group, folders, refresh, redraw, plan, skipped):
    name = item["name"]
    status = item["status"]
    if status == fr.SIMILAR:
        text = f'"{name}" is not in the repo, but it looks like:'
    elif status == fr.AMBIGUOUS:
        text = f'"{name}" exists in several places. Which one?'
    else:
        text = f'"{name}" is a new file. Where should it go?'
    nav.add(common.wrapped_label(text))

    def bind_choice(btn, ref):
        def on_state(button, state):
            if state == "down":
                _choose(item, ref)
                refresh()
        btn.bind(state=on_state)

    if status in (fr.SIMILAR, fr.AMBIGUOUS):
        for ref in item["candidates"][:MAX_CANDIDATES_SHOWN]:
            btn = _toggle(f"Replace {_where(ref)}{_stats_text(item, ref)}",
                          item["choice"] == ref and not item["skip"], group)
            bind_choice(btn, ref)
            nav.add(btn)
        nav.add(_button("It is a new file...", lambda: _make_new(item, redraw)))
    else:
        shown = list(item["folder_suggestions"])
        chosen_folder = None
        if item["choice"] is not None and not item["skip"]:
            chosen_folder = item["choice"][1].rsplit("/", 1)[0] if "/" in item["choice"][1] else ""
            if chosen_folder not in shown:
                shown.append(chosen_folder)
        if "" not in shown:
            shown.append("")
        for folder in shown:
            ref = (fr.MAIN_BRANCH, fr.join_path(folder, item["base"]))
            btn = _toggle(f"Put in {_folder_text(folder)}", item["choice"] == ref and not item["skip"], group)
            bind_choice(btn, ref)
            nav.add(btn)
        nav.add(_button("Other folder...",
                        lambda: build_folder_picker(nav, plan, folders, item, skipped)))

    skip_btn = _toggle("Skip this file", item["skip"], group)

    def on_skip(button, state):
        if state == "down":
            _skip(item)
            refresh()

    skip_btn.bind(state=on_skip)
    nav.add(skip_btn)


def _make_new(item, redraw):
    """The user says a 'similar' file is actually new: ask for a folder."""
    item["status"] = fr.NEW
    item["candidates"] = []
    item["choice"], item["skip"] = None, False
    redraw()


# -- folder picker for a new file ------------------------------------------
def _clean_folder(text: str):
    folder = text.replace("\\", "/").strip().strip("/")
    parts = [p for p in folder.split("/") if p]
    if not parts or any(p in ("..", ".git") for p in parts):
        return None
    return "/".join(parts)


def build_folder_picker(nav, plan, folders, item, skipped=()):
    nav.clear()

    def back():
        build_review(nav, plan, folders, skipped)

    def pick(folder):
        _choose(item, (fr.MAIN_BRANCH, fr.join_path(folder, item["base"])))
        back()

    nav.add(common.wrapped_label(f'Where should "{item["base"]}" go?'))
    for folder in [""] + [f for f in folders if f]:
        nav.add(_button(_folder_text(folder), lambda f=folder: pick(f)))

    message = Label(text="", size_hint_y=None, height=common.line_height(1) + 12,
                    color=(1, 0.75, 0.4, 1))
    box = TextInput(hint_text="or a new folder, e.g. tools/helpers", multiline=False,
                    size_hint_y=None, height=48)
    nav.add(box)

    def use_new():
        folder = _clean_folder(box.text)
        if folder is None:
            message.text = "Type a folder name (no ..)."
            return
        pick(folder)

    nav.add(_button("Use this new folder", use_new))
    nav.add(message)
    nav.add(common.back_button(nav, to=back))
