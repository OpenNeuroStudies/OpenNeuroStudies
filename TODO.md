# OpenNeuroStudies TODO List

**Generated**: 2026-03-10
**Based on**: Spec 001-read-file-doc compliance analysis
**Source**: doc/spec-compliance-analysis.md

## Critical Path Items

### 1. Hierarchical Statistics Completion (FR-042 series) 🟡 MEDIUM PRIORITY

**Status**: ⚠️ Sourcedata complete (FR-042a/b/c/d), derivatives pending (FR-042e/f)
**Estimated Effort**: 1-2 weeks
**Blocking**: Complete metadata extraction system

**What's Already Implemented** ✅:
- ✅ Sourcedata hierarchical extraction infrastructure (`bids_studies/extraction/`)
  - `extract_subject_stats()` - per-subject extraction
  - `extract_subjects_stats()` - all subjects in dataset
  - `aggregate_to_dataset()` - per-dataset aggregation
  - `aggregate_to_study()` - per-study aggregation
  - `write_subjects_tsv()`, `write_datasets_tsv()` - TSV file generation
- ✅ JSON sidecars (`bids_studies/schemas/sourcedata+subjects.json`, `sourcedata.json`)
- ✅ CLI integration (`metadata generate --stage imaging`)
- ✅ 12 of 40 studies have hierarchical TSV files

**Remaining Tasks**:
- [ ] Generate hierarchical files for all 40 studies (FR-042a/b)
  - [ ] Run `openneuro-studies metadata generate --stage imaging`
  - [ ] Verify all studies have sourcedata.tsv and sourcedata+subjects.tsv
  - [ ] Commit generated files
- [ ] Implement derivatives hierarchical stats (FR-042e)
  - [ ] Create `bids_studies/extraction/derivative.py` module
  - [ ] Implement `extract_derivative_subject_stats()`
  - [ ] Implement `extract_derivative_subjects_stats()`
  - [ ] Implement `aggregate_derivative_to_dataset()`
  - [ ] Generate derivatives+subjects.tsv and derivatives+datasets.tsv
  - [ ] Create JSON sidecars (derivatives+subjects.json, derivatives+datasets.json)
- [ ] Update studies.tsv aggregation (FR-042f)
  - [ ] Modify `collect_study_metadata()` to read from hierarchical TSV files
  - [ ] Read sourcedata.tsv instead of direct extraction
  - [ ] Read derivatives+datasets.tsv if exists
  - [ ] Fall back to direct extraction if TSV files missing (backwards compatibility)
- [ ] Fix CSV escaping in hierarchical TSV writing
  - [ ] Update `write_subjects_tsv()` to use manual TSV writing (like studies.tsv)
  - [ ] Update `write_datasets_tsv()` to avoid JSON escaping
- [ ] Write tests
  - [ ] Unit tests for derivative extraction functions
  - [ ] Integration test: studies.tsv aggregation from hierarchical files
  - [ ] Verify no regression in studies.tsv values
- [ ] Update documentation
  - [ ] Document hierarchical stats in quickstart
  - [ ] Update design document with current state
  - [ ] Document file locations and formats

**Design Reference**: `specs/003-hierarchical-stats/design.md`

**Dependencies**: None (infrastructure already exists)

---

## Verification & Testing

### 2. Publishing Workflow Verification (FR-024 series) 🟡 MEDIUM PRIORITY

**Status**: ⚠️ Code exists, needs testing
**Estimated Effort**: 3-5 days
**Blocking**: Public dataset sharing

**Tasks**:
- [ ] Set up test GitHub organization
  - [ ] Create test org (e.g., OpenNeuroStudiesTest)
  - [ ] Configure GITHUB_TOKEN with appropriate permissions
  - [ ] Create Maintainers team
- [ ] Test `publish` command (FR-024, FR-024a)
  - [ ] Verify repository creation on GitHub
  - [ ] Test initial push to remote
  - [ ] Verify .gitmodules URL updates
  - [ ] Check published-studies.json tracking
- [ ] Test team permissions (FR-024e)
  - [ ] Configure `maintainers_team` in config.yaml
  - [ ] Verify team is granted push access
  - [ ] Test with actual team member
- [ ] Test `unpublish` command (FR-024b)
  - [ ] Verify confirmation prompt/flag
  - [ ] Test repository deletion
  - [ ] Check published-studies.json cleanup
  - [ ] Test --dry-run mode
- [ ] Test `publish --sync` (FR-024d)
  - [ ] Manually create repo on GitHub
  - [ ] Run sync, verify addition to tracking file
  - [ ] Manually delete repo on GitHub
  - [ ] Run sync, verify removal from tracking file
  - [ ] Test commit SHA updates
