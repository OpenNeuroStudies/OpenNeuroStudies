# Refactor Error Analysis from Scripts to CLI/Makefile

**Date**: 2026-03-23
**Status**: Planning
**Priority**: High
**Related**: Error tracking implementation (Phase 1)

## Problem Statement

**Current Violation of Project Standards**:
- Created ad-hoc scripts in `code/scripts/`:
  - `analyze_extraction_quality.py`
  - `summarize_extraction_errors.py`
- These scripts bypass the established CLI and Makefile interfaces
- Users must run Python scripts directly (poor UX)
- Not discoverable via `make help` or `openneuro-studies --help`

**Project Requirements** (from CLAUDE.md):
> "Use `make` as the primary interface for all dataset operations"
> "All critical functionality must have a corresponding make target"
> "No custom scripts: Use make targets instead of standalone scripts"

## Design Principles

### Layer 1: CLI Commands (Primary Interface)
- All functionality exposed as `openneuro-studies` subcommands
- Discoverable via `--help`
- Can be used standalone or from Makefile
- Testable and documented

### Layer 2: Makefile Rules (Convenience Interface)
- Common workflows exposed as `make` targets
- Listed in `make help`
- Delegates to CLI commands
- Handles file paths and common options

### No Layer 3 (Scripts)
- ❌ No standalone scripts in `code/scripts/`
- ✅ All logic in importable modules
- ✅ CLI commands for execution
- ✅ Makefile for common patterns

## Proposed Refactoring

### Part 1: Extend CLI with Analysis Commands

#### Option A: Extend `errors` Command Group (Recommended)

```bash
# Current commands
openneuro-studies errors list
openneuro-studies errors summary
openneuro-studies errors resolve
openneuro-studies errors gc

# NEW: Add analysis commands
openneuro-studies errors analyze-quality   # Was: analyze_extraction_quality.py
openneuro-studies errors analyze-legacy    # Was: summarize_extraction_errors.py
```

**Rationale**:
- Natural extension of error tracking
- Keeps all error-related functionality together
- Clear namespace

#### Option B: Create Separate `analyze` Command Group

```bash
openneuro-studies analyze extraction-quality
openneuro-studies analyze extraction-errors
openneuro-studies analyze metadata-coverage
openneuro-studies analyze derivatives
```

**Rationale**:
- More general (can add other analyses later)
- Separates concerns (errors vs analysis)
- Room for growth

**Recommendation**: **Option A** for now (extend `errors`), can refactor to Option B later if analysis grows.

### Part 2: Add Makefile Rules

```makefile
# Error Analysis Targets
.PHONY: errors-summary errors-quality errors-report

errors-summary: ## Show summary of extraction errors across all studies
	@openneuro-studies errors summary

errors-quality: ## Analyze extraction quality (missing imaging metrics)
	@openneuro-studies errors analyze-quality
	@echo ""
	@echo "Detailed report: logs/extraction_quality.tsv"

errors-report: ## Generate comprehensive error report (quality + legacy + current)
	@echo "=== Extraction Quality Analysis ==="
	@openneuro-studies errors analyze-quality
	@echo ""
	@echo "=== Legacy Error Summary ==="
	@openneuro-studies errors analyze-legacy
	@echo ""
	@echo "=== Current Error Tracking ==="
	@openneuro-studies errors summary
	@echo ""
	@echo "Reports written to logs/"
```

### Part 3: Delete Ad-hoc Scripts

Remove:
- `code/scripts/analyze_extraction_quality.py`
- `code/scripts/summarize_extraction_errors.py`

**Migration Path**:
1. Implement CLI commands first
2. Verify functionality matches
3. Update documentation
4. Delete scripts
5. Remove from last commit via `git rebase` or create new commit

## Implementation Plan

### Step 1: Implement CLI Commands (2 hours)

**File**: `code/src/openneuro_studies/cli/errors.py` (MODIFY)

Add two new commands to existing `errors` group:

