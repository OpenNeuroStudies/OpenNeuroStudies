# Spec-Code Alignment Plan

Date: 2025-12-18
Status: ✅ COMPLETE

## Summary

Analysis of spec (`specs/001-read-file-doc/spec.md`) vs current code implementation revealed several inconsistencies that have been resolved.

## Inconsistencies Found

### 1. Spec Internal Inconsistencies (sourcedata naming)

**Problem**: The spec contradicts itself regarding sourcedata directory naming:

- **User Story 1, Scenario 2** (line 21): Says `sourcedata/raw/` should be used for single-source raw datasets
- **User Story 2, Scenario 1** (line 39): References `sourcedata/raw/` for metadata generation
- **Key Entity "Source Dataset"** (line 149): Mentions both `sourcedata/raw/` and `sourcedata/{id}/`
- **FR-003d** (line 93): Explicitly states `sourcedata/raw/` MUST NOT be used, always use `sourcedata/{dataset_id}/`

**Code Status**: Code correctly implements FR-003d - uses `sourcedata/{dataset_id}/` (see `organization/__init__.py:260`)

**Resolution**: Update User Story scenarios and Key Entities to match FR-003d (the correct behavior)

### 2. Missing Features in Code

| Feature | Spec Reference | Code Status | Priority |
|---------|---------------|-------------|----------|
| Provision command | FR-041, FR-041a | ✅ Implemented (this session) | Done |
| Validation output in `derivatives/bids-validator/` | FR-015 | ✅ Implemented (this session) | Done |
| `--when` option for validation | FR-015 | ✅ Implemented (this session) | Done |
| `code/run-bids-validator` script | FR-040 | ✅ In provision template | Done |

### 3. Documentation Comments Still Reference Old Patterns

Several code files have docstrings/comments that reference `sourcedata/raw`:
- `submodule_linker.py:32,44,60,66,185` - Example comments
- `migrate.py:149,209,210,261` - Migration logic (correctly migrates old pattern)
- `studies_tsv.py:185` - Comment about source types

**Resolution**: Update docstrings for clarity, but migrate.py is correct (it handles legacy data)

### 4. Existing Study Datasets Need Provisioning

Current study datasets lack:
- `code/run-bids-validator` script
- `README.md`
- `.openneuro-studies/template-version` file

**Resolution**: Run `openneuro-studies provision` to add templated content

### 5. Old Validation Output Format

If any validation was run, outputs may be at old locations:
- Old: `derivatives/bids-validator.json`, `derivatives/bids-validator.txt`
- New: `derivatives/bids-validator/version.txt`, `derivatives/bids-validator/report.json`, `derivatives/bids-validator/report.txt`

**Resolution**: Create migration for old validation output format

## TODO List

### High Priority - Spec Consistency Fixes

1. ✅ **Fix User Story 1, Scenario 2** - Change `sourcedata/raw/` to `sourcedata/{dataset_id}/`
2. ✅ **Fix User Story 2, Scenario 1** - Change `sourcedata/raw/` to `sourcedata/{dataset_id}/`
3. ✅ **Fix Key Entity "Source Dataset"** - Remove reference to `sourcedata/raw/`

### Medium Priority - Code Documentation Fixes

4. ✅ **Update submodule_linker.py docstrings** - Change example paths from `sourcedata/raw` to `sourcedata/ds000001`

### Low Priority - Migration Support

5. ✅ **Add validation output migration** - Move old `derivatives/bids-validator.{json,txt}` to new location
6. ✅ **Add migration command for validation outputs** - Extend `migrate` command

### Template Development

7. ✅ **Add unit tests for provision functionality** - Test template output verification
8. ✅ **Create copier template** - Populate `templates/study/` with copier template files:
   - `copier.yaml` - Copier configuration with template variables
   - `code/run-bids-validator.jinja` - Validator script template
   - `README.md.jinja` - Study README template
   - `.openneuro-studies/template-version.jinja` - Version tracking
9. ✅ **Add integration tests for copier** - Test actual copier rendering works correctly (10 tests in `test_provision_copier.py`)

### Operations - Existing Dataset Updates

10. ✅ **Provision existing studies** - Run `openneuro-studies provision` on all study-* directories
11. ✅ **Re-run validation** - Run `openneuro-studies validate` to regenerate outputs in new location

## Implementation Order

```
Phase 1: Spec Fixes (items 1-3) ✅
  └── Update spec.md to be internally consistent

Phase 2: Code Documentation (item 4) ✅
  └── Update docstrings in submodule_linker.py

Phase 3: Migration (items 5-6) ✅
  └── Extend migrate command to handle validation output format

Phase 4: Template Development (items 7-9) ✅
  ├── Unit tests for provision output (item 7) ✅
  ├── Create copier template files (item 8) ✅
  └── Integration tests for copier (item 9) ✅

Phase 5: Operations (items 10-11) ✅
  └── Run provision and validate on existing studies ✅
```

## Current Implementation Status

**COMPLETE** - All TODOs have been implemented:

- Copier is now a **required dependency** (no inline template fallback - DRY principle)
- `templates/study/` contains copier template files
- All 7 existing studies have been provisioned and validated
- Validation outputs use native bids-validator text (not custom formatting)
- 10 integration tests verify copier template rendering

## Existing Studies Current State

| Study | sourcedata/ | derivatives/ | code/ | README | .openneuro-studies/ |
|-------|-------------|--------------|-------|--------|---------------------|
| study-ds000001 | ✅ ds000001/ | ✅ fMRIPrep-21.0.1/, MRIQC-0.16.1/, bids-validator/ | ✅ | ✅ | ✅ |
| study-ds005256 | ✅ ds005256/ | ✅ bids-validator/ | ✅ | ✅ | ✅ |
| study-ds006131 | ✅ ds006131/ | ✅ 4 derivatives + bids-validator/ | ✅ | ✅ | ✅ |
| study-ds006189 | ✅ 2 sources | ✅ 1 derivative + bids-validator/ | ✅ | ✅ | ✅ |
| study-ds006190 | ✅ 3 sources | ✅ 1 derivative + bids-validator/ | ✅ | ✅ | ✅ |
| study-ds006191 | ✅ 4 sources | ✅ custom-ds006191 + bids-validator/ | ✅ | ✅ | ✅ |
| study-ds006192 | ✅ 4 sources | ✅ xcp_d-0.10.6 + bids-validator/ | ✅ | ✅ | ✅ |

All studies use correct `sourcedata/{dataset_id}/` naming (FR-003d compliant).
All studies have been provisioned with template version 1.2.0.
