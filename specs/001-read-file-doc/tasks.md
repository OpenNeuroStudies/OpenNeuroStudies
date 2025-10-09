# Implementation Tasks: OpenNeuroStudies Infrastructure Refactoring

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)
**Branch**: `001-read-file-doc` | **Date**: 2025-10-09

## Overview

This document breaks down the implementation into discrete, executable tasks organized by user story priority. Each phase builds upon the previous, enabling incremental delivery and independent testing.

**Total Tasks**: 48
**Estimated Timeline**: 5 weeks
**MVP Scope**: Phase 3 (User Story 1 - Discovery & Organization)

## Task Organization

Tasks are organized into phases:
- **Phase 1**: Setup & Project Initialization (T001-T007)
- **Phase 2**: Foundational Infrastructure (T008-T013)
- **Phase 3**: User Story 1 - Discovery & Organization [P1] (T014-T027)
- **Phase 4**: User Story 2 - Metadata Generation [P2] (T028-T038)
- **Phase 5**: User Story 3 - Validation Integration [P3] (T039-T043)
- **Phase 6**: Polish & Cross-Cutting Concerns (T044-T048)

**Legend**:
- `[P]` = Parallelizable (can run simultaneously with other [P] tasks)
- `[US1]`, `[US2]`, `[US3]` = User Story tags for traceability

---

## Phase 1: Setup & Project Initialization

**Goal**: Establish project structure and development environment.

**Duration**: 1 day

### T001: Create Project Structure [P]

**File**: `code/src/openneuro_studies/` (directory structure)

**Task**: Create the complete directory structure for the Python project:

```bash
mkdir -p code/src/openneuro_studies/{cli,models,config,discovery,organization,metadata,validation,utils}
mkdir -p code/tests/{unit,integration,fixtures/{mock_datasets,api_responses}}
touch code/src/openneuro_studies/__init__.py
touch code/src/openneuro_studies/{cli,models,config,discovery,organization,metadata,validation,utils}/__init__.py
```

**Deliverable**: Empty directory structure matching plan.md

---

### T002: Create pyproject.toml [P]

**File**: `code/pyproject.toml`

**Task**: Create uv-compatible package definition with:
- Project metadata (name: openneuro-studies, version: 0.1.0)
- Python requirement: >=3.10
- Dependencies: datalad, click>=8.0, pydantic>=2.0, requests, requests-cache
- Optional dependencies: datalad-fuse, fsspec (for imaging metrics)
- Dev dependencies: pytest, pytest-cov, tox, tox-uv, ruff
- Entry point: openneuro-studies = openneuro_studies.cli.main:cli
- pytest configuration with marks: unit, integration, ai_generated

**Deliverable**: Complete pyproject.toml

---

### T003: Create tox.ini [P]

**File**: `code/tox.ini`

**Task**: Create tox configuration with tox-uv for test environments:
- `py310`, `py311`, `py312` environments
- `lint` environment with ruff
- `integration` environment with integration test markers
- Pass-through for GITHUB_TOKEN environment variable

**Deliverable**: Working tox.ini

---

### T004: Create README.md [P]

**File**: `code/README.md`

**Task**: Write development setup documentation:
- Project description linking to main documentation
- Installation instructions (uv venv, uv pip install -e .)
- Running tests (pytest, tox commands)
- Environment variables needed (GITHUB_TOKEN)
- Link to quickstart.md for usage

**Deliverable**: Developer-focused README

---

### T005: Create .gitignore [P]

**File**: `code/.gitignore`

**Task**: Create comprehensive .gitignore for Python project:
- Virtual environments (.venv/, venvs/)
- Python artifacts (__pycache__/, *.pyc, *.egg-info/)
- Test artifacts (.pytest_cache/, .coverage, htmlcov/)
- IDE files (.vscode/, .idea/)
- OS files (.DS_Store)
- Cache directories (.openneuro-studies/cache/)

**Deliverable**: Complete .gitignore

---

### T006: Initialize Package __init__.py [P]

**File**: `code/src/openneuro_studies/__init__.py`

**Task**: Create package initialization with version:

```python
"""OpenNeuroStudies: Organize OpenNeuro datasets into BIDS study structures."""

__version__ = "0.1.0"
__author__ = "Yaroslav O. Halchenko"
```

**Deliverable**: Package __init__.py with metadata

---

### T007: Verify Setup with Placeholder CLI [P]

**File**: `code/src/openneuro_studies/cli/main.py`

**Task**: Create minimal Click CLI for smoke testing:

