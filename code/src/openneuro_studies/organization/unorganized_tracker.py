"""Tracking for datasets that could not be organized."""

import json
import logging
from pathlib import Path
from typing import Dict, List

import datalad.api as dl

from openneuro_studies.models import UnorganizedDataset

logger = logging.getLogger(__name__)


def load_unorganized_datasets(
    config_dir: Path = Path(".openneuro-studies"),
) -> List[UnorganizedDataset]:
    """Load unorganized datasets from JSON file.

    Args:
        config_dir: Configuration directory containing unorganized-datasets.json

    Returns:
        List of UnorganizedDataset instances
    """
    unorganized_file = config_dir / "unorganized-datasets.json"
    if not unorganized_file.exists():
        return []

    with open(unorganized_file) as f:
        data = json.load(f)

    return [UnorganizedDataset(**item) for item in data.get("unorganized", [])]


def save_unorganized_datasets(
    unorganized: List[UnorganizedDataset],
    config_dir: Path = Path(".openneuro-studies"),
    commit: bool = True,
) -> None:
    """Save unorganized datasets to JSON file.

    Datasets are sorted by dataset_id (primary) and url (secondary) for
    deterministic output (FR-038).

    Args:
        unorganized: List of UnorganizedDataset instances to save
        config_dir: Configuration directory for output file
        commit: Whether to commit changes to .openneuro-studies subdataset (default: True)
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    unorganized_file = config_dir / "unorganized-datasets.json"

    # Sort by dataset_id, then url (FR-038)
    unorganized_sorted = sorted(unorganized, key=lambda d: (d.dataset_id, d.url))

    # Convert to serializable format
    data = {
        "unorganized": [u.model_dump(mode="json") for u in unorganized_sorted],
        "count": len(unorganized_sorted),
    }

    with open(unorganized_file, "w") as f:
        json.dump(data, f, indent=2)

    # Commit to .openneuro-studies subdataset (FR-020a)
    # Use datalad save from top dataset - it will figure out which subdataset changed
    if commit:
        try:
            unorganized_file_abs = unorganized_file.resolve()
            dl.save(
                dataset="^",
                path=str(unorganized_file_abs),
                message=f"Update unorganized datasets\n\n"
                f"Tracked {len(unorganized_sorted)} unorganized datasets\n"
                f"Updated by openneuro-studies organize command",
            )
            logger.info("Committed unorganized-datasets.json to .openneuro-studies subdataset")
        except Exception as e:
            logger.warning(f"Failed to commit unorganized-datasets.json: {e}")


def add_unorganized_dataset(
    dataset: UnorganizedDataset,
    config_dir: Path = Path(".openneuro-studies"),
) -> None:
    """Add a dataset to the unorganized tracking file.

    Loads existing unorganized datasets, appends the new one (avoiding duplicates
    by dataset_id), and saves back to file.

    Args:
        dataset: UnorganizedDataset to track
        config_dir: Configuration directory
    """
    existing = load_unorganized_datasets(config_dir)

    # Check if dataset already tracked (by dataset_id)
    existing_ids = {u.dataset_id for u in existing}
    if dataset.dataset_id not in existing_ids:
        existing.append(dataset)
        save_unorganized_datasets(existing, config_dir)


def get_unorganized_summary(config_dir: Path = Path(".openneuro-studies")) -> Dict[str, int]:
    """Get summary counts of unorganized datasets by reason.

    Args:
        config_dir: Configuration directory

    Returns:
        Dictionary mapping reason codes to counts
    """
    unorganized = load_unorganized_datasets(config_dir)
    summary: Dict[str, int] = {}

    for dataset in unorganized:
        reason = dataset.reason.value
        summary[reason] = summary.get(reason, 0) + 1

    return summary
