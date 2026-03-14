# Hierarchical Statistics - Design and Current State

**Created**: 2026-03-11
**Status**: PARTIALLY IMPLEMENTED
**Specification**: FR-042 series from 001-read-file-doc

## Executive Summary

Hierarchical statistics extraction infrastructure is **already implemented** for sourcedata but **not yet implemented** for derivatives. The code exists in `bids_studies/extraction/` and is integrated into the metadata generation workflow via `openneuro-studies metadata generate`.

**Current Status**:
- ✅ **Sourcedata hierarchical stats** (FR-042a/b/c/d): IMPLEMENTED and WORKING
  - Per-subject extraction: `extract_subjects_stats()`
  - Per-dataset aggregation: `aggregate_to_dataset()`
  - Per-study aggregation: `aggregate_to_study()`
  - TSV file generation: `write_subjects_tsv()`, `write_datasets_tsv()`
  - JSON sidecars: Copied from `bids_studies/schemas/`
  - **12 of 40 studies** have hierarchical files generated

- ❌ **Derivatives hierarchical stats** (FR-042e): NOT IMPLEMENTED
  - No code for derivatives+subjects.tsv extraction
  - No code for derivatives+datasets.tsv aggregation

- ❌ **Studies.tsv aggregation from hierarchical files** (FR-042f): NOT IMPLEMENTED
  - Currently studies.tsv uses direct extraction via `summary_extractor.py`
  - Should read from sourcedata.tsv instead of re-extracting

## Current Implementation

### Module Structure

```
code/src/bids_studies/extraction/
├── __init__.py              # Exports all hierarchical functions
├── subject.py               # Per-subject stats extraction
├── dataset.py               # Per-dataset aggregation
├── study.py                 # Per-study aggregation
├── tsv.py                   # TSV read/write utilities
└── schemas/
    ├── sourcedata+subjects.json  # Column descriptions
    └── sourcedata.json           # Column descriptions
```

### Key Functions

#### 1. Per-Subject Extraction (`subject.py`)

```python
def extract_subject_stats(
    ds: SparseDataset,
    source_id: str,
    subject: str,
    session: Optional[str] = None,
    include_imaging: bool = False,
) -> dict[str, Any]:
    """Extract stats for a single subject (or subject+session)."""
```

**Output columns** (SUBJECTS_COLUMNS):
- source_id, subject_id, session_id
- bold_num, t1w_num, t2w_num
- bold_size, t1w_size
- bold_duration_total, bold_duration_mean
- bold_voxels_total, bold_voxels_mean
- datatypes

**Features**:
- Counts BOLD, T1w, T2w files via pattern matching
- Sums file sizes via `SparseDataset.get_file_size()`
- Optionally extracts imaging metrics (voxels, duration, TR) via NIfTI header parsing
- Detects BIDS datatypes (anat, func, dwi, etc.)
- Handles multi-session datasets (one row per subject+session)

#### 2. Per-Dataset Aggregation (`dataset.py`)

```python
def aggregate_to_dataset(
    subjects_stats: list[dict[str, Any]],
    source_id: str,
) -> dict[str, Any]:
    """Aggregate subject-level stats to dataset level."""
```

**Output columns** (DATASETS_COLUMNS):
- source_id
- subjects_num, sessions_num, sessions_min, sessions_max
- bold_num, t1w_num, t2w_num
- bold_size, t1w_size, bold_size_max
- bold_duration_total, bold_duration_mean
- bold_voxels_total, bold_voxels_mean
- datatypes

**Aggregation methods**:
- **Count unique subjects**: `subjects_num`
- **Sum counts**: bold_num, t1w_num, t2w_num, sessions_num
- **Sum sizes**: bold_size, t1w_size
- **Min/max sessions**: sessions_min, sessions_max
- **Weighted mean**: bold_duration_mean, bold_voxels_mean (weighted by bold_num)
- **Merge sets**: datatypes (comma-separated)

#### 3. Per-Study Aggregation (`study.py`)

```python
def extract_study_stats(
    study_path: Path,
    sourcedata_subdir: str = "sourcedata",
    include_imaging: bool = True,
    write_files: bool = True,
) -> dict[str, Any]:
    """Extract hierarchical stats for a study."""
```

