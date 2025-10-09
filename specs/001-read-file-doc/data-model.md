# Data Model: OpenNeuroStudies Infrastructure Refactoring

**Feature**: [specs/001-read-file-doc](./spec.md)
**Date**: 2025-10-09
**Input**: spec.md Key Entities (lines 115-126)

## Overview

This data model defines the core entities for organizing 1000+ OpenNeuro datasets into BIDS study structures. The model supports discovery, organization, metadata generation, and validation workflows while maintaining git/DataLad provenance.

## Entity Diagram

```
┌─────────────────────────────────────────────────────┐
│                  Study Dataset                       │
│  - study_id (PK)                                    │
│  - name, title, version                             │
│  - authors, bids_version                            │
│  - github_url                                       │
│  - raw_version (if single source)                   │
│  - state: discovered → organized →                  │
│           metadata_generated → validated            │
└──────────────┬──────────────────────┬───────────────┘
               │                      │
               │ 1:N                  │ M:N
               │                      │
         ┌─────▼────────┐      ┌─────▼──────────────┐
         │   Source     │      │    Derivative      │
         │   Dataset    │      │    Dataset         │
         │              │      │                    │
         │ - dataset_id │      │ - tool_name        │
         │ - url        │      │ - version          │
         │ - commit_sha │      │ - datalad_uuid     │
         │ - bids_ver   │      │ - size_stats       │
         │ - license    │      │ - exec_metrics     │
         │ - authors    │      │ - outdatedness     │
         └──────────────┘      └────────────────────┘

┌────────────────────────────────────────────────────┐
│          Source Specification (Config)             │
│  - organization_url                                │
│  - inclusion_patterns (regex)                      │
│  - access_credentials (optional)                   │
│  Loaded from: config/sources.yaml                  │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│           Metadata Indices (TSV Files)             │
│                                                    │
│  studies.tsv (WIDE format - study-centric)        │
│  - One row per study                              │
│  - derivative_ids column (list)                   │
│                                                    │
│  studies_derivatives.tsv (TALL format)            │
│  - One row per study-derivative pair              │
│  - Lead columns: study_id, derivative_id          │
│  - Detailed metrics per derivative                │
└────────────────────────────────────────────────────┘
```

## Entities

### 1. Study Dataset

**Purpose**: Represents a BIDS study folder (study-{id}) containing source and derivative datasets.

**Implementation**: `code/src/openneuro_studies/models/study.py`

**Fields**:

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| `study_id` | str | Yes | Unique identifier (e.g., "study-ds000001") | Must match pattern `^study-ds\d+$` |
| `name` | str | Yes | Human-readable study name | From dataset_description.json Name |
| `version` | str | No | Study dataset version (calendar-based) | Format: `0.YYYYMMDD.PATCH` |
| `raw_version` | str | No | Source dataset version/tag | "n/a" if multiple sources or no release |
| `title` | str | Yes | Full study title | Prefix: "Study dataset for {source title}" |
| `authors` | List[str] | Yes | Study dataset authors | From git shortlog of study dataset |
| `bids_version` | str | Yes | BIDS specification version | From source dataset_description.json |
| `hed_version` | str | No | HED schema version if applicable | From source dataset_description.json |
| `license` | str | No | Dataset license | Collated from sources |
| `source_datasets` | List[SourceDataset] | Yes | Raw datasets under sourcedata/ | At least 1 required |
| `derivative_datasets` | List[DerivativeDataset] | No | Processed datasets under derivatives/ | 0 or more |
| `github_url` | str | Yes | Published repository URL | Format: `https://github.com/{org}/study-{id}` |
| `datatypes` | List[str] | No | BIDS datatypes present | e.g., ["anat", "func"] |
| `state` | Enum | Yes | Processing state | discovered \| organized \| metadata_generated \| validated |

**Relationships**:
- **1-to-many** with SourceDataset: A study contains 1+ source datasets
- **1-to-many** with DerivativeDataset: A study contains 0+ derivative datasets

