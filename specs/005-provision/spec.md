# Feature Specification: Provision Command

**Feature Branch**: `005-provision`
**Created**: 2026-05-07
**Status**: Draft
**Input**: Standalone CLI command to provision study datasets with templated content
**Parent Requirements**: FR-041, FR-041a from `specs/001-read-file-doc/spec.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Provision All Studies After Organize (Priority: P1)

As a dataset curator, after organizing new study datasets with `openneuro-studies organize`, I need to provision them with standardized content (validation scripts, README, version tracking) so that each study has a consistent, self-contained structure that supports automated BIDS validation via `datalad run`.

**Why this priority**: Provisioning is the essential step that makes study datasets usable. Without the `code/run-bids-validator` script, studies cannot participate in automated validation workflows. Without `README.md`, studies lack discoverability. This is the core value proposition of the provision command.

**Independent Test**: Can be fully tested by running `openneuro-studies provision` against a set of study directories and verifying that all three files (`code/run-bids-validator`, `README.md`, `.openneuro-studies/template-version`) are created with correct content and permissions.

**Acceptance Scenarios**:

1. **Given** multiple study directories exist (e.g., `study-ds000001/`, `study-ds005256/`) that have not been provisioned, **When** `openneuro-studies provision` is run without arguments, **Then** all study directories receive `code/run-bids-validator` (executable), `README.md` (with dataset-specific links), and `.openneuro-studies/template-version` (with current version string)
2. **Given** the provision command completes successfully, **When** `datalad run code/run-bids-validator` is invoked within any provisioned study, **Then** BIDS validation executes and outputs are stored in `derivatives/bids-validator/`
3. **Given** a study `study-ds000001`, **When** provisioned, **Then** `README.md` contains links to `https://openneuro.org/datasets/ds000001` and `https://github.com/{configured_org}/study-ds000001`
4. **Given** the `--commit` flag is enabled (default), **When** provisioning completes, **Then** changes within each study subdataset are committed, and the parent repository is committed with a descriptive message including the count of provisioned studies

---

### User Story 2 - Incremental Provisioning with Version Tracking (Priority: P2)

As a dataset curator managing hundreds of studies, I need the provision command to skip studies that are already at the current template version so that re-running provisioning is efficient and only updates studies that need changes.

**Why this priority**: With 1000+ studies, efficiency matters. Running provisioning across all studies should complete quickly by skipping those already up-to-date. Version tracking also enables future template upgrades where only outdated studies are updated.

**Independent Test**: Can be tested by provisioning a study, then running provision again and verifying it is skipped. Then bumping `TEMPLATE_VERSION` and verifying the study is re-provisioned.

**Acceptance Scenarios**:

1. **Given** a study already provisioned with template version `1.2.0`, **When** `openneuro-studies provision` runs and `TEMPLATE_VERSION` is `1.2.0`, **Then** the study is skipped with message "skipped (up-to-date)"
2. **Given** a study provisioned with template version `1.0.0`, **When** `openneuro-studies provision` runs and `TEMPLATE_VERSION` is `1.2.0`, **Then** the study is re-provisioned with the updated template
3. **Given** a study already at current version, **When** `openneuro-studies provision --force` is run, **Then** the study is re-provisioned regardless of version match
4. **Given** 100 studies where 95 are current and 5 are outdated, **When** provisioning runs, **Then** only 5 studies are processed and the summary reports "Provisioned: 5, Skipped: 95"

---

### User Story 3 - Preview Changes Before Provisioning (Priority: P3)

As a dataset curator, I need to preview what provisioning would do before executing it so that I can verify the scope of changes, especially when running against a large collection.

**Why this priority**: Dry-run capability provides safety and transparency, important for operations that modify many study datasets at once. Less critical than actual provisioning functionality.

**Independent Test**: Can be tested by running `openneuro-studies provision --dry-run` and verifying that no files are created or modified on disk, while the output lists which studies would be provisioned and what files would be created vs updated.

**Acceptance Scenarios**:

1. **Given** an unprovisioned study, **When** `openneuro-studies provision --dry-run` is run, **Then** no files are created but output shows "create: code/run-bids-validator, README.md, .openneuro-studies/template-version"
2. **Given** a study provisioned with an older template version, **When** `openneuro-studies provision --dry-run` is run, **Then** output shows "update: code/run-bids-validator, README.md, .openneuro-studies/template-version"
3. **Given** all studies are at current version, **When** `openneuro-studies provision --dry-run` is run, **Then** all studies show "skipped (up-to-date)" and summary shows "Would provision: 0"

---

### User Story 4 - Selective Provisioning of Specific Studies (Priority: P3)

As a dataset curator, I need to provision specific studies by ID so that I can target individual studies for provisioning without processing the entire collection.

**Why this priority**: Selective provisioning is convenient for single-study workflows and debugging but not essential for the core batch provisioning workflow.

**Independent Test**: Can be tested by running `openneuro-studies provision study-ds000001` and verifying only that study is processed while others are untouched.

**Acceptance Scenarios**:

1. **Given** multiple study directories exist, **When** `openneuro-studies provision study-ds000001 study-ds005256` is run, **Then** only those two studies are provisioned
2. **Given** a study ID provided as `ds000001` (without `study-` prefix), **When** provision is run, **Then** the system normalizes it to `study-ds000001` and provisions correctly
3. **Given** a study ID that does not correspond to an existing directory, **When** provision is run, **Then** a warning is emitted to stderr and other valid studies are still processed

---

### Edge Cases

