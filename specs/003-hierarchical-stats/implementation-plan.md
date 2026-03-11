# Implementation Plan: Hierarchical Statistics Extraction

**Feature**: FR-042 series - Multi-level statistics extraction
**Priority**: 🔴 Critical Path
**Estimated Effort**: 2-3 weeks
**Status**: Ready to implement (design approved)
**Design Reference**: doc/designs/20251226-hierarchical-stats-extraction.md

## Overview

Implement hierarchical statistics extraction at multiple levels:
1. **Per-subject** → sourcedata+subjects.tsv (or sourcedata+subjects+sessions.tsv)
2. **Per-dataset** → sourcedata.tsv (aggregated from subjects)
3. **Per-derivative** → derivatives+subjects.tsv, derivatives+datasets.tsv
4. **Per-study** → studies.tsv (aggregated from datasets)

Current state: Only study-level extraction exists. Need to build bottom-up hierarchy.

## Phase 1: Core Infrastructure (Days 1-3)

### 1.1 Create Module Structure

**Files to create**:
```
code/src/bids_studies/extraction/
├── __init__.py
├── hierarchical.py          # Main hierarchical extraction logic
├── subject.py               # Existing (verify/extend)
├── dataset.py               # New: per-dataset aggregation
└── tsv.py                   # Existing TSV utilities
```

**Tasks**:
- [ ] Create `bids_studies/extraction/hierarchical.py`
- [ ] Add hierarchical extraction entry points
- [ ] Set up logging and error handling
- [ ] Define data structures for stats at each level

**Code scaffold**:
```python
# bids_studies/extraction/hierarchical.py
"""Hierarchical statistics extraction for BIDS datasets.

Extracts statistics at multiple levels:
- Subject level: per-subject metrics
- Dataset level: aggregated from subjects
- Study level: aggregated from datasets
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class SubjectStats:
    """Statistics for a single subject."""
    source_id: str
    subject_id: str
    session_id: str | None
    bold_num: int
    t1w_num: int
    t2w_num: int
    bold_size: int
    t1w_size: int
    datatypes: str
    # ... other fields

@dataclass
class DatasetStats:
    """Aggregated statistics for a dataset."""
    source_id: str
    subjects_num: int
    sessions_num: int | str
    sessions_min: int | str
    sessions_max: int | str
    bold_num: int
    t1w_num: int
    t2w_num: int
    bold_size: int
    t1w_size: int
    bold_size_max: int
    bold_trs: str  # JSON
    bold_duration_total: float
    bold_voxels: int
    bold_timepoints: int
    datatypes: str

def extract_subject_stats(
    dataset_path: Path,
    source_id: str,
    stage: str = "imaging"
) -> list[SubjectStats]:
    """Extract per-subject statistics from a dataset."""
    pass

def aggregate_dataset_stats(
    subject_stats: list[SubjectStats]
) -> DatasetStats:
    """Aggregate subject stats to dataset level."""
    pass
```

### 1.2 Update Column Definitions

**Files to modify**:
- `code/src/bids_studies/extraction/tsv.py`

**Tasks**:
- [ ] Add column definitions for hierarchical TSV files
- [ ] Define SUBJECTS_COLUMNS (source_id, subject_id, session_id, bold_num, ...)
- [ ] Define DATASETS_COLUMNS (source_id, subjects_num, sessions_num, ...)
- [ ] Add JSON sidecar definitions

**Code**:
```python
# In tsv.py
SUBJECTS_COLUMNS = [
    "source_id",
    "subject_id",
    "session_id",
    "bold_num",
    "t1w_num",
    "t2w_num",
    "bold_size",
    "t1w_size",
    "bold_duration_total",
    "bold_duration_mean",
    "bold_voxels_total",
    "bold_voxels_mean",
    "datatypes",
]

DATASETS_COLUMNS = [
    "source_id",
    "subjects_num",
    "sessions_num",
    "sessions_min",
    "sessions_max",
    "bold_num",
    "t1w_num",
    "t2w_num",
    "bold_size",
    "t1w_size",
    "bold_size_max",
    "bold_trs",
    "bold_duration_total",
    "bold_voxels",
    "bold_timepoints",
    "datatypes",
]
```

