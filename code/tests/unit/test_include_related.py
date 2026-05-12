"""Unit tests for bidirectional filter expansion (--include-related).

Tests the RelationType enum, _discover_all_derivatives helper,
_expand_filter_with_sources, _expand_filter_with_related,
backward compatibility with include_derivatives=True,
session-level memoization, and persistent derivative graph cache.
"""

import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from openneuro_studies.config import OpenNeuroStudiesConfig, SourceSpecification
from openneuro_studies.discovery.dataset_finder import (
    DatasetFinder,
    RelationType,
)
from openneuro_studies.models import DerivativeDataset, SourceDataset


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(org_url: str = "https://github.com/TestOrg") -> OpenNeuroStudiesConfig:
    """Create a minimal config with one source."""
    return OpenNeuroStudiesConfig(
        sources=[
            SourceSpecification(
                name="TestOrg",
                organization_url=org_url,
                type="derivative",
            )
        ]
    )


def _make_derivative(
    dataset_id: str,
    source_datasets: List[str],
    tool_name: str = "fmriprep",
    version: str = "21.0.1",
) -> DerivativeDataset:
    """Create a DerivativeDataset for testing."""
    return DerivativeDataset(
        dataset_id=dataset_id,
        derivative_id=f"{tool_name}-{version}",
        tool_name=tool_name,
        version=version,
        url=f"https://github.com/TestOrg/{dataset_id}.git",
        commit_sha="a" * 40,
        source_datasets=source_datasets,
    )


def _make_source(dataset_id: str) -> SourceDataset:
    """Create a SourceDataset for testing."""
    return SourceDataset(
        dataset_id=dataset_id,
        url=f"https://github.com/TestOrg/{dataset_id}.git",
        commit_sha="b" * 40,
        bids_version="1.8.0",
    )


def _make_finder(
    config: Optional[OpenNeuroStudiesConfig] = None,
    test_filter: Optional[List[str]] = None,
    include_derivatives: bool = False,
    include_related: Optional[set] = None,
) -> DatasetFinder:
    """Create a DatasetFinder with a mock GitHub client."""
    cfg = config or _make_config()
    mock_client = MagicMock()
    return DatasetFinder(
        config=cfg,
        github_client=mock_client,
        test_dataset_filter=test_filter,
        include_derivatives=include_derivatives,
        include_related=include_related,
        max_workers=2,
    )


# ---------------------------------------------------------------------------
# RelationType enum
# ---------------------------------------------------------------------------

class TestRelationType:
    """Tests for the RelationType enum."""

    def test_enum_values(self) -> None:
        assert RelationType.DERIVATIVES.value == "derivatives"
        assert RelationType.SOURCES.value == "sources"
        assert RelationType.ALL.value == "all"

    def test_string_conversion(self) -> None:
        assert str(RelationType.DERIVATIVES) == "RelationType.DERIVATIVES"
        assert RelationType.DERIVATIVES == "derivatives"
        assert RelationType.SOURCES == "sources"
        assert RelationType.ALL == "all"

    def test_enum_membership(self) -> None:
        assert "derivatives" in [e.value for e in RelationType]
        assert "sources" in [e.value for e in RelationType]
        assert "all" in [e.value for e in RelationType]

    def test_enum_from_string(self) -> None:
        assert RelationType("derivatives") == RelationType.DERIVATIVES
        assert RelationType("sources") == RelationType.SOURCES
        assert RelationType("all") == RelationType.ALL


# ---------------------------------------------------------------------------
# _discover_all_derivatives (shared helper)
# ---------------------------------------------------------------------------

