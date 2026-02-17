"""Provenance management for Snakemake workflows.

Stores provenance information in .snakemake/prov/ to avoid polluting
the main file tree. Provides utilities for:
- Recording provenance per output file
- Cleaning stale provenance entries
- Querying provenance history
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default provenance directory (relative to workflow root)
PROV_DIR = ".snakemake/prov"


def get_provenance_path(output_path: str, prov_dir: str = PROV_DIR) -> Path:
    """Get provenance file path for a given output.

    Args:
        output_path: Path to the output file (e.g., "studies.tsv")
        prov_dir: Base directory for provenance files

    Returns:
        Path to the provenance JSON file
    """
    # Sanitize output path for use as filename
    safe_name = output_path.replace("/", "__").replace("\\", "__")
    return Path(prov_dir) / f"{safe_name}.prov.json"


class ProvenanceManager:
    """Manages provenance records for workflow outputs.

    Stores provenance in .snakemake/prov/ with structure:
        .snakemake/prov/
        ├── studies.tsv.prov.json
        ├── stats__study-ds000001.json.prov.json
        ├── ...
        └── manifest.json  # tracks all managed outputs

    Each provenance file contains:
    {
        "output": "studies.tsv",
        "rule": "aggregate_studies",
        "created": "2025-01-13T10:00:00Z",
        "updated": "2025-01-13T12:00:00Z",
        "dependencies": {
            "study-ds000001": {
                "study_sha": "abc123...",
                "sourcedata_shas": {"ds000001": "def456..."}
            },
            ...
        },
        "params_hash": "sha256:...",
        "history": [
            {"timestamp": "...", "reason": "initial", "shas": {...}},
            {"timestamp": "...", "reason": "dependency_changed", "shas": {...}}
        ]
    }
    """

    def __init__(self, prov_dir: str = PROV_DIR):
        """Initialize provenance manager.

        Args:
            prov_dir: Directory for provenance files (created if needed)
        """
        self.prov_dir = Path(prov_dir)
        self.manifest_path = self.prov_dir / "manifest.json"
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        """Ensure provenance directory exists."""
        self.prov_dir.mkdir(parents=True, exist_ok=True)

    def _load_manifest(self) -> dict[str, Any]:
        """Load or create the manifest file."""
        if self.manifest_path.exists():
            with open(self.manifest_path) as f:
                return json.load(f)
        return {"outputs": {}, "created": self._now(), "updated": self._now()}

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        """Save the manifest file."""
        manifest["updated"] = self._now()
        with open(self.manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)

    @staticmethod
    def _now() -> str:
        """Get current timestamp in ISO format."""
        return datetime.now(timezone.utc).isoformat()

    def record(
        self,
        output_path: str,
        rule_name: str,
        dependencies: dict[str, Any],
        params_hash: Optional[str] = None,
    ) -> None:
        """Record provenance for an output file.

        Args:
            output_path: Path to the output file
            rule_name: Name of the Snakemake rule that created it
            dependencies: Dictionary of dependency SHAs
            params_hash: Optional hash of rule params
        """
        prov_path = get_provenance_path(output_path, str(self.prov_dir))
        now = self._now()

        # Load existing provenance or create new
        if prov_path.exists():
            with open(prov_path) as f:
                prov = json.load(f)
            # Add to history
            prov["history"].append(
                {
                    "timestamp": now,
                    "reason": "updated",
                    "dependencies": dependencies,
                }
            )
            prov["updated"] = now
        else:
            prov = {
                "output": output_path,
                "rule": rule_name,
                "created": now,
                "updated": now,
                "history": [
                    {
                        "timestamp": now,
                        "reason": "initial",
                        "dependencies": dependencies,
                    }
                ],
            }

        prov["dependencies"] = dependencies
        if params_hash:
            prov["params_hash"] = params_hash

        # Save provenance
        with open(prov_path, "w") as f:
            json.dump(prov, f, indent=2)

        # Update manifest
        manifest = self._load_manifest()
        manifest["outputs"][output_path] = {
            "prov_file": str(prov_path.relative_to(self.prov_dir)),
            "rule": rule_name,
            "updated": now,
        }
        self._save_manifest(manifest)

        logger.debug(f"Recorded provenance for {output_path}")

    def get(self, output_path: str) -> Optional[dict[str, Any]]:
        """Get provenance for an output file.

        Args:
            output_path: Path to the output file

        Returns:
            Provenance dictionary or None if not found
        """
        prov_path = get_provenance_path(output_path, str(self.prov_dir))
        if prov_path.exists():
            with open(prov_path) as f:
                return json.load(f)
        return None

    def remove(self, output_path: str) -> bool:
        """Remove provenance for an output file.

        Args:
            output_path: Path to the output file

        Returns:
            True if provenance was removed, False if not found
        """
        prov_path = get_provenance_path(output_path, str(self.prov_dir))

        if prov_path.exists():
            prov_path.unlink()

            # Update manifest
            manifest = self._load_manifest()
            if output_path in manifest["outputs"]:
                del manifest["outputs"][output_path]
                self._save_manifest(manifest)

            logger.debug(f"Removed provenance for {output_path}")
            return True

        return False

    def list_outputs(self) -> list[str]:
        """List all outputs with recorded provenance.

        Returns:
            List of output paths
        """
        manifest = self._load_manifest()
        return list(manifest["outputs"].keys())

    def find_stale(self, existing_outputs: set[str]) -> list[str]:
        """Find provenance entries for outputs that no longer exist.

        Args:
            existing_outputs: Set of output paths that currently exist

        Returns:
            List of stale output paths
        """
        manifest = self._load_manifest()
        recorded = set(manifest["outputs"].keys())
        return list(recorded - existing_outputs)


def clean_stale_provenance(
    prov_dir: str = PROV_DIR,
    existing_outputs: Optional[set[str]] = None,
    dry_run: bool = False,
) -> list[str]:
    """Remove provenance entries for outputs that no longer exist.

    Args:
        prov_dir: Provenance directory
        existing_outputs: Set of existing output paths. If None, checks filesystem.
        dry_run: If True, only report what would be removed

    Returns:
        List of removed (or would-be-removed) output paths
    """
    manager = ProvenanceManager(prov_dir)
    manifest = manager._load_manifest()

    # Determine which outputs still exist
    if existing_outputs is None:
        existing_outputs = set()
        for output_path in manifest["outputs"]:
            if Path(output_path).exists():
                existing_outputs.add(output_path)

    stale = manager.find_stale(existing_outputs)

    if dry_run:
        for output in stale:
            logger.info(f"Would remove stale provenance: {output}")
    else:
        for output in stale:
            manager.remove(output)
            logger.info(f"Removed stale provenance: {output}")

    return stale


def get_provenance_summary(prov_dir: str = PROV_DIR) -> dict[str, Any]:
    """Get a summary of all provenance records.

    Args:
        prov_dir: Provenance directory

    Returns:
        Summary dictionary with counts and latest updates
    """
    manager = ProvenanceManager(prov_dir)
    manifest = manager._load_manifest()

    return {
        "total_outputs": len(manifest["outputs"]),
        "outputs": list(manifest["outputs"].keys()),
        "created": manifest.get("created"),
        "updated": manifest.get("updated"),
    }
