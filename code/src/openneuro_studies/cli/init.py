"""Initialize OpenNeuroStudies repository."""

import os
from pathlib import Path

import click
import datalad.api as dl


@click.command()
@click.argument("path", type=click.Path(), default=".", required=False)
@click.option(
    "--github-org",
    default="OpenNeuroStudies",
    help="GitHub organization for publishing study repositories",
    show_default=True,
)
@click.option("--force", is_flag=True, help="Reinitialize existing repository (DESTRUCTIVE)")
def init(path: str, github_org: str, force: bool) -> None:
    """Initialize OpenNeuroStudies repository.

    Initialize a new OpenNeuroStudies repository as a DataLad dataset
    (git repository without git-annex). Creates configuration files,
    directory structure, and initial commit.

    \b
    Examples:
        openneuro-studies init
        openneuro-studies init /path/to/openneurostudies
        openneuro-studies init --github-org MyOrganization
    """
    repo_path = Path(path).resolve()

    # Check if already initialized
    if (repo_path / ".datalad").exists() and not force:
        click.echo(f"Error: {repo_path} is already a DataLad dataset", err=True)
        click.echo("Use --force to reinitialize (DESTRUCTIVE)", err=True)
        raise click.Abort()

    if (repo_path / ".git").exists() and not (repo_path / ".datalad").exists() and not force:
        click.echo(f"Error: {repo_path} is already a git repository", err=True)
        click.echo("Use --force to reinitialize (DESTRUCTIVE)", err=True)
        raise click.Abort()

    click.echo(f"Initializing OpenNeuroStudies repository at {repo_path}...")

    # Ensure directory exists (DataLad is fine with empty existing directories)
    repo_path.mkdir(parents=True, exist_ok=True)

    # Change to the directory
    original_cwd = Path.cwd()
    os.chdir(repo_path)

    try:
        # Create DataLad dataset without annex (current directory)
        click.echo("Creating DataLad dataset (no annex)...")
        dl.create(path=".", annex=False, force=force)

        # Create .openneuro-studies as a DataLad subdataset RIGHT AWAY before adding any content (FR-020a)
        click.echo("Creating .openneuro-studies subdataset...")
        config_dir = repo_path / ".openneuro-studies"
        dl.create(path=".openneuro-studies", dataset=".", annex=False)

        # Create config.yaml
        config_file = config_dir / "config.yaml"
        if not config_file.exists() or force:
            click.echo("Creating configuration file...")
            config_content = f"""# OpenNeuroStudies Configuration

# GitHub organization where organized study repositories will be published
github_org: {github_org}

# Dataset sources to discover
sources:
  # OpenNeuroDatasets - Raw BIDS datasets
  - name: OpenNeuroDatasets
    organization_url: https://github.com/OpenNeuroDatasets
    type: raw
    inclusion_patterns:
      - "^ds\\\\d{{6}}$"  # Match ds000001 through ds999999
    exclusion_patterns: []
    access_token_env: GITHUB_TOKEN

  # OpenNeuroDerivatives - Processed derivative datasets
  - name: OpenNeuroDerivatives
    organization_url: https://github.com/OpenNeuroDerivatives
    type: derivative
    inclusion_patterns:
      - "^ds\\\\d{{6}}-.*$"  # Match ds000001-fmriprep, ds000001-mriqc, etc.
    exclusion_patterns: []
    access_token_env: GITHUB_TOKEN
"""
            config_file.write_text(config_content)

        # Create test-discover.sh
        test_script = config_dir / "test-discover.sh"
        if not test_script.exists() or force:
            click.echo("Creating test discovery script...")
            script_content = """#!/bin/bash
# Helper script to discover the 6 MVP test datasets
# Usage: .openneuro-studies/test-discover.sh

set -e

# Ensure GITHUB_TOKEN is set
if [ -z "$GITHUB_TOKEN" ]; then
    echo "Error: GITHUB_TOKEN environment variable is not set"
    echo "Please set your GitHub personal access token:"
    echo "  export GITHUB_TOKEN='your_token_here'"
    exit 1
fi

# Run discovery with test filter
echo "Discovering 6 MVP test datasets..."
echo ""

openneuro-studies discover \\
    --test-filter ds000001 \\
    --test-filter ds005256 \\
    --test-filter ds006131 \\
    --test-filter ds006185 \\
    --test-filter ds006189 \\
    --test-filter ds006190 \\
    --output .openneuro-studies/discovered-datasets.json

echo ""
echo "Discovery complete! Results saved to .openneuro-studies/discovered-datasets.json"
echo ""
echo "Test datasets:"
echo "  Raw datasets: ds000001, ds005256, ds006131"
echo "  Derivatives:  ds006185, ds006189, ds006190"
"""
            test_script.write_text(script_content)
            test_script.chmod(0o755)

        # Create .gitignore if it doesn't exist
        gitignore_file = repo_path / ".gitignore"
        if not gitignore_file.exists() or force:
            click.echo("Creating .gitignore...")
            gitignore_content = """# OpenNeuroStudies

# Cache directories
.cache/

# Study datasets (managed as submodules)
study-*/

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
.venv/
ENV/
env/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Testing
.tox/
.pytest_cache/
htmlcov/
.coverage

# Logs
*.log
logs/*.log

# Temporary files
*.tmp
*.bak

# Git annex
.git/annex/tmp/
"""
            gitignore_file.write_text(gitignore_content)

        # Create .gitignore in .openneuro-studies subdataset (FR-020a)
        subds_gitignore = config_dir / ".gitignore"
        if not subds_gitignore.exists() or force:
            click.echo("Creating .openneuro-studies/.gitignore...")
            subds_gitignore_content = """# .openneuro-studies subdataset .gitignore

# Cache directory (API responses)
cache/
"""
            subds_gitignore.write_text(subds_gitignore_content)

        # Create dataset_description.json
        desc_file = repo_path / "dataset_description.json"
        if not desc_file.exists() or force:
            click.echo("Creating dataset_description.json...")
            desc_content = """{
  "Name": "OpenNeuroStudies: collection of OpenNeuro datasets and their derivatives",
  "BIDSVersion": "1.10.1",
  "DatasetType": "study",
  "License": "CC0",
  "Authors": [
    "OpenNeuroStudies Contributors"
  ],
  "HowToAcknowledge": "Please cite the OpenNeuroStudies project and the individual datasets included in your analysis.",
  "Funding": [
    "NIH #2R24MH117179-06 OpenNeuro: An open archive for analysis and sharing of BRAIN Initiative data. PI: Poldrack (Stanford)"
  ],
  "EthicsApprovals": [],
  "ReferencesAndLinks": [
    "https://openneuro.org",
    "https://github.com/OpenNeuroStudies/OpenNeuroStudies",
    "https://bids.neuroimaging.io/extensions/beps/bep_035.html"
  ],
  "DatasetDOI": ""
}
"""
            desc_file.write_text(desc_content)

        # Create .bidsignore
        bidsignore_file = repo_path / ".bidsignore"
        if not bidsignore_file.exists() or force:
            click.echo("Creating .bidsignore...")
            bidsignore_content = """# BIDS Ignore Configuration
# Exclude study-* subdirectories as they are individual study datasets
# managed separately, not part of the top-level BEP035 mega-analysis dataset

study-*
.openneuro-studies/
logs/
"""
            bidsignore_file.write_text(bidsignore_content)

        # Create README.md
        readme_file = repo_path / "README.md"
        if not readme_file.exists() or force:
            click.echo("Creating README.md...")
            readme_content = f"""# OpenNeuroStudies

Collection of OpenNeuro datasets organized as BIDS study structures.

## Overview

This repository organizes 1000+ OpenNeuro datasets into BIDS study structures with automated metadata generation. Each study is a separate DataLad dataset linked as a git submodule.

## GitHub Organization

Study repositories are published to: **{github_org}**

## Quick Start

1. **Set GitHub token**:
   ```bash
   export GITHUB_TOKEN="your_token_here"
   ```

2. **Discover datasets**:
   ```bash
   # Test with 6 datasets
   .openneuro-studies/test-discover.sh

   # Or discover all
   openneuro-studies discover
   ```

3. **Organize studies**:
   ```bash
   openneuro-studies organize
   ```

4. **Generate metadata**:
   ```bash
   openneuro-studies metadata generate
   ```

## Configuration

See `.openneuro-studies/config.yaml` for source configuration.

## Documentation

- Project: https://github.com/OpenNeuroStudies/OpenNeuroStudies
- BIDS BEP035: https://bids.neuroimaging.io/extensions/beps/bep_035.html

## License

CC0 - Data is from OpenNeuro under various licenses. Check individual datasets.
"""
            readme_file.write_text(readme_content)

        # Add files and create initial commit
        click.echo("Creating initial commit in .openneuro-studies subdataset...")
        dl.save(
            dataset=".openneuro-studies",
            message="Initialize .openneuro-studies subdataset\n\n"
            "Contains configuration and tracking files\n"
            "Created by openneuro-studies init command"
        )

        click.echo("Creating initial commit in parent dataset...")
        dl.save(
            message="Initialize OpenNeuroStudies repository\n\n"
            f"GitHub organization: {github_org}\n"
            "Created by openneuro-studies init command"
        )

        click.echo(f"✓ Successfully initialized OpenNeuroStudies repository at {repo_path}")
        click.echo(f"✓ GitHub organization: {github_org}")
        click.echo("\nNext steps:")
        click.echo("  1. Set GITHUB_TOKEN environment variable")
        click.echo("  2. Run: .openneuro-studies/test-discover.sh")
        click.echo("  3. Run: openneuro-studies organize")

    finally:
        # Return to original directory
        os.chdir(original_cwd)
