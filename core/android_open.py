"""Open / Share a file the app saved in Download/Yt-bridge.

``location`` is what core/android_downloads.py returned (``Saved.location``):
a content:// uri on Android 10+, a plain path on older Android. Both functions
return None when the Android chooser was opened, otherwise a short text that
says what to do instead. Pure helpers, no Kivy.
"""
from core import android_downloads


def _is_content(location):
    return str(location or "").startswith("content://")


def open_file(location, name=""):
    """\"Open with...\": Android's app chooser for the file (video player,
    gallery, PDF reader ...), every time."""
    if not location:
        return "The file location is unknown - open it from the Files app."
    try:
        from jnius import autoclass
    except Exception:
        return "Opening a file works only on the phone."
    if not _is_content(location):
        return f"Open the file from the Files app:\n{location}"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(Uri.parse(str(location)), android_downloads._mime_for(name or ""))
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        chooser = Intent.createChooser(intent, "Open with")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(chooser)
        return None
    except Exception as e:
        return f"Could not open the file: {str(e)[:80]}\nOpen it from the Files app."


def share_file(location, name=""):
    """The Android Share sheet with the FILE itself (not its link)."""
    if not location:
        return "The file location is unknown - share it from the Files app."
    try:
        from jnius import autoclass
    except Exception:
        return "Sharing a file works only on the phone."
    if not _is_content(location):
        return f"Share the file from the Files app:\n{location}"
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        intent = Intent(Intent.ACTION_SEND)
        intent.setType(android_downloads._mime_for(name or ""))
        intent.putExtra(Intent.EXTRA_STREAM, Uri.parse(str(location)))
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        chooser = Intent.createChooser(intent, "Share file")
        chooser.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(chooser)
        return None
    except Exception as e:
        return f"Could not share the file: {str(e)[:80]}"


def delete_file(location):
    """Deletes a saved file. True = deleted, False = it was already gone / could not be deleted."""
    if not location:
        return False
    location = str(location)
    if not _is_content(location):
        import os
        try:
            os.remove(location)
            return True
        except OSError:
            return False
    try:
        from jnius import autoclass
        Uri = autoclass("android.net.Uri")
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = activity.getContentResolver()
        uri = Uri.parse(location)
        if "/tree/" in location and "/document/" in location:      # a file inside a picked folder
            return bool(autoclass("android.provider.DocumentsContract").deleteDocument(resolver, uri))
        return resolver.delete(uri, None, None) > 0
    except Exception:
        return False
