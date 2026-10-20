"""Auto follow screens: the list of followed channels, one channel's page, and
the add / edit form. Widgets only - saving and loading are in
services/follow_service.py and the navigator.
"""
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.togglebutton import ToggleButton

from core import follow as fc
from screens import common
from screens.common import BTN_H, GAP, back_button, paste_row, wrapped_label

FIELD_H = 46


def _title(nav, text):
    nav.add(Label(text=text, size_hint_y=None, height=44))


def build_loading(nav, back):
    nav.clear()
    _title(nav, "Auto follow")
    nav.add(Label(text="Loading...", size_hint_y=None, height=40))
    nav.add(back_button(nav, to=back))


def build_list(nav, res, back, on_add, on_open, on_check_all, on_sync):
    nav.clear()
    _title(nav, "Auto follow")
    if not res.get("ok"):
        nav.add(wrapped_label(res.get("error", "Could not load.")))
    else:
        follows, state, new = res["follows"], res["state"], res.get("new", {})
        nav.add(wrapped_label("The app checks the channels you follow on a schedule (even when it is closed) "
                              "and adds new videos to one release per channel. They are not in Release History."))
        add = Button(text="+ Follow a channel", size_hint_y=None, height=BTN_H)
        add.bind(on_press=lambda i: on_add())
        nav.add(add)
        for f in follows:
            st = state.get(f["id"], {})
            badge = f"   [NEW {new[f['id']]}]" if new.get(f["id"]) else ""
            text = f"{f.get('name', '?')}{badge}\n{fc.summary_text(f, st)}"
            btn = Button(text=text, size_hint_y=None, height=dp(72), halign="center")
            btn.text_size = (common.content_width() - dp(16), None)
            btn.bind(on_press=lambda i, f=f: on_open(f))
            nav.add(btn)
        if not follows:
            nav.add(Label(text="No channels yet.", size_hint_y=None, height=40))
        else:
            check = Button(text="Check all channels now", size_hint_y=None, height=BTN_H)
            check.bind(on_press=lambda i: on_check_all())
            nav.add(check)
            sync = Button(text="Update schedule", size_hint_y=None, height=BTN_H)
            sync.bind(on_press=lambda i: on_sync())
            nav.add(sync)
    nav.add(back_button(nav, to=back))


def build_detail(nav, f, st, new_count, back, on_files, on_check, on_toggle, on_edit, on_delete):
    nav.clear()
    _title(nav, f.get("name", "Channel"))
    nav.add(wrapped_label(f"{f.get('url', '')}\n\n{fc.status_text(f, st)}\n\nFiles go to the release: {fc.release_tag(f)}"))
    files = Button(text="Files" + (f"  (NEW {new_count})" if new_count else ""), size_hint_y=None, height=BTN_H)
    files.bind(on_press=lambda i: on_files())
    nav.add(files)
    check = Button(text="Check now (ignores the time window)", size_hint_y=None, height=BTN_H)
    check.bind(on_press=lambda i: on_check())
    nav.add(check)
    toggle = Button(text="Pause" if f.get("enabled", True) else "Resume", size_hint_y=None, height=BTN_H)
    toggle.bind(on_press=lambda i: on_toggle())
    nav.add(toggle)
    edit = Button(text="Edit", size_hint_y=None, height=BTN_H)
    edit.bind(on_press=lambda i: on_edit())
    nav.add(edit)
    delete = Button(text="Delete this channel", size_hint_y=None, height=BTN_H)
    armed = {"on": False}

    def press(_i):
        if armed["on"]:
            on_delete()
        else:
            armed["on"] = True
            delete.text = "Press again to delete (the files stay in the release)"
    delete.bind(on_press=press)
    nav.add(delete)
    nav.add(back_button(nav, to=back))


# -- the form -----------------------------------------------------------------------------------------------
def _label(nav, text):
    nav.add(Label(text=text, size_hint_y=None, height=30, halign="left", color=(0.8, 0.85, 1, 1)))


def _text(nav, label, value="", hint=""):
    _label(nav, label)
    box = TextInput(text=str(value or ""), hint_text=hint, multiline=False, size_hint_y=None, height=FIELD_H)
    nav.add(box)
    return box


def _spinner(nav, label, values, current):
    _label(nav, label)
    sp = Spinner(text=current, values=values, size_hint_y=None, height=FIELD_H)
    nav.add(sp)
    return sp


