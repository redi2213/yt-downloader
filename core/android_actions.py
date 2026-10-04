"""Small Android integrations used by several screens: opening a link in the
browser and sharing text through the Android Share sheet.

Both go through pyjnius on Android. On desktop (or if anything fails) they
fall back to something harmless - ``webbrowser`` for links and the clipboard
for shared text - and report whether the primary action worked.
"""


def _android_activity():
    from jnius import autoclass
    return autoclass("org.kivy.android.PythonActivity").mActivity


def open_url(url) -> bool:
    """Opens ``url`` in the browser. True if some app was started."""
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
        _android_activity().startActivity(intent)
        return True
    except Exception:
        pass
    try:
        import webbrowser
        return bool(webbrowser.open(url))
    except Exception:
        return False


def share_text(text) -> bool:
    """Opens the Android Share sheet with ``text``. If that isn't possible the
    text is copied to the clipboard instead; returns True only when the Share
    sheet was shown."""
    try:
        from jnius import autoclass
        Intent = autoclass("android.content.Intent")
        String = autoclass("java.lang.String")
        intent = Intent()
        intent.setAction(Intent.ACTION_SEND)
        intent.putExtra(Intent.EXTRA_TEXT, String(text))
        intent.setType("text/plain")
        chooser = Intent.createChooser(intent, String("Share"))
        _android_activity().startActivity(chooser)
        return True
    except Exception:
        pass
    try:
        from kivy.core.clipboard import Clipboard
        Clipboard.copy(text)
    except Exception:
        pass
    return False
