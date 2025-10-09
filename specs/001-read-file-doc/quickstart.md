# Quickstart: OpenNeuroStudies

**Feature**: [specs/001-read-file-doc](./spec.md)
**Date**: 2025-10-09

## Overview

This guide will help you set up the OpenNeuroStudies infrastructure and organize your first datasets. By the end, you'll have:

- Discovered datasets from OpenNeuro sources
- Organized them into BIDS study structures
- Generated metadata files (studies.tsv, studies_derivatives.tsv)
- Validated BIDS compliance

**Note**: This repository is itself a BIDS dataset following [BEP035 (Mega-analysis)](https://bids.neuroimaging.io/extensions/beps/bep_035.html) with `DatasetType: "study"`. The repository root contains `dataset_description.json` and `.bidsignore` to exclude individual `study-*` subdirectories from top-level validation.

**Estimated time**: 15-30 minutes for setup + initial discovery

---

## Prerequisites

### Required Software

1. **Python 3.10+**
   ```bash
   python --version  # Should be 3.10 or higher
   ```

2. **DataLad** (with git-annex)
   ```bash
   # Install via pip
   pip install datalad

   # Or via conda
   conda install -c conda-forge datalad

   # Verify installation
   datalad --version
   git annex version
   ```

3. **Git** with submodule support
   ```bash
   git --version  # Should be 2.x or higher
   ```

4. **bids-validator-deno** (optional, for validation)
   ```bash
   # Install deno first if needed
   curl -fsSL https://deno.land/install.sh | sh

   # Install bids-validator-deno
   deno install -Agf https://deno.land/x/bids_validator@2.1.0/validator.ts
   ```

### Required Credentials

**GitHub Personal Access Token** with `repo` and `read:org` scopes:

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Click "Generate new token (classic)"
3. Select scopes: `repo`, `read:org`
4. Copy the generated token

**Set environment variable**:
```bash
export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"

# Add to ~/.bashrc or ~/.zshrc for persistence:
echo 'export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"' >> ~/.bashrc
```

---

## Installation

### Option 1: Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/OpenNeuroStudies/OpenNeuroStudies.git
cd OpenNeuroStudies

# Navigate to code directory
cd code

# Create virtual environment and install
uv venv
source .venv/bin/activate
uv pip install -e .

# Return to repository root for operations
cd ..

# Verify installation
openneuro-studies --help
```

### Option 2: Using pip

```bash
# Clone the repository
git clone https://github.com/OpenNeuroStudies/OpenNeuroStudies.git
cd OpenNeuroStudies/code

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in development mode
pip install -e .

# Return to repository root
cd ..

# Verify installation
openneuro-studies --help
```

### Option 3: Using tox (for testing)

```bash
# From code/ directory
cd code

# Install tox with uv plugin
pip install tox tox-uv

# Run tests
tox -e py310

# Run specific test environment
tox -e lint  # Linting
tox -e integration  # Integration tests
```

---

## Configuration

### 1. Create Source Configuration

Create a configuration file at `.openneuro-studies/config.yaml`:

```bash
mkdir -p .openneuro-studies
cat > .openneuro-studies/config.yaml <<EOF
# GitHub organization for publishing study repositories
github_org: OpenNeuroStudies

# Dataset sources to discover
sources:
  - name: OpenNeuroDatasets
    organization_url: https://github.com/OpenNeuroDatasets
    type: raw
    inclusion_patterns:
      - "^ds\\\\d{6}$"  # Match ds000001 through ds999999
    access_token_env: GITHUB_TOKEN

  - name: OpenNeuroDerivatives
    organization_url: https://github.com/OpenNeuroDerivatives
    type: derivative
    inclusion_patterns:
      - "^ds\\\\d{6}$"
    access_token_env: GITHUB_TOKEN
EOF
```

### 2. Configure GitHub Organization (Optional)

The `github_org` setting in config.yaml determines where study repositories are published.

If using a custom organization:
1. Go to https://github.com/organizations/new
2. Create organization (e.g., "MyOpenNeuroStudies")
3. Update `github_org` in `.openneuro-studies/config.yaml`
4. Ensure your GITHUB_TOKEN has write permissions for the organization

You can also override per-command with `--github-org` flag

---

## First Run: Basic Workflow

### Step 1: Discover Datasets

Discover datasets from configured sources (uses GitHub API, no cloning):

```bash
# Discover first few datasets (for testing - recommended test set)
# Test datasets: ds000001, ds000010, ds005256, ds006131, ds006185, ds006189, ds006190
openneuro-studies discover --limit 10 --output discovered.json

# View discovered datasets
cat discovered.json | jq '.[] | {id: .dataset_id, name: .name}'

# Full discovery (all datasets)
openneuro-studies discover

# With debug logging
openneuro-studies --debug-level DEBUG discover --limit 10
```

**Expected output**:
```
[INFO] Discovering datasets from OpenNeuroDatasets...
[INFO] Found 1000+ datasets
[INFO] Cached API responses to .openneuro-studies/cache/
[INFO] Saved metadata to discovered.json
```

### Step 2: Organize into Study Structures

Create study-{id} folders as DataLad datasets with git submodules:

```bash
# Organize first study only (for testing)
openneuro-studies organize study-ds000001 --no-publish  # Local only for now

# Check what was created
ls -la study-ds000001/
tree -L 2 study-ds000001/

# Organize multiple specific studies
openneuro-studies organize study-ds000001 study-ds000010

# Use shell globs
openneuro-studies organize study-ds0000*

# Organize all discovered datasets
openneuro-studies organize
```

**Expected structure**:
```
study-ds000001/
├── .datalad/
│   └── config        # DataLad dataset config (no annex)
├── .git/
├── .gitmodules       # Git submodule links
├── sourcedata/
│   └── raw/          # Git submodule → original dataset
├── derivatives/      # Git submodules → processed datasets
└── dataset_description.json  # Generated metadata
```

### Step 3: Generate Metadata

Generate studies.tsv and studies_derivatives.tsv:

```bash
# Generate basic metadata (no cloning required)
openneuro-studies metadata generate --stage basic

# View results
head studies.tsv
visidata studies.tsv  # Interactive viewer (if installed)

# View derivatives (tall table)
head studies_derivatives.tsv
```

**Expected files**:
```
studies.tsv                    # Wide format, study-centric
studies.json                   # Column descriptions
studies_derivatives.tsv        # Tall format, derivative-centric
studies_derivatives.json       # Column descriptions
```

### Step 4: Validate (Optional)

Run BIDS validation on study datasets:

```bash
# Validate specific study
openneuro-studies validate study-ds000001

# Validate all studies (parallel)
openneuro-studies validate --parallel 4

# Check validation results
cat study-ds000001/derivatives/bids-validator.json | jq '.issues'
```

---

## Verify Installation

Run these commands to verify everything is working:

```bash
# 1. Check CLI is installed
openneuro-studies --version

# 2. Check DataLad is available
datalad --version

# 3. Check GitHub token is set
echo $GITHUB_TOKEN | head -c 10

# 4. Test discovery (dry run - no cache)
openneuro-studies discover --limit 1 --output test.json
cat test.json | jq '.'

# 5. Check organization worked
ls -d study-*/

# 6. Check metadata was generated
test -f studies.tsv && echo "✓ studies.tsv exists"
test -f studies_derivatives.tsv && echo "✓ studies_derivatives.tsv exists"

# 7. Check status
openneuro-studies status
```

**Expected status output**:
```
OpenNeuroStudies Status
=======================
Total studies: 10
├─ Discovered: 10
├─ Organized: 10
├─ Metadata generated: 10
└─ Validated: 10

Processing state:
├─ discovered: 0
├─ organized: 0
├─ metadata_generated: 0
└─ validated: 10 ✓
```

---

## Advanced Workflows

### Incremental Updates

Update specific study when source dataset changes:

```bash
# Sync metadata for specific study
openneuro-studies metadata sync study-ds000001

# Sync all studies with updated sources
openneuro-studies metadata sync --check-sources
```

### Imaging Metrics Extraction

Extract NIfTI header information using sparse access (requires datalad-fuse or fsspec):

```bash
# Install datalad-fuse
pip install datalad-fuse

# Generate imaging metrics
openneuro-studies metadata generate --stage imaging --sparse-method datalad-fuse

# Check updated studies.tsv for bold_size, bold_voxels, etc.
cut -f1,15-18 studies.tsv | head
```

### Outdatedness Calculation

Calculate how many commits derivatives are behind current raw versions:

```bash
# Calculate derivative outdatedness (may clone repos)
openneuro-studies metadata generate --stage outdatedness

# Check results in studies_derivatives.tsv
cut -f1,2,12,13 studies_derivatives.tsv | head
```

### Clean Up

Remove cache and temporary files:

```bash
# Clean API cache only
openneuro-studies clean --cache

# Remove incomplete studies (after failed organization)
openneuro-studies clean --incomplete-studies --dry-run  # Preview
openneuro-studies clean --incomplete-studies  # Execute

# Clean everything
openneuro-studies clean --all
```

---

## Troubleshooting

### GitHub API Rate Limit Exceeded

**Error**: `exit code 3: API rate limit exceeded`

**Solution**:
```bash
# Check current rate limit
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/rate_limit

# Wait for reset (shown in output) or use conditional requests:
openneuro-studies discover --update-cache  # Uses ETags, doesn't count against limit
```

### DataLad Operation Failed

**Error**: `exit code 4: Git/DataLad operation failed`

**Solution**:
```bash
# Check git/DataLad setup
git config --global user.name "Your Name"
git config --global user.email "you@example.com"

# Check git-annex is available
git annex version

# Retry with debug logging
openneuro-studies --debug-level DEBUG organize study-ds000001
```

### Missing Source Datasets

**Error**: `exit code 7: Source datasets not found or inaccessible`

**Solution**:
```bash
# Check source configuration
cat config/sources.yaml

# Test GitHub access
curl -H "Authorization: token $GITHUB_TOKEN" \
  https://api.github.com/orgs/OpenNeuroDatasets/repos | jq '.[0]'

# Check inclusion/exclusion patterns with debug logging
openneuro-studies --debug-level DEBUG discover --source OpenNeuroDatasets --limit 1
```

### Validation Failures

**Error**: `exit code 5: Validation failed`

**Solution**:
```bash
# Check bids-validator-deno is installed
which bids-validator

# Run validation manually
cd study-ds000001
bids-validator .

# Check validation output
cat derivatives/bids-validator.json | jq '.issues'
```

---

## Next Steps

1. **Run Full Workflow**: Process all 1000+ datasets
   ```bash
   openneuro-studies discover
   openneuro-studies organize  # Uses github_org from config
   openneuro-studies metadata generate --stage all
   openneuro-studies validate
   ```

2. **Set Up GitHub Actions**: Automate periodic updates
   ```bash
   # Copy workflow template
   cp .github/workflows/update-studies.yml.example .github/workflows/update-studies.yml
   # Edit and commit
   ```

3. **Generate Dashboards**: Use studies.tsv and studies_derivatives.tsv
   ```bash
   # Example: Dataset statistics
   python scripts/generate_dashboard.py
   ```

4. **Read Implementation Guide**: See [tasks.md](tasks.md) for development tasks

---

## Common Operations Reference

| Task | Command |
|------|---------|
| Discover all datasets | `openneuro-studies discover` |
| Organize specific study | `openneuro-studies organize study-ds000001` |
| Generate basic metadata | `openneuro-studies metadata generate --stage basic` |
| Generate imaging metrics | `openneuro-studies metadata generate --stage imaging` |
| Calculate outdatedness | `openneuro-studies metadata generate --stage outdatedness` |
| Sync metadata | `openneuro-studies metadata sync --check-sources` |
| Validate all studies | `openneuro-studies validate` |
| Check status | `openneuro-studies status` |
| Clean cache | `openneuro-studies clean --cache` |

---

## Resources

- **Specification**: [spec.md](spec.md) - Feature requirements
- **Implementation Plan**: [plan.md](plan.md) - Technical architecture
- **Data Model**: [data-model.md](data-model.md) - Entity schemas
- **CLI Reference**: [contracts/cli.yaml](contracts/cli.yaml) - Command specifications
- **Constitution**: [.specify/memory/constitution.md](../../.specify/memory/constitution.md) - Project principles

---

## Getting Help

- **GitHub Issues**: https://github.com/OpenNeuroStudies/OpenNeuroStudies/issues
- **Debug Logging**: Use `--debug-level DEBUG` or `-l DEBUG` for detailed logs
- **Check Logs**: `logs/errors.tsv` at repository root for error tracking
- **Read Error Messages**: Pay attention to exit codes (see [CLI spec](contracts/cli.yaml))
- **Cache Logs**: `.openneuro-studies/cache/` for API response cache

---

**Last Updated**: 2025-10-09
**Version**: 0.1.0
**Status**: Phase 1 Design Complete
