# OpenNeuroStudies Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-10-09

## Active Technologies
- File-based (TSV, JSON, git submodules); no database required (001-read-file-doc)

### Core Stack (001-read-file-doc)
- **Language**: Python 3.10+ (for compatibility with DataLad ecosystem)
- **CLI Framework**: Click
- **Data Validation**: Pydantic
- **Configuration**: PyYAML
- **Templating**: Copier (for provisioning study datasets)
- **Storage**: File-based (TSV, JSON, YAML) with git/git-annex version control

### DataLad Ecosystem
- **DataLad**: Git-annex dataset management and provenance tracking
- **datalad-fuse**: Sparse data access without fetching annexed content (for cloned datasets)
- **fsspec**: Alternative sparse data access via git-annex backends

### External Services
- **PyGithub**: GitHub API interactions with caching and retry logic
- **bids-validator-deno**: BIDS compliance validation (v2.1.0+)

### Concurrency & Optimization
- **concurrent.futures.ThreadPoolExecutor**: I/O-bound parallel processing
- **requests-cache**: GitHub API response caching with ETag support

### Testing & CI/CD
- **pytest**: Unit and integration testing
- **tox**: Test runner with tox-uv plugin
- **GitHub Actions**: CI/CD workflows (act-compatible)

## Project Structure

**Note**: All code is in `code/` subdirectory. Repository root contains generated data.

```
OpenNeuroStudies/                    # Repository root (BEP035 BIDS mega-analysis dataset)
├── code/                            # All source code
│   ├── src/
│   │   └── openneuro_studies/       # Main package
│   │       ├── cli/                 # Click command-line interface
│   │       ├── config/              # Pydantic configuration models
│   │       ├── discovery/           # GitHub API dataset discovery
│   │       ├── organization/        # DataLad study creation
│   │       ├── metadata/            # TSV metadata generation
│   │       ├── validation/          # BIDS validation integration
│   │       ├── models/              # Pydantic entity models
│   │       └── lib/                 # DataLad/git operations, utilities
│   ├── tests/
│   │   ├── unit/                    # Unit tests for modules
│   │   ├── integration/             # Full workflow tests
│   │   └── fixtures/                # Sample dataset structures
│   ├── pyproject.toml               # Project metadata and dependencies
│   ├── tox.ini                      # tox test configuration
│   └── README.md                    # Code package overview
├── study-ds000001/                  # Study datasets (generated)
├── study-ds005256/
├── ...                              # More study-{id}/ directories
├── dataset_description.json         # BIDS dataset description (DatasetType: "study")
├── CHANGES                          # Version history (CPAN Changelog format)
├── .bidsignore                      # Exclude study-* from top-level validation
├── studies.tsv                      # Study metadata (wide format)
├── studies.json                     # Column descriptions
├── studies_derivatives.tsv          # Derivative metadata (tall format)
├── studies_derivatives.json         # Column descriptions
├── .openneuro-studies/
│   ├── config.yaml                  # Source specifications (user config)
│   └── cache/                       # API response cache
├── logs/
│   └── errors.tsv                   # Error log
├── specs/
│   └── 001-read-file-doc/           # Feature specifications
├── .specify/                        # SpecKit framework files
├── .github/
│   └── workflows/                   # GitHub Actions CI/CD
├── .gitmodules                      # Git submodules for all studies
└── README.md                        # Project overview
```

## Common Commands

### Development Setup
```bash
# Navigate to code directory
cd code

# Using uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e .

# Using pip
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Using tox
tox -e py310

# Return to repository root for operations
cd ..
```

### CLI Usage
```bash
# From repository root (not code/)

# Discover datasets
openneuro-studies discover --limit 10

# With debug logging
openneuro-studies --debug-level DEBUG discover --limit 10

# Organize specific studies
openneuro-studies organize study-ds000001 study-ds005256

# Organize with shell globs
openneuro-studies organize study-ds0000*

# Add derivative from URL
openneuro-studies organize https://github.com/OpenNeuroDerivatives/ds001761-fmriprep

# Generate metadata
openneuro-studies metadata generate --stage basic

# Validate
openneuro-studies validate

# Check status
openneuro-studies status
```