```python
@errors.command(name="analyze-quality")
@click.option(
    "--format",
    type=click.Choice(["table", "tsv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    type=click.Path(),
    default="logs/extraction_quality.tsv",
    help="Output TSV file path",
)
def analyze_quality(format, output):
    """Analyze extraction quality across all studies.

    Shows which datasets have incomplete imaging metrics (n/a values)
    indicating missing remote URLs or other extraction issues.

    Categories:
      - complete: All imaging metrics extracted
      - partial_imaging_metrics: Some metrics missing
      - missing_imaging_metrics: All metrics missing (likely no remote URLs)
      - no_bold: No BOLD data in dataset
    """
    from pathlib import Path
    from collections import defaultdict
    import json

    # Find all extraction JSON files
    json_files = sorted(Path(".snakemake/extracted").glob("study-*.json"))

    if not json_files:
        click.echo("No extraction JSON files found in .snakemake/extracted/")
        click.echo("Run 'make extract' first to generate metadata.")
        return

    # Analyze all studies
    results = []
    for json_path in json_files:
        try:
            with open(json_path) as f:
                data = json.load(f)

            study_id = json_path.stem

            # Check for n/a values in imaging metrics
            imaging_fields = [
                'bold_voxels_total',
                'bold_voxels_mean',
                'bold_duration_total',
                'bold_duration_mean',
            ]

            missing_imaging = sum(1 for field in imaging_fields if data.get(field) == 'n/a')
            has_bold = data.get('bold_num', 'n/a') != 'n/a' and data.get('bold_num', 0) > 0

            # Determine status
            if missing_imaging == len(imaging_fields) and has_bold:
                status = 'missing_imaging_metrics'
            elif missing_imaging > 0 and has_bold:
                status = 'partial_imaging_metrics'
            elif not has_bold:
                status = 'no_bold'
            else:
                status = 'complete'

            results.append({
                'study_id': study_id,
                'status': status,
                'subjects_num': data.get('subjects_num', 'n/a'),
                'bold_num': data.get('bold_num', 'n/a'),
                't1w_num': data.get('t1w_num', 'n/a'),
                'bold_voxels_mean': data.get('bold_voxels_mean', 'n/a'),
                'bold_duration_mean': data.get('bold_duration_mean', 'n/a'),
                'missing_count': missing_imaging,
            })
        except Exception as e:
            click.echo(f"Warning: Failed to analyze {json_path}: {e}", err=True)

    if not results:
        click.echo("No valid extraction results found.")
        return

    # Group by status
    by_status = defaultdict(list)
    for r in results:
        by_status[r['status']].append(r)

    # Output
    if format == "table":
        click.echo(f"\nAnalyzed {len(results)} studies\n")

        click.echo("## Summary by Status\n")
        click.echo(f"{'Status':<30} {'Count':<10}")
        click.echo("-" * 40)
        for status in ['complete', 'partial_imaging_metrics', 'missing_imaging_metrics', 'no_bold']:
            count = len(by_status[status])
            if count > 0:
                click.echo(f"{status:<30} {count:<10}")

        # Show datasets with missing imaging metrics
        if by_status['missing_imaging_metrics']:
            click.echo(f"\n## Datasets Missing Imaging Metrics ({len(by_status['missing_imaging_metrics'])})\n")
            click.echo("These likely have 'No remote URL' errors for all BOLD files:\n")
            click.echo(f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'T1w Files':<10}")
            click.echo("-" * 67)

            for r in sorted(by_status['missing_imaging_metrics'], key=lambda x: x['study_id']):
                click.echo(
                    f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                    f"{str(r['bold_num']):<12} {str(r['t1w_num']):<10}"
                )

        # Show datasets with partial metrics
        if by_status['partial_imaging_metrics']:
            click.echo(f"\n## Datasets with Partial Imaging Metrics ({len(by_status['partial_imaging_metrics'])})\n")
            click.echo("Some BOLD files have remote URLs, others don't:\n")
            click.echo(f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'Missing Fields':<15}")
            click.echo("-" * 72)

            for r in sorted(by_status['partial_imaging_metrics'], key=lambda x: x['study_id']):
                click.echo(
                    f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                    f"{str(r['bold_num']):<12} {r['missing_count']}/4"
                )

    # Write TSV
    output_path = Path(output)
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w') as f:
        f.write("study_id\tstatus\tsubjects_num\tbold_num\tt1w_num\t"
                "bold_voxels_mean\tbold_duration_mean\n")
        for r in sorted(results, key=lambda x: x['study_id']):
            f.write(
                f"{r['study_id']}\t{r['status']}\t{r['subjects_num']}\t"
                f"{r['bold_num']}\t{r['t1w_num']}\t{r['bold_voxels_mean']}\t"
                f"{r['bold_duration_mean']}\n"
            )

    click.echo(f"\n✓ Detailed report written to: {output_path}")


@errors.command(name="analyze-legacy")
@click.option(
    "--format",
    type=click.Choice(["table", "tsv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    type=click.Path(),
    default="logs/extraction_errors.tsv",
    help="Output TSV file path",
)
def analyze_legacy(format, output):
    """Analyze legacy extraction_errors.log files.

    Summarizes errors from old-format extraction_errors.log files
    across all studies. This command helps transition from legacy
    error logging to the new hierarchical error tracking system.

    Once all studies have errors.jsonl files, use 'errors summary'
    instead of this command.
    """
    from pathlib import Path
    from collections import defaultdict
    import re

    # Find all extraction_errors.log files
    error_logs = sorted(Path('.').glob('study-*/sourcedata/extraction_errors.log'))

    if not error_logs:
        click.echo("No extraction_errors.log files found.")
        click.echo("Either errors haven't occurred or you're using the new errors.jsonl format.")
        click.echo("Try 'openneuro-studies errors summary' instead.")
        return

    # Parse all logs
    results = []
    for log_path in error_logs:
        study_id = log_path.parts[0]

        try:
            with open(log_path) as f:
                content = f.read()

            # Parse header
            dataset_match = re.search(r'^(\w+): Extraction (?:failed|completed)', content, re.MULTILINE)
            dataset_id = dataset_match.group(1) if dataset_match else "unknown"

            errors_match = re.search(r'(\d+) errors across (\d+) subjects', content)
            total_errors = int(errors_match.group(1)) if errors_match else 0
            total_subjects = int(errors_match.group(2)) if errors_match else 0

            rate_match = re.search(r'error rate: ([\d.]+)%', content)
            error_rate = float(rate_match.group(1)) if rate_match else 0.0

            # Extract first few errors
            first_errors = []
            for line in content.split('\n'):
                if 'Failed to extract' in line:
                    first_errors.append(line.strip())
                    if len(first_errors) >= 5:
                        break

            results.append({
                'study_id': study_id,
                'dataset_id': dataset_id,
                'total_errors': total_errors,
                'total_subjects': total_subjects,
                'error_rate': error_rate,
                'first_errors': first_errors,
                'log_path': str(log_path),
            })
        except Exception as e:
            click.echo(f"Warning: Failed to parse {log_path}: {e}", err=True)

    if not results:
        click.echo("No valid error logs found.")
        return

    # Sort by total errors
    results.sort(key=lambda x: x['total_errors'], reverse=True)

    # Output
    if format == "table":
        click.echo(f"\nFound {len(error_logs)} studies with extraction errors\n")

        click.echo("## Studies with Errors (sorted by count)\n")
        click.echo(f"{'Study':<20} {'Dataset':<15} {'Errors':<10} {'Subjects':<10} {'Rate':<10}")
        click.echo("-" * 75)

        total_errors_all = 0
        for r in results:
            click.echo(
                f"{r['study_id']:<20} {r['dataset_id']:<15} {r['total_errors']:<10} "
                f"{r['total_subjects']:<10} {r['error_rate']:.1f}%"
            )
            total_errors_all += r['total_errors']

        click.echo()
        click.echo(f"Total errors across all studies: {total_errors_all}")

        # Categorize errors
        all_first_errors = []
        for r in results:
            all_first_errors.extend(r['first_errors'])

        categories = defaultdict(int)
        for error in all_first_errors:
            if 'No remote URL found' in error:
                categories['missing_remote_url'] += 1
            elif 'Network' in error or 'Connection' in error:
                categories['network_error'] += 1
            elif 'Permission denied' in error:
                categories['permission_error'] += 1
            elif 'git-annex' in error:
                categories['git_annex_error'] += 1
            else:
                categories['other'] += 1

        if categories:
            click.echo("\n## Error Breakdown by Type\n")
            for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                click.echo(f"{category:.<30} {count}")

        # Show top problematic datasets
        click.echo("\n## Top 5 Most Problematic Datasets\n")
        for i, r in enumerate(results[:5], 1):
            click.echo(f"{i}. {r['study_id']} ({r['dataset_id']})")
            click.echo(f"   Errors: {r['total_errors']} across {r['total_subjects']} subjects ({r['error_rate']:.1f}%)")
            click.echo(f"   Log: {r['log_path']}")
            if r['first_errors']:
                click.echo(f"   First error: {r['first_errors'][0][:100]}...")
            click.echo()

    # Write TSV
    output_path = Path(output)
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w') as f:
        f.write("study_id\tdataset_id\ttotal_errors\ttotal_subjects\terror_rate\tlog_path\n")
        for r in results:
            f.write(
                f"{r['study_id']}\t{r['dataset_id']}\t{r['total_errors']}\t"
                f"{r['total_subjects']}\t{r['error_rate']:.1f}\t{r['log_path']}\n"
            )

    click.echo(f"\n✓ Detailed summary written to: {output_path}")
```

