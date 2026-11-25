"""Browser profiles (pure Python: no Kivy, no Android, no Build).

A profile is a separate box of the in-app browser: its own cookies / logins (the native WebView profile), settings,
speed dial, history, bookmarks and tabs. The main profile (id "") is the data the browser had before profiles existed.
A "secure" profile (chosen when it is made) also blocks third-party trackers and cookies, WebRTC IP leaks and keeps
location / camera / microphone closed until asked. The native side is java/.../BrowserHelper.java; the screens are
screens/browser_profiles.py.
"""
import re
import time

MAX_NAME = 30
DEFAULT_NAME = "Main"
COLORS = (
    ("Blue", "#1E88E5"), ("Green", "#43A047"), ("Red", "#E53935"), ("Orange", "#FB8C00"),
    ("Purple", "#8E24AA"), ("Teal", "#00897B"), ("Pink", "#D81B60"), ("Gray", "#757575"),
)
DEFAULT_COLOR = COLORS[0][1]
_ID = re.compile(r"p[0-9]{6,20}")
_HEX = re.compile(r"#[0-9A-Fa-f]{6}")


def clean_name(text):
    return " ".join(str(text or "").split())[:MAX_NAME]


def color_ok(value, fallback=DEFAULT_COLOR):
    value = str(value or "")
    return value.upper() if _HEX.fullmatch(value) else fallback


def color_name(value):
    value = str(value or "").upper()
    return next((n for n, c in COLORS if c == value), "Custom")


def hex_rgba(value, alpha=1.0):
    value = color_ok(value)
    return (int(value[1:3], 16) / 255.0, int(value[3:5], 16) / 255.0, int(value[5:7], 16) / 255.0, alpha)


class Profiles:
    """The list of profiles, which one is active, and the profiles deleted but not yet removed by the WebView
    (a WebView profile that was used in this run can only be deleted the next time the app starts)."""

    def __init__(self, data=None):
        d = data if isinstance(data, dict) else {}
        dflt = d.get("default") if isinstance(d.get("default"), dict) else {}
        self.default_name = clean_name(dflt.get("name")) or DEFAULT_NAME
        self.default_color = color_ok(dflt.get("color"))
        self.items = []
        seen = set()
        for p in d.get("list") or []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or "")
            name = clean_name(p.get("name"))
            if not _ID.fullmatch(pid) or pid in seen or not name:
                continue
            seen.add(pid)
            self.items.append({"id": pid, "name": name, "color": color_ok(p.get("color")),
                               "secure": bool(p.get("secure"))})
        self.pending = []
        for pid in d.get("pending_delete") or []:
            pid = str(pid or "")
            if _ID.fullmatch(pid) and pid not in seen and pid not in self.pending:
                self.pending.append(pid)
        del self.pending[200:]
        active = str(d.get("active") or "")
        self.active_id = active if active in seen else ""

    @classmethod
    def from_data(cls, data):
        return cls(data)

    def to_data(self):
        return {"active": self.active_id,
                "default": {"name": self.default_name, "color": self.default_color},
                "list": [dict(p) for p in self.items],
                "pending_delete": list(self.pending)}

    def entries(self):
        """The main profile first, then the others in the order they were made."""
        main = {"id": "", "name": self.default_name, "color": self.default_color, "secure": False, "default": True}
        return [main] + [dict(p) for p in self.items]

    def get(self, pid):
        pid = str(pid or "")
        return next((e for e in self.entries() if e["id"] == pid), None)

    def current(self):
        return self.get(self.active_id)

    def spec(self, pid):
        """(native profile name, secure) of a profile: the native name of the main profile is empty."""
        e = self.get(pid) or self.get("")
        return e["id"], bool(e["secure"])

    def name_taken(self, name, skip=None):
        low = clean_name(name).lower()
        return any(e["name"].lower() == low and e["id"] != skip for e in self.entries())

    def _new_id(self):
        used = {p["id"] for p in self.items} | set(self.pending)
        n = int(time.time() * 1000)
        while f"p{n}" in used:
            n += 1
        return f"p{n}"

    def add(self, name, color=DEFAULT_COLOR, secure=False):
        """Makes a profile. Returns (profile, "") or (None, error text)."""
        name = clean_name(name)
        if not name:
            return None, "Name can't be empty"
        if self.name_taken(name):
            return None, "A profile with this name already exists"
        p = {"id": self._new_id(), "name": name, "color": color_ok(color), "secure": bool(secure)}
        self.items.append(p)
        return dict(p), ""

    def rename(self, pid, name):
        name = clean_name(name)
        if not name:
            return "Name can't be empty"
        if self.name_taken(name, skip=str(pid or "")):
            return "A profile with this name already exists"
        if not pid:
            self.default_name = name
            return ""
        p = next((x for x in self.items if x["id"] == pid), None)
        if p is None:
            return "Profile not found"
        p["name"] = name
        return ""

    def recolor(self, pid, color):
        color = color_ok(color)
        if not pid:
            self.default_color = color
            return True
        p = next((x for x in self.items if x["id"] == pid), None)
        if p is None:
            return False
        p["color"] = color
        return True

    def set_active(self, pid):
        pid = str(pid or "")
        if pid and not any(p["id"] == pid for p in self.items):
            return False
        self.active_id = pid
        return True

    def delete(self, pid):
        """Removes a profile from the list (its data goes with it). Returns "" or an error text."""
        pid = str(pid or "")
        if not pid:
            return "The main profile can't be deleted"
        if pid == self.active_id:
            return "Switch to another profile first"
        i = next((n for n, p in enumerate(self.items) if p["id"] == pid), -1)
        if i < 0:
            return "Profile not found"
        self.items.pop(i)
        if pid not in self.pending:
            self.pending.append(pid)
        return ""

    def take_pending(self):
        """The deleted profiles the WebView still has to remove (handed over once)."""
        out, self.pending = list(self.pending), []
        return out