class TestDiscoverAllDerivatives:
    """Tests for the shared _discover_all_derivatives helper."""

    def test_discovers_derivatives_from_all_sources(self) -> None:
        """Verify the helper scans all sources and collects derivatives."""
        deriv_a = _make_derivative("ds000001-fmriprep", ["ds000001"])
        deriv_b = _make_derivative("ds000002-mriqc", ["ds000002"], tool_name="mriqc")

        finder = _make_finder(test_filter=["ds000001"])
        finder.force_rescan = True  # Skip disk cache

        # Mock _process_dataset to return different results per repo
        repo_results = {
            "ds000001-fmriprep": deriv_a,
            "ds000002-mriqc": deriv_b,
            "ds000003": _make_source("ds000003"),  # raw, not derivative
        }
        finder._process_dataset = MagicMock(
            side_effect=lambda org, repo: repo_results.get(repo["name"])
        )
        finder.github_client.list_repositories.return_value = [
            {"name": name} for name in repo_results
        ]

        result = finder._discover_all_derivatives()

        assert len(result) == 2
        ids = {d.dataset_id for d in result}
        assert ids == {"ds000001-fmriprep", "ds000002-mriqc"}

    def test_empty_sources(self) -> None:
        """Config with no sources yields no derivatives."""
        cfg = OpenNeuroStudiesConfig(sources=[])
        finder = _make_finder(config=cfg, test_filter=["ds000001"])
        finder.force_rescan = True  # Skip disk cache
        result = finder._discover_all_derivatives()
        assert result == []


# ---------------------------------------------------------------------------
# _expand_filter_with_sources
# ---------------------------------------------------------------------------