**Testing**:
- Test `openneuro-studies errors analyze-quality`
- Test `openneuro-studies errors analyze-legacy`
- Verify output matches original scripts
- Test TSV output format

### Step 2: Add Makefile Rules (30 minutes)

**File**: `Makefile` (MODIFY)

Add to error analysis section:

```makefile
##@ Error Analysis

.PHONY: errors-summary errors-quality errors-legacy errors-report

errors-summary: ## Show summary of current error tracking (errors.jsonl)
	@echo "=== Current Error Tracking Summary ==="
	@openneuro-studies errors summary
	@echo ""
	@echo "Use 'openneuro-studies errors list' for detailed error listing"

errors-quality: ## Analyze extraction quality (missing imaging metrics)
	@echo "=== Extraction Quality Analysis ==="
	@openneuro-studies errors analyze-quality
	@echo ""
	@echo "Run 'make extract' to regenerate metadata if needed"

errors-legacy: ## Analyze legacy extraction_errors.log files
	@echo "=== Legacy Error Log Analysis ==="
	@openneuro-studies errors analyze-legacy
	@echo ""
	@echo "Note: Use 'make errors-summary' for new error tracking format"

errors-report: ## Generate comprehensive error report (all formats)
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║           OpenNeuroStudies Error Analysis Report            ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) errors-quality
	@echo ""
	@echo "────────────────────────────────────────────────────────────────"
	@echo ""
	@$(MAKE) errors-legacy
	@echo ""
	@echo "────────────────────────────────────────────────────────────────"
	@echo ""
	@$(MAKE) errors-summary
	@echo ""
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║ Reports written to logs/                                     ║"
	@echo "║   - extraction_quality.tsv                                   ║"
	@echo "║   - extraction_errors.tsv                                    ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
```

