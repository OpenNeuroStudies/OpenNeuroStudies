# Implementation Plan: OpenNeuroStudies Infrastructure Refactoring

**Branch**: `001-read-file-doc` | **Date**: 2025-10-09 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-read-file-doc/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

The OpenNeuroStudies infrastructure refactoring organizes 1000+ OpenNeuro raw and derivative datasets into BIDS study structures with automated metadata generation and validation. The system discovers datasets from configured sources (OpenNeuroDatasets, OpenNeuroDerivatives, openfmri), creates study-{id} folders as DataLad datasets with git submodule links, generates comprehensive metadata files (dataset_description.json, studies.tsv, studies_derivatives.tsv), and integrates BIDS validation results - all without requiring full dataset clones through strategic use of GitHub APIs, sparse data access, and cached operations.

## Technical Context

**Language/Version**: Python 3.10+ (for compatibility with DataLad ecosystem)
**Primary Dependencies**:
- DataLad (git-annex dataset management and provenance)
- datalad-fuse (sparse data access without fetching annexed content)
- fsspec (alternative sparse data access)
- Click (CLI framework)
- Pydantic (configuration and data validation)
- PyGithub (GitHub API interactions)
- PyYAML (configuration file parsing)
- bids-validator-deno 2.1.0+ (BIDS compliance validation)

**Concurrency**: NEEDS CLARIFICATION - evaluate joblib, concurrent.futures, or multiprocessing.Pool for processing study subdatasets in parallel while synchronizing top-level dataset operations

**Storage**: File-based (TSV, JSON, YAML) with git/git-annex version control - no database
**Testing**: pytest with unit and integration tests, GitHub CI via act-compatible workflows
**Target Platform**: Linux server (primary), macOS (development compatibility)
**Project Type**: Single project (CLI automation tool)
**Performance Goals**:
- Process 1000+ datasets in <2 hours using cached API responses
- Incremental updates complete in <30 seconds per study
- Zero full clones for basic metadata extraction

**Constraints**:
- GitHub API rate limits (5000 req/hour authenticated)
- Must avoid cloning 1000+ datasets (disk space and performance)
- Must operate on dirty git trees when using explicit DataLad run inputs/outputs
- Idempotent operations (running multiple times produces same result)

**Scale/Scope**:
- 1000+ OpenNeuro datasets across multiple source repositories
- Study metadata files (studies.tsv) with 20+ columns per study
- Derivative tracking (studies_derivatives.tsv) with potentially thousands of rows
- GitHub organization (OpenNeuroStudies) with 1000+ study repositories

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ I. Data Integrity & Traceability
- **Requirement**: All datasets linked via git submodules with version references
- **Status**: PASS - Design uses git submodules for all dataset links with explicit commit SHAs (FR-004, FR-022)
- **Requirement**: All transformations recorded in DataLad run records or git history
- **Status**: PASS - Using `datalad run` for all state-changing operations (FR-016, Constitution Principle IV)
- **Requirement**: Metadata files accurately reflect current state
- **Status**: PASS - Metadata generation is scripted and reproducible (FR-009, FR-010, FR-011)

### ✅ II. Automation & Reproducibility
- **Requirement**: All operations must be scripted
- **Status**: PASS - Python scripts with Click CLI, no manual operations (user input confirms)
- **Requirement**: Scripts must be idempotent
- **Status**: PASS - Explicit requirement FR-016
- **Requirement**: External API calls must implement caching and retry logic
- **Status**: PASS - FR-017 requires caching; Constitution v1.20251008.0 added retry policy

### ✅ III. Standard Formats
- **Requirement**: TSV for tabular data, JSON for structured metadata, YAML for configuration
- **Status**: PASS - studies.tsv, studies_derivatives.tsv (FR-009, FR-010), dataset_description.json (FR-005), Pydantic+YAML config (user input)
- **Requirement**: TSV column names follow BIDS tabular file conventions (snake_case)
- **Status**: PASS - Constitution v1.20251009.0 requires snake_case, spec uses study_id, subjects_num, etc.
- **Requirement**: JSON sidecars describe TSV columns
- **Status**: PASS - FR-011 requires studies.json and studies_derivatives.json

