# TODO: Code Duplication - NIfTI Header Extraction

## Issue

The function `_extract_nifti_header_from_gzip_stream` is duplicated in two locations:

1. `code/src/bids_studies/extraction/subject.py:136`
   - Uses 1MB chunk size
   - Manual header parsing with `struct.unpack`
   - Called at line 229

2. `code/src/openneuro_studies/metadata/summary_extractor.py:387`
   - Uses 10KB chunk size
   - Uses nibabel for header parsing
   - Called at line 532

## Problems

### 1. Code Duplication
- Identical logic duplicated across two packages
- Maintenance burden: bug fixes must be applied twice
- Risk of divergence (already diverged: different chunk sizes, different parsing methods)

### 2. Potentially Unnecessary Manual Decompression
**User suggestion:** nibabel may be able to handle gzipped files directly, eliminating the need for manual `zlib` decompression.

Investigation needed:
- Check if `nibabel.load()` or `nibabel.Nifti1Header.from_filename()` can read directly from gzipped HTTP streams
- If yes, simplify implementation to just pass the stream to nibabel
- Example pattern from elsewhere (e.g., annextube project)?

### 3. "Too Short" Check May Skip Valid Files
Both implementations have:
```python
if len(gzip_data) < 100:
    logger.debug(f"Not enough data read: {len(gzip_data)} bytes")
    return None
```

**User concern:** Short NIfTI files (e.g., small volumes, single-slice images) might legitimately gzip to <100 bytes and be incorrectly skipped.

Investigation needed:
- What's the minimum size of a valid gzipped NIfTI header?
- Test with actual small NIfTI files from datasets
- Consider removing or lowering the threshold (e.g., >18 bytes for gzip header minimum)

## Resolution Path

### Phase 1: Consolidate
1. Move function to shared utility module (e.g., `code/src/openneuro_studies/lib/nifti_utils.py`)
2. Update both call sites to import from shared location
3. Standardize on single implementation (prefer nibabel-based version for consistency)

### Phase 2: Investigate Nibabel Direct Loading
1. Test if nibabel can read directly from:
   - Gzipped file-like objects
   - HTTP response streams
   - Partially-read streams
2. If yes: simplify implementation to delegate to nibabel
3. If no: document why manual decompression is necessary

### Phase 3: Fix "Too Short" Check
1. Determine minimum valid gzipped NIfTI size
2. Adjust or remove the 100-byte threshold
3. Add test case with small NIfTI file to prevent regression

## References

- Nibabel documentation: https://nipy.org/nibabel/
- NIfTI-1 format spec: https://nifti.nimh.nih.gov/nifti-1/
- User mentioned looking at annextube project for implementation patterns

## Status

- **Reported:** 2026-03-10
- **Priority:** Medium (code quality issue, not blocking functionality)
- **Assigned:** TBD

## Notes

User comment: "ask to provide details on how to be done elsewhere (annextube) but I found..."

User suggests reviewing annextube project for reference implementation of nibabel usage with gzipped streams.
