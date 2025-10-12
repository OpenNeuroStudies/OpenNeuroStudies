<!--
SYNC IMPACT REPORT
==================
Version Change: 1.20251011.0 → 1.20251011.1
Principle Changes:
  - AMENDED PRINCIPLE IV: Git/DataLad-First Workflow
    * Added: Operations MUST result in clean git status across entire hierarchy
    * Added: Empty directories MUST be created for gitlinks to prevent "deleted" status
    * Clarified: Clean status ensures operations are complete
Amended Sections:
  - Core Principles: Updated Principle IV (Git/DataLad-First Workflow)
  - Impacts organize command implementation (already implemented)
  - Aligns with spec.md FR-004 and FR-004a
Templates Status:
  ✅ Implementation complete - organize command creates empty directories
  ✅ Tests verify clean status and gitlink presence
  ✅ Spec updated with FR-004a requirement
Follow-up TODOs:
  - None - changes fully implemented and tested
Previous Version (1.20251011.0):
  - Added Principle VI: No Silent Failures
  - Requires unorganized-datasets.json tracking (implementation pending)
-->

# OpenNeuroStudies Constitution

## Core Principles

### I. Data Integrity & Traceability

Every operation MUST maintain complete traceability of data sources and transformations.

- All datasets MUST be linked via git submodules with explicit version/commit references
- All transformations MUST be recorded in DataLad run records or equivalent git history
- Metadata files (dataset_description.json, studies.tsv, derivatives.tsv) MUST accurately reflect the current state
- Data provenance MUST be preserved across all reorganization operations

**Rationale**: Scientific reproducibility depends on knowing exactly which version of which dataset was used. Git submodules and DataLad provide the necessary version control infrastructure for large-scale neuroscience data.

### II. Automation & Reproducibility

All data operations MUST be scripted and reproducible from a clean repository state.

- Manual dataset manipulation is FORBIDDEN - all changes go through versioned scripts
- Scripts MUST be idempotent (running multiple times produces same result)
- All external API calls MUST implement caching to avoid rate limits and ensure reproducibility
- External API calls which makes sense to retry, should be retried on a wide range of remote service abnormal behavior or connection problems

**Rationale**: With 1000+ datasets, manual operations are error-prone and unscalable. Automation ensures consistency and allows independent verification of all data transformations.

### III. Standard Formats

Use text-based, human-readable formats for all configuration and metadata.

