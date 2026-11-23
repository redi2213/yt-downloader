"""Lab: make the repo public or private by hand (temporary, no build needed).

Uses the app's GitHub token, which must have admin rights on the repo.
Public repos have free Actions minutes; private ones have the monthly quota.
"""
REPO_URL = "https://api.github.com/repos/redi2213/yt-downloader"


def build(host):
    host.title("Repo visibility")
    host.text("Needs a GitHub token with admin rights. Before making the repo public: "
              "ntfy.json (the ntfy topic) and the other config files become readable by everyone.")
    host.status()
    host.set_status("Checking...")
    host.button("Make PUBLIC", lambda: _set(host, False))
    host.button("Make PRIVATE", lambda: _set(host, True))
    host.button("Refresh", lambda: host.replace(build))
    host.back_button("Back")
    _load(host)


def _word(private):
    return "PRIVATE" if private else "PUBLIC"


def _load(host):
    def work():
        return bool(host.gh.request("GET", REPO_URL).json().get("private"))

    def done(result, error):
        host.set_status(f"Failed: {str(error)[:120]}" if error else f"The repo is {_word(result)} now")

    host.background(work, done=done)


def _set(host, private):
    host.set_status("Changing...")

    def work():
        r = host.gh.request("PATCH", REPO_URL, json={"private": bool(private)})
        return bool(r.json().get("private"))

    def done(result, error):
        if error:
            host.set_status(f"Failed: {str(error)[:120]}")
        else:
            host.set_status(f"Done: the repo is {_word(result)} now")

    host.background(work, done=done)
