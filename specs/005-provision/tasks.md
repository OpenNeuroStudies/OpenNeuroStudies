# Tasks: Provision Command

**Input**: Design documents from `/specs/005-provision/`
**Prerequisites**: spec.md (required)
**Parent Requirements**: FR-041, FR-041a from `specs/001-read-file-doc/spec.md`

## Implementation Status Review

This feature has substantial existing implementation. Tasks below are annotated with
status based on code review of the current codebase as of 2026-05-07.

---

## Phase 1: Core Provisioner Library

**Purpose**: Backend provisioning logic (Copier integration, version tracking, result reporting)

- [x] T001 [DONE] Create provisioner module at `code/src/openneuro_studies/provision/provisioner.py`
  - ProvisionResult dataclass with study_id, provisioned, files_created, files_updated, template_version, error
  - TEMPLATE_VERSION constant (currently "1.2.0")
  - TEMPLATE_DIR pointing to bundled templates
  - TEMPLATE_VERSION_FILE = ".openneuro-studies/template-version"

- [x] T002 [DONE] Implement `get_template_version(study_path)` function
  - Reads `.openneuro-studies/template-version` file
  - Returns version string or None if not provisioned

- [x] T003 [DONE] Implement `needs_provisioning(study_path, force)` function
  - Returns True if no version file, version differs, or force=True
  - Returns False if version matches current TEMPLATE_VERSION

- [x] T004 [DONE] Implement `_get_copier_cmd()` helper
  - Checks for `copier` binary in PATH
  - Falls back to `sys.executable -m copier`

- [x] T005 [DONE] Implement `_run_copier(study_path, study_id, dataset_id, github_org)` function
  - Tracks existing files before copier runs
  - Invokes copier with --force and --data flags for variable substitution
  - Classifies output files as created vs updated
  - Sets executable permission (0755) on code/run-bids-validator

- [x] T006 [DONE] Implement `provision_study(study_path, force, dry_run, github_org)` function
  - Validates study_path exists
  - Checks needs_provisioning
  - In dry_run mode: reports what would change without executing
  - In normal mode: calls _run_copier and returns ProvisionResult
  - Error handling with logging

- [x] T007 [DONE] Create `code/src/openneuro_studies/provision/__init__.py` with public API exports
  - Exports: TEMPLATE_VERSION_DIR, TEMPLATE_VERSION_FILE, ProvisionResult, needs_provisioning, provision_study

---

## Phase 2: Copier Templates

**Purpose**: Jinja templates for study dataset content

- [x] T008 [DONE] Create copier configuration at `code/src/openneuro_studies/provision/templates/study/copier.yaml`
  - Min copier version: 9.0.0
  - Template variables: study_id, dataset_id, template_version, github_org
  - Exclusions: copier.yaml, *.pyc, __pycache__, .git

- [x] T009 [DONE] Create README template at `templates/study/README.md.jinja`
  - Title with study_id
  - Links to OpenNeuro dataset page, GitHub repo, BEP035
  - Sections: Dataset Structure, Contents, Running BIDS Validation, Links, License
  - datalad run command example

- [x] T010 [DONE] Create validator script template at `templates/study/code/run-bids-validator.jinja`
  - Bash script with shebang and set -eu
  - Validator detection: uvx > bids-validator-deno > deno > npx
  - Output directory: derivatives/bids-validator/
  - Generates: version.txt, report.json, report.txt

- [x] T011 [DONE] Create version tracking template at `templates/study/.openneuro-studies/template-version.jinja`
  - Simple template: {{ template_version }}

---

## Phase 3: CLI Command

**Purpose**: Standalone `openneuro-studies provision` command

- [x] T012 [DONE] Create CLI command at `code/src/openneuro_studies/cli/provision.py`
  - Click command with @click.command() decorator
  - Arguments: STUDY_IDS (nargs=-1, optional)
  - Options: --force, --dry-run, --commit/--no-commit

- [x] T013 [DONE] Implement study discovery logic in CLI
  - When STUDY_IDS provided: normalize (strip/add study- prefix) and resolve paths
  - When omitted: discover all study-* directories at root

- [x] T014 [DONE] Implement provisioning loop with result tracking
  - Iterate over study_paths, call provision_study for each
  - Track provisioned_count, skipped_count, error_count
  - Display per-study status (provisioned, skipped, error)

- [x] T015 [DONE] Implement summary output
  - Display totals: provisioned, skipped, errors
  - Differentiate dry-run vs actual provisioning in output

- [x] T016 [DONE] Implement commit logic (--commit flag)
  - Commit changes in each study subdataset first
  - Commit parent repository with stats via save_with_stats

- [x] T017 [DONE] Register provision command in `code/src/openneuro_studies/cli/main.py`
  - Import provision command
  - Add via cli.add_command(provision_cmd, name="provision")

---

## Phase 4: Unit Tests

**Purpose**: Unit tests for provisioner module

- [x] T018 [DONE] Create test file at `code/tests/unit/test_provision.py`

- [x] T019 [DONE] TestTemplateVersionTracking tests
  - test_template_version_file_path: verify constants
  - test_get_template_version_missing: returns None
  - test_get_template_version_exists: returns version string
  - test_needs_provisioning_no_version_file: returns True
  - test_needs_provisioning_outdated_version: returns True
  - test_needs_provisioning_current_version: returns False
  - test_needs_provisioning_force: returns True

