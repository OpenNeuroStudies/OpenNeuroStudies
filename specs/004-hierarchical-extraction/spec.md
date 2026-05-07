# Feature Specification: Hierarchical Metadata Extraction

**Feature Branch**: `004-hierarchical-extraction`
**Created**: 2026-05-07
**Status**: Draft
**Parent Spec**: FR-042 series from `specs/001-read-file-doc/spec.md`
**Library**: `bids_studies` (generic BIDS study metadata extraction)

## Overview

The `bids_studies` library provides a **generic hierarchical statistics extraction framework** for BIDS study datasets. Statistics are extracted at the lowest level (per-subject, per-session) and consolidated upward through dataset, study, and cross-study levels. A Snakemake workflow provides efficient incremental re-extraction by tracking git SHAs of source data, ensuring that only changed datasets trigger recomputation.

This spec defines WHAT the framework must do and WHY. Implementation details (module structure, function signatures, workflow rules) belong in the plan.

---

## User Scenarios & Testing

### User Story 1 - Researcher Browses Cross-Study Summary (Priority: P1)

A researcher wants to quickly compare raw data characteristics (subject counts, BOLD file counts, total scan durations, spatial resolution) across dozens of BIDS study datasets without downloading any imaging data. They open `studies.tsv` in a spreadsheet or `visidata` and filter/sort by columns to find datasets matching their inclusion criteria (e.g., "at least 50 subjects with resting-state BOLD data at 2mm resolution").

**Why this priority**: The cross-study summary is the primary output of the entire system. Without it, individual per-study files have limited utility. This is the end-user-facing deliverable.

**Independent Test**: Generate `studies.tsv` from hierarchical extraction of 3+ study datasets. Verify all numeric columns are populated and consistent with direct inspection of the underlying data.

**Acceptance Scenarios**:

1. **Given** a repository with 40 study datasets that have sourcedata subdatasets, **When** the user runs `make extract CORES=4` followed by `make metadata`, **Then** `studies.tsv` contains one row per study with all numeric columns populated from hierarchical aggregation (not direct re-extraction).
2. **Given** a `studies.tsv` with 40 rows, **When** a user opens it in visidata (`vd studies.tsv`), **Then** all columns are tab-separated with no CSV escaping artifacts, and `n/a` values are used consistently for missing data (never empty cells or `None`).
3. **Given** a study with multiple sourcedata datasets (e.g., study-ds006190 with 3 sources), **When** studies.tsv is generated, **Then** aggregate columns (subjects_num, bold_num, bold_size) reflect the sum across all sources.

---

### User Story 2 - Curator Inspects Per-Subject Detail (Priority: P1)

A data curator needs to audit a specific study's raw data quality. They want to see per-subject file counts, sizes, and imaging metrics without initializing the raw subdataset themselves. They look at `study-ds000001/sourcedata/sourcedata+subjects.tsv` to identify subjects with missing BOLD runs or anomalous file sizes.

**Why this priority**: Per-subject TSV files are the foundation of the hierarchy. If subject-level extraction is wrong, all aggregations above it are wrong. This is also the most granular level of inspection for data quality.

**Independent Test**: Extract per-subject stats for a single study and verify each row matches manual inspection of the git tree.

**Acceptance Scenarios**:

1. **Given** a study with an initialized sourcedata subdataset, **When** extraction runs, **Then** `sourcedata+subjects.tsv` is written to `{study}/sourcedata/` with one row per (source_id, subject_id) for single-session datasets.
2. **Given** a multi-session dataset, **When** extraction runs, **Then** `sourcedata+subjects+sessions.tsv` is written with one row per (source_id, subject_id, session_id).
3. **Given** a subject with 3 BOLD files and 1 T1w file, **When** extraction runs, **Then** the row shows bold_num=3, t1w_num=1, and bold_size equals the sum of the 3 BOLD file sizes.
4. **Given** a corresponding JSON sidecar, **When** a user reads `sourcedata+subjects.json`, **Then** every column in the TSV has a Description entry explaining its purpose and units.

---

### User Story 3 - Curator Audits Derivative Coverage (Priority: P2)

A curator wants to know which derivatives are available for a study, how complete they are, and whether they are up-to-date with the current raw data version. They inspect `study-ds000001/derivatives/derivatives.tsv` to see per-derivative size, file counts, processing completeness, and outdatedness metrics.