---

## Phase 2: Per-Subject Extraction (Days 4-7)

### 2.1 Implement Subject Statistics Extraction

**Files to modify**:
- `code/src/bids_studies/extraction/subject.py` (extend existing)
- `code/src/bids_studies/extraction/hierarchical.py`

**Tasks**:
- [ ] Extend existing subject extraction to collect per-subject stats
- [ ] Handle multi-session vs single-session datasets
- [ ] Use sparse access (SparseDataset) for file counts and sizes
- [ ] Extract imaging metrics per subject
- [ ] Handle missing data gracefully (mark as "n/a")

**Implementation approach**:
```python
def extract_subject_stats(
    dataset_path: Path,
    source_id: str,
    stage: str = "imaging"
) -> list[SubjectStats]:
    """Extract statistics for each subject in a dataset."""
    from bids_studies.sparse.access import SparseDataset

    sparse_ds = SparseDataset(dataset_path)
    subjects = sparse_ds.get_subjects()
    stats = []

    for subject in subjects:
        sessions = sparse_ds.get_sessions(subject)

        if sessions:
            # Multi-session: one row per (subject, session)
            for session in sessions:
                subject_stats = _extract_subject_session_stats(
                    sparse_ds, source_id, subject, session, stage
                )
                stats.append(subject_stats)
        else:
            # Single-session: one row per subject
            subject_stats = _extract_subject_session_stats(
                sparse_ds, source_id, subject, None, stage
            )
            stats.append(subject_stats)

    return stats
```

### 2.2 Generate sourcedata+subjects.tsv

**Files to create/modify**:
- `code/src/bids_studies/extraction/hierarchical.py`
- `code/src/bids_studies/extraction/tsv.py`

**Tasks**:
- [ ] Implement TSV writing for subject stats
- [ ] Handle multi-session naming (sourcedata+subjects+sessions.tsv)
- [ ] Store in study's sourcedata/ directory (not within submodules)
- [ ] Generate corresponding JSON sidecar

**File location pattern**:
```
study-ds000001/
├── sourcedata/
│   ├── sourcedata+subjects.tsv          # Single-session datasets
│   ├── sourcedata+subjects.json
│   └── ds000001/                        # Submodule (unmodified)

study-ds000030/
├── sourcedata/
│   ├── sourcedata+subjects+sessions.tsv # Multi-session datasets
│   ├── sourcedata+subjects+sessions.json
│   └── ds000030/                        # Submodule (unmodified)
```

**Code**:
```python
def generate_subjects_tsv(
    study_path: Path,
    subject_stats: list[SubjectStats],
    has_sessions: bool = False
) -> Path:
    """Generate sourcedata+subjects.tsv or sourcedata+subjects+sessions.tsv."""
    sourcedata_dir = study_path / "sourcedata"

    # Choose filename based on session presence
    if has_sessions:
        filename = "sourcedata+subjects+sessions.tsv"
    else:
        filename = "sourcedata+subjects.tsv"

    output_path = sourcedata_dir / filename

    # Write TSV manually (avoid CSV escaping)
    with open(output_path, "w", newline="") as f:
        f.write("\t".join(SUBJECTS_COLUMNS) + "\n")
        for stats in subject_stats:
            # Convert to row dict and serialize
            # ...

    return output_path
```

---

## Phase 3: Per-Dataset Aggregation (Days 8-10)

### 3.1 Implement Dataset Aggregation Logic

**Files to create**:
- `code/src/bids_studies/extraction/dataset.py`

**Tasks**:
- [ ] Implement aggregation from subject stats
- [ ] Sum counts (bold_num, t1w_num, etc.)
- [ ] Calculate min/max sessions
- [ ] Merge TR distributions (dict merge with count sum)
- [ ] Find max dimensions (bold_voxels)
- [ ] Handle "n/a" values gracefully

