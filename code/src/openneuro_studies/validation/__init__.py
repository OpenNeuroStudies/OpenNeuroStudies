"""BIDS validation integration for OpenNeuroStudies.

Implements FR-015: Run bids-validator on study datasets and store results.

Output structure:
    derivatives/bids-validator/
        version.txt   - Validator version
        report.json   - Machine-readable validation results
        report.txt    - Human-readable summary
"""

from openneuro_studies.validation.bids_validator import (
    VALIDATOR_OUTPUT_DIR,
    ValidationResult,
    ValidationStatus,
    find_validator,
    get_validator_version,
    needs_validation,
    run_validation,
    update_studies_tsv_validation,
)

__all__ = [
    "VALIDATOR_OUTPUT_DIR",
    "ValidationResult",
    "ValidationStatus",
    "find_validator",
    "get_validator_version",
    "needs_validation",
    "run_validation",
    "update_studies_tsv_validation",
]
