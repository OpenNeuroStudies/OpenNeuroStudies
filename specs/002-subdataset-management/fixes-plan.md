# Plan: Fix Metadata Extraction Issues

**Date:** 2026-03-04
**Issues:** studies.tsv n/a values, humanized sizes, processed_raw_version, JSON escaping

---

## Issue 1: studies.tsv lacks extracted stats in test

### Root Cause
**NOT A BUG** - Working as designed. The test called `generate_studies_tsv()` without explicitly passing `stage="imaging"`, so it defaulted to `stage="basic"` which only extracts:
- Author metadata (from dataset_description.json)
- Git version info
- Basic counts

The `stage="imaging"` extraction must be explicitly requested to get:
- BOLD file counts
- Voxel counts
- Timepoints
- Task lists

### Solution
**No code changes needed.** Documentation/test fix:

1. Update test script to pass `stage` parameter:
   ```python
   # Before
   generate_studies_tsv(studies, Path("studies.tsv"))

   # After
   generate_studies_tsv(studies, Path("studies.tsv"), stage="imaging")
   ```

2. Document in CLI help that `--stage=imaging` is required for BOLD metadata

---

## Issue 2: Size values are humanized instead of raw bytes

### Root Cause
`git annex info --json` returns humanized strings like "68.87 gigabytes" instead of raw byte counts.

### Solution
**File:** `code/src/openneuro_studies/metadata/derivative_extractor.py`

**Change 1:** Add `--bytes` flag (line 43-44)
```python
# Before
cmd_result = subprocess.run(
    ["git", "-C", str(derivative_path), "annex", "info", "--json"],
    capture_output=True,
    text=True,
    check=True,
)

# After
cmd_result = subprocess.run(
    ["git", "-C", str(derivative_path), "annex", "info", "--json", "--bytes"],
    capture_output=True,
    text=True,
    check=True,
)
```

**Change 2:** Update JSON parsing to handle numeric values (lines 54-61)
```python
# With --bytes, git-annex returns numbers instead of strings
# The JSON structure changes:
# Before: {"size of annexed files in working tree": "68.87 gigabytes"}
# After:  {"size of annexed files in working tree": 73954271232}

if "size of annexed files in working tree" in info:
    size_value = info["size of annexed files in working tree"]
    # With --bytes, this is already a number
    result["size_annexed"] = str(size_value) if isinstance(size_value, int) else size_value
```

**Verification needed:** Test with `git annex info --json --bytes` to confirm exact JSON structure.

---

## Issue 3: processed_raw_version is n/a

### Root Cause
Current implementation only checks `dataset_description.json` SourceDatasets.Version field, which:
1. Often doesn't exist in derivatives
2. When it exists, often contains URLs not versions
3. No fallback mechanism

### Solution
Implement UUID-based matching to find which sourcedata version was processed.

**File:** `code/src/openneuro_studies/metadata/derivative_extractor.py`

**New helper function:**
```python
def _get_dataset_uuid(path: Path) -> Optional[str]:
    """Get DataLad dataset UUID without full installation.

    Args:
        path: Path to dataset (can be uninitialized)

    Returns:
        UUID string or None if not a DataLad dataset
    """
    # Try reading .datalad/config file directly
    config_path = path / ".datalad" / "config"
    if config_path.exists():
        try:
            import configparser
            config = configparser.ConfigParser()
            config.read(config_path)
            if config.has_option("datalad.dataset", "id"):
                return config.get("datalad.dataset", "id")
        except Exception as e:
            logger.debug(f"Could not parse .datalad/config at {path}: {e}")

    # Fallback: try git config (works for initialized subdatasets)
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(path), "config", "datalad.dataset.id"],
            capture_output=True,
            text=True,
            check=False,
        )
        if cmd_result.returncode == 0:
            return cmd_result.stdout.strip()
    except Exception:
        pass

    return None


def _extract_processed_version_from_derivative_sourcedata(
    derivative_path: Path,
    raw_path: Path,
) -> str:
    """Extract the version of raw data that was processed.

    Strategy:
    1. Get UUID of the raw dataset
    2. Find matching UUID in derivative's sourcedata/
    3. Extract version from that subdataset

    Args:
        derivative_path: Path to derivative dataset
        raw_path: Path to raw sourcedata dataset

    Returns:
        Git version string or "n/a"
    """
    # Get raw dataset UUID
    raw_uuid = _get_dataset_uuid(raw_path)
    if not raw_uuid:
        logger.debug(f"Could not get UUID for raw dataset {raw_path}")
        return "n/a"

    # Check derivative's sourcedata/ for matching UUID
    deriv_sourcedata = derivative_path / "sourcedata"
    if not deriv_sourcedata.exists():
        return "n/a"

    for source_dir in deriv_sourcedata.iterdir():
        if not source_dir.is_dir() or source_dir.name.startswith("."):
            continue

        source_uuid = _get_dataset_uuid(source_dir)
        if source_uuid == raw_uuid:
            # Found matching dataset - get its version
            # Try git describe first
            try:
                cmd_result = subprocess.run(
                    ["git", "-C", str(source_dir), "describe", "--always"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                version = cmd_result.stdout.strip()
                if version:
                    return version
            except subprocess.CalledProcessError:
                pass

            # Fallback: use current commit SHA
            try:
                cmd_result = subprocess.run(
                    ["git", "-C", str(source_dir), "rev-parse", "--short", "HEAD"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return cmd_result.stdout.strip()
            except subprocess.CalledProcessError:
                pass

    return "n/a"
```

