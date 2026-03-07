"""Tests for retry logic with exponential backoff."""

import time
from unittest.mock import Mock

import pytest

from openneuro_studies.lib.exceptions import NetworkError
from openneuro_studies.lib.retry import retry_on_network_error


def test_retry_succeeds_on_first_attempt():
    """Test that successful function executes without retry."""
    mock_func = Mock(return_value="success")
    decorated = retry_on_network_error()(mock_func)

    result = decorated()

    assert result == "success"
    assert mock_func.call_count == 1


def test_retry_succeeds_after_failures():
    """Test that function succeeds after transient failures."""
    call_count = 0

    def flaky_function():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise OSError("Connection timeout")
        return "success"

    decorated = retry_on_network_error(max_attempts=5)(flaky_function)

    result = decorated()

    assert result == "success"
    assert call_count == 3


def test_retry_raises_network_error_after_max_attempts():
    """Test that NetworkError is raised after max attempts."""

    def always_fails():
        raise OSError("Connection timeout")

    decorated = retry_on_network_error(max_attempts=3)(always_fails)

    with pytest.raises(NetworkError) as exc_info:
        decorated()

    assert "failed after 3 attempts" in str(exc_info.value)
    assert exc_info.value.attempts == 3


def test_retry_raises_network_error_after_max_wait():
    """Test that NetworkError is raised after max wait time."""

    def slow_failure():
        raise OSError("Connection timeout")

    decorated = retry_on_network_error(
        max_attempts=10,
        max_wait_seconds=2,
        initial_delay=1.0,
    )(slow_failure)

    start = time.time()
    with pytest.raises(NetworkError) as exc_info:
        decorated()
    elapsed = time.time() - start

    # Should have stopped due to max wait time
    assert "exceeded max wait time" in str(exc_info.value)
    # Elapsed time should be around 2-3 seconds (2s max_wait + retries)
    assert 2 <= elapsed < 5


def test_retry_non_network_error_raised_immediately():
    """Test that non-network errors are raised immediately without retry."""

    def raises_value_error():
        raise ValueError("Invalid data")

    decorated = retry_on_network_error(max_attempts=5)(raises_value_error)

    with pytest.raises(ValueError, match="Invalid data"):
        decorated()


def test_retry_exponential_backoff():
    """Test that retry uses exponential backoff."""
    call_times = []

    def record_time():
        call_times.append(time.time())
        raise OSError("Connection timeout")

    decorated = retry_on_network_error(
        max_attempts=4,
        initial_delay=0.1,
        backoff_factor=2.0,
    )(record_time)

    with pytest.raises(NetworkError):
        decorated()

    # Verify exponential backoff between calls
    # Expected delays: 0, 0.1, 0.2, 0.4
    assert len(call_times) == 4

    # Check approximate delays (with tolerance for timing variance)
    delay1 = call_times[1] - call_times[0]
    delay2 = call_times[2] - call_times[1]
    delay3 = call_times[3] - call_times[2]

    assert 0.08 < delay1 < 0.15  # ~0.1s
    assert 0.18 < delay2 < 0.25  # ~0.2s
    assert 0.38 < delay3 < 0.45  # ~0.4s


def test_retry_with_function_arguments():
    """Test that retry works with functions that have arguments."""
    call_count = 0

    def add(a: int, b: int) -> int:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise OSError("Connection timeout")
        return a + b

    decorated = retry_on_network_error(max_attempts=3)(add)

    result = decorated(3, 5)

    assert result == 8
    assert call_count == 2


def test_retry_preserves_last_error_info():
    """Test that NetworkError contains last error information."""

    def fails_with_message():
        raise OSError("Specific network failure")

    decorated = retry_on_network_error(max_attempts=2)(fails_with_message)

    with pytest.raises(NetworkError) as exc_info:
        decorated()

    assert exc_info.value.last_error is not None
    assert isinstance(exc_info.value.last_error, OSError)
    assert "Specific network failure" in str(exc_info.value.last_error)


@pytest.mark.parametrize(
    "error_type,should_retry",
    [
        (OSError("Connection reset"), True),
        (TimeoutError("Request timeout"), True),
        (ConnectionError("Connection refused"), True),
        (ValueError("Invalid data"), False),
        (KeyError("Missing key"), False),
        (RuntimeError("Runtime error"), False),
    ],
)
def test_retry_error_detection(error_type, should_retry):
    """Test that retry logic correctly identifies retriable errors."""

    def raises_error():
        raise error_type

    decorated = retry_on_network_error(max_attempts=2)(raises_error)

    if should_retry:
        with pytest.raises(NetworkError):
            decorated()
    else:
        with pytest.raises(type(error_type)):
            decorated()