### ✅ IV. Git/DataLad-First Workflow
- **Requirement**: All state changes committed through git/DataLad with descriptive messages
- **Status**: PASS - FR-016 requires idempotent operations implying proper git commits
- **Requirement**: Use `datalad run` for state-modifying scripts
- **Status**: PASS - Constitution Principle IV, FR-021 uses `datalad create --no-annex`
- **Requirement**: Dirty trees acceptable only with explicit --input/--output flags
- **Status**: PASS - Constitution allows dirty trees with explicit flags

### ✅ V. Observability & Monitoring
- **Requirement**: Summary files provide complete overview
- **Status**: PASS - studies.tsv, studies_derivatives.tsv with comprehensive columns (FR-009, FR-010)
- **Requirement**: Incomplete datasets clearly marked
- **Status**: PASS - "n/a" entries for missing data (Constitution Metadata Completeness)
- **Requirement**: Dashboard generation supported
- **Status**: PASS - Tall table (studies_derivatives.tsv) enables per-study/per-derivative/per-subject dashboards

### ⚠️ Additional Dependencies Check
- **New Dependencies**: datalad-fuse, fsspec, Click, Pydantic, PyGithub, PyYAML
- **Justification**:
  - datalad-fuse/fsspec: Required for sparse NIfTI header access without full clones (FR-033)
  - Click: Standard Python CLI framework, minimal complexity
  - Pydantic: Type-safe configuration validation from YAML (FR-020)
  - PyGithub: GitHub API interactions without shell curl/jq (FR-002, FR-017)
  - PyYAML: Configuration file parsing (FR-020)
- **Status**: PASS - All justified by specific functional requirements

### Constitution Compliance: ✅ PASS
No violations detected. All requirements align with constitution principles.

## Project Structure

### Documentation (this feature)

```
specs/001-read-file-doc/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output - concurrency library evaluation
├── data-model.md        # Phase 1 output - Study/Source/Derivative entities
├── quickstart.md        # Phase 1 output - setup and first run
├── contracts/           # Phase 1 output - CLI commands and data schemas
│   ├── cli.yaml         # Click command specifications
│   └── schemas.json     # Pydantic model schemas
├── checklists/
│   └── requirements.md  # Quality validation (already complete)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (code/ subdirectory)

**Note**: All code resides in `code/` subdirectory. The repository root contains study-{id}/ datasets, studies.tsv, and other generated data.

```
code/
├── src/
│   └── openneuro_studies/
│       ├── __init__.py
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── main.py              # Click CLI entry point
│       │   ├── discover.py          # Dataset discovery commands
│       │   ├── organize.py          # Study organization commands
│       │   ├── metadata.py          # Metadata generation commands
│       │   └── validate.py          # BIDS validation commands
│       ├── config/
│       │   ├── __init__.py
│       │   ├── models.py            # Pydantic configuration models
│       │   └── sources.yaml         # Default source specifications
│       ├── discovery/
│       │   ├── __init__.py
│       │   ├── github_api.py        # GitHub/Forgejo tree API client
│       │   ├── dataset_finder.py    # Dataset discovery from sources
│       │   └── cache.py             # API response caching
│       ├── organization/
│       │   ├── __init__.py
│       │   ├── study_creator.py     # DataLad study dataset creation
│       │   ├── submodule_linker.py  # Git submodule operations
│       │   └── derivative_mapper.py # Derivative-to-source mapping
│       ├── metadata/
│       │   ├── __init__.py
│       │   ├── dataset_description.py  # dataset_description.json generation
│       │   ├── studies_tsv.py          # studies.tsv generation
│       │   ├── derivatives_tsv.py      # studies_derivatives.tsv generation
│       │   ├── imaging_metrics.py      # Sparse NIfTI header access
│       │   └── outdatedness.py         # Derivative version tracking
│       ├── validation/
│       │   ├── __init__.py
│       │   └── bids_validator.py    # bids-validator-deno integration
│       ├── models/
│       │   ├── __init__.py
│       │   ├── study.py             # Study dataset entity
│       │   ├── source.py            # Source dataset entity
│       │   └── derivative.py        # Derivative dataset entity
│       └── lib/
│           ├── __init__.py
│           ├── datalad_ops.py       # DataLad API wrappers (import datalad.api as dl)
│           ├── git_ops.py           # Git operations (git config, update-index)
│           ├── parallel.py          # Concurrency utilities (TBD in research)
│           └── retry.py             # API retry logic with backoff
│
├── tests/
│   ├── unit/
│   │   ├── test_discovery.py
│   │   ├── test_organization.py
│   │   ├── test_metadata.py
│   │   └── test_models.py
│   ├── integration/
│   │   ├── test_full_workflow.py   # End-to-end dataset organization
│   │   ├── test_incremental.py     # Incremental update scenarios
│   │   └── fixtures/               # Sample dataset structures
│   └── conftest.py                  # Shared pytest fixtures
│
├── pyproject.toml               # Project metadata, dependencies
├── setup.py or setup.cfg        # Distribution configuration
├── tox.ini                      # tox-uv test runner configuration
└── README.md                    # Code package overview