**State Transitions**:
```
discovered → organized → metadata_generated → validated
    ↓            ↓              ↓                 ↓
  (found)   (DataLad      (studies.tsv      (BIDS
           dataset+       generated)      validator
           submodules)                      run)
```

**Pydantic Model** (for implementation):

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, validator

class StudyState(str, Enum):
    DISCOVERED = "discovered"
    ORGANIZED = "organized"
    METADATA_GENERATED = "metadata_generated"
    VALIDATED = "validated"

class StudyDataset(BaseModel):
    study_id: str = Field(..., pattern=r"^study-ds\d+$")
    name: str
    version: Optional[str] = Field(None, pattern=r"^0\.\d{8}\.\d+$")
    raw_version: Optional[str] = "n/a"
    title: str
    authors: List[str]
    bids_version: str
    hed_version: Optional[str] = None
    license: Optional[str] = None
    source_datasets: List["SourceDataset"]
    derivative_datasets: List["DerivativeDataset"] = []
    github_url: str = Field(..., pattern=r"^https://github\.com/[\w-]+/study-ds\d+$")
    datatypes: List[str] = []
    state: StudyState

    @validator('source_datasets')
    def must_have_sources(cls, v):
        if not v:
            raise ValueError('Study must have at least one source dataset')
        return v
```

---

### 2. Source Dataset

**Purpose**: Represents a raw BIDS dataset from OpenNeuroDatasets, openfmri, or other configured sources.

**Implementation**: `code/src/openneuro_studies/models/source.py`

**Fields**:

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| `dataset_id` | str | Yes | Original dataset ID (e.g., "ds000001") | Must match pattern `^ds\d+$` |
| `url` | str | Yes | Git repository URL | Must be valid git URL |
| `commit_sha` | str | Yes | Specific commit to link | Must be 40-char hex SHA |
| `bids_version` | str | Yes | BIDS specification version | From dataset_description.json BIDSVersion |
| `license` | str | No | Dataset license | From dataset_description.json License |
| `authors` | List[str] | No | Dataset authors | From dataset_description.json Authors |
| `subjects_num` | int | No | Number of subjects | Extracted from participants.tsv or file listing |
| `sessions_num` | int | No | Total number of sessions | Counted from file structure |
| `sessions_min` | int | No | Minimum sessions per subject | "n/a" if single-session |
| `sessions_max` | int | No | Maximum sessions per subject | "n/a" if single-session |

**Relationships**:
- **Many-to-1** with StudyDataset: Multiple sources can belong to one study (rare, see multi-source derivatives)

**Pydantic Model**:

```python
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, validator

class SourceDataset(BaseModel):
    dataset_id: str = Field(..., pattern=r"^ds\d+$")
    url: HttpUrl
    commit_sha: str = Field(..., pattern=r"^[0-9a-f]{40}$")
    bids_version: str
    license: Optional[str] = None
    authors: Optional[List[str]] = []
    subjects_num: Optional[int] = None
    sessions_num: Optional[int] = None
    sessions_min: Optional[int] = None
    sessions_max: Optional[int] = None

    @validator('commit_sha')
    def validate_sha(cls, v):
        if len(v) != 40 or not all(c in '0123456789abcdef' for c in v):
            raise ValueError('commit_sha must be 40-character hex string')
        return v