- [x] T020 [DONE] TestProvisionStudy tests
  - test_provision_creates_files: verifies all three files
  - test_provision_creates_validator_script: executable, correct content
  - test_provision_creates_readme: dataset-specific content
  - test_provision_creates_version_file: correct version string
  - test_provision_nonexistent_study: returns error
  - test_provision_already_current: skips
  - test_provision_force_reprovision: updates even if current
  - test_provision_dry_run: no files created

- [x] T021 [DONE] TestValidatorScriptContent tests
  - test_script_uses_uvx_first: uvx checked before npx
  - test_script_outputs_to_correct_directory: derivatives/bids-validator/
  - test_script_has_error_handling: set -eu present

- [x] T022 [DONE] TestReadmeContent tests
  - test_readme_has_openneuro_link: correct dataset URL
  - test_readme_has_bids_study_link: BEP035 reference
  - test_readme_explains_datalad_run: command usage

---

## Phase 5: Integration Tests

**Purpose**: Integration tests for copier template rendering

- [x] T023 [DONE] Create test file at `code/tests/integration/test_provision_copier.py`
  - Skip if copier not available (pytestmark)

- [x] T024 [DONE] Template structure tests
  - test_copier_template_exists: verify all template files
  - test_copier_creates_directories: code/ and .openneuro-studies/

- [x] T025 [DONE] Template rendering tests
  - test_copier_template_renders: basic rendering success
  - test_copier_template_variable_substitution: correct values in output
  - test_copier_template_different_dataset: verify with different inputs
  - test_copier_template_script_content: validator script correctness
  - test_copier_template_readme_structure: expected sections

- [x] T026 [DONE] Quality tests
  - test_copier_excludes_config: copier.yaml not in output
  - test_copier_idempotent: two runs produce identical output
  - test_provisioner_copier_integration: end-to-end via provision_study

---

## Phase 6: Integration with Organize and Make

**Purpose**: Connect provisioning to the broader workflow

- [x] T027 [DONE] Add `make provision` target to Makefile
  - Target: `provision` and `provision-force`
  - Command: `openneuro-studies provision` / `openneuro-studies provision --force`
  - Added to .PHONY, help output, and discovery workflow section

- [x] T028 [DONE] Consider calling provision from organize workflow
  - Currently provision is NOT called from organize (deliberate separation)
  - Decision: keep separate for now; provision is an independent step in the pipeline
  - The `make full-refresh` target chains organize -> provision -> extract

- [x] T029 [DONE] Add provision step to `make full-refresh` pipeline
  - After organize, before metadata generation
  - full-refresh: studies-init discover organize provision extract metadata

- [x] T030 [DONE] Add `--when` option to provision command (parity with validate)
  - Modes: `always` (provision all, implies --force), `outdated` (only outdated versions, default)
  - --when=always is equivalent to --force for clarity

---

## Phase 7: Documentation and Polish

**Purpose**: Documentation and cross-cutting improvements

- [x] T031 [DONE] Add provision command to CLAUDE.md common commands section
  - Added to "Production Operations (Use Make)" section: make provision, make provision-force
  - Added to "Direct CLI Usage" section with examples

- [x] T032 [DONE] Add provision to project README.md workflow description
  - Added workflow line: discover -> organize -> provision -> extract -> validate

- [x] T033 [DONE] Run shellcheck on generated run-bids-validator script
  - Verified: template output passes shellcheck with zero warnings

- [x] T034 [DONE] Add CLI test for provision command (Click test runner)
  - test_provision_help: verifies --help output includes all options
  - test_provision_no_studies: verifies error message when no studies found
  - test_provision_dry_run_with_studies: verifies dry-run output
  - test_provision_specific_studies: verifies specific study targeting
  - test_provision_normalizes_study_ids: verifies ds000001 -> study-ds000001
  - test_provision_invalid_study_id: verifies warning for missing study
  - test_provision_when_always: verifies --when=always forces re-provisioning
  - test_provision_when_outdated_skips_current: verifies --when=outdated skips current

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1** (Core Library): No dependencies -- DONE
- **Phase 2** (Templates): No dependencies -- DONE
- **Phase 3** (CLI Command): Depends on Phase 1 -- DONE
- **Phase 4** (Unit Tests): Depends on Phase 1 -- DONE
- **Phase 5** (Integration Tests): Depends on Phases 1-2 -- DONE
- **Phase 6** (Workflow Integration): Depends on Phase 3 -- DONE
- **Phase 7** (Documentation): Depends on Phase 3 -- DONE

### Summary

| Phase | Status | Tasks Done | Tasks TODO |
|-------|--------|------------|------------|
| 1. Core Library | DONE | 7/7 | 0 |
| 2. Templates | DONE | 4/4 | 0 |
| 3. CLI Command | DONE | 6/6 | 0 |
| 4. Unit Tests | DONE | 5/5 | 0 |
| 5. Integration Tests | DONE | 4/4 | 0 |
| 6. Workflow Integration | DONE | 4/4 | 0 |
| 7. Documentation | DONE | 4/4 | 0 |
| **Total** | | **34/34** | **0** |

### Key Finding

The provision command is **fully implemented** (100% complete). All phases are done:
core provisioner library, Copier templates, CLI command, unit tests, integration tests,
workflow integration (Makefile targets), and documentation.

Provisioning is deliberately separate from organize, but `make full-refresh` chains them:
`discover -> organize -> provision -> extract -> metadata`. The `--when` option provides
explicit control over when provisioning runs (`always` or `outdated`).
