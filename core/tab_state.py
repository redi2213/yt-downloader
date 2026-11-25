"""Pure rules of the app tabs (plain Python, no Kivy): the state of a tab, the percent of a running
GitHub job, which tab to close to make room, and the little badge on the top-bar Tabs button.
The Kivy side is screens/tabs.py."""

MAX_TABS = 4

RUNNING = "running"
DONE = "done"
ERROR = "error"
IDLE = "idle"


def tab_state(running, finished, ok, cancelled, acked):
    """running: the tab has a job in progress. finished: its last job is done; ok: True/False/None;
    cancelled: that job was cancelled by the user; acked: the user already saw that finished job."""
    if running:
        return RUNNING
    if finished and not acked and not cancelled:
        return ERROR if ok is False else DONE
    return IDLE


def job_percent(job):
    """Percent (0-100) of a GitHub job dict ({"steps": [{"status", "conclusion"}, ...]}) from its finished
    steps; None when there is nothing to count yet."""
    if not job:
        return None
    steps = [s for s in (job.get("steps") or []) if s.get("conclusion") != "skipped"]
    if not steps:
        return None
    done = sum(1 for s in steps if s.get("status") == "completed")
    return min(100, int(done * 100 / len(steps)))


def badge_state(states, active_index):
    """What the Tabs button shows. The tab on screen counts only while it runs (the user sees its result
    anyway); a finished or failed OTHER tab asks for attention first, then running, else nothing."""
    others = [s for i, s in enumerate(states) if i != active_index]
    if ERROR in others:
        return ERROR
    if DONE in others:
        return DONE
    if RUNNING in states:
        return RUNNING
    return IDLE


def badge_suffix(state):
    return {RUNNING: " *", DONE: " +", ERROR: " !"}.get(state, "")


def pick_to_replace(states):
    """Index of the tab to close automatically when all tabs are used and a new one is needed: the oldest
    idle one, else the oldest finished/failed one; None when every tab is running (ask the user)."""
    for wanted in (IDLE, DONE, ERROR):
        for i, s in enumerate(states):
            if s == wanted:
                return i
    return None


def status_text(state, percent=None):
    if state == RUNNING:
        return f"Status: running {percent}%" if percent is not None else "Status: running"
    return {DONE: "Status: finished", ERROR: "Status: error"}.get(state, "Status: idle")