```

---

### 3. Derivative Dataset

**Purpose**: Represents a processed dataset from OpenNeuroDerivatives or OpenNeuro derivatives.

**Implementation**: `code/src/openneuro_studies/models/derivative.py`

**Fields**:

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| `dataset_id` | str | Yes | Original derivative dataset ID | Pattern: `^ds\d+$` |
| `derivative_id` | str | Yes | Unique identifier for tracking | Format: `{tool_name}-{version}[-{uuid_prefix}]` |
| `tool_name` | str | Yes | Processing tool name | e.g., "fmriprep", "mriqc" |
| `version` | str | Yes | Tool version | Semantic version or date-based |
| `datalad_uuid` | str | Yes | DataLad dataset UUID | From .datalad/config |
| `uuid_prefix` | str | No | First 8 chars of UUID | For disambiguation when tool+version match |
| `size_stats` | Dict | No | Size statistics from git annex info | Keys: total_size, annexed_size, file_count |
| `execution_metrics` | Dict | No | Runtime metrics if available | From con-duct/duct monitoring |
| `source_datasets` | List[str] | Yes | IDs of source datasets processed | From SourceDatasets in dataset_description.json |
| `processed_raw_version` | str | No | Version of raw dataset when processed | For outdatedness calculation |
| `outdatedness` | int | No | Commits behind current raw version | 0 = up-to-date, >0 = outdated |

**Relationships**:
- **Many-to-many** with StudyDataset: A derivative can be linked to multiple studies (via tall table studies_derivatives.tsv)

**Disambiguation Logic**:
```python
def generate_derivative_id(tool_name: str, version: str, datalad_uuid: str,
                          existing_ids: List[str]) -> str:
    """
    Generate unique derivative_id.

    If tool_name-version already exists, append first 8 chars of UUID.
    """
    base_id = f"{tool_name}-{version}"
    if base_id not in existing_ids:
        return base_id

    uuid_prefix = datalad_uuid[:8]
    return f"{base_id}-{uuid_prefix}"
```

**Pydantic Model**:

```python
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class DerivativeDataset(BaseModel):
    dataset_id: str = Field(..., pattern=r"^ds\d+$")
    derivative_id: str
    tool_name: str
    version: str
    datalad_uuid: str
    uuid_prefix: Optional[str] = None
    size_stats: Optional[Dict[str, int]] = {}
    execution_metrics: Optional[Dict[str, float]] = {}
    source_datasets: List[str] = Field(..., min_items=1)
    processed_raw_version: Optional[str] = None
    outdatedness: Optional[int] = None

    @validator('datalad_uuid')
    def validate_uuid(cls, v):
        # DataLad UUIDs are 36-char UUID format
        if len(v) != 36:
            raise ValueError('datalad_uuid must be 36 characters')
        return v

    @validator('uuid_prefix', always=True)
    def extract_uuid_prefix(cls, v, values):
        if 'datalad_uuid' in values:
            return values['datalad_uuid'][:8]
        return None
```

---

### 4. Source Specification

**Purpose**: Configuration model defining dataset sources to discover.

**Implementation**: `code/src/openneuro_studies/config/models.py`

**Fields**:

| Field | Type | Required | Description | Validation |
|-------|------|----------|-------------|------------|
| `name` | str | Yes | Friendly name for source | e.g., "OpenNeuroDatasets" |
| `organization_url` | str | Yes | GitHub/Forgejo organization URL | Must be valid URL |
| `type` | Enum | Yes | Source type | "raw" \| "derivative" |
| `inclusion_patterns` | List[str] | No | Regex patterns for datasets to include | Default: [".*"] (all) |
| `exclusion_patterns` | List[str] | No | Regex patterns for datasets to exclude | Default: [] |
| `access_token_env` | str | No | Environment variable name for token | e.g., "GITHUB_TOKEN" |

**Example YAML** (`.openneuro-studies/config.yaml` at repository root):

```yaml
sources:
  - name: OpenNeuroDatasets
    organization_url: https://github.com/OpenNeuroDatasets
    type: raw
    inclusion_patterns:
      - "^ds\\d{6}$"  # Match ds000001 through ds999999
    access_token_env: GITHUB_TOKEN

  - name: OpenNeuroDerivatives
    organization_url: https://github.com/OpenNeuroDerivatives
    type: derivative
    inclusion_patterns:
      - "^ds\\d{6}$"
    access_token_env: GITHUB_TOKEN

  - name: OpenfMRI
    organization_url: https://github.com/openfmri
    type: raw
    inclusion_patterns:
      - ".*"
    access_token_env: GITHUB_TOKEN