# Repository root structure (generated data):
.                                # Repository root
├── code/                        # All source code (above)
├── .openneuro-studies/
│   ├── config.yaml              # Source specifications (user config)
│   └── cache/                   # API response cache
├── study-ds000001/              # Study datasets (created by organize)
├── study-ds000010/
├── study-ds006190/
├── ...                          # More study-{id} directories
├── dataset_description.json     # BIDS dataset description (BEP035 mega-analysis)
├── CHANGES                      # Version history (CPAN Changelog format)
├── .bidsignore                  # Exclude study-* from top-level BIDS validation
├── studies.tsv                  # Study metadata (wide format)
├── studies.json                 # Column descriptions
├── studies_derivatives.tsv      # Derivative metadata (tall format)
├── studies_derivatives.json     # Column descriptions
├── logs/
│   └── errors.tsv               # Error log across all operations
├── .github/
│   └── workflows/               # CI/CD workflows
│       ├── tests.yml            # pytest on push/PR (act-compatible)
│       └── update-studies.yml   # Cron-triggered metadata updates
├── specs/                       # Feature specifications
├── .specify/                    # SpecKit framework files
├── .gitmodules                  # Git submodules for all studies
└── README.md                    # Project overview
```

**Structure Decision**: Single project structure with code separated in `code/` subdirectory. This separates the automation tool from the generated study datasets, which reside in the repository root. The repository root becomes the data directory containing 1000+ study-{id}/ folders, while all Python code, tests, and packaging configuration lives under `code/`. This enables:
- Clean separation of code vs. data
- Easy navigation to study datasets from root
- Top-level metadata files (studies.tsv) accessible without entering code/
- DataLad operations at root level for managing study subdatasets

## Complexity Tracking

*No violations to justify - Constitution Check passed without exceptions.*

## Phase 0: Research

### Research Tasks

The following unknowns from Technical Context require investigation:

1. **Concurrency Library Selection**
   - **Question**: Which Python concurrency library best fits parallel study processing with synchronized top-level operations?
   - **Options to evaluate**:
     - `concurrent.futures.ThreadPoolExecutor` (standard library, simple)
     - `concurrent.futures.ProcessPoolExecutor` (standard library, CPU-bound)
     - `joblib.Parallel` (popular in data science, good for embarrassingly parallel tasks)
     - `multiprocessing.Pool` (standard library, lower-level control)
   - **Criteria**: Ease of use, DataLad compatibility, ability to synchronize top-level git operations, error handling
   - **Output**: Decision in research.md with code examples

2. **GitHub API Rate Limit Strategy**
   - **Question**: How to efficiently cache and batch GitHub API calls to stay within 5000 req/hour limit for 1000+ datasets?
   - **Investigation**:
     - PyGithub rate limit handling
     - Cache invalidation strategies (time-based vs. commit-based)
     - Conditional requests (ETags, If-Modified-Since)
   - **Output**: Caching architecture pattern in research.md

3. **Sparse Data Access Implementation**
   - **Question**: datalad-fuse vs. fsspec for sparse data access (e.g., reading file headers without fetching full annexed content) - which is more reliable and performant?
   - **Investigation**:
     - datalad-fuse setup and API (sparse access with cloned datasets)
     - fsspec with git/git-annex backends
     - Performance characteristics for reading file headers (NIfTI, JSON, etc.)
     - Error handling for missing annexed content
   - **Output**: Recommended approach with fallback strategy in research.md

4. **DataLad API Patterns**
   - **Question**: Best practices for using `datalad.api` vs. `datalad.support.annexrepo` for git-annex operations
   - **Investigation**:
     - When to use high-level `datalad.api.create`, `datalad.api.run`
     - When to use lower-level `datalad.support.annexrepo` for git operations
     - Error handling and state management
   - **Output**: Design pattern guide in research.md

5. **GitHub Actions + act Compatibility**
   - **Question**: What GitHub Actions features work locally with act, what requires workarounds?
   - **Investigation**:
     - act limitations (Docker-based execution)
     - Secrets management locally
     - Cron scheduling testing
   - **Output**: CI/CD workflow design constraints in research.md

6. **Outdatedness Calculation Without Cloning**
   - **Question**: Can we calculate commit counts between versions using GitHub API without cloning?
   - **Investigation**:
     - GitHub Compare API (`GET /repos/{owner}/{repo}/compare/{base}...{head}`)
     - Tag/release API for version identification
     - Fallback strategies when API insufficient
   - **Output**: Implementation strategy in research.md

### Research Output

Research findings will be consolidated in `specs/001-read-file-doc/research.md` with the structure:

```markdown
# Research: OpenNeuroStudies Infrastructure Refactoring