**Update extract_version_tracking():**
```python
def extract_version_tracking(
    derivative_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    """Extract version tracking metadata."""

    # Try 1: Check dataset_description.json SourceDatasets.Version
    processed_version = "n/a"
    dd_path = derivative_path / "dataset_description.json"

    if dd_path.exists():
        try:
            with open(dd_path) as f:
                dd = json.load(f)
                sources = dd.get("SourceDatasets", [])
                if sources and isinstance(sources, list):
                    first_source = sources[0]
                    if isinstance(first_source, dict):
                        processed_version = first_source.get("Version", "n/a")
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.debug(f"Could not parse dataset_description.json: {e}")

    # Try 2: If still n/a, check derivative's sourcedata/ for UUID match
    if processed_version == "n/a":
        processed_version = _extract_processed_version_from_derivative_sourcedata(
            derivative_path, raw_path
        )

    # Get current version from raw dataset
    current_version = "n/a"
    try:
        cmd_result = subprocess.run(
            ["git", "-C", str(raw_path), "describe", "--always"],
            capture_output=True,
            text=True,
            check=True,
        )
        current_version = cmd_result.stdout.strip()
    except subprocess.CalledProcessError:
        logger.debug(f"Could not get git describe for {raw_path}")

    # Calculate uptodate and outdatedness
    # ... (rest of function unchanged)
```

**Edge case:** If derivative's sourcedata/ subdataset is not initialized, we may need to temporarily install it:
```python
# After checking all uninitialized subdatasets
if processed_version == "n/a" and deriv_sourcedata.exists():
    # Try installing one sourcedata subdataset temporarily
    for source_dir in deriv_sourcedata.iterdir():
        if not source_dir.is_dir():
            continue

        ds = Dataset(str(source_dir))
        if not ds.is_installed():
            # Install temporarily
            newly_installed = _ensure_derivative_installed(source_dir, derivative_path)
            if newly_installed:
                # Check UUID and extract version
                source_uuid = _get_dataset_uuid(source_dir)
                if source_uuid == raw_uuid:
                    processed_version = _get_git_version(source_dir)
                    if processed_version != "n/a":
                        # Drop the temporarily installed subdataset
                        _drop_derivative(source_dir, derivative_path)
                        break
```

---

## Issue 4: descriptions column has Python repr formatting

### Root Cause
Python's `csv.DictWriter` with default quoting (`QUOTE_MINIMAL`) wraps the JSON string in quotes and escapes internal quotes by doubling them.

Result: `"{""MELODIC"":48,...}"` instead of `{"MELODIC":48,...}`

### Solution
**File:** `code/src/openneuro_studies/metadata/studies_plus_derivatives_tsv.py`

