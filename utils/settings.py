import os
import json

SETTINGS_FILE = "ytdl_settings.json"


def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_settings(data):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_token():
    return load_settings().get("github_token", "")


def save_token(token):
    data = load_settings()
    data["github_token"] = token
    save_settings(data)