**Process**:
1. Find all sourcedata subdatasets in `study_path/sourcedata/`
2. For each source:
   - Extract per-subject stats via `extract_subjects_stats()`
   - Aggregate to dataset level via `aggregate_to_dataset()`
3. Write TSV files:
   - `sourcedata/sourcedata+subjects.tsv` (or `sourcedata+subjects+sessions.tsv` if multi-session)
   - `sourcedata/sourcedata.tsv`
4. Copy JSON sidecars from `bids_studies/schemas/`
5. Aggregate to study level via `aggregate_to_study()`
6. Return study-level dict for inclusion in studies.tsv

**File locations** (example for study-ds000001):
```
study-ds000001/
└── sourcedata/
    ├── ds000001/                      # Subdataset (not modified)
    ├── sourcedata+subjects.tsv        # Per-subject stats
    ├── sourcedata+subjects.json       # Column descriptions
    ├── sourcedata.tsv                 # Per-dataset stats
    └── sourcedata.json                # Column descriptions
```

### Integration with Metadata Generation

Located in `code/src/openneuro_studies/cli/main.py`:

```python
# Generate hierarchical sourcedata TSV files for counts/sizes/imaging stages
if stage in ("counts", "sizes", "imaging"):
    from bids_studies.extraction import extract_study_stats

    for study_path in study_paths:
        extract_study_stats(
            study_path,
            sourcedata_subdir="sourcedata",
            include_imaging=(stage == "imaging"),
            write_files=True,
        )
```

**Stages**:
- `--stage counts`: Extract file counts only (bold_num, t1w_num, t2w_num)
- `--stage sizes`: Add file sizes (bold_size, t1w_size)
- `--stage imaging`: Add imaging metrics (voxels, duration, TR)

### Current TSV Output

Example from `study-ds000001/sourcedata/sourcedata+subjects.tsv`:
```tsv
source_id	subject_id	session_id	bold_num	t1w_num	t2w_num	bold_size	t1w_size	...
ds000001	sub-01	n/a	3	1	0	141871303	5663237	...
ds000001	sub-02	n/a	3	1	0	152240177	5736750	...
```

Example from `study-ds000001/sourcedata/sourcedata.tsv`:
```tsv
source_id	subjects_num	sessions_num	bold_num	t1w_num	t2w_num	bold_size	t1w_size	...
ds000001	16	n/a	48	16	0	2319818025	85042746	...
```

### Schema Files

JSON sidecars are copied from `code/src/bids_studies/schemas/`:
- `sourcedata+subjects.json`: Column descriptions for per-subject TSV
- `sourcedata.json`: Column descriptions for per-dataset TSV

Schema path resolution via `bids_studies.schemas.get_schema_path()`.

## What's Missing

### 1. Derivatives Hierarchical Stats (FR-042e)

**Requirement**: Generate per-subject and per-dataset statistics for derivatives.

**Needed files** (example for study-ds000001 with mriqc derivative):
```
study-ds000001/
└── derivatives/
    └── mriqc-25.0.2/
        ├── derivatives+subjects.tsv     # Per-subject derivative stats
        ├── derivatives+subjects.json    # Column descriptions
        ├── derivatives+datasets.tsv     # Per-dataset derivative stats
        └── derivatives+datasets.json    # Column descriptions
```

**Required columns** (derivatives+subjects.tsv):
- source_id (e.g., "ds000001")
- derivative_id (e.g., "mriqc-25.0.2")
- subject_id
- session_id
- output_num (total output files)
- output_size (total output size)
- nifti_num (NIfTI files count)
- nifti_size (NIfTI files size)
- html_num (HTML reports count)

**Required columns** (derivatives+datasets.tsv):
- source_id
- derivative_id
- subjects_num
- sessions_num
- output_num
- output_size
- nifti_num
- nifti_size
- html_num

**Implementation needed**:
- New functions in `bids_studies/extraction/derivative.py`:
  - `extract_derivative_subject_stats()` - per-subject derivative extraction
  - `extract_derivative_subjects_stats()` - all subjects in derivative
  - `aggregate_derivative_to_dataset()` - aggregate subjects to dataset
