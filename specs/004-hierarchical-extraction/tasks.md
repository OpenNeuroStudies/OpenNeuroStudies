# Tasks: 004-hierarchical-extraction

**Spec**: `specs/004-hierarchical-extraction/spec.md`
**Created**: 2026-05-07
**Status**: In Progress

## Legend

- **[DONE]** -- Implemented and working in the codebase
- **[PARTIAL]** -- Code exists but is incomplete or has known issues
- **[TODO]** -- Not yet implemented

---

## Phase 1: Sourcedata Per-Subject Extraction (FR-HE-001, FR-HE-002, FR-HE-010)

### 1.1 [DONE] Per-subject stats extraction function
- File: `code/src/bids_studies/extraction/subject.py`
- `extract_subject_stats()` extracts bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_duration_total, bold_duration_mean, bold_voxels_total, bold_voxels_mean, datatypes per subject
- `extract_subjects_stats()` iterates over all subjects with session filtering

### 1.2 [DONE] Session detection with datatype filtering
- File: `code/src/bids_studies/extraction/subject.py`
- Filters out BIDS datatype directories (anat, func, fmap, etc.) from session list
- Requires `ses-` prefix for valid sessions
- Unit test: `code/tests/unit/test_hierarchical_extraction.py::TestSessionValidation`

### 1.3 [DONE] Multi-session TSV naming
- File: `code/src/bids_studies/extraction/study.py` (`_write_sourcedata_files`)
- Uses `sourcedata+subjects+sessions.tsv` when any subject has sessions
- Uses `sourcedata+subjects.tsv` otherwise

### 1.4 [DONE] Optional imaging metrics extraction
- File: `code/src/bids_studies/extraction/subject.py` (`_extract_imaging_metrics`)
- Parses NIfTI headers from gzipped streams via sparse access
- Extracts voxel counts and BOLD duration from TR and volume count

---

## Phase 2: Sourcedata Per-Dataset Aggregation (FR-HE-003, FR-HE-011)

### 2.1 [DONE] Dataset-level aggregation function
- File: `code/src/bids_studies/extraction/dataset.py`
- `aggregate_to_dataset()` implements sum, min/max, weighted mean, set union aggregation
- Handles n/a values correctly
- Unit test: `code/tests/unit/test_hierarchical_extraction.py::TestAggregateToDataset`

### 2.2 [DONE] Write sourcedata.tsv
- File: `code/src/bids_studies/extraction/study.py` (`_write_sourcedata_files`)
- Writes per-source-dataset aggregated stats via `write_datasets_tsv()`
- Stored at `{study}/sourcedata/sourcedata.tsv`

---

## Phase 3: Sourcedata Per-Study Aggregation (FR-HE-004)

### 3.1 [DONE] Study-level aggregation function
- File: `code/src/bids_studies/extraction/study.py`
- `aggregate_to_study()` aggregates across multiple source datasets
- `extract_study_stats()` orchestrates full extraction pipeline for a study

### 3.2 [DONE] Write sourcedata TSV and JSON files
- Files: `code/src/bids_studies/extraction/study.py`, `code/src/bids_studies/extraction/tsv.py`
- `write_subjects_tsv()`, `write_datasets_tsv()` produce TSV output
- JSON sidecars copied from `code/src/bids_studies/schemas/`

---

## Phase 4: Sourcedata JSON Sidecars (FR-HE-012)

### 4.1 [DONE] Schema files for sourcedata TSV
- File: `code/src/bids_studies/schemas/sourcedata+subjects.json`
- File: `code/src/bids_studies/schemas/sourcedata.json`
- Column descriptions following BIDS conventions

### 4.2 [DONE] Schema path resolution
- File: `code/src/bids_studies/schemas/__init__.py`
- `get_schema_path()` resolves schema file paths relative to package

---

## Phase 5: Derivative Per-Subject Extraction (FR-HE-020)

### 5.1 [DONE] Derivative per-subject stats extraction
- File: `code/src/bids_studies/extraction/derivative.py`
- `extract_derivative_subject_stats()` extracts output_num, output_size, nifti_num, nifti_size, html_num
- `extract_derivative_subjects_stats()` iterates over all subjects with session filtering
- Handles multi-session derivatives