- [ ] Edge case testing
  - [ ] Already published repository
  - [ ] Network failures during push
  - [ ] API rate limiting
  - [ ] Invalid credentials
- [ ] Document publishing workflow
  - [ ] Add publishing section to quickstart
  - [ ] Document team setup
  - [ ] Add troubleshooting guide

**Dependencies**: None

---

### 3. Derivative Outdatedness Calculation (FR-028-030) 🟡 MEDIUM PRIORITY

**Status**: ⚠️ Code exists, needs verification
**Estimated Effort**: 2-3 days
**Blocking**: Derivative freshness tracking

**Tasks**:
- [ ] Test outdatedness calculation
  - [ ] Find/create multi-version test datasets
  - [ ] Verify commit count calculation
  - [ ] Test with tagged vs untagged versions
  - [ ] Test with missing source datasets
- [ ] Verify caching implementation
  - [ ] Confirm results are cached
  - [ ] Test cache invalidation
  - [ ] Measure performance improvement
- [ ] Test studies+derivatives.tsv population
  - [ ] Verify outdatedness column
  - [ ] Check uptodate boolean flag
  - [ ] Test with fresh vs stale derivatives
- [ ] Document outdatedness workflow
  - [ ] Explain calculation methodology
  - [ ] Document when calculation runs
  - [ ] Add troubleshooting section

**Dependencies**: None

---

### 4. BIDS Validation at Scale (FR-015, SC-008) 🟢 LOW PRIORITY

**Status**: ⚠️ Works for small sets, not tested at scale
**Estimated Effort**: 1-2 days testing + potential optimization
**Blocking**: Validation success criteria (SC-008)

**Tasks**:
- [ ] Verify validation output storage
  - [ ] Check derivatives/bids-validator/ structure
  - [ ] Verify version.txt, report.json, report.txt creation
  - [ ] Test with valid and invalid datasets
- [ ] Test --when=new-commits logic
  - [ ] Verify skipping when no changes
  - [ ] Test with new commits
  - [ ] Check logging of skipped studies
- [ ] Scale testing
  - [ ] Run validation on all 40 organized studies
  - [ ] Measure time and resource usage
  - [ ] Monitor for memory leaks or bottlenecks
  - [ ] Test parallel execution if needed
- [ ] Performance optimization (if needed)
  - [ ] Profile slow operations
  - [ ] Implement caching if applicable
  - [ ] Consider batching strategies
- [ ] Document validation workflow
  - [ ] Add validation section to quickstart
  - [ ] Document when validation runs
  - [ ] Explain output file formats

**Dependencies**: Need 40+ organized studies (already available)

---

### 5. --include-derivatives Recursive Expansion (FR-017b) 🟢 LOW PRIORITY

**Status**: ⚠️ Implemented, needs testing
**Estimated Effort**: 1 day
**Blocking**: Complete filtering functionality

**Tasks**:
- [ ] Test recursive derivative expansion
  - [ ] Filter for single raw dataset
  - [ ] Verify all derivatives included
  - [ ] Test with derivatives-of-derivatives
  - [ ] Verify intersection logic
- [ ] Test without --include-derivatives
  - [ ] Verify only raw datasets match filter
  - [ ] Confirm derivatives excluded
- [ ] Add integration test
  - [ ] Create test with known derivative chains
  - [ ] Verify complete expansion
  - [ ] Test edge cases (circular references, missing sources)
- [ ] Document filtering behavior
  - [ ] Update CLI help text
  - [ ] Add examples to quickstart
  - [ ] Explain recursive logic

**Dependencies**: None

---

## Code Quality & Maintenance

### 6. Code Duplication Cleanup 🟡 MEDIUM PRIORITY

**Status**: ⚠️ Documented in doc/todos/
**Estimated Effort**: 1-2 weeks
**Blocking**: Code maintainability

**Tasks**:
- [ ] Consolidate `_extract_nifti_header_from_gzip_stream()` (from TODO doc)
  - [ ] Move to shared utility: `openneuro_studies/lib/nifti_utils.py`
  - [ ] Update imports in:
    - `bids_studies/extraction/subject.py`
    - `openneuro_studies/metadata/summary_extractor.py`
  - [ ] Standardize on single implementation (nibabel-based)
  - [ ] Add comprehensive unit tests
- [ ] Investigate nibabel direct gzip loading (from TODO doc)
  - [ ] Test if nibabel can read gzipped HTTP streams directly
  - [ ] If yes: simplify to delegate to nibabel
  - [ ] If no: document why manual decompression is necessary
