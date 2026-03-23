# Hierarchical Error Tracking System

**Date**: 2026-03-22
**Status**: Specification
**Authors**: Claude Sonnet 4.5

## Summary

Design for comprehensive error tracking across the OpenNeuroStudies hierarchy, enabling auditing of errors over time to determine if they're still pertinent or have been resolved.

## Problem Statement

**Current State**:
- Extraction errors logged to `study-*/sourcedata/extraction_errors.log` (plain text, per-study)
- No centralized error aggregation
- No temporal tracking (can't tell if error persists across extractions)
- No version/commit tracking (can't tell which dataset version had the error)
- No hierarchy tracking (errors at subject/session/dataset/study level conflated)

**User Need**:
> "I think we need internal tooling/interface to audit errors we observe during operation and see if they are still pertinent later on or were resolved. Should annotate clearly on which study and (sub)dataset, version, date etc... so again -- smth like errors.tsv but aggregated across hierarchy."

## Current Implementation Review

### Specification (specs/001-read-file-doc/spec.md:67)

```
A logs/errors.tsv file at the top level should aggregate information
about all errors with columns study_id, error_type, message.
```

**Status**: NOT IMPLEMENTED

### Current Error Logging (code/src/bids_studies/extraction/study.py:164-173)

```python
# Write errors to file
errors_file = sourcedata_path / "extraction_errors.log"
with open(errors_file, "w") as f:
    f.write(f"Extraction Errors ({len(all_extraction_errors)} total)\n")
    for error in all_extraction_errors:
        f.write(f"{error}\n")
```

**Issues**:
- ❌ Plain text format (not machine-readable TSV)
- ❌ Per-study location (not centralized)
- ❌ No temporal tracking (overwrites each run)
- ❌ No version/commit information
- ❌ No hierarchy level annotation (subject/session/dataset/study)
- ❌ Mixing operational and expected errors

### Error Classification (code/src/openneuro_studies/lib/error_classification.py)

```python
ErrorType = Literal["operational", "expected"]

def classify_error(error_msg: str, exception: Exception | None) -> ErrorType:
    """Classify as operational (must fail) or expected (can tolerate)."""
```

**What works**:
- ✅ Distinguishes operational vs expected errors
- ✅ Reusable classification logic

**What's missing**:
- ❌ No persistence of classification results
- ❌ No tracking of error resolution

### Exception Classes (code/src/openneuro_studies/lib/exceptions.py)

```python
class NetworkError(OpenNeuroStudiesError):
    """Network operation failed after retries."""

class ExtractionError(OpenNeuroStudiesError):
    """Data extraction failed (not network issue)."""
```

**What works**:
- ✅ Structured exception hierarchy
- ✅ Rich error context (url, file_path, field, attempts)

**What's missing**:
- ❌ No serialization to TSV
- ❌ No tracking across time

## Proposed Design: Hierarchical Error Tracking

### Hierarchy Levels

```
Repository (logs/errors.tsv)
  └─ Study (study-ds000001)
       └─ Dataset (sourcedata/ds000001, derivatives/fMRIPrep-23.2.1)
            └─ Subject/Session (sub-01, sub-01/ses-01)
                 └─ File (sub-01/func/sub-01_task-rest_bold.nii.gz)
```

### Error JSONL Schema

#### Primary: `logs/errors.jsonl` (Centralized, Append-Only)

```jsonl
{"timestamp": "2026-03-22T10:30:15", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "0bd43a59", "level": "file", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "message": "No remote URL found for sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "count": 1, "resolved": false, "first_seen": "2026-03-22T10:30:15", "last_seen": "2026-03-22T10:30:15"}
{"timestamp": "2026-03-22T10:30:16", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "0bd43a59", "level": "dataset", "subject_id": null, "session_id": null, "error_type": "operational", "error_category": "git_failure", "file_path": null, "message": "git-annex: First run: git-annex init", "count": 1, "resolved": true, "first_seen": "2026-03-22T10:30:16", "last_seen": "2026-03-22T10:30:16", "resolved_at": "2026-03-22T14:20:00"}
{"timestamp": "2026-03-22T14:15:20", "study_id": "study-ds000113", "dataset_id": "ds000113", "dataset_version": "35252aa8", "level": "dataset", "subject_id": null, "session_id": null, "error_type": "expected", "error_category": "network", "file_path": null, "message": "Network operation failed after 5 retries", "count": 5, "resolved": false, "first_seen": "2026-03-22T14:15:20", "last_seen": "2026-03-22T14:15:20"}
```

**Fields**:
- `timestamp`: ISO 8601 datetime of error occurrence
- `study_id`: Study directory name (e.g., study-ds001506)
- `dataset_id`: Dataset ID (ds001506, fMRIPrep-23.2.1)
- `dataset_version`: Git commit SHA of dataset at time of error
- `level`: Hierarchy level (study|dataset|subject|session|file)
- `subject_id`: Subject ID (sub-01) or null if not applicable
- `session_id`: Session ID (ses-01) or null if not applicable
- `error_type`: Classification (operational|expected)
- `error_category`: Specific category (missing_url|network_error|git_failure|corrupt_file|...)
- `file_path`: Relative path to problematic file or null
- `message`: Human-readable error message (full text, no truncation)
- `count`: Number of occurrences in this run (for deduplication)
- `resolved`: true if error no longer occurs in latest run, false otherwise
- `first_seen`: ISO 8601 datetime when error first occurred
- `last_seen`: ISO 8601 datetime when error last occurred
- `resolved_at`: ISO 8601 datetime when error was resolved (null if unresolved)

**Properties**:
- ✅ Append-only (preserves history)
- ✅ Machine-readable JSONL (one JSON object per line)
- ✅ Temporal tracking via timestamp, first_seen, last_seen
- ✅ Version tracking via dataset_version
- ✅ Hierarchical via level + subject/session fields
- ✅ Auditable via resolved flag + resolved_at timestamp
- ✅ Deduplication via count field

#### Secondary: `study-*/sourcedata/errors.jsonl` (Per-Dataset, Current State)

```jsonl
{"timestamp": "2026-03-22T10:30:15", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "message": "No remote URL found", "count": 1}
```

**Purpose**: Quick lookup of current errors for a specific dataset

**Relationship**: Subset of central `logs/errors.jsonl` for this dataset (latest run only, unresolved errors)

### Error Categories (error_category)

Expand beyond operational/expected to specific categories:

**Operational** (infrastructure failures):
- `git_failure`: Git/git-annex not initialized or command failed
- `network_error`: Network timeout, connection refused
- `permission_error`: Permission denied, disk full
- `io_error`: I/O error reading/writing files
- `subdataset_missing`: Subdataset not initialized

**Expected** (data-level issues):
- `missing_url`: File exists but no remote URL in git-annex
- `corrupt_file`: File corrupted or invalid format
- `missing_field`: Required metadata field missing
- `validation_error`: BIDS validation failure
- `missing_modality`: Optional modality not present (e.g., no T2w)

### Error Resolution Tracking

**How to mark errors as resolved**:

1. **Automatic** (on each extraction run):
   - Compare current errors with historical errors
   - If error from previous run doesn't occur now, mark `resolved=TRUE` in historical record
   - Update via UPDATE query on logs/errors.tsv (requires SQLite or pandas)

2. **Manual** (via CLI):
   ```bash
   openneuro-studies errors resolve study-ds001506 --error-type missing_url
   ```

**Resolution Logic**:
```python
def mark_resolved_errors(current_errors: list[Error], historical_errors: list[Error]):
    """Mark historical errors that no longer occur as resolved."""
    # Key = (study_id, dataset_id, level, subject_id, session_id, file_path, error_category)
    current_keys = {error.key for error in current_errors}
    historical_keys = {error.key for error in historical_errors if not error.resolved}

    resolved_keys = historical_keys - current_keys

    # Update logs/errors.tsv: set resolved=TRUE for resolved_keys
```

### Implementation Components

#### 1. Error Logger (`lib/error_logger.py` - NEW)

```python
class ErrorLogger:
    """Centralized error logging with hierarchy tracking."""

    def __init__(self, log_path: Path = Path("logs/errors.tsv")):
        self.log_path = log_path
        self.current_run_errors: list[ErrorRecord] = []

    def log_error(
        self,
        study_id: str,
        dataset_id: str,
        dataset_version: str,
        level: Literal["study", "dataset", "subject", "session", "file"],
        error_type: Literal["operational", "expected"],
        error_category: str,
        message: str,
        subject_id: str | None = None,
        session_id: str | None = None,
        file_path: str | None = None,
    ) -> None:
        """Log an error to centralized TSV."""

    def write_current_state(self, dataset_path: Path) -> None:
        """Write current errors to dataset-local errors.tsv."""

    def mark_resolved_errors(self) -> int:
        """Compare with historical errors and mark resolved. Returns count."""
```

#### 2. Error Record (`lib/error_logger.py` - NEW)

```python
@dataclass
class ErrorRecord:
    """Structured error record for TSV serialization."""
    timestamp: str
    study_id: str
    dataset_id: str
    dataset_version: str
    level: str
    subject_id: str
    session_id: str
    error_type: str
    error_category: str
    file_path: str
    message: str
    resolved: bool = False

    def key(self) -> tuple:
        """Unique key for deduplication."""
        return (
            self.study_id, self.dataset_id, self.level,
            self.subject_id, self.session_id, self.file_path,
            self.error_category
        )

    def to_tsv_row(self) -> str:
        """Serialize to TSV row."""
```

#### 3. Integration Points

**In `subject.py:extract_subjects_stats()`**:
```python
from openneuro_studies.lib.error_logger import ErrorLogger

logger_errors = ErrorLogger()

try:
    # Extract imaging metrics
    ...
except FileNotFoundError as e:
    if "No remote URL" in str(e):
        logger_errors.log_error(
            study_id=study_id,
            dataset_id=source_id,
            dataset_version=get_git_sha(source_path),
            level="file",
            error_type="expected",
            error_category="missing_url",
            message=str(e),
            subject_id=subject,
            session_id=session,
            file_path=bold_file,
        )
```

**In `study.py:extract_study_stats()`**:
```python
# After extraction completes
logger_errors.write_current_state(sourcedata_path)  # Per-dataset TSV
logger_errors.mark_resolved_errors()  # Update central logs/errors.tsv
```

**In Snakefile `extract_study` rule**:
```python
# No changes needed - error logging happens automatically in extraction code
```

#### 4. CLI Commands (`cli/errors.py` - NEW)

```bash
# List all errors
openneuro-studies errors list

# List errors for specific study
openneuro-studies errors list study-ds001506

# List unresolved errors only
openneuro-studies errors list --unresolved

# List by category
openneuro-studies errors list --category missing_url

# Show error summary
openneuro-studies errors summary

# Mark errors as resolved manually
openneuro-studies errors resolve study-ds001506 --category missing_url

# Garbage collect resolved errors older than N days (default 30)
openneuro-studies errors gc --days=30

# Export errors to CSV/TSV
openneuro-studies errors export --output errors.csv --format csv
```

#### 5. Garbage Collection (`cli/errors.py`)

```python
@click.command()
@click.option("--days", default=30, help="Remove resolved errors older than N days")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def gc(days: int, dry_run: bool):
    """Garbage collect resolved errors older than N days.

    Examples:
        openneuro-studies errors gc --days=30
        openneuro-studies errors gc --days=7 --dry-run
    """
    from datetime import datetime, timedelta
    from pathlib import Path
    import json

    errors_file = Path("logs/errors.jsonl")
    if not errors_file.exists():
        click.echo("No errors.jsonl found")
        return

    cutoff = datetime.now() - timedelta(days=days)

    # Read all errors
    errors = []
    removed_count = 0

    with open(errors_file) as f:
        for line in f:
            error = json.loads(line)

            # Keep if:
            # 1. Unresolved (resolved=false)
            # 2. Resolved recently (resolved_at > cutoff)
            if not error.get("resolved", False):
                errors.append(error)
            elif error.get("resolved_at"):
                resolved_at = datetime.fromisoformat(error["resolved_at"])
                if resolved_at > cutoff:
                    errors.append(error)
                else:
                    removed_count += 1
            else:
                # Resolved but no resolved_at timestamp (legacy)
                errors.append(error)

    if dry_run:
        click.echo(f"[DRY RUN] Would remove {removed_count} resolved errors older than {days} days")
        click.echo(f"[DRY RUN] Would keep {len(errors)} errors")
    else:
        # Write back
        with open(errors_file, "w") as f:
            for error in errors:
                f.write(json.dumps(error) + "\n")

        click.echo(f"✓ Removed {removed_count} resolved errors older than {days} days")
        click.echo(f"✓ Kept {len(errors)} errors ({len([e for e in errors if not e.get('resolved')])} unresolved)")
```

#### 6. Analysis Scripts

**`code/scripts/analyze_errors.py`** (Enhanced version of current scripts):
```python
#!/usr/bin/env python3
"""Analyze error trends over time."""

def analyze_error_trends():
    """Show error trends: new, resolved, persistent."""

def show_top_problematic_datasets():
    """Datasets with most errors."""

def show_error_resolution_rate():
    """% of errors resolved over time."""
```

## Migration Plan

### Phase 1: Central Error Logging (Week 1)

1. Create `lib/error_logger.py` with `ErrorLogger` and `ErrorRecord`
2. Create `logs/errors.tsv` (empty with header)
3. Add JSON sidecar `logs/errors.json` with column descriptions
4. Update `subject.py` to use `ErrorLogger` for file-level errors
5. Update `study.py` to use `ErrorLogger` for dataset-level errors
6. Keep existing `extraction_errors.log` for backward compatibility

**Testing**:
- Run extraction for 5 studies
- Verify `logs/errors.tsv` populated
- Verify hierarchical structure (study/dataset/subject/file levels)

### Phase 2: Error Resolution Tracking (Week 2)

1. Implement `mark_resolved_errors()` logic
2. Add `resolved` column updates after each extraction
3. Test with re-extraction: errors should be marked resolved if fixed

**Testing**:
- Extract with uninitialized subdataset (errors logged)
- Initialize subdataset and re-extract (errors marked resolved)
- Verify resolved=TRUE in logs/errors.tsv

### Phase 3: CLI and Analysis Tools (Week 3)

1. Create `cli/errors.py` with list/summary/resolve commands
2. Create `code/scripts/analyze_errors.py` for trend analysis
3. Add `make errors-summary` target to Makefile
4. Document in CLAUDE.md

**Testing**:
- `openneuro-studies errors list --unresolved`
- `openneuro-studies errors summary`
- `make errors-summary`

### Phase 4: Deprecate Old Format (Week 4)

1. Stop writing `extraction_errors.log` (plain text)
2. Write only `study-*/sourcedata/errors.tsv` (current state)
3. Clean up old `.log` files via `.gitignore`
4. Update documentation

## File Structure

```
logs/
├── errors.jsonl            # Centralized, append-only, all errors ever (JSONL format)
└── errors.json             # Schema/field descriptions (JSON sidecar)

study-ds001506/
└── sourcedata/
    ├── ds001506/           # Subdataset
    └── errors.jsonl        # Current errors for this dataset (latest run, JSONL)

code/src/openneuro_studies/
├── lib/
│   └── error_logger.py     # NEW: ErrorLogger, ErrorRecord
└── cli/
    └── errors.py           # NEW: CLI commands (list, summary, resolve, gc)

code/scripts/
└── analyze_errors.py       # Enhanced error analysis
```

## JSONL Format Examples

### logs/errors.jsonl (Central, Append-Only)

```jsonl
{"timestamp": "2026-03-22T10:30:15", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "0bd43a59", "level": "file", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "message": "No remote URL found for sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "count": 1, "resolved": false, "first_seen": "2026-03-22T10:30:15", "last_seen": "2026-03-22T10:30:15"}
{"timestamp": "2026-03-22T10:30:15", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "0bd43a59", "level": "file", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-02_bold.nii.gz", "message": "No remote URL found for sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-02_bold.nii.gz", "count": 1, "resolved": false, "first_seen": "2026-03-22T10:30:15", "last_seen": "2026-03-22T10:30:15"}
{"timestamp": "2026-03-22T10:35:20", "study_id": "study-ds000113", "dataset_id": "ds000113", "dataset_version": "35252aa8", "level": "dataset", "subject_id": null, "session_id": null, "error_type": "expected", "error_category": "network", "file_path": null, "message": "Network operation failed after 5 retries: Connection timeout", "count": 5, "resolved": false, "first_seen": "2026-03-22T10:35:20", "last_seen": "2026-03-22T10:35:20"}
{"timestamp": "2026-03-22T14:20:00", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "a1b2c3d4", "level": "file", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "message": "No remote URL found", "count": 1, "resolved": true, "first_seen": "2026-03-22T10:30:15", "last_seen": "2026-03-22T10:30:15", "resolved_at": "2026-03-22T14:20:00"}
```

**Note**: Last line shows same error from earlier run (dataset_version=0bd43a59) now resolved in later run (a1b2c3d4), marked with `resolved=true` and `resolved_at` timestamp.

### study-ds001506/sourcedata/errors.jsonl (Per-Dataset, Current State Only)

```jsonl
{"timestamp": "2026-03-22T10:30:15", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz", "message": "No remote URL found", "count": 1}
{"timestamp": "2026-03-22T10:30:15", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "func/sub-01_ses-imagery01_task-imagery_run-02_bold.nii.gz", "message": "No remote URL found", "count": 1}
```

**Purpose**: Quick reference for current unresolved errors in this dataset only (no history, no resolved errors).

## Success Criteria

1. ✅ Central `logs/errors.tsv` exists and aggregates all errors
2. ✅ Errors annotated with study, dataset, version, date, hierarchy level
3. ✅ Temporal tracking: can see error history over time
4. ✅ Resolution tracking: can identify resolved vs persistent errors
5. ✅ CLI tools for error auditing (`errors list`, `errors summary`)
6. ✅ Analysis scripts show trends and problematic datasets
7. ✅ Per-dataset `errors.tsv` for quick local lookup
8. ✅ Backward compatible: existing extraction code continues to work

## Design Decisions

### D1: Storage Format - JSONL (not TSV)

**Decision**: Use JSONL (JSON Lines) format instead of TSV.

**Rationale**:
- ✅ More versatile for nested/optional fields
- ✅ Easier to read/write programmatically (json.dumps/loads)
- ✅ No escaping issues with tabs/newlines in messages
- ✅ Can add fields without breaking parsers
- ✅ Better for structured error context (exception details, stack traces)

**Format**:
```jsonl
{"timestamp": "2026-03-22T10:30:15", "study_id": "study-ds001506", "dataset_id": "ds001506", "dataset_version": "0bd43a59", "level": "file", "subject_id": "sub-01", "session_id": "ses-imagery01", "error_type": "expected", "error_category": "missing_url", "file_path": "sub-01/ses-imagery01/func/..._bold.nii.gz", "message": "No remote URL found", "count": 1, "resolved": false}
{"timestamp": "2026-03-22T10:35:20", "study_id": "study-ds000113", "dataset_id": "ds000113", "dataset_version": "35252aa8", "level": "dataset", "error_type": "expected", "error_category": "network", "message": "Network operation failed", "count": 5, "resolved": false}
```

**File**: `logs/errors.jsonl` (append-only, one JSON object per line)

### D2: Error Deduplication - Unique Entity with Count

**Decision**: Log once per unique error entity with `count` field.

**Unique key** (for deduplication within a run):
```python
key = (study_id, dataset_id, level, subject_id, session_id, file_path, error_category)
```

**Example**: 1190 "No remote URL" errors for different files → 1190 separate entries (different file_path)
**Example**: Same file failing 5 times in retry loop → 1 entry with count=5

### D3: Retention Policy - Remove Resolved After N Days

**Decision**: Keep unresolved errors indefinitely, remove resolved errors after N days (default N=30).

**Policy**:
- Unresolved errors: Keep forever (need to track until fixed)
- Resolved errors: Keep for 30 days (historical context), then prune
- Explicit GC command: `openneuro-studies errors gc --days=30`

**Rationale**:
- Unresolved errors need ongoing attention (can't delete)
- Resolved errors useful for recent history (what was fixed when?)
- After 30 days, resolved errors are noise (prune to keep file manageable)
- Explicit gc command makes cleanup transparent and controllable

## References

- Spec: specs/001-read-file-doc/spec.md (line 67)
- Current implementation: code/src/bids_studies/extraction/study.py:164-173
- Error classification: code/src/openneuro_studies/lib/error_classification.py
- Design doc: doc/designs/20260321-subdataset-installation-error-handling.md