**Change:** Disable quoting for TSV output (lines 397-400)
```python
# Before
with open(output_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=STUDIES_DERIVATIVES_COLUMNS, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)

# After
with open(output_path, "w", newline="") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=STUDIES_DERIVATIVES_COLUMNS,
        delimiter="\t",
        quoting=csv.QUOTE_NONE,    # Don't quote any fields
        escapechar="\\"             # Use backslash for escaping special chars
    )
    writer.writeheader()
    writer.writerows(rows)
```

**Additional fix in derivative_extractor.py** (line 613):
Ensure JSON string properly escapes tabs and newlines for TSV:
```python
# Before
return json.dumps(result_dict, separators=(",", ":"))

# After
json_str = json.dumps(result_dict, separators=(",", ":"))
# Escape tabs and newlines for TSV safety
return json_str.replace("\\t", "\\\\t").replace("\\n", "\\\\n").replace("\t", "\\t").replace("\n", "\\n")
```

Actually, simpler approach - JSON shouldn't contain literal tabs/newlines, only `\t` and `\n` escape sequences which are already escaped by `json.dumps()`.

**Verification:** The `json.dumps()` already handles escaping, so we just need to prevent CSV from adding extra quotes.

---

## Implementation Order

1. **Issue 4 (easiest):** Add `quoting=csv.QUOTE_NONE` to CSV writer
2. **Issue 2 (simple):** Add `--bytes` flag to git-annex info
3. **Issue 1 (test fix):** Update test script to pass `stage="imaging"`
4. **Issue 3 (complex):** Implement UUID-based version tracking

---

## Testing Plan

### Unit Tests
```python
# test_derivative_extractor.py

def test_git_annex_info_bytes():
    """Verify --bytes flag returns numeric values."""
    # Mock git annex info --json --bytes output
    # Verify parsing handles numbers correctly

def test_get_dataset_uuid():
    """Test UUID extraction without installation."""
    # Test with initialized subdataset
    # Test with uninitialized subdataset
    # Test with non-DataLad directory

def test_extract_processed_version():
    """Test version extraction from derivative sourcedata."""
    # Create test derivative with sourcedata/raw subdataset
    # Mock UUID matching
    # Verify version extraction
```

### Integration Tests
```bash
# Test with real derivatives
cd /tmp/OpenNeuroStudies-test-clone

# Re-run extraction with stage=imaging
python3 -c "
from pathlib import Path
from openneuro_studies.metadata.studies_tsv import generate_studies_tsv
studies = [Path('study-ds000001'), Path('study-ds006131')]
generate_studies_tsv(studies, Path('studies.tsv'), stage='imaging')
"

# Verify results
grep "^study-ds000001" studies.tsv | cut -f19,20,21,27
# Should show: bold_num, bold_timepoints, bold_tasks, bold_voxels with real values

grep "^study-ds006131" studies+derivatives.tsv | cut -f7,8,10
# Should show: numeric sizes, processed_raw_version with actual git SHA
```

---

## Files to Modify

1. `code/src/openneuro_studies/metadata/derivative_extractor.py`
   - Add `--bytes` flag (line 43)
   - Update size parsing (lines 54-61)
   - Add `_get_dataset_uuid()` helper
   - Add `_extract_processed_version_from_derivative_sourcedata()` helper
   - Update `extract_version_tracking()` (lines 87-174)

2. `code/src/openneuro_studies/metadata/studies_plus_derivatives_tsv.py`
   - Add `quoting=csv.QUOTE_NONE, escapechar="\\"` (lines 397-400)

3. `/tmp/test_sample_clone_final.sh`
   - Add `stage="imaging"` parameter to `generate_studies_tsv()` call

4. `code/tests/unit/test_derivative_extractor.py`
   - Add tests for new UUID matching logic
   - Add tests for --bytes flag handling

---

## Expected Results After Fixes

### studies.tsv
```
study_id         bold_num  bold_voxels  bold_timepoints  bold_tasks
study-ds000001   48        139264       14400            balloonanalogrisktask
study-ds006131   480       871200       144600           bao,rat,rest
```

### studies+derivatives.tsv
```
derivative_id     size_annexed      processed_raw_version  descriptions
fMRIPrep-21.0.1   73954271232       f8e27ac                {"MELODIC":48,"about":16}
ASLPrep-0.7.5     2457862144        9a71adf4b              {"basil":506,"brain":77}
```
(No quotes around JSON, numeric bytes, actual git SHAs)