- New columns in `bids_studies/extraction/tsv.py`:
  - `DERIVATIVE_SUBJECTS_COLUMNS`
  - `DERIVATIVE_DATASETS_COLUMNS`
- New schema files in `bids_studies/schemas/`:
  - `derivatives+subjects.json`
  - `derivatives+datasets.json`

### 2. Studies.tsv Aggregation from Hierarchical Files (FR-042f)

**Requirement**: Read sourcedata.tsv and derivatives+datasets.tsv instead of re-extracting data.

**Current approach** (summary_extractor.py):
```python
# Currently: Direct extraction per study
def collect_study_metadata(study_path: Path, stage: str) -> dict:
    # Extract from sourcedata subdatasets directly
    for source in sourcedata_dirs:
        with SparseDataset(source) as ds:
            # Count files, get sizes, extract imaging metrics
            ...
```

**Desired approach**:
```python
# Future: Read from hierarchical TSV files
def collect_study_metadata(study_path: Path, stage: str) -> dict:
    # Read sourcedata.tsv
    sourcedata_tsv = study_path / "sourcedata" / "sourcedata.tsv"
    sourcedata_stats = read_datasets_tsv(sourcedata_tsv)

    # Aggregate to study level
    study_stats = aggregate_to_study(sourcedata_stats)

    # Read derivatives+datasets.tsv if exists
    for derivative in derivatives_dirs:
        derivatives_tsv = derivative / "derivatives+datasets.tsv"
        if derivatives_tsv.exists():
            derivative_stats = read_datasets_tsv(derivatives_tsv)
            # Merge into study_stats
            ...

    return study_stats
```

**Benefits**:
- **Faster**: Read pre-computed TSV files instead of re-extracting
- **Cacheable**: TSV files are versioned with study dataset
- **Transparent**: Can inspect intermediate results
- **Consistent**: Same aggregation logic for all levels

**Required changes**:
- Modify `collect_study_metadata()` in `summary_extractor.py` to:
  1. Check if hierarchical TSV files exist
  2. If yes: Read and aggregate from TSV files
  3. If no: Fall back to direct extraction (for backwards compatibility)
- Ensure hierarchical extraction runs before studies.tsv generation

## Execution Status

### Generated Hierarchical Files

**12 of 40 studies** currently have hierarchical TSV files:
```
study-ds000001/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds004078/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds005237/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds005256/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds006131/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds006189/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds006190/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds006191/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds006192/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds002766/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds002843/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
study-ds004044/sourcedata/{sourcedata+subjects.tsv, sourcedata.tsv}
```

**Why only 12?** These are the studies that had their sourcedata subdatasets initialized during metadata extraction. The extraction code requires initialized subdatasets to access git tree and file information.

**To generate for all 40 studies**: Run metadata generation with imaging stage:
```bash
openneuro-studies metadata generate --stage imaging
```

This will:
1. Initialize sourcedata subdatasets temporarily (if needed)
2. Extract hierarchical stats for each study
3. Write sourcedata+subjects.tsv and sourcedata.tsv
4. Restore subdataset initialization state

## Implementation Plan

### Phase 1: Generate Hierarchical Files for All Studies (1 day)

**Task**: Ensure all 40 studies have sourcedata hierarchical TSV files.

**Steps**:
1. Run `openneuro-studies metadata generate --stage imaging`
2. Verify all 40 studies have sourcedata.tsv and sourcedata+subjects.tsv
3. Commit generated files to study datasets

**Success criteria**: `find study-* -name "sourcedata.tsv" | wc -l` returns 40

### Phase 2: Implement Derivatives Hierarchical Stats (3-4 days)

**Files to create**:
- `code/src/bids_studies/extraction/derivative.py`
- `code/src/bids_studies/schemas/derivatives+subjects.json`
- `code/src/bids_studies/schemas/derivatives+datasets.json`

