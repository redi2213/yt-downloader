"""Getting a file's bytes (and name) from Android: the system file picker,
and files shared into the app (content:// links). pyjnius only; on desktop
every function reports that it is unavailable instead of crashing."""
import os

from kivy.clock import Clock

from core.async_utils import run_in_background

_REQUEST_PICK = 4721
_RESULT_OK = -1


def read_uri_bytes(uri) -> bytes:
    """Whole content of a content:// Uri."""
    from jnius import autoclass
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    pfd = activity.getContentResolver().openFileDescriptor(uri, "r")
    fd = pfd.detachFd()
    with os.fdopen(fd, "rb") as f:
        return f.read()


def read_uri_name(uri):
    """The file's display name (e.g. ``upload-file (1).yml``), or None."""
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        cursor = activity.getContentResolver().query(uri, None, None, None, None)
        if cursor is None:
            return None
        try:
            if cursor.moveToFirst():
                index = cursor.getColumnIndex("_display_name")
                if index >= 0:
                    name = cursor.getString(index)
                    return str(name) if name else None
        finally:
            cursor.close()
    except Exception:
        pass
    return None


def _uris_from_result(intent) -> list:
    """Every Uri the picker returned (one file or several)."""
    uris = []
    clip = intent.getClipData()
    if clip is not None:
        for i in range(clip.getItemCount()):
            uri = clip.getItemAt(i).getUri()
            if uri is not None:
                uris.append(uri)
    if not uris:
        uri = intent.getData()
        if uri is not None:
            uris.append(uri)
    return uris


def pick_files(on_files, on_error=None) -> None:
    """Opens Android's file picker, several files allowed.
    ``on_files([(name, bytes), ...])`` runs on the Kivy thread."""
    try:
        from jnius import autoclass
        from android import activity
    except Exception:
        if on_error:
            on_error("Picking a file works only on the phone.")
        return

    try:
        Intent = autoclass("android.content.Intent")
        main_activity = autoclass("org.kivy.android.PythonActivity").mActivity

        def _result(request_code, result_code, intent):
            if request_code != _REQUEST_PICK:
                return
            activity.unbind(on_activity_result=_result)
            if result_code != _RESULT_OK or intent is None:
                return
            uris = _uris_from_result(intent)
            if uris:
                run_in_background(_read_many, uris, on_files, on_error)

        activity.bind(on_activity_result=_result)
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)
        main_activity.startActivityForResult(intent, _REQUEST_PICK)
    except Exception as e:
        if on_error:
            on_error(f"Could not open the file picker: {str(e)[:50]}")


def _read_many(uris, on_files, on_error):
    files = []
    try:
        for n, uri in enumerate(uris, 1):
            name = read_uri_name(uri) or f"file{n}"
            files.append((name, read_uri_bytes(uri)))
    except Exception as e:
        if on_error:
            Clock.schedule_once(lambda dt: on_error(f"Could not read the file: {str(e)[:50]}"))
        return
    Clock.schedule_once(lambda dt: on_files(files))
