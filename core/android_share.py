"""Receiving links shared into the app from Android's Share menu.

The manifest side lives in intent_filters.xml (referenced from
buildozer.spec): it makes the app show up as a Share target for plain text.
This module does the runtime side with pyjnius:

  - cold start: the app was launched BY the share -> read the launching
    intent once at startup
  - already running: Android delivers a new intent -> android.activity's
    on_new_intent callback

Everything is wrapped so that on desktop (no jnius / android modules) or if
anything goes wrong on a device, setup() just returns False and the app
behaves exactly as before.
"""
from kivy.clock import Clock

_ACTION_SEND = "android.intent.action.SEND"
_EXTRA_TEXT = "android.intent.extra.TEXT"


def text_from_intent(intent):
    """The shared text of an ACTION_SEND intent, or None."""
    if intent is None:
        return None
    try:
        if intent.getAction() != _ACTION_SEND:
            return None
        text = intent.getStringExtra(_EXTRA_TEXT)
    except Exception:
        return None
    text = str(text).strip() if text else ""
    return text or None


_EXTRA_STREAM = "android.intent.extra.STREAM"


def stream_uri_from_intent(intent):
    """The content:// Uri of a file shared with ACTION_SEND, or None."""
    if intent is None:
        return None
    try:
        if intent.getAction() != _ACTION_SEND:
            return None
        parcel = intent.getParcelableExtra(_EXTRA_STREAM)
        if parcel is None:
            return None
        from jnius import cast
        return cast("android.net.Uri", parcel)
    except Exception:
        return None


def setup(on_text, on_file=None):
    """Starts listening. ``on_text(text)`` is called on the Kivy thread with
    the shared text, each time something is shared; ``on_file(bytes)`` with
    the content of a shared file (a project zip or config.json). Returns
    True if the Android hooks could be installed."""
    try:
        from jnius import autoclass
        from android import activity
    except Exception:
        return False

    try:
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        Intent = autoclass("android.content.Intent")
        main_activity = PythonActivity.mActivity

        def _deliver_file(uri):
            from core import android_files
            try:
                data = android_files.read_uri_bytes(uri)
            except Exception:
                return
            Clock.schedule_once(lambda dt: on_file(data))

        def _deliver(intent):
            if on_file is not None:
                uri = stream_uri_from_intent(intent)
                if uri is not None:
                    from core.async_utils import run_in_background
                    run_in_background(_deliver_file, uri)
                    return
            text = text_from_intent(intent)
            if text:
                # runs on Android's UI thread -> hop onto Kivy's thread
                Clock.schedule_once(lambda dt: on_text(text))

        activity.bind(on_new_intent=_deliver)

        # Cold start: handle the launching intent once, then replace it so a
        # later resume/rotation doesn't process the same share again.
        _deliver(main_activity.getIntent())
        main_activity.setIntent(Intent())
        return True
    except Exception:
        return False
