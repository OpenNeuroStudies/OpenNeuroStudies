"""Custom exceptions for OpenNeuroStudies."""


class OpenNeuroStudiesError(Exception):
    """Base exception for all OpenNeuroStudies errors."""

    pass


class NetworkError(OpenNeuroStudiesError):
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


class ExtractionError(OpenNeuroStudiesError):
    """Data extraction failed (not a network issue).

    Raised when extraction fails due to data issues, not network problems.
    For example: malformed NIfTI headers, invalid JSON, missing required fields.

    Attributes:
        message: Human-readable error description
        file_path: Path to file that failed extraction (if applicable)
        field: Field name that failed extraction (if applicable)
    """

    def __init__(
        self,
        message: str,
        file_path: str | None = None,
        field: str | None = None,
    ) -> None:
        """Initialize ExtractionError.

        Args:
            message: Human-readable error description
            file_path: Path to file that failed extraction (optional)
            field: Field name that failed extraction (optional)
        """
        self.message = message
        self.file_path = file_path
        self.field = field
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format comprehensive error message."""
        parts = [self.message]
        if self.file_path:
            parts.append(f"File: {self.file_path}")
        if self.field:
            parts.append(f"Field: {self.field}")
        return " | ".join(parts)


class DatasetNotFoundError(OpenNeuroStudiesError):
    """Dataset not found at expected location."""

    pass


class GitHubAPIError(OpenNeuroStudiesError):
    """GitHub API request failed."""

    pass


class ValidationError(OpenNeuroStudiesError):
    """BIDS validation failed."""

    pass