**Aggregation rules**:
- **Counts**: Sum across subjects (subjects_num, bold_num, t1w_num, bold_size, etc.)
- **Sessions**: Count unique, calculate min/max
- **TRs**: Merge dictionaries, sum counts for duplicate TRs
- **Voxels**: Take maximum across all BOLD files
- **Datatypes**: Union of all datatypes, sorted, comma-separated

**Code**:
```python
def aggregate_dataset_stats(
    subject_stats: list[SubjectStats]
) -> DatasetStats:
    """Aggregate subject-level stats to dataset level."""
    import json
    from collections import Counter

    if not subject_stats:
        return None

    source_id = subject_stats[0].source_id

    # Count subjects
    subjects_num = len(set(s.subject_id for s in subject_stats))

    # Count sessions
    sessions = [s.session_id for s in subject_stats if s.session_id]
    if sessions:
        sessions_num = len(sessions)
        session_counts = Counter(s.subject_id for s in subject_stats if s.session_id)
        sessions_min = min(session_counts.values())
        sessions_max = max(session_counts.values())
    else:
        sessions_num = "n/a"
        sessions_min = "n/a"
        sessions_max = "n/a"

    # Sum counts
    bold_num = sum(s.bold_num for s in subject_stats)
    t1w_num = sum(s.t1w_num for s in subject_stats)
    # ... etc

    # Merge TR distributions
    tr_distribution = {}
    for stats in subject_stats:
        if stats.bold_trs and stats.bold_trs != "n/a":
            subject_trs = json.loads(stats.bold_trs)
            for tr, count in subject_trs.items():
                tr_distribution[tr] = tr_distribution.get(tr, 0) + count

    bold_trs = json.dumps(tr_distribution, separators=(",", ":")) if tr_distribution else "n/a"

    # Take max voxels
    voxel_counts = [s.bold_voxels_total for s in subject_stats if s.bold_voxels_total != "n/a"]
    bold_voxels = max(voxel_counts) if voxel_counts else "n/a"

    # Union datatypes
    all_datatypes = set()
    for stats in subject_stats:
        if stats.datatypes and stats.datatypes != "n/a":
            all_datatypes.update(stats.datatypes.split(","))
    datatypes = ",".join(sorted(all_datatypes)) if all_datatypes else "n/a"

    return DatasetStats(
        source_id=source_id,
        subjects_num=subjects_num,
        sessions_num=sessions_num,
        sessions_min=sessions_min,
        sessions_max=sessions_max,
        bold_num=bold_num,
        # ... etc
    )
```

### 3.2 Generate sourcedata.tsv

**Tasks**:
- [ ] Write aggregated stats to sourcedata.tsv
- [ ] Store in study's sourcedata/ directory
- [ ] Generate JSON sidecar

**File location**:
```
study-ds000001/
├── sourcedata/
│   ├── sourcedata.tsv                   # Aggregated dataset stats
│   ├── sourcedata.json
│   ├── sourcedata+subjects.tsv          # Per-subject stats
│   ├── sourcedata+subjects.json
│   └── ds000001/                        # Submodule
```

---

## Phase 4: Derivative Statistics (Days 11-13)

### 4.1 Implement Derivative Subject Stats

**Files to modify**:
- `code/src/bids_studies/extraction/hierarchical.py`

**Tasks**:
- [ ] Extend extraction for derivative datasets
- [ ] Add derivative-specific metrics:
  - output_num (total output files)
  - output_size (total size)
  - nifti_num (NIfTI output files)
  - nifti_size (size of NIfTI files)
  - html_num (HTML reports)
- [ ] Use sparse access for derivatives

**Code**:
```python
@dataclass
class DerivativeSubjectStats(SubjectStats):
    """Statistics for a subject in a derivative dataset."""
    output_num: int
    output_size: int
    nifti_num: int
    nifti_size: int
    html_num: int
```