## 1. Concurrency Library Selection
**Decision**: [chosen library]
**Rationale**: [why chosen based on criteria]
**Alternatives considered**: [other options and why rejected]
**Code example**: [minimal proof of concept]

## 2. GitHub API Rate Limit Strategy
[same structure]

[... for all 6 research tasks]
```

## Phase 1: Design Artifacts

### Phase 1a: Data Model

**Output**: `specs/001-read-file-doc/data-model.md`

Extract entities from spec.md Key Entities section (lines 115-126):

1. **Study Dataset** (study.py)
   - Fields: study_id, title, authors, bids_version, source_datasets, derivative_datasets, github_url, raw_version, version
   - Relationships: 1-to-many with SourceDataset, 1-to-many with DerivativeDataset
   - State: discovered → organized → metadata_generated → validated

2. **Source Dataset** (source.py)
   - Fields: dataset_id, url, commit_sha, bids_version, license, authors
   - Relationships: Many-to-1 with StudyDataset
   - Validation: URL must be valid git repository

3. **Derivative Dataset** (derivative.py)
   - Fields: tool_name, version, datalad_uuid, size_stats, execution_metrics, source_datasets, processed_raw_version, outdatedness
   - Relationships: Many-to-many with StudyDataset (via studies_derivatives.tsv)
   - Validation: version must be semantic version or date-based

4. **Source Specification** (config/models.py)
   - Fields: organization_url, inclusion_patterns, access_credentials
   - Validation: Pydantic model loaded from YAML

5. **Metadata Index** (studies.tsv, studies_derivatives.tsv)
   - Wide format (studies.tsv): study-centric with derivative_ids column
   - Tall format (studies_derivatives.tsv): study_id + derivative_id lead columns with detailed metrics

### Phase 1b: Contracts

**Output**: `specs/001-read-file-doc/contracts/`

#### CLI Commands (cli.yaml)

Based on functional requirements, define Click commands:

```yaml
commands:
  discover:
    description: Discover datasets from configured sources
    options:
      --source: Source specification YAML file
      --cache-dir: API response cache directory
      --update: Update existing cache

  organize:
    description: Organize datasets into study structures
    arguments:
      targets: Study IDs, URLs, or paths (positional, supports globs)
    options:
      --github-org: GitHub organization for study repositories
      --dry-run: Show what would be done without executing

  metadata:
    subcommands:
      generate:
        description: Generate metadata files
        arguments:
          targets: Study IDs or globs (positional)
        options:
          --stage: Metadata generation stage (basic|imaging|outdatedness)

      sync:
        description: Incrementally sync metadata for updated studies
        arguments:
          targets: Study IDs or globs (positional)
        options:
          --check-sources: Check source datasets for updates

  validate:
    description: Run BIDS validation on study datasets
    arguments:
      targets: Study IDs or globs (positional)
    options:
      --validator-version: bids-validator-deno version
