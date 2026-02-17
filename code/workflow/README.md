# OpenNeuroStudies Snakemake Workflow

This workflow extracts metadata from study datasets and aggregates them into `studies.tsv`. It uses **git SHA-based dependency tracking** to determine when recomputation is needed, rather than relying on file modification times.

## Quick Start

```bash
# From repository root (not code/)
cd /path/to/OpenNeuroStudies

# Run full workflow
snakemake -s code/workflow/Snakefile --cores 4

# Dry run - show what would be done
snakemake -s code/workflow/Snakefile -n

# Rerun based on git SHA changes (not just mtime)
snakemake -s code/workflow/Snakefile --rerun-triggers params --cores 4
```

## Directory Structure

```
code/workflow/
├── Snakefile              # Main workflow definition
├── README.md              # This file
├── lib/                   # Python utilities
│   ├── __init__.py
│   ├── git_utils.py       # Git SHA extraction functions
│   └── provenance.py      # Provenance management
├── rules/                 # Additional rule files (future)
└── scripts/               # Helper scripts
    └── clean_provenance.py
```

## Provenance Storage

Provenance is stored in `.snakemake/prov/` to avoid polluting the main file tree:

```
.snakemake/prov/
├── manifest.json                    # Index of all tracked outputs
├── studies.tsv.prov.json           # Provenance for studies.tsv
├── stats__.prov__study-ds000001.json.prov.json
└── ...
```

Each provenance file records:
- Git SHAs of dependencies (submodule commits, file blobs)
- Timestamps of computation
- History of updates

## Git SHA-based Dependencies

Unlike traditional Snakemake workflows that use file modification times, this workflow tracks dependencies via git object SHAs:

```python
# In Snakefile
rule extract_study:
    params:
        deps = lambda wc: {
            "study_sha": get_gitlink_sha(wc.study),      # Submodule commit
            "sourcedata_shas": get_sourcedata_shas(...), # Nested submodules
        }
```

This means:
- **Content-based**: Two identical states have the same SHA, regardless of mtime
- **Submodule-aware**: Tracks nested git submodules properly
- **Reproducible**: SHA captures exact version of dependencies

## Commands

### Run Workflow

```bash
# Full run
snakemake -s code/workflow/Snakefile --cores 4

# With git SHA-based rerun detection
snakemake -s code/workflow/Snakefile --rerun-triggers params --cores 4

# Force rerun of specific study
snakemake -s code/workflow/Snakefile --forcerun stats/.prov/study-ds000001.json

# Show what would be done
snakemake -s code/workflow/Snakefile -n --rerun-triggers params
```

### Utility Rules

```bash
# Show dependency SHAs for all studies
snakemake -s code/workflow/Snakefile show_deps

# Show provenance summary
snakemake -s code/workflow/Snakefile show_provenance

# Clean stale provenance entries
snakemake -s code/workflow/Snakefile clean_provenance
```

### Provenance Management

```bash
# Show provenance summary
python code/workflow/scripts/clean_provenance.py --summary

# Dry run - show what would be removed
python code/workflow/scripts/clean_provenance.py --dry-run

# Actually remove stale entries
python code/workflow/scripts/clean_provenance.py
```

## Integration with fsspec Plugins

The workflow can be extended with fsspec-based storage plugins for transparent remote file access:

```bash
# Install plugins (from code/snakemake-plugins/)
pip install -e code/snakemake-plugins/snakemake-storage-plugin-fsspec
pip install -e code/snakemake-plugins/snakemake-fsspec-resolver-gitannex
```

This enables:
- Reading NIfTI headers without downloading full files
- Streaming access to S3/HTTP URLs
- git-annex URL resolution for annexed files

## DAG Visualization

```bash
# Generate workflow DAG
snakemake -s code/workflow/Snakefile --dag | dot -Tpng > dag.png

# Generate rule graph (simplified)
snakemake -s code/workflow/Snakefile --rulegraph | dot -Tpng > rulegraph.png
```
