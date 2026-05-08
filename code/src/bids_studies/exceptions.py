"""Exception classes for bids_studies.

These exceptions are defined in bids_studies (not openneuro_studies) to ensure
the library can be used standalone without any dependency on openneuro_studies.
See FR-HE-071: bids_studies MUST NOT import from openneuro_studies.
"""


class BidsStudiesError(Exception):
    """Base exception for all bids_studies errors."""

    pass


class NetworkError(BidsStudiesError):
    """Network operation failed after retries.

    Raised when network operations (HTTP requests, sparse file access) fail
    even after retrying with exponential backoff.

    Attributes:
        message: Human-readable error description
        url: URL that failed (if applicable)
        attempts: Number of retry attempts made
        last_error: The underlying exception from the last attempt
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        attempts: int = 0,
        last_error: Exception | None = None,
    ) -> None:
        """Initialize NetworkError.

        Args:
            message: Human-readable error description
            url: URL that failed (optional)
            attempts: Number of retry attempts made
            last_error: The underlying exception from the last attempt
        """
        self.message = message
        self.url = url
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format comprehensive error message."""
        parts = [self.message]
        if self.url:
            parts.append(f"URL: {self.url}")
        if self.attempts > 0:
            parts.append(f"Failed after {self.attempts} attempts")
        if self.last_error:
            parts.append(f"Last error: {type(self.last_error).__name__}: {self.last_error}")
        return " | ".join(parts)