```python
import click
from .. import __version__

@click.group()
@click.version_option(version=__version__)
def cli():
    """OpenNeuro Studies CLI"""
    pass

if __name__ == "__main__":
    cli()
```

**Test**: Run `uv pip install -e .` and verify `openneuro-studies --version` works

**Deliverable**: Working CLI entry point

**Checkpoint**: ✅ Phase 1 complete when `openneuro-studies --version` prints version

---

## Phase 2: Foundational Infrastructure

**Goal**: Build shared infrastructure required by ALL user stories.

**Duration**: 2-3 days

### T008: Create Pydantic Configuration Models

**File**: `code/src/openneuro_studies/config/models.py`

**Task**: Implement configuration models from data-model.md:
- `SourceType(Enum)`: RAW, DERIVATIVE
- `SourceSpecification(BaseModel)`: name, organization_url, type, inclusion_patterns, exclusion_patterns, access_token_env
- `OpenNeuroStudiesConfig(BaseModel)`: github_org, sources: List[SourceSpecification]
- Validation: URL format, regex pattern syntax
- Default values: github_org="OpenNeuroStudies", access_token_env="GITHUB_TOKEN"

**Reference**: data-model.md lines 318-338

**Deliverable**: Configuration models with validation

---

### T009: Create Configuration Loader

**File**: `code/src/openneuro_studies/config/__init__.py`

**Task**: Implement YAML configuration loading:
- Function `load_config(path: Path) -> OpenNeuroStudiesConfig`
- Read .openneuro-studies/config.yaml from repository root
- Parse YAML and validate with Pydantic
- Handle missing file with clear error message
- Support environment variable override: OPENNEURO_STUDIES_CONFIG

**Deliverable**: Config loader with error handling

---

### T010: Create Core Data Models [P]

**File**: `code/src/openneuro_studies/models/study.py`

**Task**: Implement StudyDataset model from data-model.md:
- `StudyState(Enum)`: DISCOVERED, ORGANIZED, METADATA_GENERATED, VALIDATED
- `StudyDataset(BaseModel)`: All fields from data-model.md lines 115-136
- Validator: must_have_sources (at least 1 source dataset)
- Pattern validation for study_id, version, github_url

**Reference**: data-model.md lines 115-136

**Deliverable**: StudyDataset Pydantic model

---

### T011: Create Source Dataset Model [P]

**File**: `code/src/openneuro_studies/models/source.py`

**Task**: Implement SourceDataset model from data-model.md:
- All fields from data-model.md lines 171-181
- Pattern validation for dataset_id, commit_sha (40 hex chars)
- HttpUrl validation for url field

**Reference**: data-model.md lines 171-181

**Deliverable**: SourceDataset Pydantic model

---

### T012: Create Derivative Dataset Model [P]

**File**: `code/src/openneuro_studies/models/derivative.py`

**Task**: Implement DerivativeDataset model from data-model.md:
- All fields from data-model.md lines 240-264
- UUID validation (36 chars)
- uuid_prefix extraction validator
- Helper function: `generate_derivative_id()` from data-model.md lines 218-231

**Reference**: data-model.md lines 240-264

**Deliverable**: DerivativeDataset Pydantic model with disambiguation logic

---

### T013: Create GitHub API Client with Caching

**File**: `code/src/openneuro_studies/discovery/api_client.py`

**Task**: Implement cached GitHub API client from research.md:
- Class `GitHubClient` with requests-cache or custom ETag caching
- Methods: `list_repos(org)`, `get_file(repo, path, ref="HEAD")`, `get_commit(repo, sha)`
- Pagination handling (Link header) for 1000+ repos
- Rate limit detection and exponential backoff with retry
- Authentication via GITHUB_TOKEN
- Cache directory: .openneuro-studies/cache/github/

**Reference**: research.md GitHub API section

**Deliverable**: GitHub client with caching and retry logic

**Checkpoint**: ✅ Phase 2 complete when models validate test data and config loads from YAML

---

## Phase 3: User Story 1 - Discovery & Organization [P1]

**Goal**: Discover datasets from GitHub and organize into study structures.

**User Story**: As a neuroscience researcher, I need to navigate a unified collection of OpenNeuro raw and derivative datasets organized as BIDS study structures.

**Duration**: 1 week

**Independent Test**: Verify system discovers datasets from configured sources, organizes them into study-{id} folders with proper sourcedata/ and derivatives/ structure, and generates complete studies.tsv index.

### T014: [US1] Implement Dataset Discovery Logic

**File**: `code/src/openneuro_studies/discovery/dataset_finder.py`

