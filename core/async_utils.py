"""Small helper so services can run work in the background without every
service module repeating the same ``threading.Thread(..., daemon=True).start()``
boilerplate, and without depending on Kivy's Clock for scheduling.

Callbacks passed into services (on_status, on_complete, ...) may therefore
be invoked from a background thread. UI layers are responsible for hopping
back onto the main thread before touching widgets (e.g. via
``kivy.clock.Clock.schedule_once``).
"""
import threading
from typing import Callable


def run_in_background(target: Callable, *args, **kwargs) -> threading.Thread:
    thread = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    thread.start()
    return thread
