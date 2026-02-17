# BIDS-Studies Subproject Migration Plan

Date: 2025-12-26
Status: Planning

## Summary

Create a new generic subproject `bids-studies` under `code/src/` to house reusable BIDS metadata extraction and aggregation functionality. The `openneuro-studies` package will depend on `bids-studies` for these generic capabilities.

## Rationale

The hierarchical stats extraction, sparse access, and summary extraction functionality we've built is:
- **Generic**: Works with any BIDS dataset, not just OpenNeuro
- **Reusable**: Could be used by other projects working with BIDS data
- **Independent**: Doesn't require OpenNeuro-specific configuration or APIs

Separating this into its own package:
- Enables reuse in other BIDS-related projects
- Clarifies the boundary between generic BIDS operations and OpenNeuro-specific workflows
- Allows independent versioning and testing
- Follows good software engineering principles (separation of concerns)

## Module Classification

### Generic BIDS Functionality → `bids-studies`

| Module | Description | Dependencies |
|--------|-------------|--------------|
| `lib/sparse_access.py` | Sparse access to git-annex datasets | datalad-fuse, fsspec |
| `lib/fuse_mount.py` | FUSE mounting utilities | datalad-fuse |
| `metadata/summary_extractor.py` | Extract BIDS metadata from datasets | sparse_access |
| `metadata/hierarchical_extractor.py` | Hierarchical stats extraction | sparse_access |

### OpenNeuro-Specific → stays in `openneuro-studies`

| Module | Description | Why OpenNeuro-specific |
|--------|-------------|------------------------|
| `cli/` | CLI commands | OpenNeuro workflow |
| `config/` | Configuration models | OpenNeuro sources config |
| `discovery/` | GitHub API discovery | OpenNeuro repos on GitHub |
| `organization/` | Study dataset creation | OpenNeuro study structure |
| `publishing/` | GitHub publishing | OpenNeuro GitHub org |
| `provision/` | Template provisioning | OpenNeuro templates |
| `validation/` | BIDS validation | Integrated with studies.tsv |
| `utils/github_client.py` | GitHub API client | OpenNeuro GitHub repos |
| `lib/datalad_utils.py` | DataLad operations | Study organization |
| `models/` | Pydantic models | OpenNeuro entities |
| `metadata/studies_tsv.py` | studies.tsv generation | OpenNeuro-specific format |
| `metadata/studies_plus_derivatives_tsv.py` | Derivatives TSV (studies+derivatives.tsv) | OpenNeuro-specific format |
| `metadata/dataset_description.py` | dataset_description.json | Study metadata |

## Proposed Package Structure

```
code/src/
├── bids_studies/                    # NEW: Generic BIDS package
│   ├── __init__.py
│   ├── sparse/                      # Sparse data access
│   │   ├── __init__.py
│   │   ├── access.py                # SparseDataset class
│   │   └── fuse.py                  # FUSE mount utilities
│   ├── extraction/                  # Metadata extraction
│   │   ├── __init__.py
│   │   ├── subject.py               # Per-subject extraction
│   │   ├── dataset.py               # Per-dataset aggregation
│   │   └── study.py                 # Study-level aggregation
│   ├── schemas/                     # JSON sidecar schemas
│   │   ├── sourcedata+subjects.json
│   │   ├── sourcedata.json
│   │   ├── derivatives+subjects.json
│   │   └── derivatives+datasets.json
│   └── utils/                       # Utilities
│       ├── __init__.py
│       └── tsv.py                   # TSV reading/writing
│
└── openneuro_studies/               # EXISTING: OpenNeuro-specific
    ├── __init__.py
    ├── cli/                         # CLI commands
    ├── config/                      # Configuration
    ├── discovery/                   # Dataset discovery
    ├── organization/                # Study creation
    ├── publishing/                  # GitHub publishing
    ├── provision/                   # Template provisioning
    ├── validation/                  # BIDS validation
    ├── models/                      # Pydantic models
    ├── metadata/                    # Metadata generation
    │   ├── __init__.py
    │   ├── studies_tsv.py           # Uses bids_studies
    │   ├── studies_plus_derivatives_tsv.py
    │   └── dataset_description.py
    ├── lib/                         # Utilities
    │   ├── __init__.py
    │   └── datalad_utils.py
    └── utils/
        └── github_client.py
```