**Task**: Implement dataset discovery from GitHub organizations:
- Function `discover_datasets(config: OpenNeuroStudiesConfig, source_filter: Optional[str], limit: Optional[int]) -> List[SourceDataset | DerivativeDataset]`
- For each source in config:
  - List repositories via GitHubClient
  - Filter by inclusion/exclusion patterns (regex)
  - Extract dataset_description.json via tree API (no cloning)
  - Parse DatasetType (raw vs derivative), BIDSVersion, Authors, License
  - For derivatives: parse SourceDatasets to extract OpenNeuro IDs
  - Create SourceDataset or DerivativeDataset instances
- Handle malformed JSON gracefully (log and skip)
- Progress indicators for long operations

**Deliverable**: Discovery function with filtering

---

### T015: [US1] Implement Discovery CLI Command [P]

**File**: `code/src/openneuro_studies/cli/discover.py`

**Task**: Implement `discover` CLI command per contracts/cli.yaml:
- Options: --source, --update-cache, --limit, --output (default: discovered-datasets.json)
- Load config from --config path
- Call dataset_finder.discover_datasets()
- Write JSON output with discovered metadata
- Handle errors and display summary (count per source)

**Reference**: contracts/cli.yaml lines 35-80

**Deliverable**: Working `openneuro-studies discover` command

---

### T016: [US1] Implement DataLad Dataset Creator

**File**: `code/src/openneuro_studies/organization/study_creator.py`

**Task**: Implement study dataset creation using DataLad:
- Function `create_study_dataset(study_id: str, github_org: str) -> Path`
- Use `datalad.api.create(path=study_id, annex=False)` from research.md
- Initialize as git repository (not git-annex)
- Create sourcedata/ and derivatives/ directories
- Generate initial dataset_description.json with DatasetType="study"
- Handle already-exists case (idempotency)

**Reference**: research.md DataLad API section

**Deliverable**: Study dataset creation function

---

### T017: [US1] Implement Git Submodule Linker

**File**: `code/src/openneuro_studies/organization/submodule_linker.py`

**Task**: Implement git submodule linking without cloning from research.md:
- Function `link_submodule(parent_repo: Path, submodule_path: str, url: str, commit_sha: str)`
- Use git commands: `git config`, `git update-index --cacheinfo 160000`
- Update .gitmodules with DataLad extended format (datalad-id, datalad-url)
- No cloning required (lazy loading)
- Idempotent (skip if already linked)

**Reference**: research.md Git Submodule section

**Deliverable**: Submodule linking without cloning

---

### T018: [US1] Implement Study Organization Logic

**File**: `code/src/openneuro_studies/organization/__init__.py`

**Task**: Implement high-level organization orchestration:
- Function `organize_study(dataset: SourceDataset | DerivativeDataset, config: OpenNeuroStudiesConfig)`
- Determine if study-{id} needed (spec.md acceptance scenarios 4-5):
  - Single raw dataset → create study
  - Derivative with single source → link under raw's derivatives/
  - Derivative with multiple sources → create study, link sources
- Call study_creator.create_study_dataset()
- Call submodule_linker.link_submodule() for sources and derivatives
- Link study-{id} as submodule in top-level repo
- Handle edge cases: missing sources, conflicting derivatives

**Reference**: spec.md lines 20-24

**Deliverable**: Complete organization orchestration

---

### T019: [US1] Implement Organize CLI Command [P]

**File**: `code/src/openneuro_studies/cli/organize.py`

**Task**: Implement `organize` CLI command per contracts/cli.yaml:
- Arguments: targets (study IDs, URLs, or paths), support globs
- Options: --github-org, --dry-run, --no-publish, --force
- Auto-detect type from dataset_description.json (raw vs derivative)
- Call organization orchestration for each target
- Display progress and summary
- Handle errors with error log (logs/errors.tsv)

**Reference**: contracts/cli.yaml lines 82-169

**Deliverable**: Working `openneuro-studies organize` command

---

### T020: [US1] Create Status Tracking [P]

**File**: `code/src/openneuro_studies/utils/state.py`

**Task**: Implement study state tracking:
- Function `get_study_state(study_path: Path) -> StudyState`
- Check existence of markers:
  - `.datalad/config` → ORGANIZED
  - `dataset_description.json` + `studies.tsv` → METADATA_GENERATED
  - `derivatives/bids-validator.json` → VALIDATED
- Function `list_studies() -> List[Tuple[str, StudyState]]`
- Scan repository for study-* directories

**Deliverable**: State tracking utilities

---

### T021: [US1] Implement Status CLI Command [P]

**File**: `code/src/openneuro_studies/cli/status.py`

