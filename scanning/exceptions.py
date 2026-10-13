"""scanning/exceptions.py
======================
Custom exceptions for the AI scanning and extraction pipeline.
"""


class ScanQuotaExceededError(Exception):
    """Raised when shop daily or monthly scan quota has been exhausted."""

    def __init__(
        self,
        message: str = "Daily scan limit reached. Please upgrade quota or enter bill manually.",
    ):
        super().__init__(message)


class AIExtractionError(Exception):
    """Raised when an AI provider call fails or returns an unrecoverable error."""

    def __init__(
        self, message: str = "AI document reading failed. Please try again or enter bill manually."
    ):
        super().__init__(message)