**Why this priority**: Derivative metadata is needed for `studies+derivatives.tsv` but is more complex than sourcedata extraction due to the variety of derivative types and the need for version tracking.

**Independent Test**: Extract derivative metadata for a study with 2+ derivatives (e.g., fmriprep + mriqc) and verify the derivatives.tsv contains correct size, version, and completeness information.

**Acceptance Scenarios**:

1. **Given** a study with an MRIQC derivative subdataset, **When** derivative extraction runs, **Then** `derivatives/derivatives.tsv` contains a row with derivative_id, tool_name="mriqc", tool_version, size_total, file_count, and processing completeness metrics.
2. **Given** a derivative where the raw data has been updated since processing, **When** extraction runs, **Then** the `uptodate` column is False and `outdatedness` shows the number of commits behind.
3. **Given** the top-level studies+derivatives.tsv generation step, **When** it runs, **Then** it reads each study's `derivatives/derivatives.tsv` and concatenates them with a `study_id` prefix column -- no access to actual derivative subdatasets is needed.

---

### User Story 4 - Operator Runs Incremental Update (Priority: P1)

An operator adds 5 new studies and updates 2 existing studies (their raw data changed). They want to extract metadata only for the 7 affected studies, not all 40. The Snakemake workflow tracks git SHAs and re-extracts only when dependencies change.

**Why this priority**: Efficiency is critical for a repository with 1000+ studies. Full re-extraction takes hours; incremental updates should take minutes.

**Independent Test**: Run extraction, change one study's sourcedata SHA, re-run extraction, and verify only that study is reprocessed.

**Acceptance Scenarios**:

1. **Given** a repository with 40 studies already extracted, **When** 2 studies have their sourcedata subdataset updated (new git commit), **Then** `make extract CORES=4` reprocesses only those 2 studies plus the aggregation steps.
2. **Given** no changes to any study, **When** `make extract` runs, **Then** Snakemake reports "Nothing to be done" and completes in seconds.
3. **Given** the extraction logic version is bumped (EXTRACTION_VERSION changes), **When** `make extract --rerun-triggers params` runs, **Then** all studies are re-extracted because the version parameter changed.

---

### User Story 5 - Operator Processes Single Study (Priority: P2)

An operator wants to debug extraction for a single study that is producing unexpected results. They run `make extract-one STUDY=study-ds002843` to process just that study, inspect intermediate files, and iterate.

**Why this priority**: Single-study processing is essential for debugging and development. It must produce the same intermediate files as the full workflow.

**Independent Test**: Run single-study extraction and verify all intermediate TSV files are generated.

**Acceptance Scenarios**:

1. **Given** a study with initialized subdatasets, **When** `make extract-one STUDY=study-ds002843` runs, **Then** the following files are produced:
   - `study-ds002843/sourcedata/sourcedata+subjects.tsv`
   - `study-ds002843/sourcedata/sourcedata.tsv`
   - `.snakemake/extracted/study-ds002843.json`
2. **Given** a study with derivatives, **When** single-study extraction runs, **Then** derivative TSV files are also produced under `derivatives/`.

---

### User Story 6 - Developer Inspects Intermediate Aggregation (Priority: P3)

A developer wants to understand how study-level numbers in `studies.tsv` were computed. They trace backward from `studies.tsv` to `sourcedata.tsv` to `sourcedata+subjects.tsv` to verify aggregation correctness.

**Why this priority**: Transparency and auditability are important but secondary to core functionality.

**Independent Test**: For a known study, manually sum subject-level stats and verify they match dataset-level stats, which in turn match study-level stats.

**Acceptance Scenarios**:

1. **Given** `sourcedata+subjects.tsv` with 16 subjects each having bold_num=3, **When** `sourcedata.tsv` is read, **Then** bold_num=48 (sum) and subjects_num=16 (count unique).
2. **Given** `sourcedata.tsv` for a study, **When** `studies.tsv` is generated from it, **Then** the study row's bold_num, t1w_num, subjects_num match the sourcedata.tsv aggregation.

---

### Edge Cases

