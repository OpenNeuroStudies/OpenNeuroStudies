# Imaging Stage Duplication Issue

**Date**: 2026-03-14
**Status**: Mitigated (immediate fix applied), proper fix needed

## Problem

Hierarchical sourcedata TSV files (`study-*/sourcedata/sourcedata+*.tsv`) have `n/a` for imaging columns (`bold_voxels_total`, `bold_voxels_mean`, `bold_duration_total`, `bold_duration_mean`) even though Snakemake extraction ran with `include_imaging=True`.

### Root Cause

`make metadata` runs two targets sequentially that BOTH generate hierarchical TSVs:

1. **`extract`** (Snakemake):
   - `code/workflow/Snakefile` line 193-198
   - Calls `extract_study_stats(study_path, include_imaging=True, write_files=True)`
   - Creates TSVs **with** imaging data ✅

2. **`derivatives-tsv`** (CLI):
   - `Makefile` line 94: `openneuro-studies metadata generate --derivatives-tsv study-*`
   - Defaults to `--stage sizes` (not `imaging`)
   - `cli/main.py` line 348: `default="sizes"`
   - Calls `extract_study_stats(study_path, include_imaging=False, write_files=True)`
   - **Overwrites** TSVs **without** imaging data ❌

The second step overwrites the first step's work.

## Immediate Mitigation (Applied)

**File**: `Makefile` line 94
**Change**: Add `--stage imaging` to `derivatives-tsv` target

```diff
 derivatives-tsv:
-	openneuro-studies metadata generate --derivatives-tsv study-*
+	openneuro-studies metadata generate --derivatives-tsv --stage imaging study-*
```

This ensures both Snakemake and CLI run with imaging enabled.

**To verify the fix works:**
```bash
make metadata CORES=4
head -2 study-ds002766/sourcedata/sourcedata+subjects+sessions.tsv
# Should now show values (not n/a) for bold_voxels_total, bold_duration_total, etc.
```

## Proper Fix (Long-term)

The architecture has duplication — both Snakemake workflow and CLI `metadata generate` regenerate hierarchical sourcedata TSVs. This is inefficient and error-prone.

### Option A: Make Snakemake Do Everything (Recommended)

**Approach**: Extend Snakemake workflow to also handle derivative TSVs.

**Changes needed**:
1. Add derivative extraction to Snakefile's `extract_study` rule (already done at line 200-224)
2. Remove hierarchical TSV generation from CLI `metadata generate`
3. CLI becomes a thin wrapper: `openneuro-studies metadata generate` → just calls Snakemake
4. Update Makefile:
   ```makefile
   metadata-tsv: studies-tsv derivatives-tsv
   # becomes:
   metadata-tsv: studies-tsv
   # (derivatives-tsv is now part of extract, no separate CLI call needed)
   ```

**Benefits**:
- Single source of truth (Snakemake)
- SHA-based dependency tracking for ALL extractions (sourcedata + derivatives)
- No duplication
- Faster (only runs when SHAs change)

**Implementation**:
The Snakefile already handles derivative extraction (lines 200-224). We just need to:
1. Remove sourcedata TSV generation from `cli/main.py` `metadata_generate()`
2. Make the CLI command delegate to Snakemake for extraction

### Option B: Make CLI Skip Sourcedata When Only Derivatives Requested

**Approach**: Add logic to skip sourcedata TSV regeneration when `--derivatives-tsv` is specified.

**Changes needed**:
1. In `cli/main.py` `metadata_generate()`:
   ```python
   # Only regenerate sourcedata TSVs if NOT derivatives-only
   if stage in ("counts", "sizes", "imaging") and not (derivatives_tsv and not studies_tsv):
       # extract_study_stats() here
   ```

2. Update flag help text to clarify:
   ```python
   @click.option(
       "--derivatives-tsv/--no-derivatives-tsv",
       help="Generate ONLY studies+derivatives.tsv (skips sourcedata TSV regeneration)"
   )
   ```

**Benefits**:
- Quick fix
- Preserves existing CLI interface

**Drawbacks**:
- Still has duplication in code
- Sourcedata and derivatives extraction happen in different places
- No SHA-based dependency tracking for CLI path

## Recommendation

Use **Option A** — consolidate all extraction into Snakemake. The infrastructure is already there (Snakefile lines 160-224 handle both sourcedata and derivatives). The CLI should become a convenience wrapper that invokes Snakemake.

This aligns with the project's direction of using Snakemake for dependency-aware extraction.

## Files Involved

### Modified (immediate fix)
- `Makefile` line 94

### For proper fix (Option A)
- `code/src/openneuro_studies/cli/main.py` — remove hierarchical TSV generation from `metadata_generate()`
- `Makefile` — simplify `metadata-tsv` target
- `code/workflow/Snakefile` — already handles both (no changes needed)

### For proper fix (Option B)
- `code/src/openneuro_studies/cli/main.py` — add conditional to skip sourcedata when derivatives-only

## Testing

After immediate fix:
```bash
# 1. Clean previous run
rm study-ds002766/sourcedata/sourcedata+*.tsv

# 2. Run full metadata generation
make metadata CORES=4

# 3. Verify imaging columns are populated
python3 -c "
import csv
with open('study-ds002766/sourcedata/sourcedata+subjects+sessions.tsv') as f:
    rows = list(csv.DictReader(f, delimiter='\t'))
    for r in rows[:3]:
        print(f\"{r['subject_id']} {r['session_id']}: \", end='')
        print(f\"voxels={r['bold_voxels_total']} duration={r['bold_duration_total']}\")
        assert r['bold_voxels_total'] != 'n/a', 'Imaging data still missing!'
"
```

## References

- Initial hierarchical extraction implementation: commit 5bcdd97
- Snakemake workflow with subdataset management: Snakefile lines 160-203
- CLI metadata generate: `cli/main.py:320-520`
