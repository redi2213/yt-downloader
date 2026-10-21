"""File kinds for the Downloads page filter."""
import os

KINDS = ("All", "Video", "Audio", "APK", "Zip", "Other")
_VIDEO = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".ts", ".m4v", ".3gp", ".flv"}
_AUDIO = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac", ".wma"}
_ZIP = {".zip", ".rar", ".7z", ".tar", ".gz"}


def kind_of(name):
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext in _VIDEO:
        return "Video"
    if ext in _AUDIO:
        return "Audio"
    if ext == ".apk":
        return "APK"
    if ext in _ZIP:
        return "Zip"
    return "Other"