**Functions to implement**:
```python
def extract_derivative_subject_stats(
    ds: SparseDataset,
    source_id: str,
    derivative_id: str,
    subject: str,
    session: Optional[str] = None,
) -> dict[str, Any]:
    """Extract derivative stats for a single subject."""

def extract_derivative_subjects_stats(
    derivative_path: Path,
    source_id: str,
    derivative_id: str,
) -> list[dict[str, Any]]:
    """Extract stats for all subjects in a derivative."""

def aggregate_derivative_to_dataset(
    subjects_stats: list[dict[str, Any]],
    source_id: str,
    derivative_id: str,
) -> dict[str, Any]:
    """Aggregate derivative subject stats to dataset level."""
```

**Integration**:
- Add to `extract_study_stats()` in `study.py`
- Add CLI flag `--include-derivatives` for metadata generate

**Testing**:
- Unit tests with mock derivative datasets
- Integration test with study-ds000001 (has mriqc derivative)

### Phase 3: Update Studies.tsv Aggregation (2-3 days)

**Modify** `code/src/openneuro_studies/metadata/summary_extractor.py`:

```python
def collect_study_metadata(study_path: Path, stage: str) -> dict:
    """Collect metadata for a study, reading from hierarchical TSV if available."""

    # Try reading from hierarchical TSV files first
    sourcedata_tsv = study_path / "sourcedata" / "sourcedata.tsv"
    if sourcedata_tsv.exists():
        from bids_studies.extraction.tsv import read_datasets_tsv
        from bids_studies.extraction.study import aggregate_to_study

        sourcedata_stats = read_datasets_tsv(sourcedata_tsv)
        result = aggregate_to_study(sourcedata_stats)
    else:
        # Fall back to direct extraction (backwards compatibility)
        result = _extract_direct(study_path, stage)

    # Add study-level metadata
    result["study_id"] = study_path.name
    result["name"] = _read_dataset_name(study_path)
    ...

    return result
```

**Benefits**:
- Faster: No re-extraction needed
- Transparent: Studies.tsv aggregated from intermediate files
- Cacheable: TSV files versioned with study

**Testing**:
- Verify studies.tsv matches previous values (no regression)
- Performance benchmark (should be faster)

### Phase 4: Documentation (1 day)

**Update**:
- `specs/001-read-file-doc/quickstart.md`: Add hierarchical stats section
- `TODO.md`: Mark FR-042 as complete
- `doc/spec-compliance-analysis.md`: Update FR-042 status

## Notes

### Code Duplication

The NIfTI header extraction code in `subject.py` is duplicated from `summary_extractor.py`. This is documented in `doc/todos/code-duplication-nifti-header-extraction.md` and should be consolidated in a future refactoring.

### CSV vs Manual TSV Writing

The TSV writing code in `tsv.py` uses `csv.DictWriter`, which escapes quotes in JSON strings. This was recently fixed for `studies.tsv` and `studies+derivatives.tsv` to use manual TSV writing. The hierarchical TSV writing should also be updated to avoid JSON escaping issues.

**Current code** (`tsv.py`):
```python
with open(output_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=SUBJECTS_COLUMNS, delimiter="\t")
    writer.writeheader()
    for stats in subjects_stats:
        row = {col: _na(stats.get(col)) for col in SUBJECTS_COLUMNS}
        writer.writerow(row)
```

**Should be**:
```python
with open(output_path, "w", newline="") as f:
    # Write header
    f.write("\t".join(SUBJECTS_COLUMNS) + "\n")
    # Write rows
    for stats in subjects_stats:
        fields = [str(stats.get(col, "")) if stats.get(col) is not None else "n/a"
                  for col in SUBJECTS_COLUMNS]
        f.write("\t".join(fields) + "\n")
```

This would match the pattern used in `studies_tsv.py` and `Snakefile`.

## Error Handling and Reporting

**Updated**: 2026-03-14
**Status**: IMPLEMENTED
**Compliance**: Constitution Principle V (Error Visibility)

### Design Principles

1. **No Silent Failures**: All extraction errors MUST be visible and reported
2. **Error Accumulation**: Errors collected during extraction and returned alongside results
3. **Error Thresholds**: Process fails when error rate indicates systemic problems
4. **Comprehensive Reporting**: Errors logged, written to files, and summarized

