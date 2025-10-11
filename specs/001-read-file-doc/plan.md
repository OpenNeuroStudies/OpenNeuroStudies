# Implementation Plan: OpenNeuroStudies Infrastructure Refactoring

**Branch**: `001-read-file-doc` | **Date**: 2025-10-09 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-read-file-doc/spec.md`

**Note**: This document outlines the implementation plan for organizing 1000+ OpenNeuro datasets into BIDS study structures with automated metadata generation.

## Summary

This feature implements infrastructure to discover, organize, and maintain OpenNeuro datasets as BIDS study structures. The system will:

1. Discover raw and derivative datasets from GitHub organizations (OpenNeuroDatasets, OpenNeuroDerivatives) without cloning
2. Create study-{id} folders as DataLad datasets with sourcedata/ and derivatives/ linked as git submodules
3. Generate comprehensive metadata (dataset_description.json, studies.tsv, studies_derivatives.tsv)
4. Validate BIDS compliance and track dataset status

**Primary Technical Approach**: Python CLI using DataLad API, GitHub REST API for discovery, git submodules for linking, TSV/JSON for metadata following BIDS conventions.

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**:
- DataLad (`datalad.api`) for dataset operations and provenance
- Click for CLI framework
- Pydantic for configuration and data validation
- requests with caching for GitHub API
- bids-validator-deno 2.1.0+ for BIDS validation

**Storage**: File-based (TSV, JSON, git submodules); no database required
**Testing**: pytest with tox for test environments; marks: unit, integration, ai_generated
**Target Platform**: Linux server (primary), macOS (development)
**Project Type**: Single Python project with CLI entry point
**Performance Goals**:
- Discover 1000+ datasets in <30 minutes with API caching
- Organize individual study in <30 seconds
- Metadata generation for all studies in <2 hours

**Constraints**:
- GitHub API rate limit: 5000 requests/hour (authenticated)
- No dataset cloning during discovery/organization (except for outdatedness/imaging metrics)
- Idempotent operations (safe to re-run)
- Must work with existing git-annex annexed datasets

**Scale/Scope**:
- 1000+ OpenNeuro datasets
- Studies with 1-200+ subjects
- Derivatives with 10GB-1TB annexed content
- Multi-source derivatives (e.g., meta-analysis studies)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ I. Data Integrity & Traceability
- **Compliance**: All datasets linked via git submodules with explicit commit SHAs
- **Evidence**: FR-004 requires git submodule linking; data-model.md includes commit_sha fields
- **No violations**

### ✅ II. Automation & Reproducibility
- **Compliance**: All operations scripted in Python CLI; idempotency required (FR-016)
- **Evidence**: FR-017 requires API caching; quickstart.md documents reproducible workflow
- **No violations**

### ✅ III. Standard Formats
- **Compliance**: TSV for tabular data, JSON for structured metadata, YAML for config
- **Evidence**: FR-009/FR-010 specify TSV outputs; FR-078 requires snake_case; data-model.md shows Pydantic models
- **No violations**

### ✅ IV. Git/DataLad-First Workflow
- **Compliance**: DataLad operations for all state changes; git submodules for linking
- **Evidence**: FR-021 requires `datalad create --no-annex`; FR-022 requires git submodule tracking
- **No violations**

### ✅ V. Observability & Monitoring
- **Compliance**: studies.tsv provides queryable overview; status command tracks progress
- **Evidence**: FR-009 specifies studies.tsv schema; cli.yaml includes status command
- **No violations**

### Data Management Standards
- ✅ **BIDS Compliance**: FR-005 requires BIDS 1.10.1 study dataset specification
- ✅ **Derivative Versioning**: FR-010 requires version tracking; data-model.md includes disambiguation logic
- ✅ **Metadata Completeness**: FR-009 lists all required columns; "n/a" for missing values

### Development Workflow
- ✅ **Dependencies**: Python preferred (constitution compliant); pytest, tox specified
- ✅ **Testing**: Quickstart.md lists test datasets (ds000001, ds000010, ds005256, etc.)

**GATE STATUS**: ✅ PASS - No violations. All requirements align with constitution principles.

## Project Structure

### Documentation (this feature)

```
specs/001-read-file-doc/
├── plan.md              # This file (implementation plan)
├── research.md          # [TO BE CREATED] Technology decisions and patterns
├── data-model.md        # ✅ COMPLETE - Entity schemas and relationships
├── quickstart.md        # ✅ COMPLETE - User guide and setup instructions
├── spec.md              # ✅ COMPLETE - Feature requirements
└── contracts/
    └── cli.yaml         # ✅ COMPLETE - CLI command specifications
