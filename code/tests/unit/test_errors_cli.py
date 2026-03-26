#!/usr/bin/env python3
"""Unit tests for error analysis CLI commands."""

import json
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from openneuro_studies.cli.errors import errors


@pytest.fixture
def runner():
    """Create Click CLI test runner."""
    return CliRunner()


def run_in_dir(runner, command_group, command_args, directory):
    """Run a Click command in a specific directory.

    CliRunner doesn't support changing working directory, so we use os.chdir().
    """
    original_cwd = os.getcwd()
    try:
        os.chdir(str(directory))
        # Verify we're in the right directory
        assert os.getcwd() == str(directory), f"chdir failed: {os.getcwd()} != {directory}"
        return runner.invoke(command_group, command_args, catch_exceptions=False)
    finally:
        os.chdir(original_cwd)


class TestAnalyzeQuality:
    """Tests for analyze-quality command."""

    def test_no_extraction_data(self, runner, tmp_path):
        """Test with no extraction data."""
        result = run_in_dir(runner, errors, ["analyze-quality"], tmp_path)

        assert result.exit_code == 0
        assert "No extraction JSON files found" in result.output
        assert ".snakemake/extracted" in result.output

    def test_single_complete_study(self, runner, tmp_path):
        """Test with single study having complete metrics."""
        # Create extraction data
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        study = {
            "subjects_num": 16,
            "bold_num": 10,
            "t1w_num": 16,
            "bold_voxels_total": 1000000,
            "bold_voxels_mean": 100000,
            "bold_duration_total": 500.0,
            "bold_duration_mean": 50.0,
        }
        (extracted_dir / "study-ds000001.json").write_text(json.dumps(study))

        result = run_in_dir(runner, errors, ["analyze-quality", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Analyzed 1 studies" in result.output
        assert "complete" in result.output

    def test_study_with_missing_metrics(self, runner, tmp_path):
        """Test with study missing all imaging metrics."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        study = {
            "subjects_num": 10,
            "bold_num": 5,
            "t1w_num": 10,
            "bold_voxels_total": "n/a",
            "bold_voxels_mean": "n/a",
            "bold_duration_total": "n/a",
            "bold_duration_mean": "n/a",
        }
        (extracted_dir / "study-ds000002.json").write_text(json.dumps(study))

        result = run_in_dir(runner, errors, ["analyze-quality", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "missing_imaging_metrics" in result.output
        assert "study-ds000002" in result.output
        assert "No remote URL" in result.output

    def test_study_with_partial_metrics(self, runner, tmp_path):
        """Test with study having partial imaging metrics."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        study = {
            "subjects_num": 8,
            "bold_num": 4,
            "t1w_num": 8,
            "bold_voxels_total": 500000,
            "bold_voxels_mean": 125000,
            "bold_duration_total": "n/a",
            "bold_duration_mean": "n/a",
        }
        (extracted_dir / "study-ds000003.json").write_text(json.dumps(study))

        result = run_in_dir(runner, errors, ["analyze-quality", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "partial_imaging_metrics" in result.output
        assert "study-ds000003" in result.output
        assert "2/4" in result.output

    def test_study_with_no_bold(self, runner, tmp_path):
        """Test with study having no BOLD data."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        study = {
            "subjects_num": 5,
            "bold_num": 0,
            "t1w_num": 5,
        }
        (extracted_dir / "study-ds000004.json").write_text(json.dumps(study))

        result = run_in_dir(runner, errors, ["analyze-quality", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "no_bold" in result.output

    def test_multiple_studies_mixed_status(self, runner, tmp_path):
        """Test with multiple studies having different statuses."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        # Complete study
        study1 = {
            "subjects_num": 10,
            "bold_num": 5,
            "t1w_num": 10,
            "bold_voxels_total": 1000000,
            "bold_voxels_mean": 200000,
            "bold_duration_total": 300.0,
            "bold_duration_mean": 60.0,
        }
        (extracted_dir / "study-ds000001.json").write_text(json.dumps(study1))

        # Missing metrics
        study2 = {
            "subjects_num": 8,
            "bold_num": 3,
            "t1w_num": 8,
            "bold_voxels_total": "n/a",
            "bold_voxels_mean": "n/a",
            "bold_duration_total": "n/a",
            "bold_duration_mean": "n/a",
        }
        (extracted_dir / "study-ds000002.json").write_text(json.dumps(study2))

        # No BOLD
        study3 = {"subjects_num": 3, "bold_num": 0, "t1w_num": 3}
        (extracted_dir / "study-ds000003.json").write_text(json.dumps(study3))

        result = run_in_dir(runner, errors, ["analyze-quality", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Analyzed 3 studies" in result.output
        assert "complete" in result.output
        assert "missing_imaging_metrics" in result.output
        assert "no_bold" in result.output

    def test_tsv_output_format(self, runner, tmp_path):
        """Test TSV output format."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        study = {"subjects_num": 5, "bold_num": 3, "t1w_num": 5}
        (extracted_dir / "study-test.json").write_text(json.dumps(study))

        output_file = tmp_path / "output.tsv"
        result = run_in_dir(runner, errors, ["analyze-quality", "--output", str(output_file)], tmp_path)

        assert result.exit_code == 0
        assert output_file.exists()

        # Verify TSV format
        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row

        # Check header
        assert "study_id\tstatus\tsubjects_num" in lines[0]

        # Check data row
        assert "study-test" in lines[1]
        assert "\t" in lines[1]

    def test_invalid_json_handling(self, runner, tmp_path):
        """Test handling of invalid JSON files."""
        extracted_dir = tmp_path / ".snakemake" / "extracted"
        extracted_dir.mkdir(parents=True)

        # Write invalid JSON
        (extracted_dir / "study-invalid.json").write_text("{ invalid json")

        # Write valid JSON
        study = {"subjects_num": 1, "bold_num": 1, "t1w_num": 1}
        (extracted_dir / "study-valid.json").write_text(json.dumps(study))

        result = run_in_dir(runner, errors, ["analyze-quality"], tmp_path)

        assert result.exit_code == 0
        assert "Warning: Failed to analyze" in result.output
        assert "study-invalid.json" in result.output


class TestAnalyzeLegacy:
    """Tests for analyze-legacy command."""

    def test_no_error_logs(self, runner, tmp_path):
        """Test with no error log files."""
        result = run_in_dir(runner, errors, ["analyze-legacy"], tmp_path)

        assert result.exit_code == 0
        assert "No extraction_errors.log files found" in result.output
        assert "errors.jsonl" in result.output

    def test_single_error_log(self, runner, tmp_path):
        """Test with single error log file."""
        study_dir = tmp_path / "study-ds001506" / "sourcedata"
        study_dir.mkdir(parents=True)

        error_log = """ds001506: Extraction completed with 100 errors across 10 subjects (error rate: 100.0%).

Failed to extract from sub-01: No remote URL found for file
Failed to extract from sub-02: No remote URL found for file
Failed to extract from sub-03: Network connection timeout
"""
        (study_dir / "extraction_errors.log").write_text(error_log)

        result = run_in_dir(runner, errors, ["analyze-legacy", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Found 1 studies with extraction errors" in result.output
        assert "ds001506" in result.output
        assert "100" in result.output
        assert "10" in result.output
        assert "100.0%" in result.output

    def test_error_categorization(self, runner, tmp_path):
        """Test error categorization by type."""
        study_dir = tmp_path / "study-test" / "sourcedata"
        study_dir.mkdir(parents=True)

        error_log = """dstest: Extraction completed with 50 errors across 5 subjects (error rate: 100.0%).

Failed to extract: No remote URL found
Failed to extract: Network connection failed
Failed to extract: Permission denied accessing file
Failed to extract: git-annex error occurred
Failed to extract: Unknown error
"""
        (study_dir / "extraction_errors.log").write_text(error_log)

        result = run_in_dir(runner, errors, ["analyze-legacy", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Error Breakdown by Type" in result.output
        assert "missing_remote_url" in result.output
        assert "network_error" in result.output
        assert "permission_error" in result.output
        assert "git_annex_error" in result.output
        assert "other" in result.output

    def test_multiple_error_logs_sorted(self, runner, tmp_path):
        """Test multiple error logs sorted by error count."""
        # Study with many errors
        study1_dir = tmp_path / "study-ds000001" / "sourcedata"
        study1_dir.mkdir(parents=True)
        log1 = "ds000001: Extraction completed with 500 errors across 50 subjects (error rate: 100.0%)."
        (study1_dir / "extraction_errors.log").write_text(log1)

        # Study with few errors
        study2_dir = tmp_path / "study-ds000002" / "sourcedata"
        study2_dir.mkdir(parents=True)
        log2 = "ds000002: Extraction completed with 10 errors across 5 subjects (error rate: 20.0%)."
        (study2_dir / "extraction_errors.log").write_text(log2)

        result = run_in_dir(runner, errors, ["analyze-legacy", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Found 2 studies" in result.output

        # Check sorting (study with more errors should appear first)
        output_lines = result.output.split("\n")
        ds1_line = next(i for i, line in enumerate(output_lines) if "ds000001" in line)
        ds2_line = next(i for i, line in enumerate(output_lines) if "ds000002" in line)
        assert ds1_line < ds2_line

    def test_top_5_problematic_datasets(self, runner, tmp_path):
        """Test top 5 problematic datasets section."""
        # Create 6 studies with different error counts
        for i in range(1, 7):
            study_dir = tmp_path / f"study-ds00000{i}" / "sourcedata"
            study_dir.mkdir(parents=True)
            error_count = i * 100
            log = f"ds00000{i}: Extraction completed with {error_count} errors across {i*10} subjects (error rate: 100.0%).\nFailed to extract: test error"
            (study_dir / "extraction_errors.log").write_text(log)

        result = run_in_dir(runner, errors, ["analyze-legacy", "--format", "table"], tmp_path)

        assert result.exit_code == 0
        assert "Top 5 Most Problematic Datasets" in result.output

        # Should only show top 5
        output_text = result.output
        top_5_section = output_text[output_text.index("Top 5"):]
        assert "1." in top_5_section
        assert "5." in top_5_section
        # ds000006 (highest) should be #1
        assert "study-ds000006" in top_5_section

    def test_tsv_output_format(self, runner, tmp_path):
        """Test TSV output format."""
        study_dir = tmp_path / "study-test" / "sourcedata"
        study_dir.mkdir(parents=True)
        error_log = "dstest: Extraction completed with 50 errors across 5 subjects (error rate: 100.0%)."
        (study_dir / "extraction_errors.log").write_text(error_log)

        output_file = tmp_path / "output.tsv"
        result = run_in_dir(runner, errors, ["analyze-legacy", "--output", str(output_file)], tmp_path)

        assert result.exit_code == 0
        assert output_file.exists()

        # Verify TSV format
        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 2  # Header + 1 data row

        # Check header
        assert "study_id\tdataset_id\ttotal_errors" in lines[0]

        # Check data row
        assert "study-test\tdstest\t50\t5\t100.0" in lines[1]

    def test_malformed_log_handling(self, runner, tmp_path):
        """Test handling of malformed log files."""
        # Malformed log (missing header)
        study1_dir = tmp_path / "study-malformed" / "sourcedata"
        study1_dir.mkdir(parents=True)
        (study1_dir / "extraction_errors.log").write_text("Some random text without header")

        # Valid log
        study2_dir = tmp_path / "study-valid" / "sourcedata"
        study2_dir.mkdir(parents=True)
        valid_log = "dsvalid: Extraction completed with 10 errors across 2 subjects (error rate: 50.0%)."
        (study2_dir / "extraction_errors.log").write_text(valid_log)

        result = run_in_dir(runner, errors, ["analyze-legacy"], tmp_path)

        assert result.exit_code == 0
        # Should process valid log despite malformed one
        assert "dsvalid" in result.output or "Found 1 studies" in result.output

    def test_empty_error_log(self, runner, tmp_path):
        """Test handling of empty error log files."""
        study_dir = tmp_path / "study-empty" / "sourcedata"
        study_dir.mkdir(parents=True)
        (study_dir / "extraction_errors.log").write_text("")

        result = run_in_dir(runner, errors, ["analyze-legacy"], tmp_path)

        assert result.exit_code == 0
        # Should handle gracefully (might show 0 errors or skip)