Update help section to include error analysis:

```makefile
help: ## Display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)
```

### Step 3: Update Documentation (30 minutes)

**File**: `CLAUDE.md` (MODIFY)

Update "Common Commands" section:

```markdown
### Error Analysis

```bash
# Show current error tracking summary
make errors-summary

# Analyze extraction quality (missing imaging metrics)
make errors-quality

# Analyze legacy error logs (extraction_errors.log format)
make errors-legacy

# Generate comprehensive error report (all formats)
make errors-report

# Direct CLI usage (for advanced filtering)
openneuro-studies errors list --category missing_url --unresolved
openneuro-studies errors analyze-quality --format tsv --output custom.tsv
```

### Step 4: Delete Ad-hoc Scripts (15 minutes)

**Actions**:
1. Delete files:
   ```bash
   rm code/scripts/analyze_extraction_quality.py
   rm code/scripts/summarize_extraction_errors.py
   ```

2. Option A - Clean commit history via rebase:
   ```bash
   git rebase -i HEAD~4  # Interactive rebase
   # Drop the commit: "feat: add extraction quality and error analysis scripts"
   ```

3. Option B - Forward commit (simpler):
   ```bash
   git rm code/scripts/analyze_extraction_quality.py
   git rm code/scripts/summarize_extraction_errors.py
   git commit -m "refactor: remove ad-hoc scripts, moved to CLI

   Deleted:
   - code/scripts/analyze_extraction_quality.py
   - code/scripts/summarize_extraction_errors.py

   Replaced with:
   - openneuro-studies errors analyze-quality
   - openneuro-studies errors analyze-legacy
   - make errors-quality
   - make errors-legacy
   - make errors-report

   Follows project principle: 'No custom scripts: Use make targets instead'
   "
   ```

**Recommendation**: Option B (forward commit) - cleaner and safer.

### Step 5: Update .gitignore (5 minutes)

**File**: `.gitignore` (MODIFY - if code/scripts/ becomes empty)

If `code/scripts/` is empty after deletion, optionally remove it or add comment:

```gitignore
# code/scripts/ - NO ad-hoc scripts allowed
# All functionality should be in CLI or Makefile
```

## Testing Plan

**CRITICAL**: These commands must be properly tested as part of the system, not treated as throwaway scripts.

### Unit Tests (NEW - Required)

**File**: `code/tests/unit/test_errors_cli.py` (NEW)

```python
"""Unit tests for error analysis CLI commands."""

