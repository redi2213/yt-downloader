from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label

from screens.common import (
    BTN_H, CARD, GAP, back_button, card_box, content_width, paint_card,
    wrapped_label_height,
)
from core.models.job import JOB_TYPE_PLAYLIST_DOWNLOAD, JOB_TYPE_FORMATS, JOB_TYPE_PLAYLIST_LINKS


def build(nav):
    nav.clear()
    history = nav.job_manager.history
    nav.add(Label(text=f"Recent jobs ({len(history)})", size_hint_y=None, height=40))
    if not history:
        nav.add(Label(text="No jobs yet", size_hint_y=None, height=40))

    inner_width = content_width() - 2 * dp(8)

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
        kind_height = wrapped_label_height(kind_text, extra_padding=dp(8), width=inner_width)
        outcome_height = wrapped_label_height(outcome, extra_padding=dp(8), width=inner_width)

        row = card_box([kind_height, outcome_height, BTN_H])
        paint_card(row, CARD)
        kind_label = Label(text=kind_text, size_hint_y=None, height=kind_height,
                            halign="left", valign="middle", text_size=(inner_width, None))
        outcome_label = Label(text=outcome, size_hint_y=None, height=outcome_height,
                               halign="left", valign="middle", text_size=(inner_width, None))
        row.add_widget(kind_label)
        row.add_widget(outcome_label)
        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=BTN_H, spacing=GAP)
        view_btn = Button(text="View")
        view_btn.bind(on_press=lambda i, j=job: nav.view_job_from_history(j))
        buttons.add_widget(view_btn)
        if job.run_id:
            github_btn = Button(text="GitHub", size_hint_x=0.35)
            github_btn.bind(on_press=lambda i, j=job: nav.open_job_on_github(j))
            buttons.add_widget(github_btn)
        row.add_widget(buttons)
        nav.add(row)

    nav.add(back_button(nav))