## pyproject.toml Configuration

### bids-studies/pyproject.toml (NEW)

```toml
[project]
name = "bids-studies"
version = "0.1.0"
description = "Generic BIDS dataset metadata extraction and aggregation"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
sparse = [
    "datalad-fuse>=0.4.0",
    "fsspec>=2023.1.0",
]
imaging = [
    "nibabel>=5.0.0",
]
all = [
    "bids-studies[sparse,imaging]",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

### openneuro-studies/pyproject.toml (UPDATED)

```toml
[project]
dependencies = [
    "bids-studies",  # Add local dependency
    # ... existing dependencies
]

[tool.hatch.metadata]
allow-direct-references = true

[project.optional-dependencies]
imaging = [
    "bids-studies[imaging]",
]
```

## Migration Steps

### Phase 1: Create Package Structure
1. Create `code/src/bids_studies/` directory
2. Create `__init__.py` files
3. Create `pyproject.toml` for bids-studies
4. Move JSON schemas to `bids_studies/schemas/`

### Phase 2: Migrate Sparse Access
1. Move `lib/sparse_access.py` → `bids_studies/sparse/access.py`
2. Move `lib/fuse_mount.py` → `bids_studies/sparse/fuse.py`
3. Update imports in openneuro-studies

### Phase 3: Migrate Extraction
1. Refactor `hierarchical_extractor.py` into:
   - `bids_studies/extraction/subject.py` - Per-subject extraction
   - `bids_studies/extraction/dataset.py` - Dataset aggregation
   - `bids_studies/extraction/study.py` - Study aggregation
2. Move `summary_extractor.py` generic parts → `bids_studies/extraction/`
3. Keep OpenNeuro-specific parts in `openneuro_studies/metadata/`

### Phase 4: Update Dependencies
1. Update `openneuro_studies` to import from `bids_studies`
2. Update `pyproject.toml` dependencies
3. Run tests to verify functionality

### Phase 5: Documentation
1. Add README.md for bids-studies
2. Update CLAUDE.md with new structure
3. Document public API

## API Design

### bids_studies.sparse

```python
from bids_studies.sparse import SparseDataset

with SparseDataset("/path/to/dataset") as ds:
    subjects = ds.list_dirs("sub-*")
    size = ds.get_file_size("sub-01/anat/sub-01_T1w.nii.gz")
    with ds.open_file("sub-01/anat/sub-01_T1w.nii.gz") as f:
        header = f.read(352)
```

### bids_studies.extraction

```python
from bids_studies.extraction import (
    extract_subject_stats,
    extract_subjects_stats,
    aggregate_to_dataset,
    aggregate_to_study,
    write_subjects_tsv,
    write_datasets_tsv,
)

# Extract per-subject stats
subjects = extract_subjects_stats(source_path, source_id)

# Aggregate to dataset level
dataset = aggregate_to_dataset(subjects, source_id)

# Write TSV files
write_subjects_tsv(output_path, subjects)
```

## Testing Strategy

1. **Unit tests** for bids-studies in `code/tests/unit/bids_studies/`
2. **Integration tests** using sample BIDS datasets
3. **Ensure openneuro-studies tests pass** after migration

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Comprehensive test coverage before migration |
| Import path changes | Use re-exports in openneuro_studies for backwards compatibility |
| Dependency conflicts | Keep bids-studies minimal, optional deps for imaging |

## Success Criteria

1. `bids-studies` is independently installable and usable
2. All existing openneuro-studies functionality works
3. Tests pass for both packages
4. Clear API documentation

## Next Steps

1. Review and approve this plan
2. Create bids-studies package structure
3. Migrate sparse access module first (least dependencies)
4. Migrate extraction module
5. Update openneuro-studies imports
6. Run full test suite
