"""Unit tests for humanized size parsing in derivative_extractor."""

import pytest
from openneuro_studies.metadata.derivative_extractor import _parse_humanized_size


class TestParseHumanizedSize:
    """Test _parse_humanized_size function."""

    def test_parse_integer(self):
        """Test parsing integer input."""
        assert _parse_humanized_size(654711933) == 654711933

    def test_parse_numeric_string(self):
        """Test parsing numeric string."""
        assert _parse_humanized_size("654711933") == 654711933
        assert _parse_humanized_size("12345") == 12345

    def test_parse_zero_bytes(self):
        """Test parsing zero bytes."""
        assert _parse_humanized_size("0 bytes") == 0
        assert _parse_humanized_size("0") == 0

    def test_parse_bytes(self):
        """Test parsing byte values."""
        assert _parse_humanized_size("100 bytes") == 100
        assert _parse_humanized_size("1 byte") == 1

    def test_parse_kilobytes(self):
        """Test parsing kilobyte values."""
        assert _parse_humanized_size("1 kilobyte") == 1024
        assert _parse_humanized_size("2 kilobytes") == 2048
        assert _parse_humanized_size("1.5 kilobytes") == 1536

    def test_parse_megabytes(self):
        """Test parsing megabyte values."""
        assert _parse_humanized_size("1 megabyte") == 1024 ** 2
        assert _parse_humanized_size("10 megabytes") == 10 * 1024 ** 2
        assert _parse_humanized_size("2.5 megabytes") == int(2.5 * 1024 ** 2)

    def test_parse_gigabytes(self):
        """Test parsing gigabyte values."""
        assert _parse_humanized_size("1 gigabyte") == 1024 ** 3
        assert _parse_humanized_size("2.29 gigabytes") == int(2.29 * 1024 ** 3)
        assert _parse_humanized_size("100 gigabytes") == 100 * 1024 ** 3

    def test_parse_terabytes(self):
        """Test parsing terabyte values."""
        assert _parse_humanized_size("1 terabyte") == 1024 ** 4
        assert _parse_humanized_size("1.5 terabytes") == int(1.5 * 1024 ** 4)

    def test_parse_petabytes(self):
        """Test parsing petabyte values."""
        assert _parse_humanized_size("1 petabyte") == 1024 ** 5

    def test_parse_without_space(self):
        """Test parsing without space between number and unit."""
        # This format might not be produced by git-annex, but good to handle
        assert _parse_humanized_size("2.29gigabytes") == int(2.29 * 1024 ** 3)

    def test_parse_case_insensitive(self):
        """Test case-insensitive parsing."""
        assert _parse_humanized_size("1 Gigabyte") == 1024 ** 3
        assert _parse_humanized_size("1 GIGABYTES") == 1024 ** 3

    def test_parse_invalid_format(self):
        """Test parsing invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Cannot parse"):
            _parse_humanized_size("invalid format")

    def test_parse_unknown_unit(self):
        """Test parsing unknown unit raises ValueError."""
        with pytest.raises(ValueError, match="Unknown unit"):
            _parse_humanized_size("100 foobar")

    def test_parse_real_world_examples(self):
        """Test real-world examples from git-annex output."""
        # Examples from user's output
        assert _parse_humanized_size("2.29 gigabytes") == int(2.29 * 1024 ** 3)
        assert _parse_humanized_size("2.54 gigabytes") == int(2.54 * 1024 ** 3)
        assert _parse_humanized_size("322.35 gigabytes") == int(322.35 * 1024 ** 3)

        # Expected byte values (approximate)
        result_2_29_gb = _parse_humanized_size("2.29 gigabytes")
        assert 2_400_000_000 < result_2_29_gb < 2_500_000_000  # ~2.29 GB

        result_322_35_gb = _parse_humanized_size("322.35 gigabytes")
        assert 345_000_000_000 < result_322_35_gb < 347_000_000_000  # ~322.35 GB
