# Dependency Tracking for Tabular Metadata

**Date**: 2026-02-17
**Status**: Design explored, prototype implemented

## Problem

`studies.tsv` is a wide-format table where each row is a study and columns are
extracted at different times from different sources:

- Some columns come from GitHub API (name, version, bids_version, license, authors)
- Some come from git tree traversal (subjects_num, bold_num, ...)
- Some come from annex key parsing (bold_size, ...)
- Some come from sparse HTTP streaming (bold_voxels, bold_duration)

Each row depends on one or more **git submodules** pointing to specific commits.
When a submodule is updated (new data, new BIDS version), only the affected rows
should be recomputed — not the whole table.

The challenge: git does not preserve file mtimes on checkout, so standard
make/mtime-based dependency tools don't work here.

## Key Insight: Git Tree SHAs as Content Checksums

Git already computes content-based checksums for everything:

```
# SHA of the submodule commit ("gitlink")
git ls-tree HEAD study-ds000001
→ 160000 commit 8a9d02a5c069...  study-ds000001

# SHA of a nested submodule (sourcedata dataset)
git -C study-ds000001 ls-tree HEAD sourcedata/ds000001
→ 160000 commit f8e27ac909e5...  sourcedata/ds000001

# SHA of a directory tree (content-addressable)
git rev-parse HEAD:study-ds000001
→ abc123...
```

Two trees with identical contents always have the same SHA. If a submodule
SHA hasn't changed, its rows don't need recomputation.

## Tools Evaluated

### pydoit
- MD5-based file tracking, custom `uptodate` callables
- **Rejected**: Inactive since 2022 (v0.36.0, no commits since)
- Could theoretically be adapted but maintenance risk is too high

### Hamilton
- DAG from Python functions, column-level lineage tracking
- **Rejected**: Oriented toward dataframe transformations, not external
  data dependencies. Would need significant wrapping.

### DVC
- Content-addressable cache for large files, pipeline caching
- **Rejected**: Designed for ML model artifacts and large binary files,
  not tabular metadata with per-row git submodule dependencies

### Make + git-restore-mtime
- `git restore-mtime` sets file mtimes to last-commit time
- Make then uses mtimes for dependency checking
- **Rejected**: Requires restoring mtimes after every checkout, fragile
  in CI. Symlinks (git-annex) have additional complications.

### Snakemake (chosen)
- Popular Python workflow manager, active development
- **Key feature**: `--rerun-triggers params` — Snakemake stores rule params
  in `.snakemake/metadata/` and reruns rules when params change
- This enables arbitrary Python functions as dependency checksums

## Snakemake Approach

### Core Mechanism

```python
rule extract_study:
    output: "stats/.prov/{study}.json"
    params:
        # These git SHAs are stored by Snakemake in .snakemake/metadata/
        # and compared on every subsequent run.
        deps = lambda wc: {
            "study_sha": get_gitlink_sha(wc.study),
            "sourcedata_shas": get_sourcedata_shas(wc.study),
        }
    run:
        result = extract_all_summaries(Path(wildcards.study), stage="imaging")
        ...
```

```bash
# First run: extract everything
snakemake -s code/workflow/Snakefile --cores 4

# Subsequent runs: only rerun rows whose git SHAs changed
snakemake -s code/workflow/Snakefile --rerun-triggers params --cores 4
```

### Provenance Storage

Stored in `.snakemake/prov/` (not the main file tree) to avoid clutter:

```
.snakemake/prov/
├── manifest.json                              # index of all tracked outputs
├── stats__.prov__study-ds000001.json.prov.json
└── studies-extracted.tsv.prov.json           # full dependency tree for aggregate
```

Each file records the git SHAs at time of computation and a history of updates.

### Cleanup of Stale Provenance

```bash
python code/workflow/scripts/clean_provenance.py --summary
python code/workflow/scripts/clean_provenance.py --dry-run
python code/workflow/scripts/clean_provenance.py
```

## Canonical vs. Workflow TSV

**Important**: The Snakemake workflow does NOT write to `studies.tsv`.