- TSV files for tabular data (studies.tsv, derivatives.tsv) to enable command-line tools like visidata
- TSV column names MUST follow BIDS tabular file conventions (https://bids-specification.readthedocs.io/en/stable/common-principles.html#tabular-files) using snake_case (e.g., study_id, subject_count, session_min)
- Exception: When copying metadata fields from JSON files that use CamelCase (e.g., BIDSVersion, SourceDatasets from dataset_description.json), preserve the original CamelCase naming in TSV columns
- JSON for structured metadata following BIDS specification standards, in particular to provide description for TSV file columns via .json sidecars
- YAML for configuration where hierarchical structure is required
- AVOID binary formats or databases that require special tools to inspect

**Rationale**: Text formats enable version control, diff viewing, and inspection with standard Unix tools. BIDS tabular file conventions ensure consistency and compatibility with the neuroscience ecosystem. This aligns with the scientific principle of transparent, inspectable data.

### IV. Git/DataLad-First Workflow

All state changes MUST be committed through git/DataLad with descriptive messages.

- Use `datalad run` for scripts that modify the repository state
- Operations MUST result in clean git status across the entire repository hierarchy (parent and all submodules) with all changes committed
- Dirty trees are acceptable only with explicit `--input` and `--output` flags and then using `run` with `--explicit` flag, but generally such operations should be avoided
- Commit messages MUST reference issue numbers or briefly describe the batch operation
- If feasible, commit messages MIGHT provide descriptive statistics on the changes (e.g. how many subdatasets were affected)
- Git submodules MUST be updated with `git submodule update --init` when needed
- For gitlinks created without cloning (via `git update-index`), empty directories MUST be created at submodule paths to prevent "deleted" status markers

**Rationale**: DataLad extends git and git-annex to ease handling collections of large datasets while maintaining complete provenance. This provides scientific audit trails and enables distributed collaboration. Clean git status ensures operations are complete and no uncommitted changes exist.

### V. Observability & Monitoring

The state of all datasets MUST be queryable and monitorable.

- Summary files (studies.tsv) MUST provide complete overview of dataset status
- Incomplete or non-BIDS datasets MUST be clearly marked (e.g., "n/a" entries)
- Dashboard generation MUST be supported (per study, per dataset, per subject/session)
- Validation results (bids-validation, mriqc, fmriprep) MUST be tracked when available

**Rationale**: With 1000+ studies, operators need quick visibility into dataset status, missing data, and processing completeness without inspecting individual directories.

### VI. No Silent Failures

All discovered datasets MUST be either organized or explicitly tracked as unorganized with documented reasons.

- Discovered datasets that cannot be organized MUST be tracked in `.openneuro-studies/unorganized-datasets.json`
- Each unorganized dataset MUST include a reason code (e.g., `raw_dataset_not_found`, `invalid_source_reference`)
- Unorganized datasets MUST be reported to the user during organize operations
- Periodic re-evaluation of unorganized datasets SHOULD be performed when new datasets are discovered

**Rationale**: Silent failures hide data quality issues and make it impossible to track the completeness of dataset organization. Explicit tracking enables operators to identify gaps, missing dependencies, and take corrective action. This is especially critical for derivative datasets that may reference raw datasets not yet available in the repository.

## Data Management Standards

### BIDS Compliance

All study datasets MUST follow BIDS 1.10.1+ specification for study datasets:

- `DatasetType: "study"` in dataset_description.json
- `sourcedata/raw/` contains original raw BIDS dataset
- `derivatives/` contains processed datasets organized by tool and version
- Original metadata preserved with `BIDSRawVersion` and `BIDSRawAuthors` fields

### Derivative Versioning

Derivative datasets MUST include version information:

- Folder naming: `toolname-version` (e.g., `fmriprep-21.0.1`)
- Support multiple versions of same tool simultaneously by adding first 8 letters of DataLad UUID (under `.datalad/config`)
- studies_derivatives.tsv (tall format at top level) MUST list all study-derivative pairs with versions, extracted statistics of size (from `git annex info`), execution metrics if collected using `con-duct`, and potentially other metrics such as successful completion, outdatedness, etc

### Metadata Completeness

- studies.tsv MUST include: study_id, name, version, raw_version, bids_version, hed_version, license, authors, subjects_num, sessions_num, sessions_min, sessions_max (or "n/a" if single session), bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_size_max, bold_voxels, datatypes (`anat`, `func`, ...), derivative_ids, bids_valid
- Missing or unknown values MUST be explicitly marked "n/a" rather than omitted
- GitHub repository information MUST be preserved in submodule configuration

## Development Workflow

### Script Development

When creating or modifying automation scripts:

1. Test on a small subset of datasets first (e.g., sample of ds000001, ds000010, ds005256, ds006131, ds006185, ds006189, ds006190)
2. Implement robust error handling for non-conformant datasets
3. Use caching for all external API calls (GitHub, etc.)
4. Provide progress indicators for long-running operations
5. Document expected inputs, outputs, and environment variables (e.g., GITHUB_TOKEN)

### Dependencies

Scripts may assume the following environment:

- Python overall is preferable; should be linted and accompanied with tests (unit and integration)
- Bash shell with standard Unix tools; should be checked using shellcheck
- Git with submodule support
- DataLad for dataset operations and provenance capture using `datalad run`
- duct (from `con-duct` if some long running processes desire capture of run time statistics and stdout/stderr)
- curl for HTTP requests
- jq for JSON processing
- Environment variable: `GITHUB_TOKEN` for API access

### Testing Approach

Before running scripts on the full dataset collection:

1. Verify on a single dataset (e.g., study-ds000001)
2. Test with datasets of different states (complete, incomplete, non-BIDS)
3. Test with multi-source derivatives (e.g., ds006190 which sources ds006189, ds006185, ds006131)
3. Verify idempotency by running twice and comparing results
4. Check that git history shows expected commits

## Governance

### Constitution Authority

This constitution defines the core principles for the OpenNeuroStudies project. All scripts, workflows, and features MUST align with these principles.

### Amendment Process

1. Proposed changes MUST be documented with rationale
2. Breaking changes to data structure require MAJOR version bump
3. MINOR version will be calendar based, such as 20251008
4. Clarifications and refinements require PATCH version bump for the same date
5. Changes MUST be propagated to dependent templates (plan, spec, tasks)

### Compliance Verification

When reviewing code or feature specifications:

- Verify automation scripts are idempotent and reproducible
- Verify all data sources have git/DataLad provenance
- Verify metadata files use standard text formats (TSV/JSON/YAML)
- Verify error handling for non-conformant datasets
- Verify API caching is implemented where needed

### Complexity Justification

Deviations from simplicity MUST be justified:

- Additional dependencies beyond core list → explain necessity
- Binary formats → explain why text format insufficient
- Manual operations → explain why automation not possible
- Database introduction → explain why file-based approach insufficient

**Version**: 1.20251011.1 | **Ratified**: 2025-10-08 | **Last Amended**: 2025-10-11
