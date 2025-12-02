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
        include_derivatives: Whether to include derivatives of filtered datasets
    """

    def __init__(
        self,
        config: OpenNeuroStudiesConfig,
        github_client: Optional[GitHubClient] = None,
        test_dataset_filter: Optional[List[str]] = None,
        include_derivatives: bool = False,
        max_workers: int = 10,
    ):
        """Initialize dataset finder.

        Args:
            config: OpenNeuroStudies configuration
            github_client: GitHub API client (creates new if None)
            test_dataset_filter: Optional list of dataset IDs for testing
                                (e.g., ["ds000001", "ds005256"])
            include_derivatives: When True, automatically include derivatives whose
                               source_datasets intersect with test_dataset_filter.
                               Recursively includes derivatives of derivatives.
            max_workers: Maximum number of parallel workers for dataset processing (default: 10)
        """
        self.config = config
        # Create GitHub client with connection pool sized for parallel workers
        # Use max_workers * 2 to account for potential connection reuse patterns
        self.github_client = github_client or GitHubClient(max_connections=max(max_workers * 2, 50))
        self.test_dataset_filter = test_dataset_filter
        self.include_derivatives = include_derivatives
        self.max_workers = max_workers

    def discover_all(
        self,
        progress_callback: Optional[Callable[[str], None]] = None,
        expansion_progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, List[Union[SourceDataset, DerivativeDataset]]]:
        """Discover all datasets from configured sources.

        When include_derivatives is True and test_dataset_filter is set, this method:
        1. Discovers all datasets from derivative sources (no filter) to find relationships
        2. Expands the filter to include derivatives whose source_datasets intersect
           with the filtered set (recursively, to handle derivatives of derivatives)
        3. Returns only datasets matching the expanded filter

        Args:
            progress_callback: Optional callback function called for each processed dataset
                             with the dataset ID as argument
            expansion_progress_callback: Optional callback(phase, message) for derivative
                                        expansion progress reporting

        Returns:
            Dictionary with 'raw' and 'derivative' keys containing lists of datasets

        Raises:
            DatasetDiscoveryError: If discovery fails
        """
        # If include_derivatives is set, we need to expand the filter
        effective_filter = self.test_dataset_filter
        if self.include_derivatives and self.test_dataset_filter:
            effective_filter = self._expand_filter_with_derivatives(
                progress_callback=expansion_progress_callback
            )
            logger.info(
                "Expanded filter from %d to %d datasets (including derivatives)",
                len(self.test_dataset_filter),
                len(effective_filter),
            )

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
                    org_name, dataset_filter=effective_filter
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

    def _expand_filter_with_derivatives(
        self,
        progress_callback: Optional[Callable[[str, str], None]] = None,
    ) -> List[str]:
        """Expand test_dataset_filter to include derivatives of filtered datasets.

        This method discovers all derivatives (without filter) and then finds which
        ones have source_datasets that intersect with the filtered set. It recursively
        expands to include derivatives of derivatives.

        Args:
            progress_callback: Optional callback(phase, message) for progress reporting

        Returns:
            Expanded list of dataset IDs including derivatives
        """
        if not self.test_dataset_filter:
            return []

        # Start with the original filter set
        expanded_set = set(self.test_dataset_filter)

        # Discover all derivatives from derivative sources to find relationships
        # We need to discover without filter to find all potential derivatives
        all_derivatives: List[DerivativeDataset] = []

        for source_spec in self.config.sources:
            try:
                org_path: Any = source_spec.organization_url.path
                org_name = str(org_path).strip("/")

                if progress_callback:
                    progress_callback("scan", f"Listing repositories from {org_name}...")

                # List ALL repositories (no filter) to find derivatives
                repos = self.github_client.list_repositories(org_name, dataset_filter=None)

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

                if progress_callback:
                    progress_callback(
                        "scan", f"Scanning {len(filtered_repos)} repos in {org_name} for derivatives..."
                    )

                # Process repositories to find derivatives
                processed_count = 0
                with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                    future_to_repo = {
                        executor.submit(self._process_dataset, org_name, repo): repo
                        for repo in filtered_repos
                    }

                    for future in as_completed(future_to_repo):
                        processed_count += 1
                        try:
                            dataset = future.result()
                            if dataset and isinstance(dataset, DerivativeDataset):
                                all_derivatives.append(dataset)
                                if progress_callback:
                                    progress_callback(
                                        "found",
                                        f"[{processed_count}/{len(filtered_repos)}] "
                                        f"Found derivative: {dataset.dataset_id}",
                                    )
                            elif progress_callback and processed_count % 50 == 0:
                                # Report progress every 50 repos
                                progress_callback(
                                    "progress",
                                    f"[{processed_count}/{len(filtered_repos)}] "
                                    f"Scanning {org_name}...",
                                )
                        except Exception as e:
                            logger.debug("Error processing dataset: %s", e)

                if progress_callback:
                    progress_callback(
                        "done", f"Found {len(all_derivatives)} derivatives in {org_name}"
                    )

            except GitHubAPIError as e:
                logger.warning("Failed to list derivatives from %s: %s", source_spec.name, e)

        # Iteratively expand the set to include derivatives whose sources are in the set
        # This handles the derivative-of-derivative case
        if progress_callback:
            progress_callback("expand", "Expanding filter to include related derivatives...")

        changed = True
        while changed:
            changed = False
            for deriv in all_derivatives:
                if deriv.dataset_id not in expanded_set:
                    # Check if any of the derivative's sources are in our set
                    if any(src in expanded_set for src in deriv.source_datasets):
                        expanded_set.add(deriv.dataset_id)
                        changed = True
                        logger.debug(
                            "Added derivative %s (sources: %s)",
                            deriv.dataset_id,
                            deriv.source_datasets,
                        )
                        if progress_callback:
                            progress_callback(
                                "added",
                                f"  + {deriv.dataset_id} (derivative of {', '.join(deriv.source_datasets)})",
                            )

        return list(expanded_set)

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

    def _create_source_from_desc(self, repo: Dict, commit_sha: str, desc: Dict) -> SourceDataset:
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
            if match := re.search(r"(ds\d{6})", source_str):
                dataset_ids.append(match.group(1))
        return dataset_ids

    def save_discovered(
        self,
        discovered: Dict[str, List],
        output_path: str = "discovered-datasets.json",
        mode: str = "update",
    ) -> None:
        """Save discovered datasets to JSON file.

        Datasets are sorted by dataset_id (primary) and url (secondary) within
        each category (raw, derivative) for deterministic output (FR-038).

        Args:
            discovered: Dictionary with 'raw' and 'derivative' datasets
            output_path: Path to output file
            mode: Save mode - 'update' merges with existing, 'overwrite' replaces all
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # If update mode and file exists, load and merge with existing
        if mode == "update" and output_file.exists():
            with open(output_file, "r") as f:
                existing = json.load(f)

            # Merge new datasets with existing, deduplicating by (dataset_id, url) tuple
            # Convert existing JSON to dataset objects for consistent handling
            existing_raw = [SourceDataset(**d) for d in existing.get("raw", [])]
            existing_derivative = [DerivativeDataset(**d) for d in existing.get("derivative", [])]

            # Create sets of (dataset_id, url) tuples for efficient deduplication
            existing_raw_keys = {(d.dataset_id, str(d.url)) for d in existing_raw}
            existing_deriv_keys = {(d.dataset_id, str(d.url)) for d in existing_derivative}

            # Add only truly new datasets
            merged_raw = existing_raw.copy()
            for dataset in discovered["raw"]:
                key = (dataset.dataset_id, str(dataset.url))
                if key not in existing_raw_keys:
                    merged_raw.append(dataset)

            merged_derivative = existing_derivative.copy()
            for dataset in discovered["derivative"]:
                key = (dataset.dataset_id, str(dataset.url))
                if key not in existing_deriv_keys:
                    merged_derivative.append(dataset)

            # Use merged datasets
            raw_to_save = merged_raw
            derivative_to_save = merged_derivative
        else:
            # Overwrite mode or no existing file - use only newly discovered
            raw_to_save = discovered["raw"]
            derivative_to_save = discovered["derivative"]

        # Sort datasets by dataset_id, then url (FR-038)
        raw_sorted = sorted(raw_to_save, key=lambda d: (d.dataset_id, str(d.url)))
        derivative_sorted = sorted(derivative_to_save, key=lambda d: (d.dataset_id, str(d.url)))

        # Convert to serializable format (mode='json' handles Pydantic types like HttpUrl)
        serializable = {
            "raw": [d.model_dump(mode="json") for d in raw_sorted],
            "derivative": [d.model_dump(mode="json") for d in derivative_sorted],
        }

        with open(output_file, "w") as f:
            json.dump(serializable, f, indent=2)