### Testing
```bash
# From code/ directory
cd code

# Run all tests
pytest

# Run with coverage
pytest --cov=src/openneuro_studies --cov-report=html

# Run specific test file
pytest tests/unit/test_discovery.py

# Run integration tests
pytest tests/integration/

# Using tox
tox -e py310        # Run tests
tox -e lint         # Linting
tox -e integration  # Integration tests

# Return to root
cd ..
```

### Linting & Formatting
```bash
# From code/ directory
cd code

# Check with ruff
ruff check .

# Format code
ruff format .

# Type checking (if mypy configured)
mypy src/openneuro_studies

cd ..
```

### DataLad Operations
```bash
# From repository root (not code/)
# Study datasets are created at root level

# Create DataLad dataset without annex
datalad create --no-annex -d . study-ds000001

# Run command with provenance
datalad run -m "Generate metadata" -- openneuro-studies metadata generate

# Check dataset status
datalad status
```

### GitHub Actions (act)
```bash
# Test workflows locally
act -j tests                    # Run tests workflow
act -j lint                     # Run linting workflow
act schedule                    # Test cron-triggered workflow
act -s GITHUB_TOKEN=$GITHUB_TOKEN  # Provide secrets
```

## Code Style

### Python Conventions
- **Style Guide**: Follow PEP 8
- **Type Hints**: Use type hints for all function signatures
- **Docstrings**: Google-style docstrings for all public functions/classes
- **Line Length**: 100 characters (ruff default)
- **Imports**: Organize with isort (part of ruff)

### DataLad API Usage
```python
# Prefer datalad.api package
import datalad.api as dl

# Create dataset
ds = dl.create(path="study-ds000001", no_annex=True)

# Run with provenance
dl.run(
    cmd=["python", "script.py"],
    message="Process dataset",
    inputs=["input.txt"],
    outputs=["output.txt"]
)
```

### Pydantic Models
```python
from pydantic import BaseModel, Field, validator

class StudyDataset(BaseModel):
    study_id: str = Field(..., pattern=r"^study-ds\d+$")
    name: str

    @validator('study_id')
    def validate_study_id(cls, v):
        if not v.startswith('study-'):
            raise ValueError('study_id must start with "study-"')
        return v
```

### Error Handling
```python
# Use specific exceptions
from openneuro_studies.lib.exceptions import (
    DatasetNotFoundError,
    GitHubAPIError,
    ValidationError
)

# Retry logic for API calls
from openneuro_studies.lib.retry import retry_on_api_error

@retry_on_api_error(max_attempts=3)
def fetch_dataset_metadata(dataset_id: str) -> dict:
    # API call implementation
    pass
```

## Testing Strategy

### Sample Datasets for Testing
Use these datasets for comprehensive testing:

**Raw Datasets:**
- **ds000001**: Single raw dataset (basic case)
- **ds005256**: Medium-sized dataset
- **ds006131**: Raw dataset with derivatives
- **ds006185**: Raw dataset with derivatives
- **ds006189**: Raw dataset with derivatives
- **ds006190**: Multi-source derivative (sources: ds006189, ds006185, ds006131)

**Derivative Datasets:**
- **ds000001-mriqc**: Quality control metrics for ds000001
- **ds000212-fmriprep**: Preprocessed data (note: raw ds000212 NOT in test set - tests unorganized derivative handling)

### Test Organization
```python
# Unit tests
@pytest.mark.unit
def test_study_creation():
    study = StudyDataset(study_id="study-ds000001", ...)
    assert study.study_id == "study-ds000001"

# Integration tests
@pytest.mark.integration
def test_full_workflow(tmp_path):
    # Test discovery → organization → metadata → validation
    pass

# AI-generated tests (mark with @pytest.mark.ai_generated)
@pytest.mark.ai_generated
async def test_my_new_feature() -> None:
    """Test description."""
    # test code
```