```

**Pydantic Model**:

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, HttpUrl, Field

class SourceType(str, Enum):
    RAW = "raw"
    DERIVATIVE = "derivative"

class SourceSpecification(BaseModel):
    name: str
    organization_url: HttpUrl
    type: SourceType
    inclusion_patterns: List[str] = Field(default_factory=lambda: [".*"])
    exclusion_patterns: List[str] = Field(default_factory=list)
    access_token_env: Optional[str] = "GITHUB_TOKEN"

class SourcesConfiguration(BaseModel):
    sources: List[SourceSpecification]
```

---

### 5. Metadata Indices (TSV Files)

**Purpose**: Provide queryable tabular summaries of studies and derivatives.

#### studies.tsv (Wide Format - Study-Centric)

**Implementation**: `code/src/openneuro_studies/metadata/studies_tsv.py`

**Schema** (one row per study):

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `study_id` | str | Study identifier | Primary key |
| `name` | str | Study name | From dataset_description.json Name |
| `version` | str | Study dataset version | Managed release version |
| `raw_version` | str | Source dataset version | From git tags or "n/a" |
| `bids_version` | str | BIDS spec version | From source dataset_description.json |
| `hed_version` | str | HED schema version | From source or "n/a" |
| `license` | str | Dataset license | Collated from sources |
| `authors` | str | Comma-separated authors | From git shortlog |
| `subjects_num` | int | Number of subjects | From participants.tsv or file count |
| `sessions_num` | int | Total sessions | Counted from structure |
| `sessions_min` | int | Min sessions per subject | Or "n/a" if single-session |
| `sessions_max` | int | Max sessions per subject | Or "n/a" if single-session |
| `bold_num` | int | Number of BOLD files | From file count |
| `t1w_num` | int | Number of T1w files | From file count |
| `t2w_num` | int | Number of T2w files | From file count |
| `bold_size` | int | Total BOLD size (bytes) | Requires sparse access |
| `t1w_size` | int | Total T1w size (bytes) | Requires sparse access |
| `bold_size_max` | int | Largest BOLD file (bytes) | Requires sparse access |
| `bold_voxels` | str | BOLD dimensions | e.g., "64x64x40x200" |
| `datatypes` | str | Comma-separated datatypes | e.g., "anat,func" |
| `derivative_ids` | str | Comma-separated derivative IDs | e.g., "fmriprep-21.0.1,mriqc-23.0.0" |
| `bids_valid` | str | BIDS validation status | "pass" \| "fail" \| "warning" \| "n/a" |

**Companion Sidecar**: `studies.json` (JSON describing each column)

#### studies_derivatives.tsv (Tall Format - Derivative-Centric)

**Implementation**: `code/src/openneuro_studies/metadata/derivatives_tsv.py`

**Schema** (one row per study-derivative pair):

| Column | Type | Description | Source |
|--------|------|-------------|--------|
| `study_id` | str | Study identifier | Foreign key to studies.tsv |
| `derivative_id` | str | Derivative identifier | Unique within study |
| `dataset_id` | str | Original derivative dataset ID | e.g., "ds006185" |
| `tool_name` | str | Processing tool | e.g., "fmriprep" |
| `version` | str | Tool version | e.g., "21.0.1" |
| `datalad_uuid` | str | DataLad dataset UUID | From .datalad/config |
| `total_size` | int | Total dataset size (bytes) | From `git annex info` |
| `annexed_size` | int | Annexed content size (bytes) | From `git annex info` |
| `file_count` | int | Number of files | From `git annex info` |
| `execution_time` | float | Processing time (seconds) | From con-duct if available |
| `peak_memory` | int | Peak memory usage (MB) | From con-duct if available |
| `processed_raw_version` | str | Raw dataset version when processed | For outdatedness |
| `outdatedness` | int | Commits behind current | 0 = up-to-date |
| `status` | str | Processing status | "complete" \| "incomplete" \| "failed" |

**Companion Sidecar**: `studies_derivatives.json`

---

## Data Flows