class TestExpandFilterWithSources:
    """Tests for backward (sources) expansion."""

    def test_adds_source_datasets(self) -> None:
        """When filter contains a derivative, its sources should be added."""
        # ds000001-fmriprep has source ds000001
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])

        finder = _make_finder(test_filter=["ds000001-fmriprep"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_sources()

        assert set(result) == {"ds000001-fmriprep", "ds000001"}

    def test_multi_source_derivative(self) -> None:
        """A derivative with multiple sources should add all of them."""
        deriv = _make_derivative(
            "ds006190", ["ds006189", "ds006185", "ds006131"],
            tool_name="analysis", version="1.0.0",
        )

        finder = _make_finder(test_filter=["ds006190"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_sources()

        assert set(result) == {"ds006190", "ds006189", "ds006185", "ds006131"}

    def test_transitive_source_chain(self) -> None:
        """Sources of sources should be found transitively."""
        # ds000001-fmriprep -> ds000001
        # ds000001 is itself a derivative of ds999999 (hypothetical chain)
        deriv_a = _make_derivative("ds000001-fmriprep", ["ds000001"])
        deriv_b = _make_derivative("ds000001", ["ds999999"], tool_name="chain", version="1.0")

        finder = _make_finder(test_filter=["ds000001-fmriprep"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv_a, deriv_b]):
            result = finder._expand_filter_with_sources()

        assert set(result) == {"ds000001-fmriprep", "ds000001", "ds999999"}

    def test_empty_filter_returns_empty(self) -> None:
        """Empty filter should return empty list."""
        finder = _make_finder(test_filter=None)
        result = finder._expand_filter_with_sources()
        assert result == []

    def test_no_matching_derivatives(self) -> None:
        """When no derivatives match the filter, return original filter."""
        deriv = _make_derivative("ds000099-fmriprep", ["ds000099"])

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_sources()

        # ds000001 is not a derivative, so no sources are added
        assert set(result) == {"ds000001"}


# ---------------------------------------------------------------------------
# _expand_filter_with_related (orchestrator)
# ---------------------------------------------------------------------------

class TestExpandFilterWithRelated:
    """Tests for the bidirectional orchestrator."""

    def test_derivatives_mode(self) -> None:
        """'derivatives' mode should delegate to _expand_filter_with_derivatives."""
        finder = _make_finder(test_filter=["ds000001"])

        with patch.object(
            finder, "_expand_filter_with_derivatives",
            return_value=["ds000001", "ds000001-fmriprep"],
        ) as mock_expand:
            result = finder._expand_filter_with_related(include_related={"derivatives"})

        mock_expand.assert_called_once()
        assert set(result) == {"ds000001", "ds000001-fmriprep"}

    def test_sources_mode(self) -> None:
        """'sources' mode should delegate to _expand_filter_with_sources."""
        finder = _make_finder(test_filter=["ds000001-fmriprep"])

        with patch.object(
            finder, "_expand_filter_with_sources",
            return_value=["ds000001-fmriprep", "ds000001"],
        ) as mock_expand:
            result = finder._expand_filter_with_related(include_related={"sources"})

        mock_expand.assert_called_once()
        assert set(result) == {"ds000001-fmriprep", "ds000001"}

    def test_all_mode_normalizes_to_both_directions(self) -> None:
        """'all' mode should expand both forward and backward."""
        # ds000001-fmriprep has sources [ds000001, ds999999]
        # Starting from ds000001: forward finds ds000001-fmriprep, backward adds ds999999
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001", "ds999999"])

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_related(include_related={"all"})

        assert set(result) == {"ds000001", "ds000001-fmriprep", "ds999999"}

    def test_bidirectional_transitive_closure(self) -> None:
        """Bidirectional expansion should reach transitive closure.

        Scenario:
        - Start with ds000001
        - Forward: ds000001 -> ds000001-fmriprep (derivative)
        - Backward: ds000001-fmriprep has source ds000002 (multi-source)
        - Forward again: ds000002 -> ds000002-mriqc
        """
        deriv_fmriprep = _make_derivative("ds000001-fmriprep", ["ds000001", "ds000002"])
        deriv_mriqc = _make_derivative("ds000002-mriqc", ["ds000002"], tool_name="mriqc")
        all_derivs = [deriv_fmriprep, deriv_mriqc]

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=all_derivs):
            result = finder._expand_filter_with_related(include_related={"all"})

        # Should find: ds000001, ds000001-fmriprep, ds000002, ds000002-mriqc
        assert set(result) == {"ds000001", "ds000001-fmriprep", "ds000002", "ds000002-mriqc"}

    def test_empty_filter_returns_empty(self) -> None:
        """Empty filter should return empty list."""
        finder = _make_finder(test_filter=None)
        result = finder._expand_filter_with_related(include_related={"all"})
        assert result == []

    def test_no_derivatives_found(self) -> None:
        """When no derivatives exist, return original filter."""
        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[]):
            result = finder._expand_filter_with_related(include_related={"all"})
        assert set(result) == {"ds000001"}


# ---------------------------------------------------------------------------
# Backward compatibility: include_derivatives=True
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    """Tests that include_derivatives=True still works when include_related is not set."""

    def test_include_derivatives_flag_uses_legacy_path(self) -> None:
        """include_derivatives=True should trigger _expand_filter_with_derivatives."""
        finder = _make_finder(
            test_filter=["ds000001"],
            include_derivatives=True,
        )
        assert finder.include_derivatives is True
        assert finder.include_related == set()

        # Mock the expansion to verify it's called from discover_all
        with patch.object(
            finder, "_expand_filter_with_derivatives",
            return_value=["ds000001", "ds000001-fmriprep"],
        ) as mock_expand:
            # Mock the main discovery loop to avoid real API calls
            finder.config = OpenNeuroStudiesConfig(sources=[])
            finder.discover_all()

        mock_expand.assert_called_once()

    def test_include_related_takes_precedence(self) -> None:
        """When both are set, include_related takes precedence."""
        finder = _make_finder(
            test_filter=["ds000001"],
            include_derivatives=True,
            include_related={"sources"},
        )

        # include_related is set, so _expand_filter_with_related should be used
        with patch.object(
            finder, "_expand_filter_with_related",
            return_value=["ds000001"],
        ) as mock_related, patch.object(
            finder, "_expand_filter_with_derivatives",
        ) as mock_derivs:
            finder.config = OpenNeuroStudiesConfig(sources=[])
            finder.discover_all()

        mock_related.assert_called_once()
        mock_derivs.assert_not_called()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge case tests for filter expansion."""

    def test_empty_filter_list(self) -> None:
        """An empty list (not None) for test_dataset_filter."""
        finder = _make_finder(test_filter=[])
        # Empty list is falsy, so no expansion should occur
        result = finder._expand_filter_with_derivatives()
        assert result == []

    def test_filter_already_contains_derivative(self) -> None:
        """If derivative is already in filter, should still add its sources."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])

        # Both the derivative and the raw dataset are already in the filter
        finder = _make_finder(test_filter=["ds000001", "ds000001-fmriprep"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_derivatives()

        # No new datasets, just the same ones
        assert set(result) == {"ds000001", "ds000001-fmriprep"}

    def test_circular_reference_terminates(self) -> None:
        """If derivatives reference each other, the loop should terminate."""
        # Hypothetical circular case (shouldn't happen in practice)
        deriv_a = _make_derivative("ds000001", ["ds000002"], tool_name="a", version="1")
        deriv_b = _make_derivative("ds000002", ["ds000001"], tool_name="b", version="1")

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv_a, deriv_b]):
            result = finder._expand_filter_with_sources()

        # Should resolve: ds000001 -> source ds000002, ds000002 -> source ds000001
        # Both already in set, terminates
        assert set(result) == {"ds000001", "ds000002"}

    def test_no_sources_in_derivative(self) -> None:
        """DerivativeDataset model requires min_length=1 for source_datasets,
        but test with single source that doesn't match filter."""
        deriv = _make_derivative("ds999999-fmriprep", ["ds888888"])

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            result = finder._expand_filter_with_derivatives()

        # ds999999-fmriprep sources don't overlap with filter -> not added
        assert set(result) == {"ds000001"}

    def test_progress_callback_called(self) -> None:
        """Verify that progress callbacks are invoked during expansion."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])
        callback = MagicMock()

        finder = _make_finder(test_filter=["ds000001"])
        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            finder._expand_filter_with_sources(progress_callback=callback)

        # At least the "expand" phase should be reported
        assert callback.call_count > 0
        phases = [call.args[0] for call in callback.call_args_list]
        assert "expand" in phases


# ---------------------------------------------------------------------------
# Session-level memoization
# ---------------------------------------------------------------------------

class TestSessionMemoization:
    """Tests for _discover_all_derivatives session-level caching."""

    def test_scan_runs_only_once(self) -> None:
        """Calling _discover_all_derivatives multiple times should scan only once."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])

        finder = _make_finder(test_filter=["ds000001"])
        finder._process_dataset = MagicMock(return_value=deriv)
        finder.github_client.list_repositories.return_value = [
            {"name": "ds000001-fmriprep"}
        ]
        # Ensure no disk cache is used
        finder.force_rescan = True

        result1 = finder._discover_all_derivatives()
        result2 = finder._discover_all_derivatives()
        result3 = finder._discover_all_derivatives()

        # list_repositories should only have been called once (during the first scan)
        assert finder.github_client.list_repositories.call_count == 1
        assert len(result1) == 1
        assert result1 is result2  # Same object, not a copy
        assert result2 is result3

    def test_cache_cleared_on_new_instance(self) -> None:
        """A new DatasetFinder instance should not reuse another's session cache."""
        finder1 = _make_finder(test_filter=["ds000001"])
        finder1._cached_all_derivatives = [_make_derivative("ds000001-fmriprep", ["ds000001"])]

        finder2 = _make_finder(test_filter=["ds000001"])
        assert finder2._cached_all_derivatives is None


# ---------------------------------------------------------------------------
# Persistent derivative graph cache
# ---------------------------------------------------------------------------

class TestPersistentCache:
    """Tests for persistent disk cache of derivative graph."""

    def test_save_and_load_roundtrip(self, tmp_path) -> None:
        """Cache save then load should return equivalent derivatives."""
        derivs = [
            _make_derivative("ds000001-fmriprep", ["ds000001"]),
            _make_derivative("ds000002-mriqc", ["ds000002"], tool_name="mriqc"),
        ]

        finder = _make_finder(test_filter=["ds000001"])
        cache_file = tmp_path / "derivative_graph.json"
        # Override cache file path
        type(finder)._cache_file = property(lambda self: cache_file)

        finder._save_derivative_graph_cache(derivs)
        assert cache_file.exists()

        loaded = finder._load_derivative_graph_cache()
        assert loaded is not None
        assert len(loaded) == 2
        assert {d.dataset_id for d in loaded} == {"ds000001-fmriprep", "ds000002-mriqc"}

    def test_load_returns_none_when_missing(self, tmp_path) -> None:
        """Loading from nonexistent file should return None."""
        finder = _make_finder()
        cache_file = tmp_path / "nonexistent.json"
        type(finder)._cache_file = property(lambda self: cache_file)

        assert finder._load_derivative_graph_cache() is None

    def test_load_returns_none_on_version_mismatch(self, tmp_path) -> None:
        """Cache with wrong version should be ignored."""
        finder = _make_finder()
        cache_file = tmp_path / "derivative_graph.json"
        type(finder)._cache_file = property(lambda self: cache_file)

        cache_file.write_text(json.dumps({
            "version": 999,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "derivatives_count": 0,
            "derivatives": [],
        }))

        assert finder._load_derivative_graph_cache() is None

    def test_load_returns_none_on_expired_ttl(self, tmp_path) -> None:
        """Cache older than TTL should be ignored."""
        finder = _make_finder()
        cache_file = tmp_path / "derivative_graph.json"
        type(finder)._cache_file = property(lambda self: cache_file)

        # Write cache with old timestamp (48 hours ago)
        old_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        cache_file.write_text(json.dumps({
            "version": 1,
            "timestamp": old_time.isoformat(),
            "derivatives_count": 0,
            "derivatives": [],
        }))

        assert finder._load_derivative_graph_cache() is None

    def test_force_rescan_bypasses_disk_cache(self, tmp_path) -> None:
        """force_rescan=True should skip disk cache and do a full scan."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])

        finder = _make_finder(test_filter=["ds000001"])
        cache_file = tmp_path / "derivative_graph.json"
        type(finder)._cache_file = property(lambda self: cache_file)

        # Pre-populate valid disk cache
        finder._save_derivative_graph_cache([deriv])
        assert cache_file.exists()

        # Set up mock for a fresh scan
        finder.force_rescan = True
        finder._process_dataset = MagicMock(return_value=deriv)
        finder.github_client.list_repositories.return_value = [
            {"name": "ds000001-fmriprep"}
        ]

        result = finder._discover_all_derivatives()

        # Should have scanned (called list_repositories), not loaded from cache
        finder.github_client.list_repositories.assert_called_once()
        assert len(result) == 1

    def test_load_returns_none_on_corrupt_json(self, tmp_path) -> None:
        """Corrupted JSON should return None without raising."""
        finder = _make_finder()
        cache_file = tmp_path / "derivative_graph.json"
        type(finder)._cache_file = property(lambda self: cache_file)

        cache_file.write_text("not valid json {{{")

        assert finder._load_derivative_graph_cache() is None


# ---------------------------------------------------------------------------
# Bidirectional closure (direct algorithm, no mutation)
# ---------------------------------------------------------------------------

class TestBidirectionalClosure:
    """Tests for the restructured bidirectional closure algorithm."""

    def test_does_not_mutate_test_dataset_filter(self) -> None:
        """Bidirectional expansion should not mutate self.test_dataset_filter."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001", "ds000002"])

        finder = _make_finder(test_filter=["ds000001"])
        original_filter = finder.test_dataset_filter.copy()

        with patch.object(finder, "_discover_all_derivatives", return_value=[deriv]):
            finder._expand_filter_with_related(include_related={"all"})

        assert finder.test_dataset_filter == original_filter

    def test_bidirectional_closure_uses_direct_algorithm(self) -> None:
        """Bidirectional expansion should call _discover_all_derivatives once,
        not delegate to _expand_filter_with_derivatives/_sources."""
        deriv = _make_derivative("ds000001-fmriprep", ["ds000001"])

        finder = _make_finder(test_filter=["ds000001"])

        with patch.object(
            finder, "_discover_all_derivatives", return_value=[deriv]
        ) as mock_discover, patch.object(
            finder, "_expand_filter_with_derivatives"
        ) as mock_fwd, patch.object(
            finder, "_expand_filter_with_sources"
        ) as mock_bwd:
            result = finder._expand_filter_with_related(include_related={"all"})

        mock_discover.assert_called_once()
        mock_fwd.assert_not_called()
        mock_bwd.assert_not_called()
        assert set(result) == {"ds000001", "ds000001-fmriprep"}
