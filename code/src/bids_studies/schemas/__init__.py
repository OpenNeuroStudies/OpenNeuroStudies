"""JSON sidecar schemas for hierarchical TSV files."""

from pathlib import Path

SCHEMAS_DIR = Path(__file__).parent


def get_schema_path(name: str) -> Path:
    """Get path to a schema file.

    Args:
        name: Schema name (e.g., "sourcedata+subjects")

    Returns:
        Path to the JSON schema file
    """
    return SCHEMAS_DIR / f"{name}.json"