| File | Managed by | Contains |
|------|-----------|----------|
| `studies.tsv` | `openneuro-studies metadata generate` | All columns including GitHub API columns, bold_voxels, bids_valid, derivative_ids |
| `stats/studies-extracted.tsv` | Snakemake workflow | Columns extractable without GitHub API: author_lead_raw, subjects_num, bold_size, etc. |
| `stats/.prov/{study}.json` | Snakemake workflow | Per-study intermediate with provenance embedded |

The eventual goal is for `openneuro-studies metadata generate` to delegate to the
Snakemake workflow and merge results into `studies.tsv`, preserving columns it
doesn't compute.

## fsspec + Snakemake for Remote Streaming

A parallel exploration looked at how to avoid downloading full NIfTI files when
only the header is needed (for bold_voxels, bold_duration extraction).

### nibabel + fsspec

`nibabel.Nifti1Image.from_stream(f)` accepts any file-like object. An fsspec
file opened with `cache_type='blockcache'` fetches only the byte ranges
requested, so reading a header from a 500MB `.nii.gz` costs ~1-2MB of network
traffic.

```python
url = get_annex_url(repo, file_path)  # git annex whereis --json
with fsspec.open(url, 'rb', cache_type='blockcache') as f:
    img = nib.Nifti1Image.from_stream(f)  # only fetches header bytes
    shape = img.header.get_data_shape()
```

This is already partially implemented in `bids_studies/sparse/access.py`
(`SparseDataset.open_file()` returns an fsspec handle from git-annex URLs).
The current `summary_extractor.py` uses manual gzip+struct parsing instead of
nibabel because the latter was not fully tested at the time — this should be
cleaned up.

### Plugin Architecture (planned, not implemented)

Two Snakemake plugins are stubbed out under `code/snakemake-plugins/`:

**`snakemake-storage-plugin-fsspec`**
Implements the Snakemake 8+ `StorageProviderBase` interface. Opens remote files
via fsspec instead of downloading them. Pluggable URL resolvers allow different
backends.

**`snakemake-fsspec-resolver-gitannex`**
Resolver that translates local annexed file paths to remote HTTPS URLs via
`git annex whereis --json`. Supports batch mode for efficiency.

Relationship to **datalad-mihextras x-snakemake**:
- datalad-mihextras monkeypatches Snakemake to call `datalad get` before file
  access — i.e., it fully downloads files
- Our plugins would instead open files via fsspec for streaming/partial access
- We could either contribute upstream to datalad-mihextras or maintain these
  as a standalone package

## Current Implementation Location

```
code/
├── workflow/
│   ├── Snakefile              # Main workflow (run from repo root)
│   ├── lib/
│   │   ├── git_utils.py       # get_gitlink_sha, get_sourcedata_shas, get_tree_sha
│   │   └── provenance.py      # ProvenanceManager, clean_stale_provenance
│   └── scripts/
│       └── clean_provenance.py
└── snakemake-plugins/
    ├── snakemake-storage-plugin-fsspec/    # stub, not yet published
    └── snakemake-fsspec-resolver-gitannex/ # stub, not yet published
```

## Next Steps

1. **Integrate workflow with `openneuro-studies metadata generate`**: the CLI
   command should optionally delegate to Snakemake and merge results, rather
   than maintaining two separate extraction paths.

2. **Switch bold_voxels extraction to nibabel.from_stream**: replace the manual
   gzip+struct parsing in `summary_extractor.py` with `nib.Nifti1Image.from_stream()`.

3. **Publish plugins**: once the storage plugin is functional, publish to PyPI
   and submit to the Snakemake plugin catalog for community use.

4. **Evaluate Snakemake 8 upgrade**: the current prototype uses Snakemake 7.32.4
   (only version compatible without dependency conflicts). Snakemake 8 has a
   proper plugin interface that avoids needing the `snakemake-interface-storage-plugins`
   compatibility shims.

## Running the Workflow

```bash
# From repository root
snakemake -s code/workflow/Snakefile --cores 4               # full run
snakemake -s code/workflow/Snakefile -n                       # dry run
snakemake -s code/workflow/Snakefile --rerun-triggers params  # SHA-based rerun
snakemake -s code/workflow/Snakefile show_deps --cores 1      # show current SHAs
snakemake -s code/workflow/Snakefile show_provenance --cores 1
```
