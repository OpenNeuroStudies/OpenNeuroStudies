"""Study organization orchestration.

High-level functions for organizing OpenNeuro datasets into study structures.
"""

from pathlib import Path
from typing import Optional, Union

import datalad.api as dl

from openneuro_studies.config import OpenNeuroStudiesConfig
from openneuro_studies.models import DerivativeDataset, SourceDataset
from openneuro_studies.organization.study_creator import create_study_dataset
from openneuro_studies.organization.submodule_linker import link_submodule

__all__ = [
    "organize_study",
    "OrganizationError",
]


class OrganizationError(Exception):
    """Raised when study organization fails."""

    pass


def organize_study(
    dataset: Union[SourceDataset, DerivativeDataset],
    config: OpenNeuroStudiesConfig,
    parent_path: Optional[Path] = None,
) -> Path:
    """Organize a dataset into study structure.

    Determines the appropriate organization strategy based on dataset type:
    - Single raw dataset -> Create study-{id} and link raw dataset
    - Derivative with single source -> Link under raw's derivatives/
    - Derivative with multiple sources -> Create study-{id} and link all sources

    Args:
        dataset: Dataset to organize (raw or derivative)
        config: OpenNeuroStudies configuration
        parent_path: Parent directory for study datasets (default: current dir)

    Returns:
        Path to organized study dataset

    Raises:
        OrganizationError: If organization fails

    Examples:
        >>> from openneuro_studies.models import SourceDataset
        >>> from openneuro_studies.config import load_config
        >>> config = load_config(".openneuro-studies/config.yaml")
        >>> dataset = SourceDataset(
        ...     dataset_id="ds000001",
        ...     url="https://github.com/OpenNeuroDatasets/ds000001",
        ...     commit_sha="f8e27ac909e50b5b5e311f6be271f0b1757ebb7b",
        ...     bids_version="1.0.0"
        ... )
        >>> study_path = organize_study(dataset, config)
        >>> print(study_path)
        study-ds000001
    """
    if parent_path is None:
        parent_path = Path.cwd()

    try:
        # Determine organization strategy
        if isinstance(dataset, SourceDataset):
            # Single raw dataset -> create study
            return _organize_raw_dataset(dataset, config, parent_path)
        elif isinstance(dataset, DerivativeDataset):
            # Derivative -> check source count
            if len(dataset.source_datasets) == 1:
                # Single source -> link under raw's derivatives/
                return _organize_single_source_derivative(dataset, config, parent_path)
            else:
                # Multiple sources -> create study
                return _organize_multi_source_derivative(dataset, config, parent_path)
        else:
            raise OrganizationError(f"Unknown dataset type: {type(dataset)}")

    except Exception as e:
        raise OrganizationError(f"Failed to organize {dataset.dataset_id}: {e}") from e


def _organize_raw_dataset(
    dataset: SourceDataset,
    config: OpenNeuroStudiesConfig,
    parent_path: Path,
) -> Path:
    """Organize a single raw dataset.

    Creates study-{id} directory and links raw dataset as sourcedata/raw submodule.

    Args:
        dataset: Raw dataset to organize
        config: Configuration
        parent_path: Parent directory

    Returns:
        Path to study dataset
    """
    study_id = f"study-{dataset.dataset_id}"
    github_org = config.github_org

    # Create study dataset
    study_path = create_study_dataset(study_id, github_org, parent_path)

    # Link raw dataset as sourcedata/raw
    link_submodule(
        parent_repo=study_path,
        submodule_path="sourcedata/raw",
        url=str(dataset.url),
        commit_sha=dataset.commit_sha,
        submodule_name=f"{dataset.dataset_id}-raw",
        datalad_id=None,  # TODO: Extract from .datalad/config if available
    )

    # Save changes
    ds = dl.Dataset(str(study_path))
    ds.save(
        message=f"Link raw dataset {dataset.dataset_id}\n\n"
        f"Added sourcedata/raw submodule pointing to {dataset.url} @ {dataset.commit_sha[:8]}"
    )

    return study_path


def _organize_single_source_derivative(
    dataset: DerivativeDataset,
    config: OpenNeuroStudiesConfig,
    parent_path: Path,
) -> Path:
    """Organize a derivative with single source.

    Links derivative under the raw dataset's derivatives/ directory.
    Creates study-{raw_id} if it doesn't exist.

    Args:
        dataset: Derivative dataset to organize
        config: Configuration
        parent_path: Parent directory

    Returns:
        Path to study dataset containing the derivative
    """
    # Get source dataset ID
    source_id = dataset.source_datasets[0]
    study_id = f"study-{source_id}"
    github_org = config.github_org

    # Create study if it doesn't exist
    study_path = create_study_dataset(study_id, github_org, parent_path)

    # Link derivative under derivatives/{tool}-{version}/
    derivative_path = f"derivatives/{dataset.tool_name}-{dataset.version}"
    link_submodule(
        parent_repo=study_path,
        submodule_path=derivative_path,
        url=dataset.dataset_id,  # TODO: Get actual URL from discovery
        commit_sha="HEAD",  # TODO: Get actual commit SHA from discovery
        submodule_name=f"{dataset.dataset_id}",
        datalad_id=dataset.datalad_uuid,
    )

    # Save changes
    ds = dl.Dataset(str(study_path))
    ds.save(
        message=f"Link derivative {dataset.derivative_id}\n\n"
        f"Added {derivative_path} submodule for {dataset.tool_name} {dataset.version}"
    )

    return study_path


def _organize_multi_source_derivative(
    dataset: DerivativeDataset,
    config: OpenNeuroStudiesConfig,
    parent_path: Path,
) -> Path:
    """Organize a derivative with multiple sources.

    Creates study-{deriv_id} and links all source datasets plus the derivative.

    Args:
        dataset: Derivative dataset with multiple sources
        config: Configuration
        parent_path: Parent directory

    Returns:
        Path to study dataset
    """
    # Use derivative ID as study ID for multi-source derivatives
    study_id = f"study-{dataset.derivative_id}"
    github_org = config.github_org

    # Create study dataset
    study_path = create_study_dataset(study_id, github_org, parent_path)

    # Link all source datasets under sourcedata/
    for source_id in dataset.source_datasets:
        source_path = f"sourcedata/{source_id}"
        link_submodule(
            parent_repo=study_path,
            submodule_path=source_path,
            url=f"https://github.com/OpenNeuroDatasets/{source_id}",  # TODO: Get from discovery
            commit_sha="HEAD",  # TODO: Get actual commit SHA
            submodule_name=f"{source_id}-raw",
            datalad_id=None,  # TODO: Extract if available
        )

    # Link derivative under derivatives/
    derivative_path = f"derivatives/{dataset.tool_name}-{dataset.version}"
    link_submodule(
        parent_repo=study_path,
        submodule_path=derivative_path,
        url=dataset.dataset_id,  # TODO: Get actual URL
        commit_sha="HEAD",  # TODO: Get actual commit SHA
        submodule_name=f"{dataset.dataset_id}",
        datalad_id=dataset.datalad_uuid,
    )

    # Save changes
    ds = dl.Dataset(str(study_path))
    ds.save(
        message=f"Link multi-source derivative {dataset.derivative_id}\n\n"
        f"Added {len(dataset.source_datasets)} source datasets and derivative {dataset.tool_name}"
    )

    return study_path