### 5.2 [DONE] Derivative per-dataset aggregation
- File: `code/src/bids_studies/extraction/derivative.py`
- `aggregate_derivative_to_dataset()` aggregates subject stats to dataset level

### 5.3 [DONE] Derivative TSV column definitions
- File: `code/src/bids_studies/extraction/tsv.py`
- `DERIVATIVE_SUBJECTS_COLUMNS` and `DERIVATIVE_DATASETS_COLUMNS` defined
- `write_derivative_subjects_tsv()` and `write_derivative_datasets_tsv()` implemented
- `read_derivative_subjects_tsv()` and `read_derivative_datasets_tsv()` implemented

### 5.4 [DONE] Derivative JSON sidecars
- File: `code/src/bids_studies/schemas/derivatives+subjects.json`
- File: `code/src/bids_studies/schemas/derivatives+datasets.json`

---

## Phase 6: Per-Study Derivative Orchestration (FR-HE-021, FR-HE-023, FR-HE-024, FR-HE-025)

### 6.1 [DONE] Derivative extraction orchestration in study.py
- File: `code/src/bids_studies/extraction/study.py`
- `extract_derivative_stats()` extracts per-subject stats and aggregates to dataset level
- `_write_derivative_files()` writes TSV and JSON files

### 6.2 [PARTIAL] Per-study derivatives.tsv generation (FR-042f)
- The Snakemake workflow (step 3c) currently generates `.snakemake/extracted/{study}.derivatives.tsv` as a cache file for the top-level `studies+derivatives.tsv`
- However, this is NOT the same as the per-study `{study}/derivatives/derivatives.tsv` specified by FR-042f
- The cache file uses `STUDIES_DERIVATIVES_COLUMNS` from openneuro_studies, not the per-study format
- **Missing**: Generation of `{study}/derivatives/derivatives.tsv` within each study directory that combines hierarchical extraction stats with derivative identity/version metadata
- **Missing**: The per-study derivatives.tsv should be the single source of truth for studies+derivatives.tsv (FR-042h)

### 6.3 [DONE] Derivative metadata extraction (version tracking, completeness)
- File: `code/src/openneuro_studies/metadata/derivative_extractor.py`
- `extract_derivative_metadata()` extracts size, version, completeness, tasks, spaces, descriptions
- However, this is in openneuro_studies, not bids_studies (see Phase 9)

---

## Phase 7: Cross-Study Aggregation (FR-HE-030, FR-HE-031)

### 7.1 [PARTIAL] studies.tsv generation from hierarchical files (FR-042g)
- File: `code/src/openneuro_studies/metadata/studies_tsv.py`
- `collect_study_metadata()` currently uses `summary_extractor.py` for direct re-extraction
- The Snakemake `merge_into_canonical` rule reads from `.snakemake/extracted/{study}.json`
- **Missing**: `collect_study_metadata()` does not read from `sourcedata.tsv`. Instead, the Snakemake workflow calls `extract_study_stats()` in step 3a and `collect_study_metadata()` in step 3e separately, and the result of 3a is not consumed by 3e
- **Impact**: studies.tsv columns come from summary_extractor direct extraction, not from the hierarchical aggregation path. This means there are TWO parallel extraction paths (violates Constitution Principle VII - DRY)

### 7.2 [DONE] studies+derivatives.tsv generation from cache files (FR-042h)
- File: `code/src/openneuro_studies/metadata/studies_plus_derivatives_tsv.py`
- `generate_studies_derivatives_tsv()` reads from `.snakemake/extracted/{study}.derivatives.tsv`
- Falls back to `collect_derivatives_for_study()` for uncached studies
- Snakemake `merge_derivatives_tsv` rule orchestrates this

### 7.3 [TODO] studies+derivatives.tsv generation from per-study derivatives.tsv (FR-042h ideal)
- FR-042h specifies reading from `{study}/derivatives/derivatives.tsv`, not cache files
- Currently cache files in `.snakemake/` serve this purpose
- Once per-study `derivatives/derivatives.tsv` exists (Phase 6.2), the aggregation should read from it

---

## Phase 8: Snakemake Workflow (FR-HE-040 through FR-HE-043)

