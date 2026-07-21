import json
import os
import urllib.parse

HISTORY_FILE = os.path.expanduser("~/.yt_downloader_history.json")


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_history(items):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def add_history_entry(entry):
    items = load_history()
    items.insert(0, entry)
    save_history(items)


def title_from_link(link):
    if not link:
        return "unknown"
    tail = link.rstrip("/").split("/")[-1]
    name = urllib.parse.unquote(tail)
    name = os.path.splitext(name)[0]
    return name


def export_history_txt(path=None):
    if path is None:
        path = os.path.expanduser("~/yt_downloader_history.txt")
    items = load_history()
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(f"Time:    {item.get('time','')}\n")
            f.write(f"Title:   {item.get('title','')}\n")
            f.write(f"Quality: {item.get('quality','')}\n")
            f.write(f"Mode:    {item.get('mode','')}\n")
            f.write(f"Source:  {item.get('source_url','')}\n")
            f.write(f"Result:  {item.get('result','')}\n")
            f.write("-" * 40 + "\n")
    return path


def print_history():
    items = load_history()
    if not items:
        print("No history yet.")
        return
    for i, item in enumerate(items, 1):
        print(f"{i}. [{item.get('time','')}] {item.get('title','')} ({item.get('quality','')}) -> {item.get('mode','')}")
