"""Opening Android's package installer for an APK the app downloaded.

The APK was saved with MediaStore (core/android_downloads.py), so the
``location`` is a content uri; the installer reads it through the read-grant
flag. The first time, Android asks to allow "install unknown apps" for this
app (the permission is in buildozer.spec); this module sends the user to that
setting when it is still off. Pure helper, no Kivy.
"""

APK_MIME = "application/vnd.android.package-archive"


def open_installer(location):
    """Returns None when the installer was opened, otherwise a short text
    explaining what to do."""
    if not location:
        return "The file location is unknown - open the APK from the Files app."
    try:
        from jnius import autoclass
    except Exception:
        return "Installing works only on the phone."
    try:
        Intent = autoclass("android.content.Intent")
        Uri = autoclass("android.net.Uri")
        sdk = autoclass("android.os.Build$VERSION").SDK_INT
        activity = autoclass("org.kivy.android.PythonActivity").mActivity

        if sdk >= 26 and not activity.getPackageManager().canRequestPackageInstalls():
            Settings = autoclass("android.provider.Settings")
            settings = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                              Uri.parse("package:" + activity.getPackageName()))
            settings.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(settings)
            return "Allow \"Install unknown apps\" for YT Bridge, come back and press Install again."

        if not str(location).startswith("content://"):
            return f"Open the APK from the Files app:\n{location}"

        intent = Intent(Intent.ACTION_VIEW)
        intent.setDataAndType(Uri.parse(str(location)), APK_MIME)
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK)
        activity.startActivity(intent)
        return None
    except Exception as e:
        return f"Could not open the installer: {str(e)[:80]}\nOpen the APK from the Files app."
