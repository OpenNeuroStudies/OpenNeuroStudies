# GitHub Repository Descriptions Enhancement

**Date**: 2026-03-23
**Status**: Specification
**GitHub Issue**: https://github.com/OpenNeuroStudies/OpenNeuroStudies/issues/2
**Authors**: Claude Sonnet 4.5

## Summary

Enhance GitHub repository descriptions during `openneuro-studies publish` to automatically populate compelling, data-rich descriptions showing coverage statistics (dataset counts, sizes, subjects) for both study repositories and the top-level OpenNeuroStudies repository.

## Problem Statement

**Current State**:
- Study repositories get generic description: `"OpenNeuroStudies study dataset: study-ds000001"`
- Top-level repository has static description
- No quantitative information about coverage, size, or scope
- Missed opportunity to showcase project scale and value

**User Request** (Issue #2):
> "Add update of description(s) to summaries + total sizes/# of datasets (raw + derivatives)"

**Inspiration**: DANDI project (https://github.com/dandi/dandisets) shows informative descriptions with dataset statistics.

## Requirements

### FR-050: Study Repository Descriptions

**When**: During `openneuro-studies publish` for each study repository

**Description Format**:
```
{study_name} | {subjects_num} subjects | {source_count} source + {derivative_count} derivative datasets | {total_size_human} | {datatypes}
```

**Example**:
```
Balloon Analog Risk-taking Task | 16 subjects | 1 source + 2 derivative datasets | 2.2 GB | anat, func
```

**Detailed Format** (if description allows longer text):
```
{study_name}

📊 {subjects_num} subjects across {sessions_num} sessions
📦 {source_count} source dataset(s): {source_ids}
🔬 {derivative_count} derivative(s): {derivative_ids}
💾 Total size: {total_size_human}
🧠 Modalities: {datatypes}
```

**Example**:
```
Balloon Analog Risk-taking Task

📊 16 subjects
📦 1 source dataset: ds000001 (v1.0.0)
🔬 2 derivatives: fMRIPrep-21.0.1, MRIQC-0.16.1
💾 Total size: 2.2 GB
🧠 Modalities: anat, func
```

**Data Sources**:
- `study_name`: From `studies.tsv` `name` column
- `subjects_num`: From `studies.tsv` `subjects_num` column
- `sessions_num`: From `studies.tsv` `sessions_num` column
- `source_count`: From `studies.tsv` `source_count` column
- `derivative_count`: From `studies.tsv` `derivative_count` column
- `total_size`: Sum of `bold_size + t1w_size` (or read from sourcedata.tsv if available)
- `datatypes`: From `studies.tsv` `datatypes` column
- `source_ids`: Parse from study's sourcedata/ directory names
- `derivative_ids`: From `studies.tsv` `derivative_ids` column

### FR-051: Top-Level Repository Description

**When**: During `openneuro-studies publish` (after all studies published) or via dedicated command

**Description Format**:
```
OpenNeuroStudies: Curated BIDS neuroimaging datasets | {total_studies} studies | {total_datasets} datasets ({total_sources} raw + {total_derivatives} derivatives) | {total_size_human}
```

**Example**:
```
OpenNeuroStudies: Curated BIDS neuroimaging datasets | 41 studies | 95 datasets (41 raw + 54 derivatives) | 450 GB
```

**Detailed Format** (for README or About section):
```
OpenNeuroStudies: Curated BIDS Neuroimaging Datasets

📊 {total_studies} studies covering {total_subjects} unique subjects
📦 {total_datasets} datasets: {total_sources} raw source datasets + {total_derivatives} derivative datasets
💾 Total repository size: {total_size_human}
🧠 Modalities: {unique_datatypes}
🔬 Pipeline tools: {unique_pipeline_tools}

Updated: {last_update_timestamp}
```

**Example**:
```
OpenNeuroStudies: Curated BIDS Neuroimaging Datasets

📊 41 studies covering 523 unique subjects
📦 95 datasets: 41 raw source datasets + 54 derivative datasets
💾 Total repository size: 450 GB
🧠 Modalities: anat, func, dwi, fmap, perf
🔬 Pipeline tools: fMRIPrep, MRIQC, QSIPrep, ASLPrep

Updated: 2026-03-23
```

**Data Sources**:
- `total_studies`: Row count from `studies.tsv`
- `total_datasets`: Sum of all `source_count + derivative_count`
- `total_sources`: Sum of all `source_count`
- `total_derivatives`: Sum of all `derivative_count`
- `total_subjects`: Sum of all `subjects_num` (or count unique if subjects overlap)
- `total_size`: Sum of all `bold_size + t1w_size` across studies
- `unique_datatypes`: Unique set from all `datatypes` columns
- `unique_pipeline_tools`: Unique pipeline names from `derivative_ids`

### FR-052: Update Existing Repository Descriptions

**When**: Optionally update existing repositories without re-pushing

**Command**:
```bash
openneuro-studies publish --update-descriptions-only
```

**Behavior**:
- Read `studies.tsv` for current metadata
- For each published study in `published-studies.json`:
  - Generate description from metadata
  - Update via GitHub API (no git push needed)
- Update top-level OpenNeuroStudies repository description
- Report summary of updated repositories

## Design

### Description Templates

**File**: `code/src/openneuro_studies/publishing/description_templates.py` (NEW)

```python
"""GitHub repository description templates."""

from typing import Any


def format_size_human(size_bytes: int | float | str) -> str:
    """Convert bytes to human-readable format.

    Args:
        size_bytes: Size in bytes (int, float, or 'n/a')

    Returns:
        Human-readable size (e.g., "2.2 GB", "450 MB", "n/a")
    """
    if size_bytes == "n/a" or size_bytes is None:
        return "n/a"

    size = float(size_bytes)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0

    return f"{size:.1f} PB"


def generate_study_description(study_metadata: dict[str, Any], format: str = "short") -> str:
    """Generate description for a study repository.

    Args:
        study_metadata: Row from studies.tsv as dict
        format: "short" (GitHub description, 350 char limit) or "detailed" (README)

    Returns:
        Formatted description string
    """
    name = study_metadata.get("name", "Unknown study")
    subjects = study_metadata.get("subjects_num", "n/a")
    sessions = study_metadata.get("sessions_num", "n/a")
    source_count = study_metadata.get("source_count", 0)
    derivative_count = study_metadata.get("derivative_count", 0)
    datatypes = study_metadata.get("datatypes", "n/a")
    derivative_ids = study_metadata.get("derivative_ids", "")

    # Calculate total size
    bold_size = study_metadata.get("bold_size", 0)
    t1w_size = study_metadata.get("t1w_size", 0)

    if bold_size == "n/a":
        bold_size = 0
    if t1w_size == "n/a":
        t1w_size = 0

    total_size = int(bold_size) + int(t1w_size) if bold_size and t1w_size else 0
    size_human = format_size_human(total_size) if total_size > 0 else "n/a"

    if format == "short":
        # GitHub description has 350 character limit
        parts = [name]

        if subjects != "n/a":
            subj_text = f"{subjects} subject{'s' if int(subjects) != 1 else ''}"
            if sessions != "n/a" and sessions != subjects:
                subj_text += f" × {sessions} sessions"
            parts.append(subj_text)

        dataset_text = f"{source_count} source + {derivative_count} derivative dataset{'s' if derivative_count != 1 else ''}"
        parts.append(dataset_text)

        if size_human != "n/a":
            parts.append(size_human)

        if datatypes != "n/a":
            parts.append(datatypes)

        return " | ".join(parts)

    else:  # detailed
        lines = [
            name,
            "",
            f"📊 Coverage:",
        ]

        if subjects != "n/a":
            if sessions != "n/a" and sessions != subjects:
                lines.append(f"  • {subjects} subjects across {sessions} sessions")
            else:
                lines.append(f"  • {subjects} subjects")

        lines.append(f"📦 Datasets:")
        lines.append(f"  • {source_count} source dataset(s)")

        if derivative_count > 0 and derivative_ids:
            deriv_list = derivative_ids.split(",")
            lines.append(f"  • {derivative_count} derivative(s): {', '.join(deriv_list)}")
        else:
            lines.append(f"  • {derivative_count} derivative(s)")

        if size_human != "n/a":
            lines.append(f"💾 Total size: {size_human}")

        if datatypes != "n/a":
            lines.append(f"🧠 Modalities: {datatypes}")

        return "\n".join(lines)


def generate_toplevel_description(
    total_studies: int,
    total_datasets: int,
    total_sources: int,
    total_derivatives: int,
    total_size: int,
    total_subjects: int,
    unique_datatypes: set[str],
    unique_tools: set[str],
    format: str = "short",
) -> str:
    """Generate description for top-level OpenNeuroStudies repository.

    Args:
        total_studies: Number of studies
        total_datasets: Total datasets (sources + derivatives)
        total_sources: Number of source datasets
        total_derivatives: Number of derivative datasets
        total_size: Total size in bytes
        total_subjects: Total unique subjects (sum or unique count)
        unique_datatypes: Set of unique datatypes
        unique_tools: Set of unique pipeline tools
        format: "short" (GitHub description) or "detailed" (README)

    Returns:
        Formatted description string
    """
    size_human = format_size_human(total_size)

    if format == "short":
        # GitHub description limit: 350 chars
        return (
            f"OpenNeuroStudies: Curated BIDS neuroimaging datasets | "
            f"{total_studies} studies | "
            f"{total_datasets} datasets ({total_sources} raw + {total_derivatives} derivatives) | "
            f"{size_human}"
        )

    else:  # detailed
        from datetime import datetime

        datatypes_str = ", ".join(sorted(unique_datatypes))
        tools_str = ", ".join(sorted(unique_tools)) if unique_tools else "n/a"
        timestamp = datetime.now().strftime("%Y-%m-%d")

        return f"""OpenNeuroStudies: Curated BIDS Neuroimaging Datasets

📊 {total_studies} studies covering {total_subjects:,} subjects
📦 {total_datasets} datasets: {total_sources} raw source datasets + {total_derivatives} derivative datasets
💾 Total repository size: {size_human}
🧠 Modalities: {datatypes_str}
🔬 Pipeline tools: {tools_str}

Updated: {timestamp}
"""
```

### Integration with GitHubPublisher

**File**: `code/src/openneuro_studies/publishing/github_publisher.py` (MODIFIED)

**Add method**:
```python
def update_repository_description(self, repo_name: str, description: str) -> None:
    """Update repository description via GitHub API.

    Args:
        repo_name: Repository name (e.g., "study-ds000001")
        description: New description text

    Raises:
        PublishError: If update fails
    """
    try:
        repo = self.organization.get_repo(repo_name)
        repo.edit(description=description)
        logger.info(f"Updated description for {repo_name}")
    except UnknownObjectException as e:
        raise PublishError(f"Repository '{repo_name}' not found") from e
    except GithubException as e:
        raise PublishError(f"Failed to update description for '{repo_name}': {e}") from e
```

**Modify `create_repository` method**:
```python
def create_repository(
    self,
    repo_name: str,
    description: str | None = None,
    private: bool = False,
) -> str:
    """Create a new repository with enhanced description."""
    # If no description provided, try to generate from metadata
    if description is None:
        description = self._generate_study_description(repo_name)

    # Rest of existing code...
```

**Add helper**:
```python
def _generate_study_description(self, study_id: str) -> str:
    """Generate description for study from studies.tsv.

    Args:
        study_id: Study identifier (e.g., "study-ds000001")

    Returns:
        Generated description or fallback
    """
    try:
        from openneuro_studies.publishing.description_templates import generate_study_description
        import csv

        studies_tsv = Path("studies.tsv")
        if not studies_tsv.exists():
            return f"OpenNeuroStudies study dataset: {study_id}"

        with open(studies_tsv) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                if row["study_id"] == study_id:
                    return generate_study_description(row, format="short")

        # Study not in studies.tsv yet
        return f"OpenNeuroStudies study dataset: {study_id}"

    except Exception as e:
        logger.warning(f"Failed to generate description for {study_id}: {e}")
        return f"OpenNeuroStudies study dataset: {study_id}"
```

### CLI Integration

**File**: `code/src/openneuro_studies/cli/publish.py` (MODIFIED)

**Add option**:
```python
@click.option(
    "--update-descriptions",
    is_flag=True,
    help="Update repository descriptions from metadata (no git push)",
)
```

**Add logic**:
```python
# After study publishing OR if --update-descriptions
if update_descriptions or (published_count > 0 and not dry_run):
    click.echo("\nUpdating repository descriptions...")

    from openneuro_studies.publishing.description_templates import (
        generate_study_description,
        generate_toplevel_description,
    )
    import csv

    # Update study descriptions
    with open("studies.tsv") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            study_id = row["study_id"]

            # Only update if published
            if tracker.is_published(study_id):
                try:
                    description = generate_study_description(row, format="short")
                    publisher.update_repository_description(study_id, description)
                    click.echo(f"  ✓ Updated {study_id}")
                except Exception as e:
                    click.echo(f"  ✗ Failed {study_id}: {e}", err=True)

    # Update top-level repository description
    click.echo("\nUpdating OpenNeuroStudies repository description...")
    # ... (calculate aggregates and update)
```

## Implementation Plan

### Phase 1: Description Templates (Week 1)

1. Create `description_templates.py` with:
   - `format_size_human()` - bytes to human-readable
   - `generate_study_description()` - per-study descriptions
   - `generate_toplevel_description()` - top-level description
   - Unit tests for all functions

2. Test description generation:
   - Read studies.tsv
   - Generate descriptions for 5 sample studies
   - Verify formatting and character limits

### Phase 2: GitHub API Integration (Week 1)

1. Add `update_repository_description()` to GitHubPublisher
2. Modify `create_repository()` to generate descriptions
3. Add `_generate_study_description()` helper
4. Test with test organization (not production)

### Phase 3: CLI Integration (Week 2)

1. Add `--update-descriptions` flag to publish command
2. Implement description update logic after publishing
3. Add top-level repository description update
4. Test end-to-end workflow

### Phase 4: Batch Update (Week 2)

1. Create `openneuro-studies descriptions update` subcommand
2. Update all published repositories at once
3. Generate report of updated repositories
4. Document in CLAUDE.md and README

## Testing Strategy

### Unit Tests

**File**: `code/tests/unit/test_description_templates.py` (NEW)

```python
def test_format_size_human():
    assert format_size_human(1024) == "1.0 KB"
    assert format_size_human(1048576) == "1.0 MB"
    assert format_size_human(2319818025) == "2.2 GB"
    assert format_size_human("n/a") == "n/a"

def test_generate_study_description_short():
    metadata = {
        "name": "Balloon Analog Risk-taking Task",
        "subjects_num": "16",
        "sessions_num": "n/a",
        "source_count": "1",
        "derivative_count": "2",
        "bold_size": "2319818025",
        "t1w_size": "85042746",
        "datatypes": "anat,func",
        "derivative_ids": "fMRIPrep-21.0.1,MRIQC-0.16.1",
    }

    desc = generate_study_description(metadata, format="short")

    assert "Balloon Analog Risk-taking Task" in desc
    assert "16 subjects" in desc
    assert "1 source + 2 derivative" in desc
    assert "2.2 GB" in desc
    assert "anat,func" in desc
    assert len(desc) <= 350  # GitHub limit

def test_generate_toplevel_description():
    desc = generate_toplevel_description(
        total_studies=41,
        total_datasets=95,
        total_sources=41,
        total_derivatives=54,
        total_size=450_000_000_000,
        total_subjects=523,
        unique_datatypes={"anat", "func", "dwi"},
        unique_tools={"fMRIPrep", "MRIQC"},
        format="short",
    )

    assert "41 studies" in desc
    assert "95 datasets" in desc
    assert "450" in desc  # Size
    assert len(desc) <= 350
```

### Integration Tests

1. **Test with test organization**:
   - Create test study repository
   - Publish with description
   - Verify description via GitHub API

2. **Test update-only mode**:
   - Modify studies.tsv
   - Run `publish --update-descriptions`
   - Verify descriptions updated without git push

### Manual Verification

```bash
# 1. Generate descriptions for all studies
python -c "
import csv
from openneuro_studies.publishing.description_templates import generate_study_description

with open('studies.tsv') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        desc = generate_study_description(row, format='short')
        print(f'{row[\"study_id\"]}: {desc}')
        print(f'  Length: {len(desc)} chars')
        print()
"

# 2. Test publish with descriptions
openneuro-studies publish --dry-run study-ds000001

# 3. Update descriptions only (no git push)
openneuro-studies publish --update-descriptions --dry-run
```

## Success Criteria

1. ✅ Study repositories have informative descriptions showing:
   - Study name
   - Subject count
   - Dataset counts (source + derivative)
   - Total size
   - Datatypes

2. ✅ Top-level repository description shows:
   - Total studies
   - Total datasets
   - Total size
   - Coverage summary

3. ✅ Descriptions auto-generated during publish
4. ✅ Existing repositories can be updated without re-push
5. ✅ Character limits respected (GitHub description limit: 350 chars)
6. ✅ Graceful fallback if metadata missing

## Open Questions

### Q1: Should we update top-level description automatically?

**Options**:
- A. Update during every `publish` (could be rate-limited by GitHub)
- B. Update only with explicit flag `--update-toplevel`
- C. Separate command `openneuro-studies update-toplevel-description`

**Recommendation**: Option B (explicit flag, default off)

### Q2: Where to show detailed description (with emojis)?

**Options**:
- A. GitHub description (limited to 350 chars, may not support emojis well)
- B. README.md in repository
- C. GitHub "About" section (supports markdown)

**Recommendation**: Short format in description, detailed in README.md

### Q3: Handle studies.tsv not up-to-date?

If studies.tsv is stale (extraction not run recently), descriptions may be inaccurate.

**Options**:
- A. Warn user, use stale data
- B. Fail and require fresh extraction
- C. Re-extract on demand

**Recommendation**: Option A (warn but proceed)

## References

- GitHub Issue: https://github.com/OpenNeuroStudies/OpenNeuroStudies/issues/2
- DANDI project: https://github.com/dandi/dandisets
- PyGithub API docs: https://pygithub.readthedocs.io/
- Current implementation: `code/src/openneuro_studies/publishing/github_publisher.py`
- Metadata schema: `studies.json`
