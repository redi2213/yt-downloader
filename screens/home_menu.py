"""The global Home drop-down: the \"Home\" button (top bar of every screen, and the browser Menu)
opens a list of the main entries of the first screen, so any screen is two taps from anywhere.
When the Home screen gets a new main button, add it to ``_entries`` too."""
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.button import Button
from kivy.uix.dropdown import DropDown

_ROW_H = dp(48)


def _entries(nav):
    items = []
    running = nav.job_manager.active_jobs
    if running:
        items.append((f"Running jobs ({len(running)})", nav.show_running_jobs))
    items += [
        ("Home", nav.show_home),
        ("YouTube Download", nav.show_youtube_download),
        ("Download Anything", nav.show_dynamic_actions),
    ]
    try:
        from screens import lab
        items.append(("Lab (test tools)", lambda: lab.show(nav)))
    except ImportError:
        pass
    items += [
        ("Browser", nav.show_browser),
        ("Auto follow", nav.show_follow_menu),
        ("Downloads", nav.show_downloads),
        ("Release History", nav.show_release_history),
        ("Check GitHub Actions status", nav.show_actions_status),
        ("Settings", nav.show_settings),
    ]
    return items


def open(nav, anchor):
    """Opens the drop-down right under ``anchor`` (any widget)."""
    dd = DropDown(auto_width=False, width=max(anchor.width, dp(260)), max_height=Window.height * 0.7)

    def go(fn):
        dd.dismiss()
        Clock.schedule_once(lambda dt: fn(), 0.05)

    for text, fn in _entries(nav):
        btn = Button(text=text, size_hint_y=None, height=_ROW_H)
        btn.bind(on_release=lambda b, f=fn: go(f))
        dd.add_widget(btn)
    dd.open(anchor)