### 8.1 [DONE] Git SHA-based dependency tracking
- File: `code/workflow/Snakefile`
- `get_study_deps()` extracts gitlink and sourcedata SHAs
- `get_study_deps_with_version()` includes EXTRACTION_VERSION
- Params trigger rerun via `--rerun-triggers params`

### 8.2 [DONE] Parallel extraction support
- Snakemake `--cores N` enables parallel study extraction
- Each study's extraction is independent

### 8.3 [DONE] Provenance tracking
- File: `code/workflow/lib/provenance.py`
- `ProvenanceManager.record()` stores rule, deps, timestamp per output
- Clean stale provenance for deleted outputs

### 8.4 [DONE] Hierarchical extraction in Snakemake
- Snakemake `extract_study` rule calls `extract_study_stats()` (step 3a)
- Also calls `extract_derivative_stats()` for each derivative (step 3b)
- Caches derivative metadata (step 3c)
- Deinitializes derivative subdatasets (step 3d)

### 8.5 [DONE] Single-study extraction
- `make extract-one STUDY=study-ds002843` via Snakemake config filter

---

## Phase 9: Library Boundary (FR-HE-070 through FR-HE-073)

### 9.1 [PARTIAL] bids_studies must not import openneuro_studies (FR-HE-071)
- **Current violations** (6 import sites):
  1. `bids_studies/extraction/subject.py` imports `openneuro_studies.lib.exceptions.NetworkError`
  2. `bids_studies/extraction/subject.py` imports `openneuro_studies.lib.error_classification.aggregate_errors`
  3. `bids_studies/extraction/derivative.py` imports `openneuro_studies.lib.exceptions.NetworkError`
  4. `bids_studies/extraction/study.py` imports `openneuro_studies.lib.error_tracking.ErrorLevel, log_error`
  5. `bids_studies/sparse/access.py` imports `openneuro_studies.lib.retry.retry_on_network_error`
  6. `bids_studies/subdatasets/__init__.py` imports `openneuro_studies.metadata.studies_tsv.collect_study_metadata`
- Items 1 and 3 use try/except ImportError with fallback, so they work standalone
- Items 2 and 4 do NOT have fallbacks -- they will fail without openneuro_studies
- **Required**: Move NetworkError, error_classification, error_tracking to bids_studies or remove the dependency

### 9.2 [TODO] Migrate derivative_extractor.py to bids_studies (FR-042i)
- File: `code/src/openneuro_studies/metadata/derivative_extractor.py`
- Contains generic extraction logic: git-annex size, version tracking, completeness analysis, task extraction, space extraction, description extraction
- These functions should move to `code/src/bids_studies/extraction/derivative_metadata.py` (or similar)
- The `extract_derivative_metadata()` function is the main entry point
- Only orchestration (CLI, subdataset install/drop) should remain in openneuro_studies
- **Complexity**: Medium. Functions are self-contained but there are many of them (~10 functions, ~500 lines)

---

## Phase 10: Subdataset Management (FR-HE-050 through FR-HE-053)

### 10.1 [DONE] Sourcedata initialization in workflow
- Snakemake `extract_study` rule step 2a initializes uninitialized sourcedata
- Uses `get_uninitialized_sourcedata()` and `initialize_subdatasets()`
- Fails fast on initialization errors

### 10.2 [DONE] Derivative initialization and cleanup in workflow
- Snakemake `extract_study` rule steps 2b and 3d
- Initializes derivative subdatasets before extraction
- Deinitializes after extraction (frees disk space)
- Tracks which were initialized vs already present

### 10.3 [DONE] DataLad-based subdataset management
- File: `code/src/openneuro_studies/lib/subdataset_manager.py`
- Uses DataLad commands for install/uninstall

---

## Phase 11: Error Handling (FR-HE-060 through FR-HE-064)

### 11.1 [DONE] Error accumulation in extraction functions
- `extract_subject_stats()` returns `(result, errors)` tuple
- `extract_subjects_stats()` accumulates errors across subjects
- `extract_study_stats()` accumulates errors across datasets

### 11.2 [DONE] Error threshold and failure
- `extract_subjects_stats()` raises RuntimeError on operational errors
- Distinguishes operational vs expected failures via `aggregate_errors()`