**Task**: Implement `status` CLI command per contracts/cli.yaml:
- Arguments: targets (optional filter)
- Options: --filter (all, discovered, organized, etc.), --format (table, json, csv)
- Display counts per state
- Show incomplete studies
- Support filtering and formatting

**Reference**: contracts/cli.yaml lines 329-371

**Deliverable**: Working `openneuro-studies status` command

---

### T022: [US1] [P] Unit Tests for Models

**File**: `code/tests/unit/test_models.py`

**Task**: Write unit tests for Pydantic models:
- Test StudyDataset validation (valid/invalid study_id, version patterns)
- Test SourceDataset validation (commit_sha format, URL validation)
- Test DerivativeDataset validation (UUID format, uuid_prefix extraction)
- Test derivative_id disambiguation logic
- Test must_have_sources validator
- Mark tests with `@pytest.mark.unit` and `@pytest.mark.ai_generated`

**Deliverable**: Comprehensive model tests

---

### T023: [US1] [P] Unit Tests for Discovery

**File**: `code/tests/unit/test_discovery.py`

**Task**: Write unit tests for discovery module:
- Mock GitHubClient responses
- Test dataset filtering (inclusion/exclusion patterns)
- Test dataset_description.json parsing (raw vs derivative)
- Test SourceDatasets parsing for derivatives
- Test malformed JSON handling
- Mock fixtures in tests/fixtures/api_responses/

**Deliverable**: Discovery module tests

---

### T024: [US1] [P] Unit Tests for Organization

**File**: `code/tests/unit/test_organization.py`

**Task**: Write unit tests for organization module:
- Mock DataLad API calls
- Test study creation (single source, multi-source derivative)
- Test submodule linking logic
- Test idempotency (re-running organization)
- Test edge cases: missing sources, conflicting derivatives

**Deliverable**: Organization module tests

---

### T025: [US1] Integration Test: Discover & Organize Flow

**File**: `code/tests/integration/test_discover_organize.py`

**Task**: Write end-to-end integration test for US1:
- Setup: Mock GitHub API with test datasets (ds000001, ds000010, ds006131, ds006185, ds006190)
- Test discovery: Verify all datasets found and categorized correctly
- Test organization: Verify study-{id} folders created with correct structure
- Test submodule linking: Verify .gitmodules entries
- Test multi-source derivative handling (ds006190 → ds006189, ds006185, ds006131)
- Cleanup temporary git repositories
- Mark with `@pytest.mark.integration` and `@pytest.mark.ai_generated`

**Reference**: spec.md User Story 1 acceptance scenarios

**Deliverable**: Full US1 integration test

---

### T026: [US1] Create Error Logging Utility [P]

**File**: `code/src/openneuro_studies/utils/error_log.py`

**Task**: Implement error logging to logs/errors.tsv:
- Function `log_error(study_id: str, error_type: str, message: str)`
- Create logs/ directory if needed
- Append to errors.tsv with columns: timestamp, study_id, error_type, message
- Thread-safe file writing

**Reference**: spec.md edge cases line 65

**Deliverable**: Error logging utility

---

### T027: [US1] Test Against Real Datasets (Manual)

**File**: N/A (manual testing)

**Task**: Manually test with real OpenNeuro datasets:
- Test with sample datasets: ds000001, ds000010, ds005256, ds006131, ds006185, ds006189, ds006190
- Verify discovery finds all datasets
- Verify organization creates correct structure
- Verify multi-source derivative handling (ds006190)
- Document any edge cases found
- Update error handling based on findings

**Deliverable**: Test results documentation + any bug fixes

**Checkpoint**: ✅ US1 complete when system discovers and organizes test datasets correctly

---

## Phase 4: User Story 2 - Metadata Generation [P2]

**Goal**: Generate comprehensive metadata files for studies and derivatives.

**User Story**: As a dataset curator, I need automatically generated and synchronized metadata files for tracking provenance, licensing, and derivatives.

**Duration**: 1 week

**Independent Test**: Verify metadata generation produces correct dataset_description.json, populates studies.tsv with accurate data, and creates studies_derivatives.tsv with derivative tracking.

### T028: [US2] Implement Study dataset_description.json Generator

**File**: `code/src/openneuro_studies/metadata/dataset_description.py`

**Task**: Generate dataset_description.json for study datasets per spec.md:
- Function `generate_study_description(study_path: Path) -> dict`
- Fields: Name, BIDSVersion="1.10.1", DatasetType="study", License, Authors (from git shortlog), ReferencesAndLinks, Funding, Acknowledgements
- GeneratedBy field with Claude Code provenance (FR-007)
- SourceDatasets referencing all sourcedata entries (FR-006)
- Collate metadata from source dataset_description.json files (FR-008)
- Title: "Study dataset for {source title}"

