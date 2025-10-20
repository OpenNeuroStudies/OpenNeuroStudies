"""Study organization orchestration.

High-level functions for organizing OpenNeuro datasets into study structures.
"""

import subprocess
from pathlib import Path
from typing import Optional, Union

from openneuro_studies.config import OpenNeuroStudiesConfig
from openneuro_studies.models import DerivativeDataset, SourceDataset
from openneuro_studies.organization.locks import study_lock
from openneuro_studies.organization.study_creator import create_study_dataset
from openneuro_studies.organization.submodule_linker import link_submodule

__all__ = [
    "organize_study",
    "OrganizationError",
]


class OrganizationError(Exception):
    """Raised when study organization fails."""

    pass


def _git_commit_gitlink(repo_path: Path, commit_message: str) -> None:
    """Commit gitlinks without specifying paths.

    IMPORTANT: Do NOT specify paths when committing gitlinks!
    - git update-index adds the gitlink to the index (mode 160000)
    - But there's no directory on disk (we don't clone)
    - Committing with explicit paths fails because git looks in worktree
    - Solution: Commit without paths - commits everything in the index

    Args:
        repo_path: Path to git repository
        commit_message: Commit message

    Raises:
        OrganizationError: If commit fails
    """
    try:
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "commit",
                "-m",
                commit_message,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise OrganizationError(
            f"Failed to commit gitlink in {repo_path}: {e.stderr if e.stderr else str(e)}"
        ) from e