```

### Source Code (repository root)

```
code/
├── src/
│   └── openneuro_studies/
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py           # Click CLI entry point
│       │   ├── discover.py       # Discovery command
│       │   ├── organize.py       # Organization command
│       │   ├── metadata.py       # Metadata commands (group)
│       │   ├── validate.py       # Validation command
│       │   ├── status.py         # Status command
│       │   └── clean.py          # Cleanup command
│       ├── models/
│       │   ├── __init__.py
│       │   ├── study.py          # StudyDataset model
│       │   ├── source.py         # SourceDataset model
│       │   └── derivative.py     # DerivativeDataset model
│       ├── config/
│       │   ├── __init__.py
│       │   └── models.py         # OpenNeuroStudiesConfig, SourceSpecification
│       ├── discovery/
│       │   ├── __init__.py
│       │   ├── dataset_finder.py # GitHub API discovery
│       │   └── api_client.py     # Cached GitHub client
│       ├── organization/
│       │   ├── __init__.py
│       │   ├── study_creator.py  # DataLad dataset creation
│       │   └── submodule_linker.py # Git submodule operations
│       ├── metadata/
│       │   ├── __init__.py
│       │   ├── dataset_description.py  # study dataset_description.json
│       │   ├── studies_tsv.py    # studies.tsv generation
│       │   └── derivatives_tsv.py # studies_derivatives.tsv generation
│       ├── validation/
│       │   ├── __init__.py
│       │   └── bids_validator.py # bids-validator-deno integration
│       └── utils/
│           ├── __init__.py
│           ├── cache.py          # API response caching
│           └── git_ops.py        # Git helper functions
├── tests/
│   ├── unit/
│   │   ├── test_models.py
│   │   ├── test_discovery.py
│   │   ├── test_organization.py
│   │   └── test_metadata.py
│   ├── integration/
│   │   ├── test_discover_organize.py
│   │   ├── test_metadata_generation.py
│   │   └── test_validation.py
│   └── fixtures/
│       ├── mock_datasets/
│       └── api_responses/
├── pyproject.toml          # uv-compatible package definition
├── tox.ini                 # Test environments with tox-uv
└── README.md               # Development setup

