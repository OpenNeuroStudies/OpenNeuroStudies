# Fix Sparse Access for S3 Special Remotes

**Date**: 2026-04-08
**Status**: In Progress
**Authors**: Claude

## Summary

Metadata extraction takes 17+ hours and incorrectly reports "No remote URL found"
for files that ARE publicly accessible on S3. The root cause is that
`_get_remote_url()` only looks for explicitly registered per-file URLs, but
S3 special remotes (like `s3-PUBLIC`) don't register per-file URLs.

## Problem Statement

### Symptoms
1. `make metadata CORES=4` takes ~17 hours wall clock
2. 4 datasets report "No remote URL found" despite files being publicly accessible:
   - ds000113: 3814 failed files
   - ds001499: 2970 failed files
   - ds001506: 1190 failed files (study-level failure)
   - ds006623: 1975 failed files
3. Total: ~9,000+ wasted retry attempts with 15s exponential backoff each

### Root Causes

**1. `_get_remote_url()` doesn't understand S3 special remotes**

The function only checks `remote["urls"]` from `git annex whereis --json`:
```python
for remote in data.get("whereis", []):
    for url in remote.get("urls", []):  # ALWAYS EMPTY for S3 remotes!
        if url.startswith("http"):
            return str(url)
```

S3 special remotes with `exporttree: yes` store files by path, and URLs must
be constructed from the remote's `publicurl` configuration.

Proof that URLs work:
```
$ curl -sI "https://s3.amazonaws.com/openneuro.org/ds000113/sub-01/.../bold.nii.gz"
HTTP/1.1 200 OK
```

**2. `FsspecAdapter` from datalad-fuse is not available**

```python
>>> from datalad_fuse import FsspecAdapter
ImportError: cannot import name 'FsspecAdapter'
```

The code falls through to `_open_via_whereis()` which is the broken path.

**3. `FileNotFoundError` incorrectly retried as network error**

`FileNotFoundError` is a subclass of `OSError`, so the retry decorator treats
it as a transient network error:
```python
if isinstance(error, (OSError, TimeoutError)):
    return True  # FileNotFoundError matches!
```

This wastes 15 seconds per file (1s + 2s + 4s + 8s backoff).

**4. No dependency tracking in Makefile** (partially fixed)

`derivatives-tsv` was a PHONY target that always re-ran. Fixed in commit 7286a36
but the CLI commands themselves still unconditionally reprocess all studies.

## Time Breakdown (from duct logs, March 21 run)

| Phase | Duration | Details |
|-------|----------|---------|
| Snakemake extract (run 1, 10 studies) | ~2h | Parallel, CORES=4 |
| Snakemake extract (run 2, 31 studies) | ~2h | Parallel, CORES=4 |
| dataset_description.json | ~1s | Fast, just writing JSON |
| studies.tsv generation | ~4.5h | Sequential, 41 studies |
| Hierarchical sourcedata stats | ~5h | Sequential, 41 studies |
| Hierarchical derivative stats | ~2h | Sequential, 34 derivatives |
| studies+derivatives.tsv | ~1s | Just merging TSVs |
| **Total** | **~17h** | |

Top 5 slowest studies (Snakemake phase):
- ds003097: 118 min
- ds005165: 80 min
- ds002785: 63 min
- ds003604: 46 min
- ds002790: 45 min

## Datasets with "No remote URL" Claims

| Dataset | File path | git-annex remotes | Accessible? |
|---------|-----------|-------------------|-------------|
| ds000113 | sub-01/ses-auditoryperception/func/sub-01_ses-auditoryperception_task-auditoryperception_run-01_bold.nii.gz | s3-PUBLIC (3 copies) | YES |
| ds001499 | sub-CSI1/ses-01/func/sub-CSI1_ses-01_task-5000scenes_run-01_bold.nii.gz | s3-PUBLIC (3 copies) | YES |
| ds001506 | sub-01/ses-imagery01/func/sub-01_ses-imagery01_task-imagery_run-01_bold.nii.gz | s3-PUBLIC (3 copies) | YES |
| ds006623 | sub-02/func/sub-02_task-imagery_run-1_bold.nii.gz | OpenNeuro (1 copy) | YES |

All files are publicly accessible at: `https://s3.amazonaws.com/openneuro.org/{dataset_id}/{path}`

## Proposed Fixes

### Fix 1: Construct S3 URLs from special remote config

In `_get_remote_url()`, after checking registered URLs, check for S3 special
remotes with `publicurl` and `exporttree: yes`:

```python
# After checking whereis URLs, try S3 special remotes
result = subprocess.run(
    ["git", "-C", str(self.path), "annex", "info", "--json"],
    capture_output=True, text=True, check=True
)
# Parse trusted/semitrusted remotes, find ones with type=S3 + publicurl
# Construct URL as: {publicurl}/{path}
```

### Fix 2: Don't retry FileNotFoundError from URL lookup

In `retry.py`, exclude `FileNotFoundError` from retryable errors:

```python
if isinstance(error, (OSError, TimeoutError)):
    # FileNotFoundError means the URL genuinely doesn't exist - don't retry
    if isinstance(error, FileNotFoundError):
        return False
    return True
```

### Fix 3: Cache remote info per dataset

Don't call `git annex info` for every file. Cache the S3 publicurl per
SparseDataset instance.

## Success Criteria

1. `make metadata CORES=4` completes in < 4 hours (down from 17h)
2. No "No remote URL" errors for datasets with S3 special remotes
3. Imaging metrics extracted for ds000113, ds001499, ds001506, ds006623
4. All existing tests continue to pass
