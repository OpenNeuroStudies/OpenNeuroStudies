"""Study dataset provisioning with copier templates.

Implements FR-041: Provision study datasets with templated content including
code/run-bids-validator script and README.md.
"""

from openneuro_studies.provision.provisioner import (
    TEMPLATE_VERSION_DIR,
    TEMPLATE_VERSION_FILE,
    ProvisionResult,
    needs_provisioning,
    provision_study,
)

__all__ = [
    "TEMPLATE_VERSION_DIR",
    "TEMPLATE_VERSION_FILE",
    "ProvisionResult",
    "needs_provisioning",
    "provision_study",
]