```

**Structure Decision**: Single Python project structure chosen because:
- CLI tool with single entry point (`openneuro-studies`)
- No frontend/backend split needed
- All operations are command-line driven
- Code organization follows domain boundaries (discovery, organization, metadata, validation)

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations identified** - All requirements align with constitution principles.

## Phase 0: Research (TO BE COMPLETED)

### Research Topics Identified

Based on Technical Context analysis, the following areas require research:

1. **DataLad Python API Patterns**
   - How to use `datalad.api.create()` for --no-annex datasets
   - Best practices for git submodule manipulation via DataLad vs direct git
   - Error handling patterns for DataLad operations

2. **GitHub API Discovery Without Cloning**
   - Using GitHub tree API to read dataset_description.json
   - Efficient pagination for organizations with 1000+ repositories
   - ETag-based caching to respect rate limits

3. **Git Submodule Linking Without Cloning**
   - Using `git config` and `git update-index` to link submodules
   - .gitmodules format for study repositories
   - Publishing study repositories to GitHub organization

4. **Imaging Metrics Sparse Access**
   - datalad-fuse vs fsspec for NIfTI header reading
   - Performance characteristics of sparse access methods
   - Integration with git-annex special remotes

5. **BIDS Study Dataset Conventions**
   - BIDS 1.10.1 study dataset specification details
   - BEP035 (Mega-analysis) compliance requirements
   - Appropriate use of .bidsignore for subdirectories

**Output**: `research.md` documenting decisions, rationale, and code examples for each topic.

**Status**: ⏳ PENDING - To be generated in Phase 0

## Phase 1: Design & Contracts (MOSTLY COMPLETE)

### 1.1 Data Model ✅

**Status**: ✅ COMPLETE

**File**: `data-model.md`

**Contents**:
- Entity definitions: StudyDataset, SourceDataset, DerivativeDataset, SourceSpecification
- Pydantic models with validation
- TSV schema for studies.tsv and studies_derivatives.tsv
- State transitions and data flows
- Validation rules

### 1.2 API Contracts ✅

**Status**: ✅ COMPLETE

**File**: `contracts/cli.yaml`

**Contents**:
- CLI structure with Click commands
- Command specifications: discover, organize, metadata, validate, status, clean
- Arguments, options, and return values
- Exit codes and error handling
- Environment variable requirements

### 1.3 Quickstart Guide ✅

**Status**: ✅ COMPLETE

**File**: `quickstart.md`

**Contents**:
- Installation instructions (uv, pip, tox)
- Configuration setup
- First-run workflow with test datasets
- Troubleshooting guide
- Common operations reference

### 1.4 Agent Context Update ⏳

**Status**: ⏳ PENDING

**Action**: Run `.specify/scripts/bash/update-agent-context.sh claude` to add:
- DataLad API usage patterns
- GitHub API integration
- Click CLI framework
- Pydantic validation models

## Phase 2: Implementation Tasks (NOT PART OF THIS COMMAND)

**Note**: Task generation is handled by `/speckit.tasks` command, not `/speckit.plan`.

The tasks.md file will break down implementation into:
- Core infrastructure (models, config loading)
- Discovery module (GitHub API client, dataset finder)
- Organization module (DataLad operations, submodule linking)
- Metadata module (TSV generation, dataset_description.json)
- Validation module (bids-validator integration)
- CLI layer (Click commands, argument parsing)
- Testing (unit tests, integration tests, fixtures)

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goal**: Establish project structure, models, and configuration loading.

**Deliverables**:
1. Project scaffold with pyproject.toml, tox.ini
2. Pydantic models (StudyDataset, SourceDataset, DerivativeDataset)
3. Configuration loading from .openneuro-studies/config.yaml
4. CLI skeleton with Click
5. Unit tests for models and config

**Dependencies**: None (foundational work)

**Success Criteria**:
- `openneuro-studies --version` works
- Config file loads correctly
- Models validate test data
- Tests pass with pytest

### Phase 2: Discovery Module (Week 1-2)

**Goal**: Implement dataset discovery using GitHub API without cloning.

**Deliverables**:
1. GitHub API client with caching (requests-cache or custom)
2. Dataset discovery from organization repositories
3. Metadata extraction (dataset_description.json via tree API)
4. `discover` CLI command
5. Integration tests with mock API responses

**Dependencies**: Phase 1 (models, config)

**Success Criteria**:
- Discover 10 datasets in <10 seconds
- Cache prevents redundant API calls
- Handles API errors gracefully
- Outputs discovered-datasets.json

### Phase 3: Organization Module (Week 2-3)

**Goal**: Create study datasets and link submodules without cloning.

**Deliverables**:
1. DataLad dataset creation (datalad.api.create)
2. Git submodule linking (git config + git update-index)
3. Study repository initialization
4. `organize` CLI command
5. Unorganized dataset tracking (`.openneuro-studies/unorganized-datasets.json`)
6. Integration tests with temporary git repos

**Dependencies**: Phase 2 (discovery output)

**Success Criteria**:
- Creates study-{id} DataLad datasets
- Links sourcedata and derivatives as submodules
- Tracks unorganizable derivatives with reason codes
- Reports organized vs unorganized counts to user
- No dataset cloning occurs
- Idempotent (safe to re-run)

**Unorganized Dataset Tracking**:

Per Constitution Principle VI (No Silent Failures), all discovered datasets must be either organized or explicitly tracked. The organize command must:

1. Check if source datasets exist for each derivative
2. Track derivatives without sources in `.openneuro-studies/unorganized-datasets.json`:
   ```json
   {
     "derivatives_without_raw": [
       {
         "dataset_id": "ds000212-fmriprep",
         "derivative_id": "fmriprep-v20.2.0-abc123",
         "tool_name": "fmriprep",
         "version": "20.2.0",
         "source_datasets": ["ds000212"],
         "reason": "raw_dataset_not_found",
         "discovered_at": "2025-10-11T12:34:56Z",
         "notes": "Raw dataset ds000212 not in discovered datasets"
       }
     ]
   }
   ```
3. Report summary to user:
   ```
   Organizing 50 datasets:
     ✓ 48 datasets organized
     ⚠ 2 derivatives unorganized (missing source datasets)

   See .openneuro-studies/unorganized-datasets.json for details
   ```

**Reason Codes**:
- `raw_dataset_not_found`: Source raw dataset(s) not in discovered datasets
- `invalid_source_reference`: SourceDatasets field cannot be parsed
- `multi_source_incomplete`: Multi-source derivative missing some source datasets

### Phase 4: Metadata Generation (Week 3-4)

**Goal**: Generate studies.tsv, studies_derivatives.tsv, and dataset_description.json.

**Deliverables**:
1. dataset_description.json generation for studies
2. studies.tsv generation (wide format)
3. studies_derivatives.tsv generation (tall format)
4. JSON sidecar generation
5. `metadata generate` and `metadata sync` commands
6. Unit and integration tests

**Dependencies**: Phase 3 (organized studies)

**Success Criteria**:
- All required columns populated or "n/a"
- TSV follows BIDS tabular conventions (snake_case)
- JSON sidecars describe columns
- Incremental updates work correctly

### Phase 5: Validation Integration (Week 4)

**Goal**: Integrate bids-validator-deno and track validation results.

**Deliverables**:
1. bids-validator-deno subprocess execution
2. Validation result parsing and storage
3. studies.tsv bids_valid column updates
4. `validate` CLI command
5. Integration tests with sample datasets

**Dependencies**: Phase 4 (metadata complete)

**Success Criteria**:
- Validation runs on study datasets
- Results stored in derivatives/bids-validator.{json,txt}
- bids_valid column reflects status
- Handles validation failures gracefully

### Phase 6: Status & Utilities (Week 4-5)

**Goal**: Implement status reporting and cleanup commands.

**Deliverables**:
1. Status command showing processing progress
2. Clean command for cache/temp files
3. Error logging to logs/errors.tsv
4. Progress indicators for long operations
5. Full integration test suite

**Dependencies**: All previous phases

**Success Criteria**:
- `status` shows accurate counts
- `clean` removes cached data
- Error logs track failures
- All tests pass in tox environments

### Phase 7: Documentation & Polish (Week 5)

**Goal**: Finalize documentation, handle edge cases, prepare for release.

**Deliverables**:
1. README with installation instructions
2. Troubleshooting documentation
3. GitHub Actions workflow examples
4. Handle edge cases (multi-source derivatives, missing metadata)
5. Performance optimization (parallelization, batch operations)

**Dependencies**: Phase 6 (complete feature set)

**Success Criteria**:
- Quickstart guide verified with clean environment
- All edge cases from spec.md handled
- Performance meets goals (30min discovery, 2hr metadata)
- Ready for 0.20251009.0 release

## Risk Assessment

### High Risk
- **GitHub API Rate Limits**: Mitigated by aggressive caching and conditional requests (ETags)
- **DataLad API Stability**: Mitigated by extensive error handling and fallback to git commands
- **Git Submodule Complexity**: Mitigated by thorough testing with various repository states

### Medium Risk
- **Non-BIDS Datasets**: Handled gracefully with "n/a" markers and error logging
- **Multi-Source Derivatives**: Tested with ds006190 which has 3 source datasets
- **Network Failures**: Retry logic with exponential backoff for transient errors

### Low Risk
- **Disk Space**: No cloning except for specific operations (outdatedness, imaging metrics)
- **Python Version Compatibility**: Target 3.10+ with clear version requirement
- **Test Dataset Availability**: Use known stable datasets (ds000001, ds000010, etc.)

## Success Metrics

**Phase 1 Complete When**:
- All models defined and tested
- Config loading functional
- CLI skeleton works

**Phase 2 Complete When**:
- Discovers 1000+ datasets in <30 minutes
- API caching reduces redundant calls
- Integration tests pass

**Phase 3 Complete When**:
- Organizes study datasets without cloning
- Submodules linked correctly
- Idempotency verified

**Phase 4 Complete When**:
- Metadata generation <2 hours for all studies
- All TSV columns populated or "n/a"
- Incremental updates functional

**Phase 5-7 Complete When**:
- Full workflow tested end-to-end
- Documentation complete
- Ready for production use

## Next Steps

1. ✅ **Complete Plan** (this document)
2. ⏳ **Phase 0: Create research.md** - Document technology decisions and patterns
3. ⏳ **Update Agent Context** - Run update-agent-context.sh with new technologies
4. 📋 **Phase 2: Generate tasks.md** - Use `/speckit.tasks` command (separate from this workflow)
5. 🚀 **Begin Implementation** - Follow tasks.md for step-by-step execution

**Current Status**: Plan complete, ready for Phase 0 research documentation.
