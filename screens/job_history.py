from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import back_button, content_width
from core.models.job import JOB_TYPE_PLAYLIST_DOWNLOAD, JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS


def build(nav):
    nav.clear()
    history = nav.job_manager.history
    nav.add(Label(text=f"Recent jobs ({len(history)})", size_hint_y=None, height=40))
    if not history:
        nav.add(Label(text="No jobs yet", size_hint_y=None, height=40))

    width = content_width()
    chars_per_line = max(10, int(width / 15))

    for job in history:
        kind = job.type or "?"
        result = job.result or {}
        if result.get("ok"):
            if kind == JOB_TYPE_PLAYLIST_DOWNLOAD:
                n_ok = len(result.get("playlist_results") or [])
                n_err = len(result.get("playlist_errors") or [])
                outcome = f"{n_ok} ready, {n_err} failed"
            elif kind in (JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS):
                outcome = "Ready to pick quality"
            else:
                outcome = "Ready"
        else:
            outcome = result.get("error", "Unknown error")

        label_text = job.input or "(upload)"
        if len(label_text) > 45:
            label_text = label_text[:42] + "..."

        kind_text = f"[{kind}] {label_text}"
        kind_lines = max(1, (len(kind_text) + chars_per_line - 1) // chars_per_line)
        kind_height = kind_lines * 40 + 12
        outcome_lines = max(1, (len(outcome) + chars_per_line - 1) // chars_per_line)
        outcome_height = outcome_lines * 40 + 12
        row_height = kind_height + outcome_height + 40 + 6

        row = BoxLayout(orientation="vertical", size_hint_y=None, height=row_height, spacing=2, padding=(0, 4))
        kind_label = Label(text=kind_text, size_hint_y=None, height=kind_height,
                            halign="left", valign="top", text_size=(width, None))
        outcome_label = Label(text=outcome, size_hint_y=None, height=outcome_height,
                               halign="left", valign="top", text_size=(width, None))
        row.add_widget(kind_label)
        row.add_widget(outcome_label)
        view_btn = Button(text="View", size_hint_y=None, height=40)
        view_btn.bind(on_press=lambda i, j=job: nav.view_job_from_history(j))
        row.add_widget(view_btn)
        nav.add(row)

    nav.add(back_button(nav))
