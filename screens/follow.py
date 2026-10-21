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
                              "and adds new videos to one release per channel. The files of each channel are under "
                              "Release History (one button per channel)."))
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
    # The channel's files are in Release History (one button per channel, titled with its name).
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


# -- the form ---------------------------------------------------------------------------------------------------
# Simple first: the link, what to fetch, and Save. Everything else sits in
# folded sections (tap a title to open it) and only the options that fit the
# choices made so far are shown (series / latest, YouTube / Aparat, ...).
def _hint(text, color=(0.75, 0.8, 0.9, 1)):
    label = Label(text=text, size_hint_y=None, halign="left", valign="top", color=color)
    label.text_size = (common.content_width() - dp(8), None)
    label.height = common.wrapped_label_height(text, extra_padding=dp(8), width=common.content_width() - dp(8))
    return label


def _caption(text):
    return Label(text=text, size_hint_y=None, height=30, halign="left", color=(0.8, 0.85, 1, 1))


def build_form(nav, f, is_new, on_save, back):
    """Add / edit one channel. ``on_save(follow dict)`` gets the filled-in follow."""
    nav.clear()
    _title(nav, "Follow a channel" if is_new else f"Edit: {f.get('name', '')}")
    d = dict(f)                       # the draft: every widget writes here before a re-draw
    d["stop"] = dict(f.get("stop") or {})
    d["start_from"] = dict(f.get("start_from") or {"type": "now", "value": None})
    opened = {"when": False, "quality": False, "more": False}
    refs = {}                         # key -> widget of the current draw
    status = Label(text="", size_hint_y=None, height=48, color=(1, 0.6, 0.5, 1))
    status.text_size = (common.content_width(), None)

    body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=GAP)
    body.bind(minimum_height=body.setter("height"))

    def val(key, default=""):
        w = refs.get(key)
        return w.text if w is not None else default

    def sync():
        """Copies what is typed / picked into the draft (before every re-draw and on Save)."""
        if not refs:
            return
        d["url"] = fc.clean_url(val("url", d.get("url", "")))
        d["site"] = fc.site_of(d["url"])
        d["name"] = val("name", d.get("name", "")).strip()
        if "days" in refs:
            d["days"] = [n for n, b in refs["days"] if b.state == "down"]
        for key, name in (("start", "start"), ("end", "end")):
            if key in refs:
                d[name] = refs[key].text
        if "every" in refs:
            d["every_days"] = fc.to_int(refs["every"].text, 1)
        if "quality" in refs:
            d["quality"] = refs["quality"].text
        if "per_run" in refs:
            d["max_per_run"] = fc.to_int(refs["per_run"].text, 1)
        if "min" in refs:
            d["min_minutes"] = fc.to_int(refs["min"].text)
        if "max" in refs:
            d["max_minutes"] = fc.to_int(refs["max"].text)
        if "include" in refs:
            d["include"] = fc.words(refs["include"].text)
        if "exclude" in refs:
            d["exclude"] = fc.words(refs["exclude"].text)
        if "zip" in refs:
            d["zip"] = refs["zip"].text == "Yes"
        if "stop_ep" in refs:
            d["stop"]["episode"] = fc.to_int(refs["stop_ep"].text) or None
        if "stop_date" in refs:
            d["stop"]["date"] = refs["stop_date"].text.strip() or None
        if "stop_count" in refs:
            d["stop"]["count"] = fc.to_int(refs["stop_count"].text) or None
        # where to start
        if d.get("mode") == "series":
            if "from_ep" in refs:
                ep = refs["from_ep"].text.strip()
                d["start_from"] = {"type": "episode", "value": ep} if ep else {"type": "now", "value": None}
        else:
            kind = "now"
            if "first" in refs and refs["first"].text == FIRST_LAST_N:
                kind = "last_n"
            date = refs["from_date"].text.strip() if "from_date" in refs else ""
            if date:
                d["start_from"] = {"type": "date", "value": date}
            elif kind == "last_n":
                d["start_from"] = {"type": "last_n", "value": refs["last_n"].text.strip() if "last_n" in refs else ""}
            else:
                d["start_from"] = {"type": "now", "value": None}

    def put(widget_key, widget):
        refs[widget_key] = widget
        body.add_widget(widget)
        return widget

    def field(key, label, value="", hint="", numbers=False):
        body.add_widget(_caption(label))
        box = TextInput(text=str(value or ""), hint_text=hint, multiline=False, size_hint_y=None, height=FIELD_H,
                        **({"input_filter": "int"} if numbers else {}))
        return put(key, box)

    def pick(key, label, values, current):
        body.add_widget(_caption(label))
        return put(key, Spinner(text=str(current), values=values, size_hint_y=None, height=FIELD_H))

    def section(key, title, summary):
        btn = Button(text=f"{'-' if opened[key] else '+'}  {title}:  {summary}", size_hint_y=None, height=dp(54),
                     halign="left", valign="middle", background_color=(0.25, 0.3, 0.4, 1))
        btn.text_size = (common.content_width() - dp(16), None)

        def flip(_i):
            sync()
            opened[key] = not opened[key]
            render()
        btn.bind(on_press=flip)
        body.add_widget(btn)
        return opened[key]

    def choose_mode(mode):
        sync()
        if d.get("mode") != mode:
            d["mode"] = mode
            if mode == "series":              # sensible series defaults: one long episode a night
                if not d.get("min_minutes"):
                    d["min_minutes"] = 60
                if d.get("start") == "20:00":
                    d["start"] = "21:00"
                d["start_from"] = {"type": "now", "value": None}
            else:
                d["start_from"] = {"type": "now", "value": None}
        render()

    def render():
        sync()
        refs.clear()
        body.clear_widgets()
        site = d.get("site") or fc.site_of(d.get("url", ""))
        aparat = site == "aparat"
        if aparat:
            d["mode"] = "latest"
        series = d.get("mode") == "series"

        # 1. the channel
        field("url", "Channel link (YouTube or Aparat)", d.get("url", ""), "https://youtube.com/@channel")
        body.add_widget(paste_row(refs["url"]))
        shape = (site, fc.looks_like_video(d.get("url", "")))

        def url_changed(_inst, value):
            # Paste / typing: draw again only when the kind of link changed
            # (YouTube <-> Aparat, channel <-> one video), so the options fit it
            if (fc.site_of(value), fc.looks_like_video(value)) != shape:
                render()
        refs["url"].bind(text=url_changed)
        if fc.looks_like_video(d.get("url", "")):
            body.add_widget(_hint("This looks like the link of ONE video. Open the channel page and copy that link "
                                  "(youtube.com/@name).", (1, 0.7, 0.5, 1)))
        field("name", "Name (for the list and the release)", d.get("name", ""))

        # 2. what to fetch: two big choices, then only the questions that belong to the choice
        body.add_widget(_caption("What do you want?"))
        row = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(60), spacing=GAP)
        for label, mode in (("Series\n(next episode)", "series"), ("Latest\nvideos", "latest")):
            b = ToggleButton(text=label, group="mode", state="down" if d.get("mode") == mode else "normal",
                             allow_no_selection=False, halign="center",
                             disabled=(mode == "series" and aparat))
            b.bind(on_press=lambda i, m=mode: choose_mode(m))
            row.add_widget(b)
        body.add_widget(row)
        if series:
            body.add_widget(_hint("Gets one new episode at a time, by the number in the title (like 'episode 81'). "
                                  "Videos shorter than the limit below (clips, trailers) are skipped."))
            sf = d.get("start_from") or {}
            field("from_ep", "Start from episode number (empty = only new episodes from now on)",
                  sf.get("value") if sf.get("type") == "episode" else "", "75", numbers=True)
            field("min", "Ignore videos shorter than (minutes)", d.get("min_minutes") or "", "60", numbers=True)
        else:
            if aparat:
                body.add_widget(_hint("Aparat channels can be followed with 'Latest videos'."))
            pick("every", "Look for new videos every ... days", fc.EVERY_DAYS, d.get("every_days", 3))
            sf = d.get("start_from") or {}
            first_now = FIRST_LAST_N if sf.get("type") == "last_n" else FIRST_ONLY_NEW
            pick("first", "The first time", [FIRST_ONLY_NEW, FIRST_LAST_N], first_now)
            refs["first"].bind(text=lambda i, v: render())     # shows / hides the "how many" box
            if first_now == FIRST_LAST_N:
                field("last_n", "How many of the latest videos?", sf.get("value") or "", "3", numbers=True)

        # 3. when
        if section("when", "When to check", f"{fc.days_text(d)}, {d.get('start')}-{d.get('end')} (Iran time)"):
            body.add_widget(_hint("Days: none picked = every day."))
            drow = BoxLayout(orientation="horizontal", size_hint_y=None, height=FIELD_H, spacing=GAP)
            toggles = []
            for label, num in fc.WEEK_BUTTONS:
                b = ToggleButton(text=label, state="down" if num in (d.get("days") or []) else "normal")
                toggles.append((num, b))
                drow.add_widget(b)
            refs["days"] = toggles
            body.add_widget(drow)
            pick("start", "From", fc.HOURS, d.get("start", "20:00"))
            pick("end", "Until", fc.HOURS, d.get("end", "23:59"))

        # 4. quality and amount
        if section("quality", "Quality and amount", f"{d.get('quality', 'best')}, {d.get('max_per_run', 1)} per check"):
            pick("quality", "Quality", fc.QUALITIES, d.get("quality", "best"))
            pick("per_run", "Most videos started per check", fc.PER_RUN, d.get("max_per_run", 1))
            if aparat:
                pick("zip", "Put every check's videos in one zip file", ["No", "Yes"], "Yes" if d.get("zip") else "No")

        # 5. everything else
        more_bits = []
        if d.get("include") or d.get("exclude"):
            more_bits.append("title words")
        if any((d.get("stop") or {}).values()):
            more_bits.append("stop rule")
        if section("more", "More options", ", ".join(more_bits) or "filters, stop rules"):
            if not aparat and not series:
                field("min", "Ignore videos shorter than (minutes)", d.get("min_minutes") or "", "0", numbers=True)
            if not aparat:
                field("max", "Ignore videos longer than (minutes)", d.get("max_minutes") or "", "0", numbers=True)
            field("include", "Title must contain one of these words (comma separated)",
                  ", ".join(d.get("include") or []))
            field("exclude", "Title must NOT contain (comma separated)", ", ".join(d.get("exclude") or []))
            if not series:
                sf = d.get("start_from") or {}
                field("from_date", "Only videos uploaded since this date (2026-10-19)",
                      sf.get("value") if sf.get("type") == "date" else "")
            body.add_widget(_hint("Stop automatically (all optional):"))
            stop = d.get("stop") or {}
            if series:
                field("stop_ep", "After this episode number", stop.get("episode") or "", "", numbers=True)
            field("stop_date", "After this date (2026-12-31)", stop.get("date") or "")
            field("stop_count", "After this many videos", stop.get("count") or "", "", numbers=True)

    def save(_i):
        sync()
        out = dict(d)
        out["name"] = out.get("name") or fc.name_from_url(out.get("url", ""))
        if is_new:
            out["slug"] = f["slug"]
        problem = fc.validate(out)
        if problem:
            status.text = problem
            return
        on_save(out)

    render()
    nav.add(body)
    nav.add(status)
    save_btn = Button(text="Save", size_hint_y=None, height=BTN_H)
    save_btn.bind(on_press=save)
    nav.add(save_btn)
    nav.add(back_button(nav, to=back))


FIRST_ONLY_NEW = "Only new videos from now on"
FIRST_LAST_N = "Also take the latest few"