## Environment Variables

```bash
# Required
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"

# Optional
export OPENNEURO_STUDIES_CONFIG=".openneuro-studies/config.yaml"
export OPENNEURO_STUDIES_CACHE=".openneuro-studies/cache"
```

## Git Workflow

### Commit Messages
```bash
# Feature commits
git commit -m "feat: add dataset discovery via GitHub API"

# Bug fixes
git commit -m "fix: handle missing dataset_description.json gracefully"

# Documentation
git commit -m "docs: update quickstart with sparse access examples"

# Using datalad run
datalad run -m "Generate metadata for all studies" -- openneuro-studies metadata generate
```

### Pre-commit Hooks
If pre-commit modifies files:
```bash
# Just commit again - files are already fixed
git commit -m "your message"
```

## BIDS Compliance (BEP035)

This repository is itself a **BIDS dataset** following [BEP035 (Mega-analysis)](https://bids.neuroimaging.io/extensions/beps/bep_035.html):

- **DatasetType**: `"study"` - This is a meta-dataset aggregating information about multiple studies
- **dataset_description.json**: At repository root following [BIDS specification](https://bids-specification.readthedocs.io/en/stable/modality-agnostic-files/dataset-description.html)
- **CHANGES**: Version history following [CPAN Changelog convention](https://metacpan.org/dist/CPAN-Changes/view/lib/CPAN/Changes/Spec.pod)
  - Format: `VERSION DATE\n  - Change description\n`
  - Encoding: UTF-8
  - **Git Tag Requirement**: Each CHANGES entry MUST be accompanied by a matching git tag (e.g., `0.20251009.0`)
  - Example:
    ```
    0.20251009.0 2025-10-09
      - Initial infrastructure implementation
      - Dataset discovery and organization
    ```
  - Use `/openneuro-studies.release` command to generate new release entries from git history (see `.specify/commands/openneuro-studies.release.md`)
- **.bidsignore**: Excludes `study-*` subdirectories from top-level BIDS validation
  - Each `study-{id}/` is its own BIDS dataset (DatasetType: "study")
  - Top-level validation focuses on metadata files (studies.tsv, studies_derivatives.tsv)

## Constitution Compliance

This project follows the [OpenNeuroStudies Constitution](/.specify/memory/constitution.md):

✅ **Data Integrity**: All datasets linked via git submodules with explicit versions
✅ **Automation**: All operations scripted and idempotent
✅ **Standard Formats**: TSV/JSON/YAML only, no binary formats
✅ **Git/DataLad-First**: All state changes via datalad run or git commits
✅ **Observability**: Complete status via studies.tsv and studies_derivatives.tsv

## Recent Changes
- 001-read-file-doc: Added Python 3.10+

- **2025-10-09** (001-read-file-doc): Implementation planning phase complete
  - Added core Python stack (Click, Pydantic, PyYAML, PyGithub)
  - Added DataLad ecosystem (DataLad, datalad-fuse, fsspec)
  - Selected ThreadPoolExecutor for concurrency
  - Defined project structure and CLI commands
  - Created data model with Pydantic schemas
  - Generated research findings for technical decisions

## Resources

- **Specification**: [specs/001-read-file-doc/spec.md](specs/001-read-file-doc/spec.md)
- **Implementation Plan**: [specs/001-read-file-doc/plan.md](specs/001-read-file-doc/plan.md)
- **Data Model**: [specs/001-read-file-doc/data-model.md](specs/001-read-file-doc/data-model.md)
- **CLI Reference**: [specs/001-read-file-doc/contracts/cli.yaml](specs/001-read-file-doc/contracts/cli.yaml)
- **Quickstart Guide**: [specs/001-read-file-doc/quickstart.md](specs/001-read-file-doc/quickstart.md)
- **Constitution**: [.specify/memory/constitution.md](.specify/memory/constitution.md)

<!-- MANUAL ADDITIONS START -->
<!-- Add project-specific notes, conventions, or reminders here -->
<!-- MANUAL ADDITIONS END -->
