"""Getting a file's bytes from Android: the system file picker, and files
shared into the app (content:// links). pyjnius only; on desktop every
function reports that it is unavailable instead of crashing."""
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


def pick_file(on_data, on_error=None) -> None:
    """Opens Android's file picker. ``on_data(bytes)`` runs on the Kivy
    thread after a file is chosen."""
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
            uri = intent.getData()
            if uri is None:
                return
            run_in_background(_read_and_deliver, uri, on_data, on_error)

        activity.bind(on_activity_result=_result)
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("*/*")
        main_activity.startActivityForResult(intent, _REQUEST_PICK)
    except Exception as e:
        if on_error:
            on_error(f"Could not open the file picker: {str(e)[:50]}")


def _read_and_deliver(uri, on_data, on_error):
    try:
        data = read_uri_bytes(uri)
    except Exception as e:
        if on_error:
            Clock.schedule_once(lambda dt: on_error(f"Could not read the file: {str(e)[:50]}"))
        return
    Clock.schedule_once(lambda dt: on_data(data))