import json
from pathlib import Path
from click.testing import CliRunner
import pytest

from openneuro_studies.cli.errors import analyze_quality, analyze_legacy


def test_analyze_quality_no_data(tmp_path, monkeypatch):
    """Test analyze-quality with no extraction data."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(analyze_quality)

    assert result.exit_code == 0
    assert "No extraction JSON files found" in result.output


def test_analyze_quality_basic(tmp_path, monkeypatch):
    """Test analyze-quality with sample data."""
    monkeypatch.chdir(tmp_path)

    # Create sample extraction data
    extracted_dir = tmp_path / ".snakemake" / "extracted"
    extracted_dir.mkdir(parents=True)

    # Study with complete metrics
    study1 = {
        "subjects_num": 16,
        "bold_num": 10,
        "t1w_num": 16,
        "bold_voxels_total": 1000000,
        "bold_voxels_mean": 100000,
        "bold_duration_total": 500.0,
        "bold_duration_mean": 50.0,
    }
    (extracted_dir / "study-ds000001.json").write_text(json.dumps(study1))

    # Study with missing metrics
    study2 = {
        "subjects_num": 10,
        "bold_num": 5,
        "t1w_num": 10,
        "bold_voxels_total": "n/a",
        "bold_voxels_mean": "n/a",
        "bold_duration_total": "n/a",
        "bold_duration_mean": "n/a",
    }
    (extracted_dir / "study-ds000002.json").write_text(json.dumps(study2))

    runner = CliRunner()
    result = runner.invoke(analyze_quality, ["--format", "table"])

    assert result.exit_code == 0
    assert "complete" in result.output
    assert "missing_imaging_metrics" in result.output
    assert "study-ds000001" in result.output
    assert "study-ds000002" in result.output


def test_analyze_quality_tsv_output(tmp_path, monkeypatch):
    """Test analyze-quality TSV output."""
    monkeypatch.chdir(tmp_path)

    # Create sample data
    extracted_dir = tmp_path / ".snakemake" / "extracted"
    extracted_dir.mkdir(parents=True)
    study = {"subjects_num": 5, "bold_num": 3, "t1w_num": 5}
    (extracted_dir / "study-test.json").write_text(json.dumps(study))

    output_file = tmp_path / "output.tsv"
    runner = CliRunner()
    result = runner.invoke(analyze_quality, ["--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()

    # Verify TSV format
    content = output_file.read_text()
    assert "study_id\tstatus\tsubjects_num" in content
    assert "study-test" in content


def test_analyze_legacy_no_logs(tmp_path, monkeypatch):
    """Test analyze-legacy with no log files."""
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(analyze_legacy)

    assert result.exit_code == 0
    assert "No extraction_errors.log files found" in result.output


def test_analyze_legacy_with_errors(tmp_path, monkeypatch):
    """Test analyze-legacy with sample error logs."""
    monkeypatch.chdir(tmp_path)

    # Create sample error log
    study_dir = tmp_path / "study-ds001506" / "sourcedata"
    study_dir.mkdir(parents=True)

    error_log = """ds001506: Extraction completed with 100 errors across 10 subjects (error rate: 100.0%).

