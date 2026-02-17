"""Unit tests for workflow/lib/provenance.py.

Pure file I/O — no git or Snakemake required.
All tests use tmp_path and leave no side effects.
"""

import pytest

from workflow.lib.provenance import (
    ProvenanceManager,
    clean_stale_provenance,
    get_provenance_path,
    get_provenance_summary,
)

SAMPLE_DEPS = {
    "study_sha": "abc123def456" * 3 + "abcd",  # 40 chars
    "sourcedata_shas": {"ds000001": "fedcba987654" * 3 + "fedc"},
}


@pytest.fixture
def prov_dir(tmp_path):
    return str(tmp_path / "prov")


@pytest.fixture
def manager(prov_dir):
    return ProvenanceManager(prov_dir)


@pytest.mark.unit
class TestGetProvenancePath:
    def test_slashes_replaced(self, prov_dir):
        path = get_provenance_path("stats/study-ds000001.json", prov_dir)
        assert "/" not in path.name

    def test_ends_with_prov_json(self, prov_dir):
        path = get_provenance_path("output.tsv", prov_dir)
        assert path.name.endswith(".prov.json")

    def test_lives_in_prov_dir(self, prov_dir):
        path = get_provenance_path("output.tsv", prov_dir)
        assert str(path).startswith(prov_dir)


@pytest.mark.unit
class TestProvenanceManagerRecord:
    def test_creates_prov_file(self, manager, prov_dir):
        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        prov_path = get_provenance_path("output.tsv", prov_dir)
        assert prov_path.exists()

    def test_prov_file_is_valid_json(self, manager, prov_dir):
        import json

        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        prov_path = get_provenance_path("output.tsv", prov_dir)
        data = json.loads(prov_path.read_text())
        assert data["output"] == "output.tsv"
        assert data["rule"] == "test_rule"
        assert data["dependencies"] == SAMPLE_DEPS

    def test_initial_history_entry(self, manager, prov_dir):
        import json

        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        prov_path = get_provenance_path("output.tsv", prov_dir)
        data = json.loads(prov_path.read_text())
        assert len(data["history"]) == 1
        assert data["history"][0]["reason"] == "initial"

    def test_second_record_appends_history(self, manager, prov_dir):
        import json

        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        updated_deps = {**SAMPLE_DEPS, "study_sha": "newsha" + "0" * 34}
        manager.record("output.tsv", "test_rule", updated_deps)
        prov_path = get_provenance_path("output.tsv", prov_dir)
        data = json.loads(prov_path.read_text())
        assert len(data["history"]) == 2
        assert data["history"][1]["reason"] == "updated"
        assert data["dependencies"] == updated_deps  # latest deps

    def test_manifest_updated(self, manager, prov_dir):
        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        manifest = manager._load_manifest()
        assert "output.tsv" in manifest["outputs"]

    def test_multiple_outputs(self, manager):
        manager.record("output_a.tsv", "rule_a", SAMPLE_DEPS)
        manager.record("output_b.tsv", "rule_b", SAMPLE_DEPS)
        outputs = manager.list_outputs()
        assert "output_a.tsv" in outputs
        assert "output_b.tsv" in outputs


@pytest.mark.unit
class TestProvenanceManagerGet:
    def test_get_existing(self, manager):
        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        prov = manager.get("output.tsv")
        assert prov is not None
        assert prov["rule"] == "test_rule"

    def test_get_nonexistent_returns_none(self, manager):
        assert manager.get("does-not-exist.tsv") is None


@pytest.mark.unit
class TestProvenanceManagerRemove:
    def test_remove_existing(self, manager, prov_dir):
        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        removed = manager.remove("output.tsv")
        assert removed is True
        prov_path = get_provenance_path("output.tsv", prov_dir)
        assert not prov_path.exists()

    def test_remove_clears_manifest(self, manager):
        manager.record("output.tsv", "test_rule", SAMPLE_DEPS)
        manager.remove("output.tsv")
        assert "output.tsv" not in manager.list_outputs()

    def test_remove_nonexistent_returns_false(self, manager):
        assert manager.remove("does-not-exist.tsv") is False


@pytest.mark.unit
class TestFindStale:
    def test_all_existing_not_stale(self, manager):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        manager.record("b.tsv", "rule", SAMPLE_DEPS)
        stale = manager.find_stale({"a.tsv", "b.tsv"})
        assert stale == []

    def test_missing_output_is_stale(self, manager):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        manager.record("b.tsv", "rule", SAMPLE_DEPS)
        stale = manager.find_stale({"a.tsv"})  # b.tsv missing
        assert "b.tsv" in stale

    def test_empty_existing_all_stale(self, manager):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        stale = manager.find_stale(set())
        assert "a.tsv" in stale


@pytest.mark.unit
class TestCleanStaleProvenance:
    def test_removes_stale(self, manager, prov_dir, tmp_path):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        manager.record("b.tsv", "rule", SAMPLE_DEPS)
        removed = clean_stale_provenance(prov_dir, existing_outputs={"a.tsv"})
        assert "b.tsv" in removed
        assert manager.get("b.tsv") is None

    def test_dry_run_does_not_remove(self, manager, prov_dir):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        removed = clean_stale_provenance(prov_dir, existing_outputs=set(), dry_run=True)
        assert "a.tsv" in removed
        assert manager.get("a.tsv") is not None  # still there

    def test_no_stale_returns_empty(self, manager, prov_dir):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        removed = clean_stale_provenance(prov_dir, existing_outputs={"a.tsv"})
        assert removed == []


@pytest.mark.unit
class TestGetProvenanceSummary:
    def test_empty_dir(self, prov_dir):
        summary = get_provenance_summary(prov_dir)
        assert summary["total_outputs"] == 0
        assert summary["outputs"] == []

    def test_counts_outputs(self, manager, prov_dir):
        manager.record("a.tsv", "rule", SAMPLE_DEPS)
        manager.record("b.tsv", "rule", SAMPLE_DEPS)
        summary = get_provenance_summary(prov_dir)
        assert summary["total_outputs"] == 2
        assert set(summary["outputs"]) == {"a.tsv", "b.tsv"}