def organize_study(
    dataset: Union[SourceDataset, DerivativeDataset],
    config: OpenNeuroStudiesConfig,
    parent_path: Optional[Path] = None,
    discovered_datasets: Optional[dict[str, Union[SourceDataset, DerivativeDataset]]] = None,
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
        discovered_datasets: Optional lookup dictionary (dataset_id -> dataset)
                           for resolving source dataset URLs/commits

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
                return _organize_multi_source_derivative(
                    dataset, config, parent_path, discovered_datasets
                )
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

    Raises:
        OrganizationError: If linking fails; cleans up orphaned study directory
    """
    study_id = f"study-{dataset.dataset_id}"
    github_org = config.github_org

    # Create study dataset
    study_path = create_study_dataset(study_id, github_org, parent_path)

    try:
        # Use per-study lock to prevent race conditions when multiple workers
        # try to modify the same study (e.g., raw + derivative)
        with study_lock(study_path):
            # Link raw dataset as sourcedata/raw
            link_submodule(
                parent_repo=study_path,
                submodule_path="sourcedata/raw",
                url=str(dataset.url),
                commit_sha=dataset.commit_sha,
                submodule_name=f"{dataset.dataset_id}-raw",
                datalad_id=None,  # TODO: Extract from .datalad/config if available
            )

            # Commit the submodule changes using git directly
            # (DataLad's save() doesn't handle gitlinks created via update-index properly)
            _git_commit_gitlink(
                study_path,
                f"Link raw dataset {dataset.dataset_id}\n\n"
                f"Added sourcedata/raw submodule pointing to {dataset.url} @ {dataset.commit_sha[:8]}",
            )

            # Create empty directory for the gitlink to prevent "deleted" status
            # Git requires the directory to exist for submodules, even if not cloned
            (study_path / "sourcedata" / "raw").mkdir(parents=True, exist_ok=True)

        # Register the study dataset as a submodule in the parent repository
        # IMPORTANT: Must be done AFTER committing changes in the study repo
        _register_study_in_parent(study_path, study_id, github_org)

        return study_path

    except Exception as e:
        # Clean up orphaned study directory if linking failed
        # import shutil
        # if study_path.exists():
        #     shutil.rmtree(study_path)
        raise OrganizationError(f"Failed to link raw dataset for {study_id}: {e}") from e


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

    # Use per-study lock to prevent race conditions when multiple workers
    # try to modify the same study (e.g., raw + derivative)
    with study_lock(study_path):
        # Link derivative under derivatives/{tool}-{version}/
        derivative_path = f"derivatives/{dataset.tool_name}-{dataset.version}"
        link_submodule(
            parent_repo=study_path,
            submodule_path=derivative_path,
            url=dataset.url,
            commit_sha=dataset.commit_sha,
            submodule_name=dataset.dataset_id,  # Use derivative's own dataset ID (e.g., ds006143)
            datalad_id=dataset.datalad_uuid,
        )

        # Commit the submodule changes using git directly
        # (DataLad's save() doesn't handle gitlinks created via update-index properly)
        _git_commit_gitlink(
            study_path,
            f"Link derivative {dataset.derivative_id}\n\n"
            f"Added {derivative_path} submodule for {dataset.tool_name} {dataset.version}",
        )

        # Create empty directory for the gitlink to prevent "deleted" status
        # Git requires the directory to exist for submodules, even if not cloned
        (study_path / derivative_path).mkdir(parents=True, exist_ok=True)

    # Register the study dataset as a submodule in the parent repository
    _register_study_in_parent(study_path, study_id, github_org)

    return study_path


def _organize_multi_source_derivative(
    dataset: DerivativeDataset,
    config: OpenNeuroStudiesConfig,
    parent_path: Path,
    discovered_datasets: Optional[dict[str, Union[SourceDataset, DerivativeDataset]]] = None,
) -> Path:
    """Organize a derivative with multiple sources.

    Creates study-{dataset_id} and links all source datasets plus the derivative.

    Args:
        dataset: Derivative dataset with multiple sources
        config: Configuration
        parent_path: Parent directory
        discovered_datasets: Optional lookup dictionary for resolving source info

    Returns:
        Path to study dataset

    Raises:
        OrganizationError: If linking fails; cleans up orphaned study directory
    """
    # Use dataset_id (repository name) as study ID for multi-source derivatives
    # E.g., ds006189 (not tedana-24.0.2)
    study_id = f"study-{dataset.dataset_id}"
    github_org = config.github_org

    # Create study dataset
    study_path = create_study_dataset(study_id, github_org, parent_path)

    try:
        # Use per-study lock to prevent race conditions
        with study_lock(study_path):
            # Track all submodule paths for later commit
            submodule_paths = [".gitmodules"]

            # Link all source datasets under sourcedata/
            for source_id in dataset.source_datasets:
                source_path = f"sourcedata/{source_id}"

                # Look up source dataset info from discovered datasets
                # IMPORTANT: We must have the actual commit SHA, not "HEAD"
                # Git update-index --cacheinfo requires a real 40-char hex SHA
                if not discovered_datasets or source_id not in discovered_datasets:
                    raise OrganizationError(
                        f"Source dataset {source_id} not found in discovered datasets. "
                        f"Multi-source derivatives require all sources to be discovered first."
                    )

                source_dataset = discovered_datasets[source_id]
                source_url = str(source_dataset.url)
                source_commit = source_dataset.commit_sha
                source_datalad_id = None

                # Get datalad_uuid if the source is a derivative
                if isinstance(source_dataset, DerivativeDataset):
                    source_datalad_id = source_dataset.datalad_uuid

                link_submodule(
                    parent_repo=study_path,
                    submodule_path=source_path,
                    url=source_url,
                    commit_sha=source_commit,
                    submodule_name=f"{source_id}",  # Use source_id directly (can be raw or derivative)
                    datalad_id=source_datalad_id,
                )
                submodule_paths.append(source_path)

            # Link derivative under derivatives/
            derivative_path = f"derivatives/{dataset.tool_name}-{dataset.version}"
            link_submodule(
                parent_repo=study_path,
                submodule_path=derivative_path,
                url=dataset.url,
                commit_sha=dataset.commit_sha,
                submodule_name=f"{dataset.dataset_id}",
                datalad_id=dataset.datalad_uuid,
            )
            submodule_paths.append(derivative_path)

            # Commit the submodule changes using git directly
            # (DataLad's save() doesn't handle gitlinks created via update-index properly)
            _git_commit_gitlink(
                study_path,
                f"Link multi-source derivative {dataset.derivative_id}\n\n"
                f"Added {len(dataset.source_datasets)} source datasets and derivative {dataset.tool_name}",
            )

            # Create empty directories for all gitlinks to prevent "deleted" status
            # Git requires the directories to exist for submodules, even if not cloned
            for source_id in dataset.source_datasets:
                (study_path / "sourcedata" / source_id).mkdir(parents=True, exist_ok=True)
            (study_path / derivative_path).mkdir(parents=True, exist_ok=True)

        # Register the study dataset as a submodule in the parent repository
        _register_study_in_parent(study_path, study_id, github_org)

        return study_path

    except Exception as e:
        # Clean up orphaned study directory if linking failed
        # import shutil
        # if study_path.exists():
        #     shutil.rmtree(study_path)
        raise OrganizationError(f"Failed to link submodules for {study_id}: {e}") from e


def _register_study_in_parent(study_path: Path, study_id: str, github_org: str) -> None:
    """Register a study dataset as a submodule in the parent repository.

    NOTE: This only adds the submodule to .gitmodules and git index.
    The parent repository commit should be done separately in a batch operation
    to avoid git index.lock conflicts with parallel workers.

    Args:
        study_path: Path to the study dataset
        study_id: Study identifier (e.g., "study-ds000001")
        github_org: GitHub organization for study repository URL

    Raises:
        OrganizationError: If registration fails
    """
    parent_repo = study_path.parent

    # Get current HEAD commit SHA of the study
    try:
        if result := subprocess.run(
            ["git", "-C", str(study_path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ):
            study_commit_sha = result.stdout.strip()
    except subprocess.CalledProcessError as e:
        raise OrganizationError(f"Failed to get study commit SHA: {e}") from e

    # Link study as submodule in parent using configured GitHub org
    study_url = f"https://github.com/{github_org}/{study_id}.git"

    # Get DataLad ID from study's .datalad/config
    datalad_id = None
    if (datalad_config := study_path / ".datalad" / "config").exists():
        try:
            if (
                result := subprocess.run(
                    ["git", "config", "-f", str(datalad_config), "datalad.dataset.id"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            ).returncode == 0:
                datalad_id = result.stdout.strip()
        except Exception:
            pass  # DataLad ID is optional

    link_submodule(
        parent_repo=parent_repo,
        submodule_path=study_id,
        url=study_url,
        commit_sha=study_commit_sha,
        submodule_name=study_id,
        datalad_id=datalad_id,
    )

    # Create empty directory for the study gitlink to prevent "deleted" status
    # Git requires the directory to exist for submodules, even if not cloned
    (parent_repo / study_id).mkdir(parents=True, exist_ok=True)