### 4.2 Generate Derivative TSV Files

**Tasks**:
- [ ] Generate derivatives+subjects.tsv
- [ ] Generate derivatives+datasets.tsv
- [ ] Store in study's derivatives/ directory
- [ ] Generate JSON sidecars

**File location**:
```
study-ds000001/
├── derivatives/
│   ├── derivatives+subjects.tsv         # Per-subject derivative stats
│   ├── derivatives+subjects.json
│   ├── derivatives+datasets.tsv         # Per-derivative aggregation
│   ├── derivatives+datasets.json
│   ├── fmriprep-21.0.1/                # Derivative submodule
│   └── mriqc-0.16.1/                   # Derivative submodule
```

---

## Phase 5: Study-Level Aggregation (Days 14-16)

### 5.1 Update studies.tsv Generation

**Files to modify**:
- `code/src/openneuro_studies/metadata/studies_tsv.py`

**Tasks**:
- [ ] Update `collect_study_metadata()` to read from hierarchical TSV files
- [ ] Aggregate from sourcedata.tsv and derivatives+datasets.tsv
- [ ] Maintain backward compatibility (fall back to direct extraction if TSV missing)
- [ ] Verify all columns populated correctly

**Code**:
```python
def collect_study_metadata(
    study_path: Path,
    stage: str = "imaging",
) -> dict[str, Any]:
    """Collect metadata for studies.tsv, using hierarchical stats if available."""

    # Try to load from hierarchical stats first
    sourcedata_tsv = study_path / "sourcedata" / "sourcedata.tsv"

    if sourcedata_tsv.exists():
        # Load aggregated stats from TSV
        summaries = _load_from_hierarchical_tsv(sourcedata_tsv)
    else:
        # Fall back to direct extraction (current behavior)
        summaries = extract_all_summaries(study_path, stage=stage)

    # Merge in derivative stats if available
    derivatives_tsv = study_path / "derivatives" / "derivatives+datasets.tsv"
    if derivatives_tsv.exists():
        # Update derivative_count and other derivative metrics
        # ...

    # Build final metadata dict
    return {
        "study_id": study_path.name,
        # ... populate from summaries
    }
```

---

## Phase 6: CLI Integration & Workflow (Days 17-18)

### 6.1 Add --stage Flag

**Files to modify**:
- `code/src/openneuro_studies/cli/main.py`

**Tasks**:
- [ ] Add `--stage` option to metadata generate command
  - `basic`: Top-level stats only (current behavior)
  - `subjects`: Include per-subject stats
  - `full`: All hierarchical levels (default)
- [ ] Update command help text

**Code**:
```python
@click.option(
    "--stage",
    type=click.Choice(["basic", "subjects", "full"]),
    default="full",
    help="Extraction depth: basic (study-level only), subjects (include per-subject), full (all levels)"
)
def metadata_generate(..., stage: str):
    """Generate metadata files."""
    # ...
```

### 6.2 Update Snakemake Workflow

**Files to modify**:
- `code/workflow/Snakefile`

**Tasks**:
- [ ] Update extract_study rule to generate hierarchical stats
- [ ] Add dependencies for hierarchical TSV files
- [ ] Update merge_into_canonical to read from hierarchical stats

**Code**:
```python
rule extract_study:
    output:
        json_file = ".snakemake/extracted/{study}.json",
        subjects_tsv = "{study}/sourcedata/sourcedata+subjects.tsv",  # New
        datasets_tsv = "{study}/sourcedata/sourcedata.tsv",           # New
    run:
        # Generate all hierarchical stats
        # ...
```

---

## Phase 7: Testing (Days 19-21)

### 7.1 Unit Tests

**Files to create**:
- `code/tests/unit/test_hierarchical_extraction.py`

**Test cases**:
- [ ] Subject stats extraction
  - Single-session dataset
  - Multi-session dataset
  - Empty dataset (no subjects)
  - Missing data (handle gracefully)