Failed to extract from sub-01: No remote URL found
Failed to extract from sub-02: No remote URL found
"""
    (study_dir / "extraction_errors.log").write_text(error_log)

    runner = CliRunner()
    result = runner.invoke(analyze_legacy, ["--format", "table"])

    assert result.exit_code == 0
    assert "ds001506" in result.output
    assert "100" in result.output  # error count
    assert "missing_remote_url" in result.output


def test_analyze_legacy_tsv_output(tmp_path, monkeypatch):
    """Test analyze-legacy TSV output format."""
    monkeypatch.chdir(tmp_path)

    # Create sample error log
    study_dir = tmp_path / "study-test" / "sourcedata"
    study_dir.mkdir(parents=True)
    error_log = "dstest: Extraction completed with 50 errors across 5 subjects (error rate: 100.0%)."
    (study_dir / "extraction_errors.log").write_text(error_log)

    output_file = tmp_path / "output.tsv"
    runner = CliRunner()
    result = runner.invoke(analyze_legacy, ["--output", str(output_file)])

    assert result.exit_code == 0
    assert output_file.exists()

    # Verify TSV format
    content = output_file.read_text()
    assert "study_id\tdataset_id\ttotal_errors" in content
    assert "study-test\tdstest\t50" in content
```

**Test Coverage Goal**: 90%+ for new CLI commands

### Integration Tests
1. **Test CLI commands**:
   ```bash
   cd /path/to/OpenNeuroStudies

   # Test quality analysis
   openneuro-studies errors analyze-quality
   test -f logs/extraction_quality.tsv

   # Test legacy analysis
   openneuro-studies errors analyze-legacy
   test -f logs/extraction_errors.tsv

   # Test TSV output format
   openneuro-studies errors analyze-quality --format tsv --output /tmp/test.tsv
   test -f /tmp/test.tsv
   ```

2. **Test Makefile rules**:
   ```bash
   make errors-quality
   make errors-legacy
   make errors-summary
   make errors-report
   ```

3. **Verify output matches original scripts**:
   ```bash
   # Run original script (before deletion)
   python3 code/scripts/analyze_extraction_quality.py > /tmp/original.txt

   # Run new CLI command
   openneuro-studies errors analyze-quality > /tmp/new.txt

   # Compare (should be identical or very similar)
   diff /tmp/original.txt /tmp/new.txt
   ```

## Migration Guide (for users)

### Before (ad-hoc scripts)
```bash
python3 code/scripts/analyze_extraction_quality.py
python3 code/scripts/summarize_extraction_errors.py
```

### After (CLI + Makefile)
```bash
# Quick access via Makefile
make errors-quality
make errors-legacy

# Or direct CLI access
openneuro-studies errors analyze-quality
openneuro-studies errors analyze-legacy

# Comprehensive report
make errors-report
```

## Success Criteria

- [x] No files in `code/scripts/` (scripts deleted)
- [ ] All functionality available via `openneuro-studies errors` subcommands
- [ ] Common operations available via `make` targets
- [ ] `make help` shows error analysis targets
- [ ] `openneuro-studies errors --help` shows new commands
- [ ] Output matches original scripts
- [ ] Documentation updated (CLAUDE.md)
- [ ] All tests passing

## Benefits

**Discoverability**:
- `make help` shows all available error analysis commands
- `openneuro-studies errors --help` shows all error subcommands
- No need to know about hidden scripts

**Consistency**:
- All functionality follows same interface pattern
- CLI for direct access, Makefile for common workflows
- No special cases

**Maintainability**:
- Code in proper module structure (can be tested)
- No orphaned scripts that drift out of sync
- Clear responsibility boundaries

**User Experience**:
- Single command interface (`openneuro-studies`)
- Familiar `make` targets for common tasks
- Tab completion works (for CLI)

## Risks & Mitigations

**Risk**: Breaking existing workflows that use scripts
**Mitigation**:
- Search codebase for references to scripts
- Update automation (if any) to use new commands
- Add deprecation warning before deletion (optional)

**Risk**: Output format changes break downstream consumers
**Mitigation**:
- Verify output matches exactly
- Keep TSV format identical
- Add tests to lock format

**Risk**: Performance regression (CLI overhead)
**Mitigation**:
- Logic is identical (just moved)
- CLI overhead is negligible (<100ms)
- Can measure with `time` command

## Timeline

| Task | Effort | Dependencies |
|------|--------|--------------|
| Implement CLI commands | 2 hours | None |
| Add Makefile rules | 30 min | CLI complete |
| Update documentation | 30 min | Makefile complete |
| Delete scripts | 15 min | All above complete |
| Testing | 1 hour | All above complete |
| **Total** | **4 hours** | |

## Future Enhancements

After refactoring complete, could add:

1. **HTML Report Generation**:
   ```bash
   make errors-report-html
   # Generates logs/error_report.html with charts
   ```

2. **Error Trend Analysis**:
   ```bash
   openneuro-studies errors trends --since 2026-03-01
   # Shows error count over time
   ```

3. **Error Resolution Automation**:
   ```bash
   openneuro-studies errors auto-resolve --category missing_url --if-fixed
   # Automatically marks errors as resolved if they no longer appear
   ```

## References

- Project Standards: `CLAUDE.md` - "Primary Interface: Makefile"
- Error Tracking Spec: `doc/designs/20260322-hierarchical-error-tracking.md`
- Implementation: `doc/designs/20260323-error-tracking-implementation.md`
- Current CLI: `code/src/openneuro_studies/cli/errors.py`
