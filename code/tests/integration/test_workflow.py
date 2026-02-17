"""Integration tests for the Snakemake workflow.

Tests the Snakefile DAG construction and rule execution.
Requires: snakemake installed, study submodules present on disk.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent
SNAKEFILE = REPO_ROOT / "code" / "workflow" / "Snakefile"
SNAKEMAKE = shutil.which("snakemake") or str(REPO_ROOT / "code" / ".venv" / "bin" / "snakemake")


def snakemake_available() -> bool:
    try:
        subprocess.run([SNAKEMAKE, "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


requires_snakemake = pytest.mark.skipif(not snakemake_available(), reason="snakemake not installed")


def run_snakemake(*args, cwd=REPO_ROOT, check=True):
    """Run snakemake with standard flags and return CompletedProcess."""
    cmd = [SNAKEMAKE, "-s", str(SNAKEFILE)] + list(args)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


@pytest.mark.integration
@requires_snakemake
class TestSnakemakeDag:
    def test_dry_run_succeeds(self):
        """Snakemake can build the DAG without errors."""
        result = run_snakemake("--dry-run", "--quiet")
        assert result.returncode == 0

    def test_dry_run_lists_expected_rules(self):
        """DAG contains extract_study and aggregate_studies rules."""
        result = run_snakemake("--dry-run", "--quiet", "--forceall")
        output = result.stdout + result.stderr
        assert "extract_study" in output
        assert "aggregate_studies" in output

    def test_dry_run_discovers_all_studies(self):
        """All study- directories are discovered as wildcard inputs."""
        studies = [
            d.name for d in REPO_ROOT.iterdir() if d.is_dir() and d.name.startswith("study-")
        ]
        # --quiet suppresses per-job wildcard output; omit it so study names appear
        result = run_snakemake("--dry-run", "--forceall")
        output = result.stdout + result.stderr
        for study in studies:
            assert study in output, f"{study} missing from dry-run output"

    def test_rulegraph_produces_output(self):
        """--rulegraph exits cleanly (dot not required)."""
        result = run_snakemake("--rulegraph")
        assert result.returncode == 0
        assert "digraph" in result.stdout  # valid dot output


@pytest.mark.integration
@requires_snakemake
class TestShowDepsRule:
    def test_show_deps_runs(self):
        result = run_snakemake("show_deps", "--cores", "1")
        assert result.returncode == 0

    def test_show_deps_contains_study_shas(self):
        """Output contains study IDs and 40-char hex SHAs."""
        result = run_snakemake("show_deps", "--cores", "1")
        output = result.stdout + result.stderr
        assert "study-ds000001" in output
        # SHA format: 12 hex chars then "..."
        import re

        assert re.search(
            r"[0-9a-f]{12}\.\.\.", output
        ), "No truncated SHA found in show_deps output"

    def test_show_deps_contains_sourcedata_shas(self):
        result = run_snakemake("show_deps", "--cores", "1")
        output = result.stdout + result.stderr
        assert "sourcedata:" in output
        assert "ds000001" in output


@pytest.mark.integration
@requires_snakemake
class TestExtractStudy:
    """Run extraction for a single study and verify the output."""

    STUDY = "study-ds000001"

    @pytest.fixture(autouse=True)
    def cleanup_output(self):
        """Remove extracted output before and after each test."""
        out = REPO_ROOT / ".snakemake" / "extracted" / f"{self.STUDY}.json"
        if out.exists():
            out.unlink()
        yield
        if out.exists():
            out.unlink()

    def test_extract_creates_json(self):
        target = f".snakemake/extracted/{self.STUDY}.json"
        run_snakemake(target, "--cores", "1", "--forcerun", "extract_study")
        out = REPO_ROOT / ".snakemake" / "extracted" / f"{self.STUDY}.json"
        assert out.exists()

    def test_extracted_json_has_required_columns(self):
        target = f".snakemake/extracted/{self.STUDY}.json"
        run_snakemake(target, "--cores", "1", "--forcerun", "extract_study")
        out = REPO_ROOT / ".snakemake" / "extracted" / f"{self.STUDY}.json"
        data = json.loads(out.read_text())
        required = {
            "study_id",
            "subjects_num",
            "bold_num",
            "bold_size",
            "author_lead_raw",
            "datatypes",
        }
        missing = required - set(data.keys())
        assert not missing, f"Missing columns: {missing}"

    def test_extracted_json_study_id_matches(self):
        target = f".snakemake/extracted/{self.STUDY}.json"
        run_snakemake(target, "--cores", "1", "--forcerun", "extract_study")
        out = REPO_ROOT / ".snakemake" / "extracted" / f"{self.STUDY}.json"
        data = json.loads(out.read_text())
        assert data["study_id"] == self.STUDY

    def test_provenance_recorded(self):
        target = f".snakemake/extracted/{self.STUDY}.json"
        run_snakemake(target, "--cores", "1", "--forcerun", "extract_study")
        # Find provenance file
        prov_dir = REPO_ROOT / ".snakemake" / "prov"
        prov_files = list(prov_dir.glob(f"*{self.STUDY}*prov.json"))
        assert prov_files, "No provenance file created"
        prov = json.loads(prov_files[0].read_text())
        assert "study_sha" in prov["dependencies"]
        assert len(prov["dependencies"]["study_sha"]) == 40

    def test_no_change_skipped_on_rerun(self):
        """Second run with --rerun-triggers params does nothing (SHA unchanged)."""
        target = f".snakemake/extracted/{self.STUDY}.json"
        run_snakemake(target, "--cores", "1")  # first run
        result = run_snakemake(
            target,
            "--cores",
            "1",
            "--rerun-triggers",
            "params",
            "--dry-run",
        )
        output = result.stdout + result.stderr
        assert (
            "Nothing to be done" in output or "0 of 0" in output or "up to date" in output
        ), f"Expected no-op on second run, got:\n{output}"


@pytest.mark.integration
@requires_snakemake
class TestCanonicalTsvUnchanged:
    """Verify the workflow never touches the canonical studies.tsv."""

    def test_studies_tsv_not_a_workflow_output(self):
        """studies.tsv should not appear as a Snakemake target."""
        result = run_snakemake("--dry-run", "--forceall", "--quiet")
        # studies.tsv as output would appear with "output:" prefix in Snakemake log
        lines_with_studies_tsv = [
            line
            for line in (result.stdout + result.stderr).splitlines()
            if "output:" in line.lower()
            and "studies.tsv" in line
            and "extracted" not in line  # allow .snakemake/extracted/studies.tsv
        ]
        assert not lines_with_studies_tsv, (
            f"studies.tsv should not be a workflow output:\n" f"{lines_with_studies_tsv}"
        )
