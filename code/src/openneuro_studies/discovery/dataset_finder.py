"""Dataset discovery from GitHub/Forgejo organizations."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

from openneuro_studies.config import OpenNeuroStudiesConfig
from openneuro_studies.models import DerivativeDataset, SourceDataset
from openneuro_studies.utils import GitHubAPIError, GitHubClient

logger = logging.getLogger(__name__)


class DatasetDiscoveryError(Exception):
    """Raised when dataset discovery fails."""

    pass


class DatasetFinder:
    """Discovers datasets from configured sources without cloning.

    Attributes:
        config: OpenNeuroStudies configuration
        github_client: GitHub API client
        test_dataset_filter: Optional list of dataset IDs to filter for testing
    """

    def __init__(
        self,
        config: OpenNeuroStudiesConfig,
        github_client: Optional[GitHubClient] = None,
        test_dataset_filter: Optional[List[str]] = None,
        max_workers: int = 10,
    ):
        """Initialize dataset finder.

        Args:
            config: OpenNeuroStudies configuration
            github_client: GitHub API client (creates new if None)
            test_dataset_filter: Optional list of dataset IDs for testing
                                (e.g., ["ds000001", "ds005256"])
            max_workers: Maximum number of parallel workers for dataset processing (default: 10)
        """
        self.config = config
        # Create GitHub client with connection pool sized for parallel workers
        # Use max_workers * 2 to account for potential connection reuse patterns
        self.github_client = github_client or GitHubClient(max_connections=max(max_workers * 2, 50))
        self.test_dataset_filter = test_dataset_filter
        self.max_workers = max_workers

    def discover_all(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, List[Union[SourceDataset, DerivativeDataset]]]:
        """Discover all datasets from configured sources.

        Args:
            progress_callback: Optional callback function called for each processed dataset
                             with the dataset ID as argument

        Returns:
            Dictionary with 'raw' and 'derivative' keys containing lists of datasets

        Raises:
            DatasetDiscoveryError: If discovery fails
        """
        discovered: Dict[str, List[Union[SourceDataset, DerivativeDataset]]] = {
            "raw": [],
            "derivative": [],
        }

        for source_spec in self.config.sources:
            try:
                # Extract organization name from URL
                org_path: Any = source_spec.organization_url.path
                org_name = str(org_path).strip("/")

                # List repositories with optional filtering
                repos = self.github_client.list_repositories(
                    org_name, dataset_filter=self.test_dataset_filter
                )

                # Filter by inclusion/exclusion patterns
                filtered_repos = self._filter_repos(repos, source_spec.inclusion_patterns)
                if source_spec.exclusion_patterns:
                    filtered_repos = [
                        r
                        for r in filtered_repos
                        if not any(
                            re.match(pattern, r["name"])
                            for pattern in source_spec.exclusion_patterns
                        )
                    ]

                # Process repositories in parallel using ThreadPoolExecutor
                # This is I/O-bound work (GitHub API calls), so threading provides speedup
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    # Submit all processing tasks
                    future_to_repo = {
                        executor.submit(self._process_dataset, org_name, repo): repo
                        for repo in filtered_repos
                    }

                    # Collect results as they complete
                    for future in as_completed(future_to_repo):
                        repo = future_to_repo[future]
                        try:
                            dataset = future.result()
                            if dataset:
                                if isinstance(dataset, DerivativeDataset):
                                    discovered["derivative"].append(dataset)
                                elif isinstance(dataset, SourceDataset):
                                    discovered["raw"].append(dataset)

                            # Call progress callback if provided
                            if progress_callback:
                                progress_callback(repo["name"])
                        except Exception as e:
                            # Log error but continue with other datasets
                            logger.warning("Failed to process dataset %s: %s", repo["name"], e)
                            if progress_callback:
                                progress_callback(repo["name"])

            except GitHubAPIError as e:
                raise DatasetDiscoveryError(
                    f"Failed to discover from {source_spec.name}: {e}"
                ) from e

        return discovered

    def _process_dataset(
        self, org_name: str, repo: Dict
    ) -> Optional[Union[SourceDataset, DerivativeDataset]]:
        """Process a dataset repository, determining type from dataset_description.json.

        This method fetches dataset_description.json ONCE and determines whether
        the dataset is raw or derivative based on the DatasetType field, ensuring
        efficient API usage (FR-017a).

        Args:
            org_name: GitHub organization name
            repo: Repository dictionary from GitHub API

        Returns:
            SourceDataset or DerivativeDataset instance, or None if processing fails
        """
        try:
            # Get current commit SHA
            commit_sha = self.github_client.get_default_branch_sha(org_name, repo["name"])

            # Fetch dataset_description.json once
            try:
                desc_json = self.github_client.get_file_content(
                    org_name, repo["name"], "dataset_description.json", ref=commit_sha
                )
                desc = json.loads(desc_json)
            except GitHubAPIError:
                # File not found or invalid - skip this dataset
                return None

            # Check DatasetType to determine if derivative or raw
            if desc.get("DatasetType") == "derivative":
                # Process as derivative
                return self._create_derivative_from_desc(repo, commit_sha, desc)
            else:
                # Process as raw dataset (DatasetType is optional for raw, defaults to "raw")
                return self._create_source_from_desc(repo, commit_sha, desc)

        except Exception as e:
            logger.debug("Failed to process dataset %s: %s", repo["name"], e)
            return None

    def _create_source_from_desc(
        self, repo: Dict, commit_sha: str, desc: Dict
    ) -> SourceDataset:
        """Create SourceDataset from already-fetched dataset_description.json.

        Args:
            repo: Repository dictionary from GitHub API
            commit_sha: Git commit SHA
            desc: Parsed dataset_description.json content

        Returns:
            SourceDataset instance
        """
        return SourceDataset(
            dataset_id=repo["name"],
            url=repo["clone_url"],
            commit_sha=commit_sha,
            bids_version=desc.get("BIDSVersion", "unknown"),
            license=desc.get("License"),
            authors=desc.get("Authors", []),
        )

    def _create_derivative_from_desc(
        self, repo: Dict, commit_sha: str, desc: Dict
    ) -> Optional[DerivativeDataset]:
        """Create DerivativeDataset from already-fetched dataset_description.json.

        Args:
            repo: Repository dictionary from GitHub API
            commit_sha: Git commit SHA
            desc: Parsed dataset_description.json content

        Returns:
            DerivativeDataset instance or None if required fields missing
        """
        # Extract tool name and version from GeneratedBy
        generated_by = desc.get("GeneratedBy", [])
        if not generated_by:
            return None

        tool_info = generated_by[0]
        tool_name = tool_info.get("Name", "unknown")
        version = tool_info.get("Version", "unknown")

        # Extract source datasets
        source_datasets = self._extract_source_dataset_ids(desc.get("SourceDatasets", []))
        if not source_datasets:
            return None

        # Use repository name as dataset_id (e.g., "ds006143" for the derivative dataset)
        # This is the actual OpenNeuro dataset ID for the derivative, not the source
        dataset_id = repo["name"]

        # TODO: Fetch DataLad UUID from .datalad/config via GitHub API
        # The UUID is needed for disambiguation when multiple derivative datasets
        # exist with the same tool-version combination.
        datalad_uuid = None

        # Generate derivative_id (without UUID, uses tool-version)
        from openneuro_studies.models import generate_derivative_id

        derivative_id = generate_derivative_id(tool_name, version, datalad_uuid, [])

        return DerivativeDataset(
            dataset_id=dataset_id,
            derivative_id=derivative_id,
            tool_name=tool_name,
            version=version,
            url=repo["clone_url"],
            commit_sha=commit_sha,
            datalad_uuid=datalad_uuid,
            source_datasets=source_datasets,
        )

    def _filter_repos(self, repos: List[Dict], patterns: List[str]) -> List[Dict]:
        """Filter repositories by inclusion patterns.

        Args:
            repos: List of repository dictionaries
            patterns: List of regex patterns to match

        Returns:
            Filtered list of repositories
        """
        if not patterns or patterns == [".*"]:
            return repos

        filtered = []
        for repo in repos:
            if any(re.match(pattern, repo["name"]) for pattern in patterns):
                filtered.append(repo)
        return filtered

    def _extract_source_dataset_ids(self, source_datasets: List[Union[str, Dict]]) -> List[str]:
        """Extract OpenNeuro dataset IDs from SourceDatasets field.

        BIDS SourceDatasets can be either strings or objects with URL/DOI fields.

        Args:
            source_datasets: List of source dataset references (strings, or dicts with URL/DOI)

        Returns:
            List of extracted dataset IDs (e.g., ["ds000001"])
        """
        dataset_ids = []
        for source in source_datasets:
            # Handle both string format and dict format (BIDS spec)
            if isinstance(source, dict):
                # Try URL first, then DOI
                source_str = source.get("URL") or source.get("DOI") or ""
            else:
                source_str = source

            # Try to extract ds[0-9]+ pattern from URLs or DOIs
            if (match := re.search(r"(ds\d{6})", source_str)):
                dataset_ids.append(match.group(1))
        return dataset_ids

    def save_discovered(
        self, discovered: Dict[str, List], output_path: str = "discovered-datasets.json"
    ) -> None:
        """Save discovered datasets to JSON file.

        Datasets are sorted by dataset_id (primary) and url (secondary) within
        each category (raw, derivative) for deterministic output (FR-038).

        Args:
            discovered: Dictionary with 'raw' and 'derivative' datasets
            output_path: Path to output file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Sort datasets by dataset_id, then url (FR-038)
        raw_sorted = sorted(discovered["raw"], key=lambda d: (d.dataset_id, d.url))
        derivative_sorted = sorted(discovered["derivative"], key=lambda d: (d.dataset_id, d.url))

        # Convert to serializable format (mode='json' handles Pydantic types like HttpUrl)
        serializable = {
            "raw": [d.model_dump(mode="json") for d in raw_sorted],
            "derivative": [d.model_dump(mode="json") for d in derivative_sorted],
        }

        with open(output_file, "w") as f:
            json.dump(serializable, f, indent=2)