- **Empty sourcedata directory**: A study may have a sourcedata/ directory but no subdatasets inside it (e.g., during initial setup). Extraction MUST return empty results, not fail.
- **Uninitialized subdatasets**: If a sourcedata subdataset is not initialized (empty directory with gitlink only), the workflow MUST initialize it before extraction and leave it initialized after (sourcedata is kept initialized; derivatives are dropped after extraction).
- **Mixed single/multi-session datasets**: A study with multiple sourcedata datasets where one is single-session and another is multi-session. The TSV filename MUST use the `+sessions` variant if ANY source has sessions.
- **Failed extraction for one subject**: If imaging metrics extraction fails for some subjects but succeeds for others, the successfully extracted metrics MUST be preserved and the failures MUST be logged at WARNING level with contextual identifiers.
- **Extraction failure exceeding threshold**: If more than 50% of subjects fail extraction due to operational errors (not expected failures like missing remote URLs), the extraction MUST raise RuntimeError to prevent producing misleading partial data.
- **No BOLD files**: A study with only anatomical data (no func/ directory). bold_num MUST be 0, and bold_size, bold_duration_total, bold_voxels_total MUST be "n/a".
- **Stale intermediate files**: If a sourcedata+subjects.tsv exists from a previous extraction but the underlying data has changed, Snakemake MUST detect the change (via git SHA params) and regenerate the file.
- **Concurrent extraction**: Multiple Snakemake jobs extracting different studies in parallel. Each study's extraction MUST be independent; no shared mutable state between studies.
- **Missing JSON sidecars**: If schema JSON files are missing from `bids_studies/schemas/`, the extraction MUST still produce TSV files and log a warning about the missing sidecar.
- **Derivative without subjects**: A derivative dataset that has dataset-level outputs (e.g., group analysis) but no per-subject directories. Extraction MUST produce a derivatives.tsv row with subjects_num=0 but still capture size and version metadata.

---

## Requirements

### Functional Requirements

#### Extraction Hierarchy

- **FR-HE-001**: The `bids_studies` library MUST extract statistics at four hierarchical levels: per-subject, per-dataset, per-study, and cross-study. Statistics are computed at the lowest level and aggregated upward.

- **FR-HE-002**: Per-subject extraction MUST produce one row per (source_id, subject_id) for single-session datasets, or one row per (source_id, subject_id, session_id) for multi-session datasets. Session detection MUST filter out non-session directories (e.g., BIDS datatypes like anat/, func/) by requiring the `ses-` prefix.

- **FR-HE-003**: Per-dataset aggregation MUST aggregate subject-level stats using the following methods:
  - **Count unique**: subjects_num
  - **Sum**: bold_num, t1w_num, t2w_num, bold_size, t1w_size, sessions_num, bold_duration_total, bold_voxels_total
  - **Min/Max**: sessions_min, sessions_max, bold_size_max
  - **Weighted mean**: bold_duration_mean (weighted by bold_num), bold_voxels_mean (weighted by bold_num)
  - **Set union**: datatypes (comma-separated, sorted)

- **FR-HE-004**: Per-study aggregation MUST aggregate dataset-level stats across all sourcedata datasets within a study. Aggregation methods are the same as FR-HE-003 applied one level up.

- **FR-HE-005**: Cross-study aggregation MUST produce the top-level `studies.tsv` by reading each study's per-dataset stats and combining with study-level metadata (name, version, bids_version, license, authors, derivative_ids). The aggregation step MUST NOT require access to actual sourcedata subdatasets -- all needed data is in intermediate TSV files.

#### Sourcedata TSV Files

- **FR-HE-010**: System MUST generate `sourcedata+subjects.tsv` (or `sourcedata+subjects+sessions.tsv` for multi-session) within each study's `sourcedata/` directory. Required columns: source_id, subject_id, session_id, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_duration_total, bold_duration_mean, bold_voxels_total, bold_voxels_mean, datatypes.

- **FR-HE-011**: System MUST generate `sourcedata.tsv` within each study's `sourcedata/` directory with per-source-dataset aggregated statistics. Required columns: source_id, subjects_num, sessions_num, sessions_min, sessions_max, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_size_max, bold_duration_total, bold_duration_mean, bold_voxels_total, bold_voxels_mean, datatypes.

- **FR-HE-012**: System MUST generate JSON sidecar files (`sourcedata+subjects.json`, `sourcedata.json`) describing column purposes and units following BIDS conventions. Sidecars MUST be copied from canonical schemas in `bids_studies/schemas/`.

- **FR-HE-013**: Hierarchical stats files MUST be stored within study datasets but OUTSIDE submodules. For example, `study-ds000001/sourcedata/sourcedata+subjects.tsv` -- NOT inside `study-ds000001/sourcedata/ds000001/`. This ensures original datasets remain unmodified.

