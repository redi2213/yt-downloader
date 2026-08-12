"""App-wide exception hierarchy.

Keeping distinct, meaningful exception types means the UI layer can decide
how to react (which message to show, whether a retry makes sense, etc.)
without inspecting error strings, and every layer below the UI can raise
the exception that actually describes what went wrong.
"""


class AppError(Exception):
    """Base class for all application-specific errors."""


class AuthenticationError(AppError):
    """The GitHub token is missing, invalid, expired, or lacks permissions."""


class NetworkError(AppError):
    """A network-level failure talking to an external service."""


class WorkflowError(AppError):
    """A GitHub Actions workflow run could not be found, started, or finished as expected."""


class DownloadError(AppError):
    """A video/audio download job failed."""


class UploadError(AppError):
    """A file upload job failed."""


class FormatError(AppError):
    """Video formats/qualities could not be retrieved or parsed."""


class CancellationError(AppError):
    """Raised when an operation is stopped because the user cancelled it."""


class ConfigurationError(AppError):
    """The app is missing configuration it needs to proceed (e.g. no token)."""
