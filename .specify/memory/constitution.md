<!--
SYNC IMPACT REPORT
==================
Version Change: Initial (template) → 1.0.0
Principle Changes:
  - Added: I. Data Integrity & Traceability
  - Added: II. Automation & Reproducibility
  - Added: III. Standard Formats
  - Added: IV. Git/DataLad-First Workflow
  - Added: V. Observability & Monitoring
Added Sections:
  - Data Management Standards
  - Development Workflow
  - Governance
Removed Sections: None
Templates Status:
  ✅ plan-template.md - Constitution Check section aligned
  ✅ spec-template.md - Requirements sections aligned with data integrity principles
  ✅ tasks-template.md - Task categorization supports automation and reproducibility
  ⚠ agent-file-template.md - Generic template, no updates required
  ⚠ checklist-template.md - Generic template, no updates required
Follow-up TODOs: None
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
- Scripts MUST handle partial completion and resume capability
- All external API calls MUST implement caching to avoid rate limits and ensure reproducibility

**Rationale**: With 1000+ datasets, manual operations are error-prone and unscalable. Automation ensures consistency and allows independent verification of all data transformations.

### III. Standard Formats

Use text-based, human-readable formats for all configuration and metadata.

- TSV files for tabular data (studies.tsv, derivatives.tsv) to enable command-line tools like visidata
- JSON for structured metadata following BIDS specification standards
- YAML for configuration where hierarchical structure is required
- AVOID binary formats or databases that require special tools to inspect

**Rationale**: Text formats enable version control, diff viewing, and inspection with standard Unix tools. This aligns with the scientific principle of transparent, inspectable data.

### IV. Git/DataLad-First Workflow

All state changes MUST be committed through git/DataLad with descriptive messages.

- Use `datalad run` for scripts that modify the repository state
- Dirty trees are acceptable only with explicit `--input` and `--output` flags
- Commit messages MUST reference issue numbers or describe the batch operation
- Git submodules MUST be updated with `git submodule update --init` when needed

**Rationale**: DataLad extends git to handle large datasets while maintaining complete provenance. This provides scientific audit trails and enables distributed collaboration.

### V. Observability & Monitoring

The state of all datasets MUST be queryable and monitorable.

- Summary files (studies.tsv) MUST provide complete overview of dataset status
- Incomplete or non-BIDS datasets MUST be clearly marked (e.g., "n/a" entries)
- Dashboard generation MUST be supported (per study, per dataset, per subject/session)
- Validation results (bids-validation, mriqc, fmriprep) MUST be tracked when available

**Rationale**: With 1000+ studies, operators need quick visibility into dataset status, missing data, and processing completeness without inspecting individual directories.

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
- Support multiple versions of same tool simultaneously
- derivatives.tsv MUST list all available derivatives with versions

### Metadata Completeness

- studies.tsv MUST include: Study ID, Name, BIDS version, License, Authors, derivatives list
- Missing or unknown values MUST be explicitly marked "n/a" rather than omitted
- GitHub repository information MUST be preserved in submodule configuration

## Development Workflow

### Script Development

When creating or modifying automation scripts:

1. Test on a small subset of datasets first (e.g., ds000001-ds000010)
2. Implement robust error handling for non-conformant datasets
3. Use caching for all external API calls (GitHub, etc.)
4. Provide progress indicators for long-running operations
5. Document expected inputs, outputs, and environment variables (e.g., GITHUB_TOKEN)

### Dependencies

Scripts may assume the following environment:

- Bash shell with standard Unix tools
- Git with submodule support
- curl for HTTP requests
- jq for JSON processing
- Python for complex JSON manipulation
- DataLad for dataset operations
- Environment variable: `GITHUB_TOKEN` for API access

### Testing Approach

Before running scripts on the full dataset collection:

1. Verify on a single dataset (e.g., study-ds000001)
2. Test with datasets of different states (complete, incomplete, non-BIDS)
3. Verify idempotency by running twice and comparing results
4. Check that git history shows expected commits

## Governance

### Constitution Authority

This constitution defines the core principles for the OpenNeuroStudies project. All scripts, workflows, and features MUST align with these principles.

### Amendment Process

1. Proposed changes MUST be documented with rationale
2. Breaking changes to data structure require MAJOR version bump
3. New principles or substantial additions require MINOR version bump
4. Clarifications and refinements require PATCH version bump
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

**Version**: 1.0.0 | **Ratified**: 2025-10-08 | **Last Amended**: 2025-10-08
