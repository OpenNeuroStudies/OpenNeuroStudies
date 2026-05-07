# Bidirectional Filter Expansion for Dataset Discovery

**Date**: 2026-05-07
**Status**: In Progress
**Authors**: OpenNeuroStudies contributors

## Summary

Adds bidirectional filter expansion to the `DatasetFinder` discovery workflow.
When a test filter is specified (e.g., `--test-filter ds006131`), the system can
automatically expand the filter to include related datasets in either direction
(derivatives, sources, or both) until transitive closure is reached.

## Context / Problem Statement

The existing `--include-derivatives` flag only expands the discovery filter in
the forward direction (raw datasets to their derivatives). This is insufficient
for several real-world workflows:

1. **Derivative-first analysis**: A researcher starts with a derivative dataset
   (e.g., `ds000001-fmriprep`) and needs its source raw dataset (`ds000001`)
   to be discovered automatically.

2. **Multi-source derivatives**: Datasets like `ds006190` have multiple sources
   (`ds006189`, `ds006185`, `ds006131`). Starting from any one of these should
   discover the entire dependency graph.

3. **Complete study graphs**: For integration testing or full study provisioning,
   starting from a single dataset should discover the entire connected component
   of raw and derivative datasets.

## Proposed Solution / Design

### RelationType Enum

A `RelationType(str, Enum)` with three values:

- `DERIVATIVES` ("derivatives") -- Forward: raw datasets to their derivatives
- `SOURCES` ("sources") -- Backward: derivatives to their source raw datasets
- `ALL` ("all") -- Both directions until transitive closure

### Shared Discovery Helper

`_discover_all_derivatives()` is a single method that scans all configured
source organizations (without any dataset filter) to collect every
`DerivativeDataset` and its `source_datasets` relationships. This is the
foundation for all expansion directions, extracted to eliminate code duplication
between `_expand_filter_with_derivatives()` and `_expand_filter_with_sources()`.

### Expansion Methods

1. **`_expand_filter_with_derivatives()`** -- Uses the shared helper, then
   iteratively adds derivatives whose sources overlap with the current filter
   set. Also adds sources required by any derivative in the set (FR-017b).

2. **`_expand_filter_with_sources()`** -- Uses the shared helper, then
   iteratively adds source datasets of any derivative in the current filter set.

3. **`_expand_filter_with_related(include_related)`** -- Orchestrator that
   dispatches to the appropriate method(s):
   - Single direction: delegates directly
   - Bidirectional ("all"): iterates both directions in a loop until no new
     datasets are discovered (transitive closure)

### CLI Integration

The `discover` command gains a new `--include-related` option:

```
--include-related {derivatives,sources,all}
```

- Takes precedence over `--include-derivatives` when both are specified
- `--include-derivatives` remains as a deprecated backward-compatible alias
  for `--include-related derivatives`

### Backward Compatibility

- `include_derivatives=True` in the Python API still works as before
- `--include-derivatives` CLI flag still works
- When `include_related` is set, it takes precedence over `include_derivatives`

## Implementation Steps

1. **Phase 1-4**: Core algorithm -- `RelationType` enum, `_expand_filter_with_sources()`,
   `_expand_filter_with_related()`, bidirectional expansion in `discover_all()` (done)
2. **Refactoring**: Extract `_discover_all_derivatives()` shared helper to eliminate
   duplication between forward and backward expansion methods
3. **Phase 5**: CLI integration -- `--include-related` Click option in `discover.py`
4. **Tests**: Unit tests for enum, expansion methods, backward compatibility, edge cases

## Alternatives Considered

### Single-pass expansion (rejected)

Instead of iterating until closure, compute all reachable datasets in a single
BFS/DFS pass. Rejected because:

- The iterative approach naturally handles the bidirectional case where
  discovering a derivative in one direction may reveal new sources in the other
- Single-pass would require building an explicit graph data structure upfront
- The current iteration count is typically 2-3 for real-world dependency graphs

### Separate `--include-sources` flag (rejected)

Adding a separate boolean flag for each direction. Rejected because:

- Would create ambiguity when both flags are set (is that "all" or sequential?)
- A `Choice` type is cleaner and extensible
- Backward compatibility is simpler with one new option that overrides the old one

## Success Criteria

- `openneuro-studies discover --include-related all --test-filter ds006131`
  discovers ds006131 plus all its derivatives and their source datasets transitively
- All unit tests pass (24 tests covering enum, expansion, backward compatibility,
  and edge cases)
- No code duplication between forward and backward expansion (shared
  `_discover_all_derivatives()` helper)
- `--include-derivatives` still works identically to before

## Timeline / Effort Estimate

- Core algorithm (Phases 1-4): Complete
- Refactoring + CLI + Tests: 1 session

## References

- Branch: `enh-include-related`
- Original `--include-derivatives` implementation: `55310ad`
- FR-017b: Multi-source derivative handling