- [ ] Dataset aggregation
  - Sum counts correctly
  - Merge TR distributions
  - Calculate session min/max
  - Handle "n/a" values
- [ ] TSV writing
  - Correct column order
  - JSON serialization (no escaping)
  - Sidecar generation

### 7.2 Integration Tests

**Files to create**:
- `code/tests/integration/test_hierarchical_workflow.py`

**Test cases**:
- [ ] End-to-end extraction for test studies
  - study-ds000001 (single-session, single-source)
  - study-ds000030 (multi-session, single-source)
  - study-ds006190 (multi-source derivative)
- [ ] Verify aggregation accuracy
  - Compare aggregated totals with direct extraction
  - Verify TR distributions match
  - Check session counts
- [ ] Verify file locations
  - TSV files in correct directories
  - JSON sidecars created
  - Submodules unmodified

### 7.3 Regression Testing

**Tasks**:
- [ ] Verify studies.tsv output unchanged (when hierarchical stats available)
- [ ] Verify backward compatibility (direct extraction still works)
- [ ] Performance comparison (hierarchical vs direct)

---

## Phase 8: Documentation & Finalization (Day 22)

### 8.1 Update Documentation

**Files to update**:
- `specs/001-read-file-doc/quickstart.md`
- `CLAUDE.md`
- `README.md`

**Sections to add**:
- Hierarchical statistics overview
- File naming conventions (sourcedata+subjects.tsv, etc.)
- Extraction stages (basic/subjects/full)
- Aggregation methodology
- Examples

### 8.2 Update Spec Compliance

**Files to update**:
- `doc/spec-compliance-analysis.md`
- `TODO.md`

**Tasks**:
- [ ] Mark FR-042 series as ✅ DONE
- [ ] Update completion percentages
- [ ] Remove from critical path
- [ ] Add to completed items

---

## Success Criteria

- [ ] All 6 FR-042 requirements implemented
- [ ] Unit tests passing (>90% coverage for new code)
- [ ] Integration tests passing with test studies
- [ ] Documentation complete
- [ ] studies.tsv output matches direct extraction
- [ ] Performance acceptable (<5 min per study with 100+ subjects)
- [ ] Backward compatible (old workflows still work)

---

## Dependencies & Prerequisites

**Required**:
- ✅ Current extraction infrastructure (summary_extractor.py)
- ✅ Sparse data access (SparseDataset)
- ✅ TSV writing utilities (tsv.py)
- ✅ Snakemake workflow

**None blocking** - Ready to start immediately!

---

## Risk Mitigation

**Risk**: Performance degradation with large datasets
**Mitigation**: Use sparse access, implement caching, test with ds003097 (394K files)

**Risk**: Aggregation errors (incorrect totals)
**Mitigation**: Extensive unit tests, compare with direct extraction, validate with known datasets

**Risk**: TSV file bloat
**Mitigation**: Monitor file sizes, consider compression for very large studies

**Risk**: Backward compatibility issues
**Mitigation**: Maintain fallback to direct extraction, gradual rollout

---

## Timeline

| Phase | Days | Deliverable |
|-------|------|-------------|
| 1. Infrastructure | 1-3 | Module structure, column definitions |
| 2. Subject extraction | 4-7 | sourcedata+subjects.tsv generation |
| 3. Dataset aggregation | 8-10 | sourcedata.tsv generation |
| 4. Derivative stats | 11-13 | derivatives+*.tsv generation |
| 5. Study aggregation | 14-16 | Updated studies.tsv from hierarchical stats |
| 6. CLI integration | 17-18 | --stage flag, Snakemake updates |
| 7. Testing | 19-21 | Unit + integration tests |
| 8. Documentation | 22 | Docs, spec updates |

**Total**: ~22 working days (4.5 weeks calendar time)

---

## Next Steps

1. Review this implementation plan
2. Get user approval to proceed
3. Start Phase 1: Create module structure
4. Implement incrementally, testing at each phase
5. Regular check-ins at phase boundaries

**Ready to begin?** 🚀
