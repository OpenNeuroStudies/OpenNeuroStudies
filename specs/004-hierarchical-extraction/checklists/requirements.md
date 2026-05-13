# Requirements Quality Checklist: 004-hierarchical-extraction

**Spec**: `specs/004-hierarchical-extraction/spec.md`
**Reviewed**: 2026-05-07

## Completeness

- [x] All parent spec requirements (FR-042 through FR-042i) are covered by at least one FR-HE requirement
- [x] Each extraction level (subject, dataset, study, cross-study) has dedicated requirements
- [x] Sourcedata and derivative extraction have separate but parallel requirements
- [x] TSV file naming, location, and column definitions are specified
- [x] JSON sidecar requirements are specified
- [x] Error handling requirements cover both operational and expected failures
- [x] Library boundary (bids_studies vs openneuro_studies) is clearly defined
- [x] Efficiency requirements (Snakemake, git SHA tracking, incremental) are specified
- [x] Subdataset management lifecycle (init, extract, deinit) is specified
- [x] Data format conventions (tab-separated, n/a, snake_case) are specified

## Traceability

| Parent FR | 004 FR(s) | Status |
|-----------|-----------|--------|
| FR-042 | FR-HE-001, FR-HE-070, FR-HE-071, FR-HE-072 | Covered |
| FR-042a | FR-HE-010 | Covered |
| FR-042b | FR-HE-011 | Covered |
| FR-042c | FR-HE-012, FR-HE-022 | Covered |
| FR-042d | FR-HE-013 | Covered |
| FR-042e | FR-HE-020 | Covered |
| FR-042f | FR-HE-021, FR-HE-023, FR-HE-024, FR-HE-025 | Covered |
| FR-042g | FR-HE-031 | Covered |
| FR-042h | FR-HE-030 | Covered |
| FR-042i | FR-HE-073 | Covered |

## Clarity

- [x] Requirements use MUST/SHOULD/MAY consistently (RFC 2119 style)
- [x] Each requirement has a unique identifier (FR-HE-NNN)
- [x] Aggregation methods are explicitly listed (sum, min, max, weighted mean, set union)
- [x] TSV column lists are explicitly enumerated
- [x] Edge cases are documented with expected behavior
- [x] Error threshold behavior is specified (operational errors = fail, expected = info)

## Testability

- [x] Each user story has acceptance scenarios in Given/When/Then format
- [x] Success criteria are measurable (specific numbers, time limits, coverage targets)
- [x] Edge cases suggest specific test scenarios
- [x] Regression test criteria specified (aggregated values match direct extraction)

## Constitution Compliance

- [x] **Principle I (Data Integrity)**: Git submodules with explicit versions; intermediate files version-controlled
- [x] **Principle II (Automation)**: All operations via make/Snakemake; idempotent extraction
- [x] **Principle III (Standard Formats)**: TSV for tabular data; JSON for sidecars; snake_case columns
- [x] **Principle IV (Git/DataLad-First)**: DataLad commands for subdataset management; provenance tracking
- [x] **Principle V (Error Visibility)**: WARNING/ERROR logging; no silent failures; error summaries; accessible logs
- [x] **Principle VI (No Silent Failures)**: Uninitialized subdatasets detected and handled; missing data tracked
- [x] **Principle VII (DRY)**: Single extraction path through hierarchy; library boundary prevents duplication

## Open Questions

- [ ] **Q1**: Should `derivatives.tsv` (per-study) also include per-derivative subject/session counts from hierarchical extraction, or only from git-annex metadata? Currently FR-HE-021 says "per-derivative aggregated statistics plus identity metadata" but the exact column list for derivatives.tsv is not fully specified in the parent spec (FR-042f lists expected columns).
  - **Resolution**: FR-042f explicitly lists the columns. FR-HE-021 must match that list.

- [ ] **Q2**: The parent spec FR-042e mentions an `uptodate` column in derivative+subjects.tsv computed per-subject by comparing git history. This is a complex operation (requires git rev-list per subject). Is this feasible at scale, and is it worth the cost?
  - **Resolution**: Defer per-subject uptodate computation to a future iteration. Per-derivative uptodate (already implemented) is sufficient for initial release.

- [ ] **Q3**: The current derivative_extractor.py is in openneuro_studies but FR-042i requires it to be in bids_studies. How much of the derivative_extractor.py logic is truly generic vs. OpenNeuro-specific?
  - **Resolution**: Most logic is generic (git-annex size, version tracking, completeness). The only OpenNeuro-specific part is URL handling from .gitmodules. Migration path: move extraction functions to bids_studies, keep orchestration (install/drop/CLI) in openneuro_studies.