```

#### Data Schemas (schemas.json)

Pydantic models exported as JSON Schema:

- `StudyDataset`: Corresponds to data-model.md Study entity
- `SourceDataset`: Corresponds to Source entity
- `DerivativeDataset`: Corresponds to Derivative entity
- `SourceSpecification`: Configuration model
- `StudiesRow`: Row schema for studies.tsv
- `DerivativesRow`: Row schema for studies_derivatives.tsv

### Phase 1c: Quickstart

**Output**: `specs/001-read-file-doc/quickstart.md`

Structure:

```markdown
# Quickstart: OpenNeuroStudies

## Prerequisites
- Python 3.10+
- DataLad installed
- Git with submodule support
- GITHUB_TOKEN environment variable

## Installation
[pip install or uv commands]

## Configuration
1. Copy default sources.yaml
2. Configure GitHub organization
3. Set API credentials

## First Run
1. Discover datasets: `openneuro-studies discover --source sources.yaml`
2. Organize into studies: `openneuro-studies organize --github-org OpenNeuroStudies`
3. Generate metadata: `openneuro-studies metadata generate --stage basic`
4. Validate: `openneuro-studies validate`

## Verify Installation
[Commands to check that setup worked]
```

### Phase 1d: Agent Context Update

**Output**: Updated `.specify/agent-files/claude.md` (or appropriate agent file)

Run:
```bash
.specify/scripts/bash/update-agent-context.sh claude
```

This will add technology from this plan (DataLad, Click, Pydantic, PyGithub, datalad-fuse, fsspec) to the agent-specific context file, preserving any manual additions.

## Constitution Re-Check (Post-Design)

*To be performed after Phase 1 artifacts are generated*

Verify that:
- [ ] Data model uses text-based formats (TSV, JSON) ✓ (anticipated pass)
- [ ] CLI commands support idempotent operations ✓ (anticipated pass)
- [ ] All external APIs have caching and retry logic ✓ (anticipated pass)
- [ ] DataLad operations use `datalad.api` package ✓ (anticipated pass)
- [ ] No binary formats or databases introduced ✓ (anticipated pass)

## Next Steps

1. **Complete Phase 0**: Generate research.md with all decisions documented
2. **Complete Phase 1**: Generate data-model.md, contracts/, quickstart.md
3. **Run `/speckit.tasks`**: Generate tasks.md for implementation
4. **Run `/speckit.implement`**: Execute tasks.md to build the system

## Notes

- This plan follows Constitution v1.20251009.1 requirements
- All TSV column names use snake_case with _num, _min, _max, _size suffix patterns
- Study repositories will be created as DataLad datasets without annex (`datalad create --no-annex`)
- Three-stage metadata extraction: basic (no clone) → imaging (sparse) → outdatedness (selective clone)
- Concurrency decision deferred to Phase 0 research to evaluate joblib vs concurrent.futures
