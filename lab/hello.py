"""Lab example. Edit this file on GitHub (lab branch, lab/hello.py), then
open it again from the Lab (or tap "Try again"): no build needed."""


def build(host):
    host.title("Hello Lab")
    host.text("This screen comes from lab/hello.py. Every button below opens "
              "another screen of the same plugin.")
    host.button("Sub-menu", lambda: host.show(sub_menu))
    host.button("Input and choice", lambda: host.show(form))
    host.button("Ask GitHub for a quote (background HTTP)", lambda: host.show(quote))
    host.button("Saved counter", lambda: host.show(counter))
    host.button("Copy log", lambda: _copy_log(host))
    host.status()
    host.back_button("Back")            # leaves the plugin


def sub_menu(host):
    host.title("Sub-menu")
    host.button("Go deeper", lambda: host.show(deeper))
    host.button("Back to the first screen", host.home)
    host.back_button()


def deeper(host):
    host.title("Deeper")
    host.text("Back returns one step; the phone's Back key does the same.")
    host.back_button()


def form(host):
    host.title("Input and choice")
    field = host.input("Type something")
    mode = host.choice(["Fast", "Normal", "Slow"], default="Normal")
    host.status()

    def go():
        host.log("form:", field.text, mode.value)
        host.set_status(f"{field.text or '(empty)'} / {mode.value}")

    host.button("Use these", go)
    host.back_button()


def quote(host):
    host.title("Background HTTP")
    host.text("Plain HTTP; the GitHub token is never sent by host.get.")
    host.status()
    host.set_status("Asking...")

    def work():
        return host.get("https://api.github.com/zen").text

    def done(result, error):
        host.set_status(f"Failed: {error}" if error else result)

    host.background(work, done=done)
    host.back_button()


def counter(host):
    host.title("Saved counter")
    host.status()
    host.set_status(f"Opened {host.store.get('opened', 0)} times before")
    host.store.set("opened", host.store.get("opened", 0) + 1)
    host.back_button()


def _copy_log(host):
    """The button that used to open the log screen: it only copies the log now."""
    try:
        text = host._log.text()
    except Exception:
        host.show_log()
        return
    host.copy(text or "(empty)")
    host.set_status("Log copied")