- [ ] Fix "too short" file check (from TODO doc)
  - [ ] Determine minimum valid gzipped NIfTI size
  - [ ] Test with actual small NIfTI files from datasets
  - [ ] Adjust or remove 100-byte threshold
  - [ ] Add test case with small NIfTI file
- [ ] Extract shared TSV writing pattern
  - [ ] Create `lib/tsv_utils.py` with `write_tsv_with_json()`
  - [ ] Replace duplicated logic in:
    - `metadata/studies_tsv.py`
    - `metadata/studies_plus_derivatives_tsv.py`
    - `workflow/Snakefile` (merge_into_canonical rule)
  - [ ] Ensure consistent JSON serialization

**Dependencies**: None

---

### 7. Test Coverage Improvements 🟢 LOW PRIORITY

**Status**: ✅ 26 test files, needs expansion
**Estimated Effort**: Ongoing
**Blocking**: Code reliability

**Tasks**:
- [ ] Add unit tests for new subdataset management code
  - [ ] `test_subdataset_manager.py` (already has 25 tests ✅)
  - [ ] Add edge cases for nested repos
  - [ ] Test failure handling
- [ ] Add integration tests for hierarchical stats (when implemented)
  - [ ] Test full extraction pipeline
  - [ ] Verify aggregation accuracy
  - [ ] Test with multi-source studies
- [ ] Expand coverage for publishing commands
  - [ ] Mock GitHub API responses
  - [ ] Test error conditions
  - [ ] Verify tracking file updates
- [ ] Add performance benchmarks
  - [ ] Discovery speed
  - [ ] Organization speed
  - [ ] Metadata extraction speed
  - [ ] Set baseline expectations

**Dependencies**: None

---

### 8. Documentation Updates 🟢 LOW PRIORITY

**Status**: ✅ CLAUDE.md exists, needs expansion
**Estimated Effort**: Ongoing
**Blocking**: User adoption

**Tasks**:
- [ ] Update quickstart with hierarchical stats section
- [ ] Document publishing workflow
- [ ] Add troubleshooting guide
  - [ ] Common errors and solutions
  - [ ] GitHub API issues
  - [ ] Subdataset initialization problems
  - [ ] Validation failures
- [ ] Create architecture diagram
  - [ ] Show module relationships
  - [ ] Illustrate data flow
  - [ ] Document key design decisions
- [ ] Add examples directory
  - [ ] Sample config.yaml
  - [ ] Example workflows
  - [ ] Common use cases
- [ ] Update README with current status
  - [ ] Feature completeness
  - [ ] Quick start guide
  - [ ] Link to full docs

**Dependencies**: Complete hierarchical stats, publishing verification

---

## Future Enhancements (Not in Current Spec)

### 9. Performance Optimization

**Tasks**:
- [ ] Profile metadata extraction at scale (1000+ datasets)
- [ ] Optimize API call patterns
- [ ] Implement better caching strategies
- [ ] Consider parallel processing for independent operations
- [ ] Optimize sparse data access patterns

### 10. Advanced Features

**Tasks**:
- [ ] Dashboard generation from TSV files
- [ ] Search/query interface for studies.tsv
- [ ] Automated quality reports
- [ ] Derivative recommendation system
- [ ] Citation generation for studies

---

## Recently Completed ✅

- [x] Subdataset initialization fix (commit d9e438a) - 2026-03-10
  - Fixed repository context bug
  - Achieved 97.5% metadata extraction success (39/40 studies)
  - Added `_find_immediate_parent_repo()` function

- [x] Bold TRs JSON serialization fix (commit a0376c4) - 2026-03-10
  - Fixed double-escaped JSON in studies.tsv
  - Serialize to JSON at collection time
  - Write TSV manually to avoid CSV escaping
  - Clean output: `{"2.0":48}` instead of `"{""2.0"":48}"`

- [x] Provenance manifest error handling (commit e124944) - 2026-03-10
  - Handle empty/corrupt manifest files
  - Added robust error handling in provenance.py

- [x] Code duplication TODO documentation - 2026-03-10
  - Created doc/todos/code-duplication-nifti-header-extraction.md
  - Documented issues and resolution path

- [x] Spec compliance analysis (commit c0c13f8) - 2026-03-10
  - Comprehensive FR-by-FR assessment
  - Gap analysis with mitigation plan
  - 85% overall compliance score

---

## Notes

- **Priority Key**: 🔴 High | 🟡 Medium | 🟢 Low
- **Status Key**: ✅ Done | ⚠️ In Progress/Needs Verification | ❌ Not Started
- Items are ordered by priority within each section
- Estimated efforts are approximate and may vary based on complexity discovered during implementation
- This TODO list should be reviewed and updated regularly as work progresses

---

**Last Updated**: 2026-03-10
**Next Review**: After hierarchical stats implementation
