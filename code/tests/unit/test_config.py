"""Unit tests for configuration loading."""

import os
from pathlib import Path

import pytest
import yaml

from openneuro_studies.config import (
    ConfigLoadError,
    OpenNeuroStudiesConfig,
    SourceType,
    create_example_config,
    load_config,
)


@pytest.mark.unit
@pytest.mark.ai_generated
class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        """Test loading a valid configuration file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "github_org": "TestOrg",
            "sources": [
                {
                    "name": "TestSource",
                    "organization_url": "https://github.com/TestOrg",
                    "type": "raw",
                    "inclusion_patterns": ["^ds\\d+$"],
                }
            ],
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Mock environment variable
        os.environ["GITHUB_TOKEN"] = "test_token"

        config = load_config(str(config_file))
        assert config.github_org == "TestOrg"
        assert len(config.sources) == 1
        assert config.sources[0].name == "TestSource"
        assert config.sources[0].type == SourceType.RAW

        # Cleanup
        del os.environ["GITHUB_TOKEN"]

    def test_missing_config_file(self) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigLoadError, match="Configuration file not found"):
            load_config("/nonexistent/config.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        """Test error with invalid YAML syntax."""
        config_file = tmp_path / "bad_config.yaml"
        with open(config_file, "w") as f:
            f.write("invalid: yaml: syntax: here:")

        with pytest.raises(ConfigLoadError, match="Invalid YAML"):
            load_config(str(config_file))

    def test_empty_config_file(self, tmp_path: Path) -> None:
        """Test error with empty config file."""
        config_file = tmp_path / "empty.yaml"
        config_file.touch()

        with pytest.raises(ConfigLoadError, match="empty"):
            load_config(str(config_file))

    def test_validation_error(self, tmp_path: Path) -> None:
        """Test error with invalid config structure."""
        config_file = tmp_path / "invalid.yaml"
        config_data = {
            "github_org": "TestOrg",
            "sources": [
                {
                    "name": "TestSource",
                    "organization_url": "not-a-url",  # Invalid URL
                    "type": "raw",
                }
            ],
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        with pytest.raises(ConfigLoadError, match="validation failed"):
            load_config(str(config_file))

    def test_missing_env_token(self, tmp_path: Path) -> None:
        """Test error when required environment variable is missing."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "github_org": "TestOrg",
            "sources": [
                {
                    "name": "TestSource",
                    "organization_url": "https://github.com/TestOrg",
                    "type": "raw",
                    "access_token_env": "MISSING_TOKEN",
                }
            ],
        }

        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Ensure token is not set
        os.environ.pop("MISSING_TOKEN", None)

        with pytest.raises(ConfigLoadError, match="Environment variable MISSING_TOKEN not set"):
            load_config(str(config_file))


@pytest.mark.unit
@pytest.mark.ai_generated
class TestCreateExampleConfig:
    """Tests for create_example_config function."""

    def test_creates_example_config(self, tmp_path: Path) -> None:
        """Test creating example configuration file."""
        output_path = tmp_path / "example_config.yaml"
        create_example_config(str(output_path))

        assert output_path.exists()

        with open(output_path) as f:
            config_data = yaml.safe_load(f)

        assert "github_org" in config_data
        assert "sources" in config_data
        assert len(config_data["sources"]) == 2
        assert config_data["github_org"] == "OpenNeuroStudies"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Test that parent directories are created if they don't exist."""
        output_path = tmp_path / "nested" / "dir" / "config.yaml"
        create_example_config(str(output_path))

        assert output_path.exists()
        assert output_path.parent.exists()


@pytest.mark.unit
@pytest.mark.ai_generated
class TestOpenNeuroStudiesConfig:
    """Tests for OpenNeuroStudiesConfig model."""

    def test_default_github_org(self) -> None:
        """Test default github_org value."""
        config = OpenNeuroStudiesConfig(sources=[])
        assert config.github_org == "OpenNeuroStudies"

    def test_custom_github_org(self) -> None:
        """Test custom github_org value."""
        config = OpenNeuroStudiesConfig(github_org="CustomOrg", sources=[])
        assert config.github_org == "CustomOrg"

    def test_source_with_defaults(self) -> None:
        """Test source specification with default values."""
        config_data = {
            "github_org": "TestOrg",
            "sources": [
                {
                    "name": "TestSource",
                    "organization_url": "https://github.com/TestOrg",
                    "type": "raw",
                }
            ],
        }

        config = OpenNeuroStudiesConfig(**config_data)
        source = config.sources[0]

        assert source.inclusion_patterns == [".*"]
        assert source.exclusion_patterns == []
        assert source.access_token_env == "GITHUB_TOKEN"
