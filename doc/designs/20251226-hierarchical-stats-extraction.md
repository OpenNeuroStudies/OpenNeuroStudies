# Hierarchical Stats Extraction Plan

Date: 2025-12-26
Status: Planning

## Summary

Formalize a hierarchical approach to extracting dataset statistics at multiple levels:
- Per subject (+session if multi-session)
- Per sourcedata/derivative dataset
- Per study
- Across all studies

Stats are extracted at the lowest level and consolidated upward, enabling:
- Detailed per-subject analysis
- Consistent aggregation methodology
- Reusable stats that don't modify original datasets

## Key Design Decisions

### 1. Entity-Indexed TSV Files

Per [BIDS issue #2273](https://github.com/bids-standard/bids-specification/issues/2273), use `+` to join multiple entities in filenames:

```
study-ds000001/
├── sourcedata/
│   ├── ds000001/                    # Git submodule (unchanged)
│   ├── sourcedata+subjects.tsv      # Stats per subject across all sources
│   └── sourcedata+subjects.json     # Column descriptions
├── derivatives/
│   ├── fMRIPrep-21.0.1/             # Git submodule (unchanged)
│   ├── MRIQC-0.16.1/
│   ├── derivatives+subjects.tsv     # Stats per subject across all derivatives
│   └── derivatives+subjects.json
└── dataset_description.json
```

For multi-session datasets:
```
sourcedata+subjects+sessions.tsv     # One row per subject+session combination
```

### 2. File Locations

Stats files are stored **within the study dataset** but **outside the submodules**:
- `study-ds000001/sourcedata/sourcedata+subjects.tsv` (not in `sourcedata/ds000001/`)
- `study-ds000001/derivatives/derivatives+subjects.tsv` (not in `derivatives/fMRIPrep-21.0.1/`)

This ensures:
- Original datasets remain unmodified
- Stats are version-controlled with the study
- Clear hierarchy of aggregation

### 3. Consolidation Flow

```
                    Per-File Metrics
                          │
                          ▼
         sourcedata+subjects+sessions.tsv (if multi-session)
                          │
                          ▼
              sourcedata+subjects.tsv
                          │
                          ▼
    ┌─────────────────────┴─────────────────────┐
    │                                           │
    ▼                                           ▼
sourcedata+datasets.tsv              derivatives+datasets.tsv
    │                                           │
    └─────────────────────┬─────────────────────┘
                          ▼
                    studies.tsv (aggregated across studies)
```

## File Schemas

### sourcedata+subjects.tsv

One row per (source_dataset, subject) or (source_dataset, subject, session):

| Column | Description | Aggregation |
|--------|-------------|-------------|
| `source_id` | Sourcedata dataset ID (e.g., ds000001) | Index |
| `subject_id` | Subject ID (e.g., sub-01) | Index |
| `session_id` | Session ID if multi-session, else "n/a" | Index (optional) |
| `bold_num` | Number of BOLD files | Sum per subject |
| `t1w_num` | Number of T1w files | Sum per subject |
| `t2w_num` | Number of T2w files | Sum per subject |
| `bold_size` | Total BOLD size in bytes | Sum per subject |
| `t1w_size` | Total T1w size in bytes | Sum per subject |
| `bold_duration_total` | Total BOLD duration in seconds | Sum per subject |
| `bold_duration_mean` | Mean BOLD run duration | Mean per subject |
| `bold_voxels_total` | Total voxels across all BOLD | Sum per subject |
| `bold_voxels_mean` | Mean voxels per BOLD file | Mean per subject |
| `datatypes` | Datatypes present for this subject | Set union |

### sourcedata+datasets.tsv

One row per sourcedata dataset (aggregated from subjects):

| Column | Description | Aggregation |
|--------|-------------|-------------|
| `source_id` | Sourcedata dataset ID | Index |
| `subjects_num` | Number of subjects | Count |
| `sessions_num` | Total sessions | Sum |
| `sessions_min` | Min sessions per subject | Min |
| `sessions_max` | Max sessions per subject | Max |
| `bold_num` | Total BOLD files | Sum |
| `t1w_num` | Total T1w files | Sum |
| `bold_size` | Total BOLD size | Sum |
| `t1w_size` | Total T1w size | Sum |
| `bold_duration_total` | Total BOLD duration | Sum |
| `bold_duration_mean` | Mean BOLD duration (weighted) | Weighted mean |
| `bold_voxels_total` | Total BOLD voxels | Sum |
| `bold_voxels_mean` | Mean voxels (weighted by duration) | Weighted mean |
| `datatypes` | All datatypes present | Set union |

### derivatives+subjects.tsv

Similar structure to sourcedata, but for derivatives:

| Column | Description |
|--------|-------------|
| `derivative_id` | Derivative directory name (e.g., fMRIPrep-21.0.1) |
| `subject_id` | Subject ID |
| `session_id` | Session ID if applicable |
| `output_num` | Number of output files |
| `output_size` | Total output size |
| ... | (derivative-specific metrics) |

### studies.tsv Columns (Updated)

Aggregate from `sourcedata+datasets.tsv` and `derivatives+datasets.tsv`:

| Column | Source | Aggregation |
|--------|--------|-------------|
| `subjects_num` | sourcedata+datasets.tsv | Sum across sources |
| `sessions_num` | sourcedata+datasets.tsv | Sum across sources |
| `bold_num` | sourcedata+datasets.tsv | Sum across sources |
| `bold_size` | sourcedata+datasets.tsv | Sum across sources |
| `bold_duration_total` | sourcedata+datasets.tsv | Sum across sources |
| `bold_duration_mean` | sourcedata+datasets.tsv | Weighted mean by bold_num |
| `bold_voxels_total` | sourcedata+datasets.tsv | Sum across sources |
| `bold_voxels_mean` | sourcedata+datasets.tsv | Weighted mean by duration |
| ... | | |

## New Metrics

### BOLD Duration

Extracted from NIfTI headers:
- `TR` (repetition time) from header
- `n_volumes` (4th dimension) from shape
- `duration = TR * n_volumes`

```python
import nibabel as nib

def get_bold_duration(nifti_file) -> float:
    """Get BOLD run duration in seconds."""
    img = nib.load(nifti_file)
    tr = img.header.get_zooms()[3]  # 4th dimension is TR
    n_volumes = img.shape[3] if len(img.shape) > 3 else 1
    return tr * n_volumes
```

### Weighted Voxel Count

For aggregation, weight voxel counts by duration:

```python
bold_voxels_mean = sum(voxels_i * duration_i) / sum(duration_i)
```

This gives more weight to longer runs, which is more meaningful for fMRI analysis.

## Implementation Phases

### Phase 0: Schema Definition
- Define TSV schemas for each level
- Create JSON sidecar descriptions
- Add to spec.md

### Phase 1: Per-Subject Extraction
- Extract metrics for each subject in sourcedata
- Generate `sourcedata+subjects.tsv` within study
- Handle both single-session and multi-session datasets

### Phase 2: Dataset Aggregation
- Aggregate subject stats to `sourcedata+datasets.tsv`
- Implement weighted averaging for duration-weighted metrics

### Phase 3: Study Aggregation
- Update `studies.tsv` generation to use `sourcedata+datasets.tsv`
- Ensure consistent aggregation methodology

### Phase 4: Derivatives Support
- Extend to `derivatives+subjects.tsv`
- Handle derivative-specific metrics

### Phase 5: CLI Integration
- Add `--level` option to metadata command
- `metadata generate --level=subjects` for per-subject
- `metadata generate --level=datasets` for per-dataset
- `metadata generate --level=studies` for full aggregation

## File Generation Flow

```python
# 1. Extract per-subject stats
for study in studies:
    subjects_stats = []
    for source_dir in study.sourcedata:
        for subject in source_dir.glob("sub-*"):
            stats = extract_subject_stats(subject)
            subjects_stats.append(stats)

    write_tsv(study / "sourcedata" / "sourcedata+subjects.tsv", subjects_stats)

# 2. Aggregate to per-dataset
    datasets_stats = aggregate_subjects_to_datasets(subjects_stats)
    write_tsv(study / "sourcedata" / "sourcedata+datasets.tsv", datasets_stats)

# 3. Aggregate to study level (for studies.tsv)
    study_stats = aggregate_datasets_to_study(datasets_stats)
```

## Example Output

### sourcedata+subjects.tsv (study-ds000001)

```tsv
source_id	subject_id	session_id	bold_num	t1w_num	bold_size	bold_duration_total	bold_voxels_total	datatypes
ds000001	sub-01	n/a	3	1	145234567	720.0	12582912	anat,func
ds000001	sub-02	n/a	3	1	145678901	720.0	12582912	anat,func
ds000001	sub-03	n/a	3	1	144567890	720.0	12582912	anat,func
...
```

### sourcedata+datasets.tsv (study-ds000001)

```tsv
source_id	subjects_num	sessions_num	bold_num	t1w_num	bold_size	bold_duration_total	bold_duration_mean	bold_voxels_total	bold_voxels_mean	datatypes
ds000001	16	n/a	48	16	2319818025	11520.0	240.0	201326592	4194304	anat,func
```

## Dependencies

```python
# Add to pyproject.toml
[project.optional-dependencies]
imaging = [
    "datalad-fuse>=0.4.0",
    "fsspec>=2023.1.0",
    "nibabel>=5.0.0",
]
```

## Open Questions

1. **Session handling**: How to handle datasets where some subjects have sessions and others don't?
   - Recommendation: Use "n/a" for session_id when not applicable

2. **Multi-source studies**: How to aggregate across multiple source datasets?
   - Recommendation: Sum counts, weighted mean for averages

3. **Derivative metrics**: What metrics are meaningful for derivatives?
   - Recommendation: Start with output counts and sizes, add tool-specific later

4. **Caching**: Should per-subject stats be cached?
   - Recommendation: Yes, regenerate only when source changes

5. **Version tracking**: How to handle version changes in extraction logic?
   - Recommendation: Include extraction version in JSON sidecar

## Next Steps

1. Add new columns to spec.md (bold_duration_total, bold_duration_mean, bold_voxels_total, bold_voxels_mean)
2. Define TSV schemas for sourcedata+subjects.tsv and sourcedata+datasets.tsv
3. Implement per-subject extraction with duration calculation
4. Implement aggregation logic with weighted means
5. Update studies_tsv.py to use aggregated data
6. Add CLI support for `--level` option
