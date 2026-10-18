"""Finding any run of the repo: the screens behind "Runs by workflow" and
"Runs by app menu" in Latest GitHub Actions runs.

* ``build_workflows``  - every workflow file of the repo (also those with no
  button in the app); a tap opens that workflow's runs.
* ``build_groups``     - the app's menus (YouTube, Aparat, ...); a tap opens the
  group's workflows (a group with one workflow opens its runs directly).
* ``build_runs``       - one workflow's runs, newest first, Previous / Next.
* ``build_manual_run`` - run a workflow by hand: one box, ``name=value`` lines.
"""
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.metrics import dp

from screens import actions_status, common
from screens.common import BTN_H, GAP


def build_loading(nav, title, back):
    nav.clear()
    nav.add(Label(text=title, size_hint_y=None, height=44))
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))
    nav.add(common.back_button(nav, to=back))


def _workflow_button(nav, wf, on_open):
    text = wf["tool"] if wf["tool"] == wf["file"] else f"{wf['tool']}\n{wf['file']}"
    btn = Button(text=text, size_hint_y=None, height=56, halign="center", valign="middle")
    btn.text_size = (common.content_width() - dp(16), None)
    btn.bind(on_press=lambda i, w=wf: on_open(w))
    nav.add(btn)


def build_workflows(nav, title, workflows, on_open, back):
    nav.clear()
    nav.add(Label(text=title, size_hint_y=None, height=44))
    if not workflows:
        nav.add(Label(text="No workflows found", size_hint_y=None, height=40))
    for wf in workflows:
        _workflow_button(nav, wf, on_open)
    nav.add(common.back_button(nav, to=back))


def build_groups(nav, groups, on_open, back):
    """``groups``: [(title, [workflow dicts])]."""
    nav.clear()
    nav.add(Label(text="Runs by app menu", size_hint_y=None, height=44))
    if not groups:
        nav.add(Label(text="No workflows found", size_hint_y=None, height=40))
    for title, workflows in groups:
        btn = Button(text=f"{title} ({len(workflows)})", size_hint_y=None, height=56)
        btn.bind(on_press=lambda i, t=title, w=workflows: on_open(t, w))
        nav.add(btn)
    nav.add(common.back_button(nav, to=back))


def build_runs(nav, wf, res, page, on_page, on_manual, on_refresh, back):
    """One page of a workflow's runs. ``res`` is the runs_service result."""
    nav.clear()
    nav.add(Label(text=wf["tool"] + (f"\n{wf['file']}" if wf["tool"] != wf["file"] else ""),
                  size_hint_y=None, height=60 if wf["tool"] != wf["file"] else 40))
    if not res.get("ok"):
        nav.add(common.wrapped_label(res.get("error", "Could not load the runs")))
    else:
        runs = res["runs"]
        if not runs:
            nav.add(Label(text="No runs yet", size_hint_y=None, height=40))
        actions_status.add_run_rows(nav, runs, origin="wf")
        if page > 1 or res.get("has_next"):
            row = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
            prev_btn = Button(text="Previous", disabled=page <= 1)
            prev_btn.bind(on_press=lambda i: on_page(page - 1))
            next_btn = Button(text="Next", disabled=not res.get("has_next"))
            next_btn.bind(on_press=lambda i: on_page(page + 1))
            row.add_widget(prev_btn)
            row.add_widget(next_btn)
            nav.add(row)
            nav.add(Label(text=f"Page {page}", size_hint_y=None, height=32))
    manual_btn = Button(text="Run this workflow by hand", size_hint_y=None, height=52)
    manual_btn.bind(on_press=lambda i: on_manual())
    nav.add(manual_btn)
    refresh_btn = Button(text="Refresh", size_hint_y=None, height=48)
    refresh_btn.bind(on_press=lambda i: on_refresh())
    nav.add(refresh_btn)
    nav.add(common.back_button(nav, to=back))


def build_manual_run(nav, wf, on_run, back, text="", message=""):
    """``on_run(text)``: called with the box content when Run is pressed."""
    nav.clear()
    nav.add(Label(text=f"Run {wf['tool']}", size_hint_y=None, height=44))
    nav.add(common.wrapped_label(
        "Type the inputs of the workflow, one per line, like:\nurl=https://...\nquality=720\n"
        "Leave the box empty for a workflow without inputs. It runs on the app's branch."))
    box = TextInput(text=text, hint_text="name=value", multiline=True, size_hint_y=None, height=dp(160))
    nav.add(box)
    nav.add(common.paste_row(box, append=True))
    info = Label(text=message, size_hint_y=None, height=40, color=(1, 0.75, 0.4, 1))
    run_btn = Button(text="Run", size_hint_y=None, height=56)
    run_btn.bind(on_press=lambda i: on_run(box.text))
    nav.add(run_btn)
    nav.add(info)
    nav.add(common.back_button(nav, to=back))
    nav.set_status_label(info)
