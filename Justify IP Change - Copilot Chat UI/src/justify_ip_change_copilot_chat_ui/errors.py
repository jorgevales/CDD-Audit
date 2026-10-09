import asyncio


class ApplicationError(RuntimeError):
    """Expected, operator-actionable application error."""


class WorkspaceError(ApplicationError):
    """The selected operational workspace is invalid."""


class ResourceError(ApplicationError):
    """A required runtime resource is missing or invalid."""


class BatchLockedError(ApplicationError):
    """Another run currently owns a requested batch."""


class CopilotUIError(ApplicationError):
    """The visible Copilot UI did not reach a safe, proven state."""


class SubmissionUncertainError(CopilotUIError):
    """Send may have occurred; automatic retry is unsafe."""


class PostSendCancelledError(asyncio.CancelledError):
    """Cancellation occurred after Send was attempted and requires review."""