### Discovery Flow
```
SourceSpecification (YAML)
    ↓ (discovery/dataset_finder.py)
List of discovered datasets
    ↓ (models/source.py, models/derivative.py)
SourceDataset + DerivativeDataset instances
```

### Organization Flow
```
SourceDataset + DerivativeDataset
    ↓ (organization/study_creator.py)
StudyDataset (state=discovered)
    ↓ (datalad create --no-annex)
study-{id}/ directory
    ↓ (organization/submodule_linker.py)
Git submodules for sources/derivatives
    ↓ (update state)
StudyDataset (state=organized)
```

### Metadata Generation Flow
```
StudyDataset (state=organized)
    ↓ (metadata/dataset_description.py)
study-{id}/dataset_description.json
    ↓ (metadata/studies_tsv.py)
studies.tsv (wide format)
    ↓ (metadata/derivatives_tsv.py)
studies_derivatives.tsv (tall format)
    ↓ (update state)
StudyDataset (state=metadata_generated)
```

### Validation Flow
```
StudyDataset (state=metadata_generated)
    ↓ (validation/bids_validator.py)
study-{id}/derivatives/bids-validator.json
study-{id}/derivatives/bids-validator.txt
    ↓ (update studies.tsv bids_valid column)
StudyDataset (state=validated)
```

---

## Implementation Notes

1. **Pydantic Models**: All entities should be implemented as Pydantic models for:
   - Type validation
   - JSON schema generation (for contracts/schemas.json)
   - Easy serialization/deserialization

2. **State Management**: Study state transitions should be explicit and validated:
   ```python
   def transition_state(study: StudyDataset, new_state: StudyState) -> StudyDataset:
       valid_transitions = {
           StudyState.DISCOVERED: [StudyState.ORGANIZED],
           StudyState.ORGANIZED: [StudyState.METADATA_GENERATED],
           StudyState.METADATA_GENERATED: [StudyState.VALIDATED],
       }
       if new_state not in valid_transitions.get(study.state, []):
           raise ValueError(f"Invalid transition: {study.state} → {new_state}")
       study.state = new_state
       return study
   ```

3. **TSV Writing**: Use pandas or csv module with explicit column ordering matching the schemas above.

4. **Missing Data**: Use "n/a" string for missing values in TSV files (per Constitution Metadata Completeness requirement).

5. **ID Generation**:
   - Study IDs: Extract from source dataset ID (e.g., ds000001 → study-ds000001)
   - Derivative IDs: Use tool-version pattern with UUID disambiguation when needed

---

## Validation Rules

1. **Study Dataset**:
   - Must have at least one source dataset
   - github_url must match configured organization
   - study_id must be unique across all studies

2. **Source Dataset**:
   - commit_sha must be valid git commit
   - url must be accessible (checked during discovery)

3. **Derivative Dataset**:
   - All source_datasets must exist in the collection
   - tool_name and version must be extractable from dataset_description.json

4. **Cross-Entity**:
   - studies.tsv derivative_ids must match actual derivatives linked
   - studies_derivatives.tsv rows must have corresponding study in studies.tsv
   - Outdatedness calculation only valid when processed_raw_version is known

---

## Constitution Alignment

✅ **Data Integrity & Traceability**: All entities include version/commit references
✅ **Standard Formats**: TSV/JSON with Pydantic models for schema validation
✅ **Observability**: Wide + tall tables enable comprehensive querying
✅ **Git/DataLad-First**: State transitions map to git commits
✅ **Automation**: Entities designed for programmatic generation, no manual fields

---

## Next Steps

This data model will be implemented in:
- `code/src/openneuro_studies/models/study.py`
- `code/src/openneuro_studies/models/source.py`
- `code/src/openneuro_studies/models/derivative.py`
- `code/src/openneuro_studies/config/models.py`

With corresponding tests in:
- `code/tests/unit/test_models.py`

The models will be used by all workflow modules (discovery, organization, metadata, validation) as defined in plan.md Phase 1.
