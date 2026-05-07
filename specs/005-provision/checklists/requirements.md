# Requirements Quality Checklist: Provision Command

**Purpose**: Validate completeness, clarity, and consistency of the provision command specification
**Created**: 2026-05-07
**Feature**: [specs/005-provision/spec.md](../spec.md)

## Completeness

- [x] CHK001 All parent spec requirements (FR-041, FR-041a) are addressed by feature requirements
- [x] CHK002 All three provisioned files are specified: code/run-bids-validator, README.md, .openneuro-studies/template-version
- [x] CHK003 CLI options are fully enumerated: --force, --dry-run, --commit/--no-commit, STUDY_IDS
- [x] CHK004 Error handling is specified for: missing study directory, copier failure, missing copier
- [x] CHK005 Version tracking lifecycle is complete: create, check, skip, force-update
- [x] CHK006 Template variable list is complete: study_id, dataset_id, template_version, github_org
- [x] CHK007 Commit behavior is specified for both study subdatasets and parent repository
- [x] CHK008 Study ID normalization is specified (both study-ds000001 and ds000001 accepted)

## Clarity

- [x] CHK009 ProvisionResult dataclass fields are explicitly listed with types
- [x] CHK010 Template version comparison logic is described (string equality, not semver)
- [x] CHK011 File permission requirements are specified (0755 for run-bids-validator)
- [x] CHK012 Copier fallback order is specified (copier binary, then python -m copier)
- [x] CHK013 Validator script priority order is specified (uvx > bids-validator-deno > deno > npx)
- [x] CHK014 Idempotency requirement is clearly stated with testable criteria

## Consistency

- [x] CHK015 Template version constant location matches implementation (provisioner.py TEMPLATE_VERSION)
- [x] CHK016 File paths in spec match actual template output paths
- [x] CHK017 CLI command name matches registration in main.py (provision)
- [x] CHK018 Copier template directory matches TEMPLATE_DIR in provisioner.py
- [x] CHK019 ProvisionResult fields match existing dataclass implementation
- [x] CHK020 GitHub org default matches copier.yaml default (OpenNeuroStudies)

## Constitution Compliance

- [x] CHK021 Principle I (Data Integrity): Template version tracking provides traceability
- [x] CHK022 Principle II (Automation): Fully scripted, idempotent provisioning
- [x] CHK023 Principle III (Standard Formats): Template-version is plain text; README is markdown
- [x] CHK024 Principle IV (Git/DataLad-First): Changes committed via git with descriptive messages
- [x] CHK025 Principle V (Observability): Summary output reports provisioned/skipped/error counts
- [x] CHK026 Principle VI (No Silent Failures): Errors are reported per-study with specific messages
- [x] CHK027 Principle VII (DRY): Single provisioner implementation used by CLI command

## Testability

- [x] CHK028 Each acceptance scenario is independently verifiable
- [x] CHK029 Success criteria include measurable metrics (completion time, pass rates)
- [x] CHK030 Unit tests exist for core provisioner functions (version tracking, dry-run, force)
- [x] CHK031 Integration tests exist for copier template rendering
- [x] CHK032 Edge cases are identified and can be tested in isolation

## Notes

- Check items off as completed: `[x]`
- All items are currently checked because they verify the spec's coverage of the existing implementation
- Items would be unchecked if gaps were found between spec and implementation