#### Derivative TSV Files

- **FR-HE-020**: System MUST generate `derivative+subjects.tsv` (or `derivative+subjects+sessions.tsv` for multi-session) within each derivative's directory under `derivatives/`. Required columns: source_id, derivative_id, subject_id, session_id, output_num, output_size, nifti_num, nifti_size, html_num.

- **FR-HE-021**: System MUST generate `derivatives.tsv` within each study's `derivatives/` directory with per-derivative aggregated statistics plus identity metadata. One row per derivative. This file MUST contain all information needed to produce the top-level `studies+derivatives.tsv` without access to derivative subdatasets.

- **FR-HE-022**: System MUST generate JSON sidecar files (`derivatives+subjects.json`, `derivatives+datasets.json`) for derivative TSV files.

- **FR-HE-023**: Derivative extraction MUST capture version tracking metadata: processed_raw_version, current_raw_version, uptodate (boolean), and outdatedness (commit count).

- **FR-HE-024**: Derivative extraction MUST capture completeness metadata: tasks_processed, tasks_missing, anat_processed, func_processed, processing_complete, template_spaces, transform_spaces, descriptions.

- **FR-HE-025**: Derivative extraction MUST capture size metadata from git-annex: size_total (git-tracked + annexed), size_annexed, file_count.

#### Cross-Study Aggregation

- **FR-HE-030**: System MUST generate top-level `studies+derivatives.tsv` by reading each study's `derivatives/derivatives.tsv` (or cached `.derivatives.tsv`) and prefixing with study_id. No access to actual derivative subdatasets is required for this step.

- **FR-HE-031**: System MUST generate top-level `studies.tsv` by aggregating each study's `sourcedata.tsv` stats with study-level metadata. The aggregation MUST NOT require subdataset access -- all data comes from intermediate files.

#### Efficiency and Incremental Processing

- **FR-HE-040**: System MUST use Snakemake for workflow orchestration with git SHA-based dependency tracking. A study MUST be re-extracted only when:
  - Its gitlink SHA changes (sourcedata or study updated)
  - The extraction logic version changes (EXTRACTION_VERSION bumped)
  - A forced re-run is requested

- **FR-HE-041**: System MUST support parallel extraction across studies via Snakemake's `--cores` parameter. Each study's extraction MUST be independent with no shared mutable state.

- **FR-HE-042**: System MUST support single-study extraction for debugging (e.g., `make extract-one STUDY=study-ds002843`).

- **FR-HE-043**: Provenance records MUST be maintained for each extraction output, recording the rule name, dependency SHAs, and timestamp. These records enable auditing which version of data and code produced each output.

#### Subdataset Management

- **FR-HE-050**: Before extraction, the workflow MUST initialize sourcedata subdatasets that are not already initialized. Initialization failure for sourcedata MUST be treated as a fatal error (fail-fast).

- **FR-HE-051**: Before derivative extraction, the workflow MUST initialize derivative subdatasets. Initialization failure for derivatives MUST be treated as a warning (best-effort), not fatal.

- **FR-HE-052**: After derivative extraction, the workflow MUST deinitialize derivative subdatasets that were initialized by the workflow (to free disk space). Sourcedata subdatasets MUST remain initialized for future operations.

- **FR-HE-053**: Subdataset initialization and deinitialization MUST use DataLad commands (`datalad install`/`datalad uninstall`), not direct `git submodule` commands.

#### Error Handling

- **FR-HE-060**: Extraction errors MUST be logged at WARNING or ERROR level (never silently swallowed at DEBUG level only). This complies with Constitution Principle V (Error Visibility).

- **FR-HE-061**: Extraction functions MUST return both results and accumulated errors as a tuple `(results, errors)`. Callers MUST inspect the error list.

- **FR-HE-062**: If operational errors exceed a threshold (currently: any operational error triggers failure), the extraction MUST raise RuntimeError with contextual error messages including dataset ID, subject ID, and file path.

- **FR-HE-063**: Expected failures (e.g., missing remote URLs for individual files in sparse access) MUST be classified separately from operational failures and logged at INFO level. Classification logic MAY reside in the `openneuro_studies` package since it is deployment-specific.

- **FR-HE-064**: Error logs MUST be written to accessible locations: structured JSONL at `{study}/sourcedata/errors.jsonl` and legacy plain-text at `{study}/sourcedata/extraction_errors.log`.