### 11.3 [DONE] Error logging at WARNING/ERROR
- All extraction errors logged at WARNING level
- Study-level failures at ERROR level
- Constitution Principle V compliance

### 11.4 [DONE] Structured error logs
- JSONL error logs at `{study}/sourcedata/errors.jsonl`
- Legacy plain-text at `{study}/sourcedata/extraction_errors.log`
- Error context includes study_id, dataset_id, subject_id, session_id, file_path

---

## Phase 12: Data Format (FR-HE-080 through FR-HE-083)

### 12.1 [PARTIAL] TSV writing without CSV escaping (FR-HE-080)
- Snakemake `merge_into_canonical` and `merge_derivatives_tsv` rules use manual TSV writing (correct)
- `studies_tsv.py` `generate_studies_tsv()` uses manual TSV writing (correct)
- `studies_plus_derivatives_tsv.py` uses manual TSV writing (correct)
- **But**: `bids_studies/extraction/tsv.py` still uses `csv.DictWriter` for hierarchical files
- **Impact**: JSON values in fields (if any) may get double-quoted
- **Fix needed**: Switch `write_subjects_tsv()`, `write_datasets_tsv()`, etc. to manual TSV writing

### 12.2 [DONE] Consistent n/a handling
- `_na()` helper converts None to "n/a"
- All extraction functions use "n/a" for missing data
- TSV readers handle "n/a" strings

### 12.3 [DONE] BIDS column naming
- All column names use snake_case per BIDS conventions
- TSV filenames use `+` per BIDS issue #2273

---

## Phase 13: Testing

### 13.1 [PARTIAL] Unit tests for extraction
- File: `code/tests/unit/test_hierarchical_extraction.py`
- Tests session validation, dataset aggregation, study aggregation
- **Missing**: Tests for derivative extraction and aggregation
- **Missing**: Tests for TSV read/write functions
- **Missing**: Tests for error handling paths

### 13.2 [PARTIAL] Integration tests
- File: `code/tests/integration/test_extraction_with_subdatasets.py`
- File: `code/tests/integration/test_derivative_extraction.py`
- **Missing**: End-to-end test comparing hierarchical aggregation to direct extraction
- **Missing**: Test for multi-source study (ds006190)

### 13.3 [TODO] Regression test: aggregated values match direct extraction
- Verify that studies.tsv values from hierarchical path match direct extraction path
- This test is critical since two extraction paths currently exist (Phase 7.1)

---

## Summary

| Phase | Status | Key Gap |
|-------|--------|---------|
| 1. Subject extraction | DONE | -- |
| 2. Dataset aggregation | DONE | -- |
| 3. Study aggregation | DONE | -- |
| 4. JSON sidecars (sourcedata) | DONE | -- |
| 5. Derivative extraction | DONE | -- |
| 6. Derivative orchestration | PARTIAL | Per-study derivatives.tsv not generated (FR-042f) |
| 7. Cross-study aggregation | PARTIAL | studies.tsv uses direct extraction, not hierarchical (DRY violation) |
| 8. Snakemake workflow | DONE | -- |
| 9. Library boundary | PARTIAL | bids_studies imports openneuro_studies (6 sites); derivative_extractor.py not migrated |
| 10. Subdataset management | DONE | -- |
| 11. Error handling | DONE | -- |
| 12. Data format | PARTIAL | Hierarchical TSV uses csv.DictWriter (should be manual) |
| 13. Testing | PARTIAL | Missing derivative tests, regression test, multi-source test |

### Critical Path (must-fix for spec compliance)

1. **Phase 6.2**: Generate per-study `derivatives/derivatives.tsv` (FR-042f)
2. **Phase 7.1**: Make studies.tsv read from hierarchical files, not re-extract (FR-042g, DRY)
3. **Phase 9.1**: Remove openneuro_studies imports from bids_studies (FR-HE-071)
4. **Phase 9.2**: Migrate derivative_extractor.py to bids_studies (FR-042i)

### Quality Improvements (important but not blocking)

5. **Phase 12.1**: Switch hierarchical TSV writing to manual (no csv.DictWriter)
6. **Phase 13.1**: Add derivative extraction unit tests
7. **Phase 13.3**: Add regression test comparing extraction paths
