"""Dataset discovery from GitHub/Forgejo organizations."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from openneuro_studies.config import OpenNeuroStudiesConfig, SourceType
from openneuro_studies.models import DerivativeDataset, SourceDataset
from openneuro_studies.utils import GitHubAPIError, GitHubClient


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
    ):
        """Initialize dataset finder.

        Args:
            config: OpenNeuroStudies configuration
            github_client: GitHub API client (creates new if None)
            test_dataset_filter: Optional list of dataset IDs for testing
                                (e.g., ["ds000001", "ds000010"])
        """
        self.config = config
        self.github_client = github_client or GitHubClient()
        self.test_dataset_filter = test_dataset_filter

    def discover_all(
        self,
    ) -> Dict[str, List[Union[SourceDataset, DerivativeDataset]]]:
        """Discover all datasets from configured sources.

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

                # Process each repository
                for repo in filtered_repos:
                    try:
                        if source_spec.type == SourceType.RAW:
                            dataset = self._process_raw_dataset(org_name, repo)
                            if dataset:
                                discovered["raw"].append(dataset)
                        elif source_spec.type == SourceType.DERIVATIVE:
                            deriv_dataset = self._process_derivative_dataset(org_name, repo)
                            if deriv_dataset:
                                discovered["derivative"].append(deriv_dataset)
                    except Exception as e:
                        # Log error but continue with other datasets
                        print(f"Warning: Failed to process {repo['name']}: {e}")

            except GitHubAPIError as e:
                raise DatasetDiscoveryError(
                    f"Failed to discover from {source_spec.name}: {e}"
                ) from e

        return discovered

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

    def _process_raw_dataset(self, org_name: str, repo: Dict) -> Optional[SourceDataset]:
        """Process a raw dataset repository.

        Args:
            org_name: GitHub organization name
            repo: Repository dictionary from GitHub API

        Returns:
            SourceDataset instance or None if processing fails
        """
        try:
            # Get current commit SHA
            commit_sha = self.github_client.get_default_branch_sha(org_name, repo["name"])

            # Try to get dataset_description.json
            try:
                desc_json = self.github_client.get_file_content(
                    org_name, repo["name"], "dataset_description.json", ref=commit_sha
                )
                desc = json.loads(desc_json)
            except GitHubAPIError:
                # File not found or invalid - skip this dataset
                return None

            return SourceDataset(
                dataset_id=repo["name"],
                url=repo["clone_url"],
                commit_sha=commit_sha,
                bids_version=desc.get("BIDSVersion", "unknown"),
                license=desc.get("License"),
                authors=desc.get("Authors", []),
            )
        except Exception as e:
            print(f"Warning: Failed to process raw dataset {repo['name']}: {e}")
            return None

    def _process_derivative_dataset(self, org_name: str, repo: Dict) -> Optional[DerivativeDataset]:
        """Process a derivative dataset repository.

        Args:
            org_name: GitHub organization name
            repo: Repository dictionary from GitHub API

        Returns:
            DerivativeDataset instance or None if processing fails
        """
        try:
            # Get current commit SHA
            commit_sha = self.github_client.get_default_branch_sha(org_name, repo["name"])

            # Try to get dataset_description.json
            try:
                desc_json = self.github_client.get_file_content(
                    org_name, repo["name"], "dataset_description.json", ref=commit_sha
                )
                desc = json.loads(desc_json)
            except GitHubAPIError:
                return None

            # Check if this is actually a derivative
            if desc.get("DatasetType") != "derivative":
                return None

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

            # For now, use repo name as UUID (will be updated when we have access to .datalad/config)
            # In real implementation, we'd need to clone or use git API to get .datalad/config
            datalad_uuid = f"{repo['name']}-0000-0000-0000-000000000000"

            # Generate derivative_id
            from openneuro_studies.models import generate_derivative_id

            derivative_id = generate_derivative_id(tool_name, version, datalad_uuid, [])

            return DerivativeDataset(
                dataset_id=repo["name"],
                derivative_id=derivative_id,
                tool_name=tool_name,
                version=version,
                datalad_uuid=datalad_uuid,
                source_datasets=source_datasets,
            )
        except Exception as e:
            print(f"Warning: Failed to process derivative dataset {repo['name']}: {e}")
            return None

    def _extract_source_dataset_ids(self, source_datasets: List[str]) -> List[str]:
        """Extract OpenNeuro dataset IDs from SourceDatasets field.

        Args:
            source_datasets: List of source dataset references (URLs, DOIs, etc.)

        Returns:
            List of extracted dataset IDs (e.g., ["ds000001"])
        """
        dataset_ids = []
        for source in source_datasets:
            # Try to extract ds[0-9]+ pattern from URLs or DOIs
            match = re.search(r"(ds\d{6})", source)
            if match:
                dataset_ids.append(match.group(1))
        return dataset_ids

    def save_discovered(
        self, discovered: Dict[str, List], output_path: str = "discovered-datasets.json"
    ) -> None:
        """Save discovered datasets to JSON file.

        Args:
            discovered: Dictionary with 'raw' and 'derivative' datasets
            output_path: Path to output file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format (mode='json' handles Pydantic types like HttpUrl)
        serializable = {
            "raw": [d.model_dump(mode="json") for d in discovered["raw"]],
            "derivative": [d.model_dump(mode="json") for d in discovered["derivative"]],
        }

        with open(output_file, "w") as f:
            json.dump(serializable, f, indent=2)