### Implementation

#### Function Return Signatures

All extraction functions now return tuples: `(results, errors)`

```python
# Subject-level extraction
def extract_subject_stats(...) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    # ... extraction logic
    if extraction_fails:
        errors.append(f"Failed to extract from {file}: {error}")
    return result, errors

# Dataset-level extraction
def extract_subjects_stats(...) -> tuple[list[dict[str, Any]], list[str]]:
    all_errors: list[str] = []
    for subject in subjects:
        stats, errors = extract_subject_stats(...)
        all_errors.extend(errors)

    # Fail if error rate exceeds 50%
    if error_rate > 0.5:
        raise RuntimeError(f"Extraction failed: {len(all_errors)} errors")

    return results, all_errors
```

#### Error Reporting Levels

1. **Per-File Errors** (WARNING level):
   - Logged when individual BOLD file extraction fails
   - Example: `"Failed to extract imaging metrics from sub-01_bold.nii.gz: NetworkError"`

2. **Subject/Session Errors** (WARNING level):
   - Logged when all files in a subject/session fail
   - Example: `"Failed to extract imaging metrics from all 3 BOLD files"`

3. **Dataset Errors** (ERROR level):
   - Logged when extraction error rate exceeds threshold
   - Example: `"Extraction completed with 15 errors across 40 subjects (37.5% error rate)"`

4. **Study Errors** (ERROR level):
   - Logged when entire dataset extraction fails
   - Written to `sourcedata/extraction_errors.log`
   - Example: `"Study extraction completed with 5 errors"`

#### Error Thresholds and Failure Conditions

**50% Error Rate Threshold**:
- If >50% of subjects/sessions have extraction errors → RuntimeError raised
- Indicates systemic problem (subdatasets not initialized, network failure, etc.)
- Prevents producing incomplete metadata that appears valid

**Complete Failure**:
- If ALL extractions fail → RuntimeError raised immediately
- No partial results returned

**Partial Failures**:
- If <50% fail → Continue extraction, return results with error list
- Errors logged and written to file for investigation

#### Error Log Files

**Location**: `{study}/sourcedata/extraction_errors.log`

**Format**:
```
Extraction Errors (15 total)
============================================================

Failed to extract imaging metrics from sub-01/ses-01/func/sub-01_ses-01_bold.nii.gz: FileNotFoundError
Failed to extract imaging metrics from sub-01/ses-02/func/sub-01_ses-02_bold.nii.gz: NetworkError
...
```

**Usage**:
- Created automatically when errors occur
- Truncated to first 10 errors in console output
- Full error list written to file

#### Workflow Integration

**Snakemake Workflow** (`code/workflow/Snakefile`):
```python
try:
    extract_study_stats(study_path, include_imaging=True, write_files=True)
except RuntimeError as e:
    logger.error(f"Extraction failed: {e}")
    # Write error to .snakemake/extraction_errors.tsv
    # Continue with other studies
```

**Error Summary at Workflow End**:
- Reports total error count across all studies
- Lists studies with failures
- Exit code indicates success/failure

### Compliance with Constitution Principle V

✅ **Error Visibility**: Errors logged at WARNING/ERROR (not DEBUG)
✅ **No Silent Failures**: Exceptions raised or errors accumulated and reported
✅ **Error Summaries**: Workflows report error counts and rates
✅ **Accessible Logs**: Errors written to `sourcedata/extraction_errors.log`
✅ **Distinguishable Failures**: Failed extractions produce errors, not just "n/a" values

## Summary

**What's Done**:
- ✅ Sourcedata hierarchical extraction (FR-042a/b/c/d)
- ✅ CLI integration (`metadata generate --stage imaging`)
- ✅ JSON sidecars and schema files
- ✅ 12/40 studies have hierarchical files

**What's Left**:
- ❌ Generate hierarchical files for remaining 28 studies
- ❌ Derivatives hierarchical extraction (FR-042e)
- ❌ Studies.tsv aggregation from hierarchical files (FR-042f)
- ❌ Fix CSV escaping in hierarchical TSV writing (code quality)

**Estimated effort**: 1-2 weeks (7-10 working days)