**Reference**: spec.md lines 38, FR-005 to FR-008

**Deliverable**: Study dataset_description.json generation

---

### T029: [US2] Implement studies.tsv Generator

**File**: `code/src/openneuro_studies/metadata/studies_tsv.py`

**Task**: Generate studies.tsv with all required columns per FR-009:
- Function `generate_studies_tsv(study_paths: List[Path]) -> pd.DataFrame`
- Columns: study_id, name, version, raw_version, bids_version, hed_version, license, authors, author_lead_raw, author_senior_raw, subjects_num, sessions_num, sessions_min, sessions_max, bold_num, t1w_num, t2w_num, bold_size, t1w_size, bold_size_max, bold_voxels, datatypes, derivative_ids, bids_valid
- Extract authors from git shortlog (study dataset contributors)
- Extract author_lead_raw/author_senior_raw from raw dataset Authors array (first/last elements)
- Handle multiple sources: "n/a" if conflicting, use value if all same, duplicate if single author
- Extract raw_version from git tags or CHANGES file (FR-025, FR-026)
- Extract subject/session counts from participants.tsv or file structure
- Mark missing values as "n/a" explicitly
- snake_case column names per BIDS conventions

**Reference**: spec.md lines 39, FR-009, FR-027

**Deliverable**: studies.tsv generation with all columns

---

### T030: [US2] Implement studies_derivatives.tsv Generator

**File**: `code/src/openneuro_studies/metadata/derivatives_tsv.py`

**Task**: Generate studies_derivatives.tsv (tall format) per FR-010:
- Function `generate_derivatives_tsv(study_paths: List[Path]) -> pd.DataFrame`
- Columns: study_id, derivative_id, dataset_id, tool_name, version, datalad_uuid, total_size, annexed_size, file_count, execution_time, peak_memory, processed_raw_version, outdatedness, status
- One row per study-derivative pair
- Extract size statistics from `git annex info` (FR-010)
- Extract execution metrics if con-duct logs available
- Calculate outdatedness as commit count between versions (FR-028, FR-029)
- Handle missing derivatives gracefully

**Reference**: spec.md lines 41-42, FR-010, FR-028, FR-029

**Deliverable**: studies_derivatives.tsv generation (tall format)

---

### T031: [US2] Implement JSON Sidecar Generator [P]

**File**: `code/src/openneuro_studies/metadata/__init__.py`

**Task**: Generate JSON sidecar files describing TSV columns per FR-011:
- Function `generate_tsv_sidecar(tsv_path: Path, column_descriptions: dict)`
- Create studies.json describing studies.tsv columns
- Create studies_derivatives.json describing studies_derivatives.tsv columns
- Follow BIDS sidecar conventions (column name → description dict)

**Reference**: FR-011, BIDS specification

**Deliverable**: JSON sidecar generation

---

### T032: [US2] Implement Outdatedness Calculator

**File**: `code/src/openneuro_studies/utils/outdatedness.py`

**Task**: Calculate derivative outdatedness as separate batch operation per FR-030:
- Function `calculate_outdatedness(derivative: DerivativeDataset, raw_dataset: SourceDataset) -> int`
- Compare processed_raw_version to current raw version
- Use git log to count commits between versions
- May require temporary shallow clones (minimize cloning)
- Cache results to avoid repeated cloning

**Reference**: spec.md lines 42, FR-028, FR-029, FR-030

**Deliverable**: Outdatedness calculation with caching

---

### T033: [US2] Implement Imaging Metrics Extractor (Basic)

**File**: `code/src/openneuro_studies/utils/imaging_metrics.py`