- What happens when copier is not installed? System should fall back to `python -m copier` and if that also fails, return an error with installation instructions.
- What happens when a study directory exists but is empty (no git repo)? Provisioning should still create the files since it only requires the directory to exist.
- What happens when template files exist but `.openneuro-studies/template-version` is missing? Study is treated as needing provisioning (version tracking file is the authority).
- What happens when provisioning is interrupted mid-way through multiple studies? Each study is provisioned independently; completed studies retain their changes while incomplete ones remain unchanged.
- What happens when the `code/` directory does not exist in a study? Copier should create it as part of provisioning.
- What happens when provisioning runs in parallel with organize? Provisioning should be run after organize completes, not concurrently. The current implementation is sequential per study.
- What happens when a study was manually modified after provisioning (e.g., custom README)? Re-provisioning with `--force` overwrites manual changes. Without `--force`, the study is skipped if at current version.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-005-001**: System MUST provide a standalone `provision` CLI command accessible as `openneuro-studies provision [STUDY_IDS...]`
- **FR-005-002**: System MUST provision each study with three files: `code/run-bids-validator` (executable bash script), `README.md` (study overview with dataset-specific links), and `.openneuro-studies/template-version` (version tracking)
- **FR-005-003**: System MUST use Copier templates for file generation, supporting variable substitution for `study_id`, `dataset_id`, `template_version`, and `github_org`
- **FR-005-004**: System MUST track template version in `.openneuro-studies/template-version` within each provisioned study to enable incremental updates
- **FR-005-005**: System MUST skip studies already at current template version unless `--force` is specified
- **FR-005-006**: System MUST support `--dry-run` mode that reports what would change without modifying any files
- **FR-005-007**: System MUST support `--force` flag to re-provision studies regardless of current template version
- **FR-005-008**: System MUST support `--commit/--no-commit` flag (default: commit) to control whether changes are committed via git
- **FR-005-009**: System MUST accept optional study ID arguments to provision specific studies; when omitted, all `study-*` directories are processed
- **FR-005-010**: System MUST normalize study ID input, accepting both `study-ds000001` and `ds000001` formats
- **FR-005-011**: System MUST make the `code/run-bids-validator` script executable (mode 0755) after provisioning
- **FR-005-012**: System MUST extract `dataset_id` from `study_id` by stripping the `study-` prefix (e.g., `study-ds000001` yields `ds000001`)
- **FR-005-013**: System MUST display a summary after provisioning showing counts of provisioned, skipped, and errored studies
- **FR-005-014**: System MUST return a structured `ProvisionResult` for each study with fields: `study_id`, `provisioned` (bool), `files_created` (list), `files_updated` (list), `template_version` (str), and optional `error` (str)
- **FR-005-015**: System MUST commit changes in study subdatasets first, then commit the parent repository with descriptive statistics
- **FR-005-016**: System MUST be idempotent -- running provision multiple times with the same template version produces the same result
- **FR-005-017**: The `code/run-bids-validator` script MUST support multiple validator backends in priority order: uvx, bids-validator-deno, deno, npx
- **FR-005-018**: The `code/run-bids-validator` script MUST store outputs in `derivatives/bids-validator/` with files: `version.txt`, `report.json`, `report.txt`
- **FR-005-019**: The `README.md` MUST include links to the OpenNeuro dataset page, GitHub repository, and BIDS BEP035 specification
- **FR-005-020**: System MUST log provisioning operations at INFO level and errors at ERROR level via Python logging

### Key Entities

- **ProvisionResult**: Dataclass tracking the outcome of provisioning a single study. Key attributes: study_id, provisioned (bool), files_created (list of relative paths), files_updated (list of relative paths), template_version (current version string), error (optional error message).

- **Copier Template**: A template directory at `code/src/openneuro_studies/provision/templates/study/` containing Jinja-rendered files and a `copier.yaml` configuration. Variables: study_id, dataset_id, template_version, github_org.

- **Template Version**: A string constant (`TEMPLATE_VERSION` in `provisioner.py`) that tracks the current template version. Incremented when template content changes. Stored per-study in `.openneuro-studies/template-version`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `openneuro-studies provision` successfully provisions all existing study directories (100% success rate for directories that exist and are accessible)
- **SC-002**: Incremental provisioning of 1000+ studies where 95% are current completes in under 30 seconds (version check is fast)
- **SC-003**: All provisioned studies pass `shellcheck` on the generated `code/run-bids-validator` script
- **SC-004**: `datalad run code/run-bids-validator` succeeds in any provisioned study when a BIDS validator is available
- **SC-005**: Running `openneuro-studies provision` twice in succession produces identical study content (idempotency)
- **SC-006**: All unit tests for provisioner module pass (template version tracking, dry-run, force, error handling)
- **SC-007**: All integration tests for copier template rendering pass (variable substitution, directory creation, idempotency)

## Assumptions

- Copier (version 9.0.0+) is available either as a standalone command or via `python -m copier`
- Study directories follow the naming convention `study-{dataset_id}` and exist at repository root level
- The configured GitHub organization is used for README links (defaults to `OpenNeuroStudies`)
- Template changes are tracked by bumping `TEMPLATE_VERSION` in `provisioner.py`; there is no automated version detection from template file changes
- Provisioning does not require network access; all templates are bundled with the package

## Out of Scope

- Template customization per-study (all studies receive the same template with different variable values)
- Automatic detection of template changes for version bumping (manual process)
- Integration with the `organize` command (provisioning is deliberately separate to allow independent use)
- Provisioning of non-study directories (only `study-*` directories are processed)
- Custom template directories specified by the user (templates are bundled with the package)
- A `--when` option for controlling provisioning timing (unlike validate, provision runs on demand)
- Make target for provisioning (could be added later; currently only CLI)
