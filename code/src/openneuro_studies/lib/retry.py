"""Retry logic with exponential backoff for network operations."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import TypeVar

from openneuro_studies.lib.exceptions import NetworkError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_network_error(
    max_attempts: int = 5,
    max_wait_seconds: int = 60,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry function on network errors with exponential backoff.

    Retries network operations (HTTP requests, sparse file access) when they fail
    due to transient network issues. Uses exponential backoff between attempts.

    Args:
        max_attempts: Maximum number of attempts (default: 5)
        max_wait_seconds: Maximum total wait time across all retries (default: 60)
        initial_delay: Initial delay in seconds before first retry (default: 1.0)
        backoff_factor: Multiplier for delay between retries (default: 2.0)

    Returns:
        Decorated function that retries on network errors

    Raises:
        NetworkError: If all retry attempts fail

    Example:
        >>> @retry_on_network_error(max_attempts=3, max_wait_seconds=30)
        ... def fetch_file(url: str) -> bytes:
        ...     response = requests.get(url)
        ...     response.raise_for_status()
        ...     return response.content

    Retry Schedule (default):
        - Attempt 1: Immediate
        - Attempt 2: After 1.0s (total: 1.0s)
        - Attempt 3: After 2.0s (total: 3.0s)
        - Attempt 4: After 4.0s (total: 7.0s)
        - Attempt 5: After 8.0s (total: 15.0s)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:  # type: ignore[return]
            delay = initial_delay
            total_wait = 0.0
            last_error: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    is_network_error = _is_retriable_network_error(e)

                    if not is_network_error:
                        # Not a network error - raise immediately
                        raise

                    if attempt == max_attempts:
                        # Final attempt failed - raise NetworkError
                        raise NetworkError(
                            message=f"Network operation failed after {max_attempts} attempts",
                            attempts=max_attempts,
                            last_error=last_error,
                        ) from last_error

                    if total_wait >= max_wait_seconds:
                        # Exceeded max wait time - raise NetworkError
                        raise NetworkError(
                            message=f"Network operation exceeded max wait time ({max_wait_seconds}s)",
                            attempts=attempt,
                            last_error=last_error,
                        ) from last_error

                    # Log retry and wait
                    logger.warning(
                        f"Network error on attempt {attempt}/{max_attempts}: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                    total_wait += delay
                    delay *= backoff_factor

        return wrapper

    return decorator


def _is_retriable_network_error(error: Exception) -> bool:
    """Check if error is a retriable network error.

    Args:
        error: Exception to check

    Returns:
        True if error is retriable (network-related), False otherwise

    Retriable errors:
        - OSError (connection errors, timeouts)
        - TimeoutError
        - aiohttp client errors (if aiohttp is used)
        - requests connection errors (if requests is used)
        - fsspec remote file system errors
    """
    # Check error type name (avoid hard dependency on optional libraries)
    error_type = type(error).__name__

    # OSError and subclasses (ConnectionError, TimeoutError, etc.)
    if isinstance(error, (OSError, TimeoutError)):
        return True

    # aiohttp errors (check by name to avoid import)
    if error_type in {
        "ClientError",
        "ClientConnectorError",
        "ClientConnectionError",
        "ClientOSError",
        "ServerDisconnectedError",
        "ClientResponseError",
        "ClientPayloadError",
        "ClientTimeout",
    }:
        return True

    # requests errors (check by name)
    if error_type in {
        "ConnectionError",
        "Timeout",
        "ReadTimeout",
        "ConnectTimeout",
        "HTTPError",  # For 5xx errors
    }:
        return True

    # fsspec errors (check by name)
    if error_type in {
        "FSTimeoutError",
        "HttpError",
    }:
        return True

    # Check HTTP status codes for requests.HTTPError
    if error_type == "HTTPError" and hasattr(error, "response"):
        # Retry on 5xx server errors and some 4xx errors
        status_code = getattr(error.response, "status_code", None)
        if status_code is not None:
            # 5xx: Server errors (retriable)
            # 408: Request timeout (retriable)
            # 429: Too many requests (retriable)
            # 503: Service unavailable (retriable)
            # 504: Gateway timeout (retriable)
            if status_code >= 500 or status_code in {408, 429, 503, 504}:
                return True

    return False
