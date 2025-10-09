"""Configuration loading utilities."""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from openneuro_studies.config.models import OpenNeuroStudiesConfig


class ConfigLoadError(Exception):
    """Raised when configuration cannot be loaded or validated."""

    pass


def load_config(config_path: Optional[str] = None) -> OpenNeuroStudiesConfig:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to configuration file. If None, defaults to
                    .openneuro-studies/config.yaml in current directory.

    Returns:
        Validated OpenNeuroStudiesConfig instance

    Raises:
        ConfigLoadError: If file not found, invalid YAML, or validation fails
    """
    if config_path is None:
        config_path = ".openneuro-studies/config.yaml"

    config_file = Path(config_path)

    if not config_file.exists():
        raise ConfigLoadError(
            f"Configuration file not found: {config_path}\n"
            f"Expected location: .openneuro-studies/config.yaml\n"
            f"See documentation for setup instructions."
        )

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigLoadError(f"Invalid YAML in {config_path}: {e}") from e
    except Exception as e:
        raise ConfigLoadError(f"Failed to read {config_path}: {e}") from e

    if config_data is None:
        raise ConfigLoadError(f"Configuration file is empty: {config_path}")

    try:
        config = OpenNeuroStudiesConfig(**config_data)
    except ValidationError as e:
        raise ConfigLoadError(f"Configuration validation failed:\n{e}") from e

    # Validate environment variables for access tokens
    for source in config.sources:
        if source.access_token_env:
            if not os.getenv(source.access_token_env):
                raise ConfigLoadError(
                    f"Environment variable {source.access_token_env} not set "
                    f"(required for source: {source.name})"
                )

    return config


def create_example_config(output_path: str = ".openneuro-studies/config.yaml") -> None:
    """Create an example configuration file.

    Args:
        output_path: Where to write the example config

    Raises:
        ConfigLoadError: If file cannot be written
    """
    example_config = {
        "github_org": "OpenNeuroStudies",
        "sources": [
            {
                "name": "OpenNeuroDatasets",
                "organization_url": "https://github.com/OpenNeuroDatasets",
                "type": "raw",
                "inclusion_patterns": ["^ds\\d{6}$"],
                "access_token_env": "GITHUB_TOKEN",
            },
            {
                "name": "OpenNeuroDerivatives",
                "organization_url": "https://github.com/OpenNeuroDerivatives",
                "type": "derivative",
                "inclusion_patterns": ["^ds\\d{6}$"],
                "access_token_env": "GITHUB_TOKEN",
            },
        ],
    }

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(example_config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise ConfigLoadError(f"Failed to write example config to {output_path}: {e}") from e