**Task**: Extract basic imaging metrics without sparse access:
- Function `extract_imaging_counts(raw_dataset_path: Path) -> dict`
- Count BOLD files (bold_num): find sub-*/func/*_bold.nii* files
- Count T1w files (t1w_num): find sub-*/anat/*_T1w.nii* files
- Count T2w files (t2w_num): find sub-*/anat/*_T2w.nii* files
- No cloning required (use GitHub tree API)

**Reference**: spec.md line 40, FR-031

**Deliverable**: Basic imaging file counts

---

### T034: [US2] Implement Imaging Metrics Extractor (Sparse Access)

**File**: `code/src/openneuro_studies/utils/imaging_metrics.py` (extend)

**Task**: Extract imaging characteristics using sparse access per FR-032, FR-033:
- Function `extract_imaging_metrics_sparse(raw_dataset_path: Path, method: str) -> dict`
- Methods: "datalad-fuse" or "fsspec" (from research.md)
- Extract bold_size, t1w_size (total sizes in bytes)
- Extract bold_size_max (largest BOLD file)
- Extract bold_voxels (dimensions from NIfTI header, e.g. "64x64x40x200")
- Use sparse access to read headers without full clone
- Separate operation stage (not run by default)

**Reference**: spec.md lines 40, 73, FR-032, FR-033

**Deliverable**: Sparse imaging metrics extraction

---

### T035: [US2] Implement Metadata CLI Commands

**File**: `code/src/openneuro_studies/cli/metadata.py`

**Task**: Implement metadata CLI command group per contracts/cli.yaml:
- Click group for metadata operations
- Subcommand `generate`: --stage (basic, imaging, outdatedness, all), --force-refresh, --sparse-method
- Subcommand `sync`: --check-sources, --since (ISO date)
- Call appropriate metadata generators based on stage
- Display progress and summary

**Reference**: contracts/cli.yaml lines 170-274

**Deliverable**: Working `openneuro-studies metadata` commands

---

### T036: [US2] [P] Unit Tests for Metadata

**File**: `code/tests/unit/test_metadata.py`

**Task**: Write unit tests for metadata module:
- Test dataset_description.json generation (all required fields)
- Test studies.tsv generation (column count, snake_case naming)
- Test studies_derivatives.tsv generation (tall format correctness)
- Test author extraction logic (single author, multiple authors, conflicting authors)
- Test "n/a" handling for missing values
- Test JSON sidecar generation

**Deliverable**: Metadata module tests

---

### T037: [US2] Integration Test: Metadata Generation Flow

**File**: `code/tests/integration/test_metadata_generation.py`

**Task**: Write end-to-end integration test for US2:
- Setup: Create mock study datasets with sourcedata and derivatives
- Test basic metadata generation: Verify studies.tsv columns and values
- Test derivatives metadata: Verify studies_derivatives.tsv rows
- Test incremental sync: Update one study, verify only that study regenerated
- Test multi-source derivative handling: Verify author_lead_raw/author_senior_raw logic
- Mark with `@pytest.mark.integration` and `@pytest.mark.ai_generated`

**Reference**: spec.md User Story 2 acceptance scenarios

**Deliverable**: Full US2 integration test

---

### T038: [US2] Test Metadata Against Real Studies (Manual)

**File**: N/A (manual testing)

**Task**: Manually test metadata generation with real studies:
- Test with organized datasets from T027
- Verify studies.tsv has all required columns populated or "n/a"
- Verify studies_derivatives.tsv correctly tracks derivatives
- Verify JSON sidecars describe columns accurately
- Test incremental sync with modified studies
- Document any edge cases or data quality issues

**Deliverable**: Test results + bug fixes

**Checkpoint**: ✅ US2 complete when metadata generates correctly for all test studies

---

## Phase 5: User Story 3 - Validation Integration [P3]

**Goal**: Integrate BIDS validation and track results.

**User Story**: As a data quality manager, I need automated BIDS validation results for identifying compliance issues.

**Duration**: 2-3 days

**Independent Test**: Verify BIDS validator runs on study datasets and outputs are stored with validation status reflected in studies.tsv.

### T039: [US3] Implement BIDS Validator Wrapper

**File**: `code/src/openneuro_studies/validation/bids_validator.py`

**Task**: Integrate bids-validator-deno per FR-015:
- Function `run_bids_validator(study_path: Path, validator_version: str) -> dict`
- Execute `bids-validator` subprocess
- Capture JSON output → derivatives/bids-validator.json
- Capture text output → derivatives/bids-validator.txt
- Parse validation status: pass/fail/warning
- Handle validation errors gracefully
- Timeout for long-running validations

**Reference**: spec.md lines 57-59, FR-015

**Deliverable**: BIDS validator integration

---

### T040: [US3] Update studies.tsv with Validation Status

**File**: `code/src/openneuro_studies/metadata/studies_tsv.py` (extend)

**Task**: Add bids_valid column updates:
- Function `update_validation_status(study_id: str, status: str)`
- Read existing studies.tsv
- Update bids_valid column for study
- Rewrite studies.tsv
- Values: "pass", "fail", "warning", "n/a"

**Reference**: spec.md line 58, FR-009

**Deliverable**: Validation status tracking in studies.tsv

---

### T041: [US3] Implement Validate CLI Command

**File**: `code/src/openneuro_studies/cli/validate.py`

**Task**: Implement `validate` CLI command per contracts/cli.yaml:
- Arguments: targets (study IDs or globs)
- Options: --validator-version, --config-file, --parallel
- Run bids-validator on each study
- Store results in derivatives/
- Update studies.tsv bids_valid column
- Display summary (pass/fail/warning counts)
- Support parallel execution

**Reference**: contracts/cli.yaml lines 275-328

**Deliverable**: Working `openneuro-studies validate` command

---

### T042: [US3] [P] Integration Test: Validation Flow

**File**: `code/tests/integration/test_validation.py`

**Task**: Write end-to-end integration test for US3:
- Setup: Create mock study datasets (BIDS-compliant and non-compliant)
- Test validation execution: Verify bids-validator runs
- Test output storage: Verify JSON and text files created
- Test studies.tsv update: Verify bids_valid column reflects status
- Test parallel validation: Verify multiple studies processed correctly
- Mark with `@pytest.mark.integration` and `@pytest.mark.ai_generated`

**Reference**: spec.md User Story 3 acceptance scenarios

**Deliverable**: Full US3 integration test

---

### T043: [US3] Test Validation with Real Studies (Manual)

**File**: N/A (manual testing)

**Task**: Manually test validation with real studies:
- Test with known BIDS-compliant dataset (e.g., ds000001)
- Test with known non-compliant dataset (if available)
- Verify validation outputs are stored correctly
- Verify studies.tsv reflects validation status
- Test parallel validation with multiple studies

**Deliverable**: Test results + bug fixes

**Checkpoint**: ✅ US3 complete when validation runs and tracks results for test studies

---

## Phase 6: Polish & Cross-Cutting Concerns

**Goal**: Finalize CLI, add utilities, handle edge cases, prepare for release.

**Duration**: 2-3 days

### T044: Implement Clean CLI Command

**File**: `code/src/openneuro_studies/cli/clean.py`

**Task**: Implement `clean` CLI command per contracts/cli.yaml:
- Options: --cache, --temp, --incomplete-studies, --all, --dry-run
- Remove API cache (.openneuro-studies/cache/)
- Remove temp files
- Remove incomplete study datasets (missing .datalad/config)
- Display summary of cleaned files

**Reference**: contracts/cli.yaml lines 372-412

**Deliverable**: Working `openneuro-studies clean` command

---

### T045: Implement Global CLI Options and Help

**File**: `code/src/openneuro_studies/cli/main.py` (extend)

**Task**: Enhance main CLI with global options per contracts/cli.yaml:
- Global options: --debug-level/-l, --config/-c, --cache-dir
- Set up Python logging based on --debug-level
- Load configuration from --config path
- Register all command groups: discover, organize, metadata, validate, status, clean
- Improve help text for each command

**Reference**: contracts/cli.yaml lines 15-33

**Deliverable**: Complete CLI with all commands and global options

---

### T046: Add Progress Indicators and Logging

**File**: `code/src/openneuro_studies/utils/progress.py`

**Task**: Implement progress indicators for long operations:
- Use tqdm or click.progressbar for batch operations
- Show progress for: discovery (per source), organization (per study), metadata generation (per study), validation (per study)
- Log to stderr, output to stdout
- Configurable via --debug-level

**Deliverable**: Progress indicators for CLI

---

### T047: Handle Edge Cases and Error Recovery

**File**: Multiple files (throughout codebase)

**Task**: Implement edge case handling from spec.md:
- Unreachable repositories: Cache last known state, log error, continue
- Malformed dataset_description.json: Mark fields as "n/a", log warning
- Duplicate derivative versions: Disambiguate with UUID (already in T012)
- Non-OpenNeuro SourceDatasets: Preserve in metadata, skip linking
- Missing source dependencies: Log and mark unavailable
- Same-day versioning: Increment PATCH number (0.20251009.0 → 0.20251009.1)
- No git tags: Use CHANGES file or mark "n/a"

**Reference**: spec.md lines 65-73

**Deliverable**: Robust error handling throughout

---

### T048: Final Integration Test Suite

**File**: `code/tests/integration/test_full_workflow.py`

**Task**: Write comprehensive end-to-end test:
- Setup: Clean environment with mock GitHub API
- Execute full workflow: discover → organize → metadata → validate
- Verify all outputs: studies.tsv, studies_derivatives.tsv, validation results
- Test incremental updates: Modify one dataset, re-run, verify only that study updated
- Test error recovery: Introduce errors, verify graceful handling
- Mark with `@pytest.mark.integration` and `@pytest.mark.ai_generated`

**Deliverable**: Full system integration test

**Checkpoint**: ✅ Phase 6 complete when all commands work and edge cases handled

---

## Dependency Graph

```
Phase 1 (Setup)
  └─→ Phase 2 (Foundational)
        ├─→ Phase 3 (US1: Discovery & Organization)
        │     ├─→ Phase 4 (US2: Metadata Generation)
        │     │     └─→ Phase 5 (US3: Validation)
        │     │           └─→ Phase 6 (Polish)
        │     └─→ Phase 6 (Polish) [some tasks]
        └─→ Phase 6 (Polish) [some tasks]
```

**Critical Path**: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

**Parallel Opportunities**:
- Within Phase 1: T001-T007 all parallelizable
- Within Phase 2: T010-T012 (models) parallelizable
- Within Phase 3: T015, T019, T020, T021, T022, T023, T024, T026 parallelizable after core logic
- Within Phase 4: T031, T036 parallelizable
- Tests can run in parallel with implementation within same phase

---

## Parallel Execution Examples

### Phase 1: Setup (All Parallel)
```bash
# All setup tasks can run simultaneously
T001 & T002 & T003 & T004 & T005 & T006 & T007 &
wait
```

### Phase 3: After Core Discovery/Organization Logic
```bash
# After T014, T016, T017, T018 complete:
T015 & T019 & T020 & T021 & T022 & T023 & T024 & T026 &
wait
```

### Phase 4: After Core Metadata Logic
```bash
# After T028, T029, T030 complete:
T031 & T036 &
wait
```

---

## Testing Strategy

**Unit Tests**: Run continuously during development with pytest
```bash
pytest -m unit --cov=openneuro_studies
```

**Integration Tests**: Run after each phase completion
```bash
pytest -m integration --cov=openneuro_studies
```

**Manual Tests**: Run with real datasets before release
- Use test dataset list from quickstart.md: ds000001, ds000010, ds005256, ds006131, ds006185, ds006189, ds006190

**Test Coverage Goal**: >80% line coverage

---

## Implementation Strategy

### MVP Scope (Phase 3 Only - User Story 1)

**Minimum Viable Product includes**:
- T001-T007: Project setup
- T008-T013: Foundational infrastructure
- T014-T027: Discovery and organization (US1 complete)

**MVP Deliverable**: System that discovers and organizes datasets into study structures, enabling manual inspection and validation.

**MVP Timeline**: 2 weeks

### Incremental Delivery

**Week 1**: Complete Phase 1-2 (Setup + Foundation)
- Deliverable: Working CLI with config loading and models

**Week 2**: Complete Phase 3 (US1 - Discovery & Organization)
- Deliverable: MVP - Discover and organize datasets

**Week 3**: Complete Phase 4 (US2 - Metadata Generation)
- Deliverable: Full metadata tracking and reporting

**Week 4**: Complete Phase 5 (US3 - Validation Integration)
- Deliverable: Automated BIDS validation

**Week 5**: Complete Phase 6 (Polish & Cross-Cutting)
- Deliverable: Production-ready release 0.1.0

### Quality Gates

Each phase must pass quality gate before proceeding:
- ✅ All tests pass (unit + integration)
- ✅ Code linted with ruff
- ✅ Manual testing with real datasets successful
- ✅ Checkpoint criteria met (see phase checkpoints)

---

## Success Metrics

**Phase 3 (US1) Success**:
- Discovers 10 test datasets in <10 seconds
- Organizes study-ds000001 in <30 seconds
- Handles multi-source derivative (ds006190) correctly
- Tests pass: T022, T023, T024, T025

**Phase 4 (US2) Success**:
- Generates studies.tsv with all 24 columns
- Generates studies_derivatives.tsv with correct row count
- Incremental sync updates only modified studies
- Tests pass: T036, T037

**Phase 5 (US3) Success**:
- Validation runs on study datasets
- Results stored in derivatives/
- studies.tsv bids_valid column updated
- Tests pass: T042

**Overall Success**:
- All 48 tasks complete
- All tests pass (unit + integration)
- Manual testing with 7 test datasets successful
- Ready for 0.1.0 release

---

## Notes

- **Tests are AI-generated**: Mark all test functions with `@pytest.mark.ai_generated`
- **Idempotency**: All operations must be safe to re-run (FR-016)
- **Error Handling**: Use logs/errors.tsv for error aggregation
- **Performance**: Discovery <30min, Organization <30sec/study, Metadata <2hr total
- **API Caching**: Essential for respecting GitHub rate limits
- **No Cloning**: Except for outdatedness and imaging metrics (separate stages)

---

**Generated**: 2025-10-09
**Status**: Ready for implementation
**Next Step**: Begin Phase 1 (T001-T007)