def build_form(nav, f, is_new, on_save, back):
    """Add / edit one channel. ``on_save(follow dict)`` gets the filled-in follow."""
    nav.clear()
    _title(nav, "Follow a channel" if is_new else f"Edit: {f.get('name', '')}")
    status = Label(text="", size_hint_y=None, height=40, color=(1, 0.6, 0.5, 1))

    url = _text(nav, "Channel link (YouTube or Aparat)", f.get("url", ""), "https://youtube.com/@channel")
    nav.add(paste_row(url))
    name = _text(nav, "Name (used for the release and the list)", f.get("name", ""))

    mode_labels = [m[0] for m in fc.MODES]
    mode_now = next((l for l, v in fc.MODES if v == f.get("mode")), mode_labels[1])
    mode = _spinner(nav, "What to fetch", mode_labels, mode_now)

    _label(nav, "Days to check (none picked = every day)")
    days_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=FIELD_H, spacing=GAP)
    day_buttons = []
    for label, num in fc.WEEK_BUTTONS:
        b = ToggleButton(text=label, state="down" if num in (f.get("days") or []) else "normal")
        day_buttons.append((num, b))
        days_row.add_widget(b)
    nav.add(days_row)

    start = _spinner(nav, "Check from (Iran time)", fc.HOURS, f.get("start", "20:00"))
    end = _spinner(nav, "Check until (Iran time)", fc.HOURS, f.get("end", "23:59"))
    every = _spinner(nav, "Latest videos: look at most every ... days", fc.EVERY_DAYS, str(f.get("every_days", 3)))
    quality = _spinner(nav, "Quality", fc.QUALITIES, f.get("quality", "best"))
    per_run = _spinner(nav, "Most videos started per check", fc.PER_RUN, str(f.get("max_per_run", 1)))

    nav.add(Label(text="Filters", size_hint_y=None, height=34))
    min_m = _text(nav, "YouTube: shortest video (minutes, 0 = any)", f.get("min_minutes") or "", "60")
    max_m = _text(nav, "YouTube: longest video (minutes, 0 = any)", f.get("max_minutes") or "", "")
    include = _text(nav, "Title must contain one of (comma separated)", ", ".join(f.get("include") or []), "")
    exclude = _text(nav, "Title must NOT contain (comma separated)", ", ".join(f.get("exclude") or []), "")

    nav.add(Label(text="Where to start", size_hint_y=None, height=34))
    sf = f.get("start_from") or {"type": "now", "value": None}
    from_labels = [t[0] for t in fc.FROM_TYPES]
    from_now = next((l for l, v in fc.FROM_TYPES if v == sf.get("type")), from_labels[0])
    start_from = _spinner(nav, "Start", from_labels, from_now)
    start_value = _text(nav, "Episode number / date (2026-10-19) / how many videos", sf.get("value") or "", "")

    nav.add(Label(text="Stop automatically (all optional)", size_hint_y=None, height=34))
    stop = f.get("stop") or {}
    stop_ep = _text(nav, "After this episode number", stop.get("episode") or "", "")
    stop_date = _text(nav, "After this date (2026-12-31)", stop.get("date") or "", "")
    stop_count = _text(nav, "After this many videos", stop.get("count") or "", "")

    zip_sp = _spinner(nav, "Aparat: zip every check into one file", ["No", "Yes"], "Yes" if f.get("zip") else "No")
    nav.add(wrapped_label("YouTube files over 2 GB are cut into playable parts (part1, part2). "
                          "Aparat can only be followed in the 'Latest videos' way."))

    def save(_i):
        out = dict(f)
        out["url"] = fc.clean_url(url.text)
        out["site"] = fc.site_of(out["url"])
        out["name"] = name.text.strip() or fc.name_from_url(out["url"])
        out["mode"] = next((v for l, v in fc.MODES if l == mode.text), "latest")
        out["days"] = [n for n, b in day_buttons if b.state == "down"]
        out["start"], out["end"] = start.text, end.text
        out["every_days"] = fc.to_int(every.text, 1)
        out["quality"] = quality.text
        out["max_per_run"] = fc.to_int(per_run.text, 1)
        out["min_minutes"], out["max_minutes"] = fc.to_int(min_m.text), fc.to_int(max_m.text)
        out["include"], out["exclude"] = fc.words(include.text), fc.words(exclude.text)
        kind = next((v for l, v in fc.FROM_TYPES if l == start_from.text), "now")
        out["start_from"] = {"type": kind, "value": start_value.text.strip() or None}
        out["stop"] = {"episode": fc.to_int(stop_ep.text) or None, "date": stop_date.text.strip() or None,
                       "count": fc.to_int(stop_count.text) or None}
        out["zip"] = zip_sp.text == "Yes"
        if is_new:
            out["slug"] = f["slug"]
        problem = fc.validate(out)
        if problem:
            status.text = problem
            return
        on_save(out)

    save_btn = Button(text="Save", size_hint_y=None, height=BTN_H)
    save_btn.bind(on_press=save)
    nav.add(status)
    nav.add(save_btn)
    nav.add(back_button(nav, to=back))
