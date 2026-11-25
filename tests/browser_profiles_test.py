"""Browser profiles (plain Python, no Kivy needed):  python3 tests/browser_profiles_test.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import browser_profiles as bp  # noqa: E402

pf = bp.Profiles()
assert pf.active_id == "" and [e["id"] for e in pf.entries()] == [""] and pf.current()["name"] == bp.DEFAULT_NAME
assert pf.spec("") == ("", False)

# making profiles
a, err = pf.add("  Work   one ", "#43a047", True)
assert not err and a["name"] == "Work one" and a["color"] == "#43A047" and a["secure"] is True
assert pf.add("", "#fff")[1] == "Name can't be empty"
assert pf.add("work ONE")[1] == "A profile with this name already exists"
assert pf.add("main")[1] == "A profile with this name already exists"
b, err = pf.add("Home", "not-a-color")
assert not err and b["color"] == bp.DEFAULT_COLOR and b["secure"] is False and b["id"] != a["id"]
assert pf.spec(a["id"]) == (a["id"], True) and pf.spec(b["id"]) == (b["id"], False)
assert pf.spec("zzz") == ("", False)

# switching
assert pf.set_active(a["id"]) and pf.active_id == a["id"] and pf.current()["name"] == "Work one"
assert not pf.set_active("p999999999") and pf.active_id == a["id"]
assert pf.set_active("") and pf.active_id == ""

# rename / recolor (the main profile too)
assert pf.rename(b["id"], "Home 2") == "" and pf.get(b["id"])["name"] == "Home 2"
assert pf.rename(b["id"], "work one") == "A profile with this name already exists"
assert pf.rename("", "Everyday") == "" and pf.current()["name"] == "Everyday"
assert pf.rename("p123456789", "X") == "Profile not found"
assert pf.recolor(b["id"], "#E53935") and pf.get(b["id"])["color"] == "#E53935"
assert pf.recolor("", "#8E24AA") and pf.get("")["color"] == "#8E24AA"

# deleting: not the main one, not the active one; the WebView removes it later
assert pf.delete("") == "The main profile can't be deleted"
pf.set_active(a["id"])
assert pf.delete(a["id"]) == "Switch to another profile first"
pf.set_active("")
assert pf.delete(a["id"]) == "" and pf.get(a["id"]) is None and pf.pending == [a["id"]]
assert pf.delete(a["id"]) == "Profile not found"

# saved and read back (junk is dropped)
back = bp.Profiles.from_data(pf.to_data())
assert [e["id"] for e in back.entries()] == ["", b["id"]] and back.pending == [a["id"]]
assert back.current()["name"] == "Everyday" and back.get(b["id"])["name"] == "Home 2"
junk = bp.Profiles.from_data({"active": "p42", "list": [{"id": "../x", "name": "Bad"}, {"id": "p123456", "name": ""},
                                                          "no", {"id": "p123456", "name": "Ok", "color": "zz"}],
                              "pending_delete": ["p123456", "p777777", 5]})
assert [e["id"] for e in junk.entries()] == ["", "p123456"] and junk.active_id == ""
assert junk.get("p123456")["color"] == bp.DEFAULT_COLOR and junk.pending == ["p777777"]
assert bp.Profiles.from_data(None).entries()[0]["name"] == bp.DEFAULT_NAME

# the deleted ones are handed to the WebView once
assert back.take_pending() == [a["id"]] and back.pending == [] and back.take_pending() == []

# colours
assert bp.hex_rgba("#FF0000") == (1.0, 0.0, 0.0, 1.0) and bp.color_name("#1e88e5") == "Blue"
print("browser profiles: OK")