#### Library Boundary

- **FR-HE-070**: All generic extraction logic (per-subject stats, per-dataset aggregation, per-study aggregation, TSV read/write, column definitions, JSON schema files) MUST reside in `bids_studies`.

- **FR-HE-071**: The `bids_studies` package MUST NOT import from `openneuro_studies`. Any shared functionality needed by both packages MUST reside in `bids_studies`.

- **FR-HE-072**: The `openneuro_studies` package provides CLI commands, Snakemake integration, subdataset install/drop orchestration, and deployment-specific error classification. It calls into `bids_studies` extraction functions.

- **FR-HE-073**: All derivative metadata extraction logic (file listing, size computation from git-annex, subject counting, version tracking, completeness analysis) MUST reside in `bids_studies`. Currently some of this logic is in `openneuro_studies/metadata/derivative_extractor.py` and MUST be migrated.

#### Data Format

- **FR-HE-080**: TSV files MUST use tab (`\t`) as the field separator. Values MUST NOT be quoted or escaped using CSV conventions. JSON values within fields (e.g., bold_trs) MUST be written as raw strings.

- **FR-HE-081**: Missing or unknown values MUST be represented as `n/a` (not empty string, not `None`, not `null`).

- **FR-HE-082**: Column names MUST follow BIDS tabular file conventions using snake_case. Exception: fields copied from BIDS metadata (e.g., BIDSVersion) preserve CamelCase.

- **FR-HE-083**: TSV file naming MUST use `+` to join entity names per BIDS issue #2273 (e.g., `sourcedata+subjects.tsv`, `studies+derivatives.tsv`).

---

### Key Entities

- **SubjectStats**: Per-subject statistics for a single sourcedata dataset. Key attributes: source_id, subject_id, session_id, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_duration_total, bold_duration_mean, bold_voxels_total, bold_voxels_mean, datatypes.

- **DatasetStats**: Aggregated statistics for a single sourcedata dataset across all subjects. Key attributes: source_id, subjects_num, sessions_num, sessions_min, sessions_max, plus aggregated versions of SubjectStats fields.

- **DerivativeSubjectStats**: Per-subject statistics for a single derivative dataset. Key attributes: source_id, derivative_id, subject_id, session_id, output_num, output_size, nifti_num, nifti_size, html_num.

- **DerivativeDatasetStats**: Aggregated statistics for a single derivative dataset, plus identity and version tracking metadata. Key attributes: derivative_id, tool_name, tool_version, datalad_uuid, url, size_total, size_annexed, file_count, processing completeness metrics, plus aggregated DerivativeSubjectStats fields.

- **StudyStats**: Aggregated statistics for a study across all its sourcedata datasets. Computed by aggregating DatasetStats entries. Used to populate columns in studies.tsv.

- **ProvenanceRecord**: Tracks which data and code version produced each extraction output. Key attributes: output_path, rule_name, dependency_shas, timestamp.

---

## Success Criteria

### Measurable Outcomes

- **SC-001**: All study datasets with initialized sourcedata subdatasets have `sourcedata+subjects.tsv` and `sourcedata.tsv` generated with correct, non-empty data.

- **SC-002**: `studies.tsv` numeric columns (subjects_num, bold_num, bold_size, etc.) are populated from hierarchical aggregation of intermediate TSV files, not from direct re-extraction. Aggregated values match direct extraction values (regression test).

- **SC-003**: `studies+derivatives.tsv` is generated by reading per-study `derivatives.tsv` (or cached files) without accessing derivative subdatasets. The generation step completes in under 10 seconds for 40 studies.

- **SC-004**: Incremental extraction (no changes) completes in under 5 seconds for 40 studies. Extraction of a single changed study completes in under 5 minutes (including subdataset initialization).

- **SC-005**: All extraction errors are visible in logs at WARNING or ERROR level. No "n/a" values appear in TSV files without a corresponding log entry explaining the failure.

- **SC-006**: Unit tests achieve at least 90% code coverage for extraction modules in `bids_studies/extraction/`.

- **SC-007**: The `bids_studies` package has zero imports from `openneuro_studies` (verified by static analysis or import test).

- **SC-008**: Per-subject extraction correctly handles single-session, multi-session, and mixed datasets (verified by integration tests with known study datasets ds000001, ds000030, ds006190).
