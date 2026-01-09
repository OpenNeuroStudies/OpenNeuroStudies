# OpenNeuroStudies

Infrastructure for organizing OpenNeuro datasets as BIDS study structures.

## Overview

OpenNeuroStudies provides tools to discover, organize, and maintain 1000+ OpenNeuro datasets as BIDS study structures with automated metadata generation. The system creates study-{id} folders linking raw datasets and derivatives without requiring full clones.

## Features

- **Dataset Discovery**: Discovers raw and derivative datasets from GitHub organizations (OpenNeuroDatasets, OpenNeuroDerivatives) without cloning
- **Study Organization**: Creates study-{id} folders as DataLad datasets with sourcedata/ and derivatives/ linked as git submodules
- **Metadata Generation**: Generates comprehensive metadata (dataset_description.json, studies.tsv, studies+derivatives.tsv)
- **BIDS Validation**: Integrates bids-validator-deno to track compliance status

## Installation

### Using uv (recommended)

```bash
# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate

# Install package with dependencies
uv pip install -e .

# Install with development dependencies
uv pip install -e ".[dev]"
```

### Using pip

```bash
# Create virtual environment
python3.10 -m venv .venv
source .venv/bin/activate

# Install package
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

## Development Setup

### Prerequisites

- Python 3.10 or later
- DataLad (install via system package manager or pip)
- Git
- GitHub personal access token (set as `GITHUB_TOKEN` environment variable)
- bids-validator-deno 2.1.0+ (optional, for validation features)

### Configuration

Create `.openneuro-studies/config.yaml` in your project root:

```yaml
github_org: "OpenNeuroStudies"  # GitHub organization for publishing study repos

sources:
  - organization: "OpenNeuroDatasets"
    type: "github"
    patterns:
      - "ds\\d{6}"

  - organization: "OpenNeuroDerivatives"
    type: "github"
    patterns:
      - "ds\\d{6}"
```

Set your GitHub token:

```bash
export GITHUB_TOKEN="your_github_token_here"
```

### Running Tests

Using tox (recommended):

```bash
# Install tox with uv support
pip install tox tox-uv

# Run all tests
tox

# Run tests for specific Python version
tox -e py310

# Run only unit tests
tox -e unit

# Run only integration tests
tox -e integration

# Run linting
tox -e lint

# Run type checking
tox -e type
```

Using pytest directly:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=openneuro_studies --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

### Code Quality

**IMPORTANT: Before committing**, always run linting and type checking to ensure code quality:

```bash
# Run all quality checks before committing
tox -e lint    # Check formatting and linting
tox -e type    # Type checking with mypy

# Auto-format code if needed
tox -e format

# Or run all checks at once
tox -e lint,type
```

**Git Workflow Best Practice**:
1. Make code changes
2. Run `tox -e format` to auto-format
3. Run `tox -e lint,type` to verify quality
4. Fix any errors reported
5. Commit changes

This ensures all commits maintain consistent code quality and type safety.

## Usage

### Quick Start with Test Datasets

```bash
# Discover test datasets
openneuro-studies discover

# Organize specific studies
openneuro-studies organize study-ds000001 study-ds005256

# Generate metadata for all studies
openneuro-studies metadata generate

# Validate BIDS compliance
openneuro-studies validate study-ds000001

# Check processing status
openneuro-studies status
```

### Full Workflow

1. **Discovery**: Identify available datasets

```bash
openneuro-studies discover --config .openneuro-studies/config.yaml
```

2. **Organization**: Create study structures

```bash
# Organize all discovered datasets
openneuro-studies organize

# Or organize specific studies
openneuro-studies organize study-ds000001 study-ds006131
```

3. **Metadata Generation**: Create studies.tsv and related files

```bash
# Generate all metadata
openneuro-studies metadata generate

# Sync metadata for specific studies
openneuro-studies metadata sync study-ds000001
```

4. **Validation**: Run BIDS validator

```bash
# Validate all studies
openneuro-studies validate

# Validate specific study
openneuro-studies validate study-ds000001
```

5. **Status Tracking**: Monitor progress

```bash
openneuro-studies status
```

## Project Structure

```
src/openneuro_studies/
├── cli/              # Click CLI commands
├── models/           # Pydantic data models
├── config/           # Configuration loading
├── discovery/        # GitHub API dataset discovery
├── organization/     # DataLad dataset creation
├── metadata/         # Metadata generation
├── validation/       # BIDS validation integration
└── utils/            # Shared utilities

tests/
├── unit/             # Unit tests
├── integration/      # Integration tests
└── fixtures/         # Test fixtures and mock data
```

## Documentation

See the [specs/001-read-file-doc/](../specs/001-read-file-doc/) directory for detailed documentation:

- **spec.md**: Feature specification with user stories and requirements
- **plan.md**: Implementation plan with phases and architecture
- **data-model.md**: Entity schemas and relationships
- **quickstart.md**: User guide and troubleshooting
- **contracts/cli.yaml**: CLI command specifications

## Contributing

This project follows the BIDS specification 1.10.1 and BEP035 (Mega-analysis) conventions. All TSV columns use snake_case naming following BIDS tabular file conventions.

### Testing Requirements

- All new features must have tests
- Mark AI-generated tests with `@pytest.mark.ai_generated`
- Unit tests should be fast and isolated
- Integration tests may interact with GitHub API (use caching)

## License

MIT License - see LICENSE file for details

## Acknowledgments

Funded by NIH #2R24MH117179-06 OpenNeuro: An open archive for analysis and sharing of BRAIN Initiative data. PI: Poldrack (Stanford)
