#!/usr/bin/env python
"""Clean stale provenance entries from .snakemake/prov/.

This script removes provenance records for outputs that no longer exist,
keeping the provenance directory tidy.

Usage:
    # From repository root
    python code/workflow/scripts/clean_provenance.py

    # Dry run (show what would be removed)
    python code/workflow/scripts/clean_provenance.py --dry-run

    # Verbose output
    python code/workflow/scripts/clean_provenance.py -v

    # Custom provenance directory
    python code/workflow/scripts/clean_provenance.py --prov-dir .snakemake/prov
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from workflow.lib.provenance import (
    ProvenanceManager,
    clean_stale_provenance,
    get_provenance_summary,
)

logging.basicConfig(
    format="%(levelname)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="Clean stale provenance entries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--prov-dir",
        default=".snakemake/prov",
        help="Provenance directory (default: .snakemake/prov)",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be removed without actually removing",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show provenance summary and exit",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    prov_dir = Path(args.prov_dir)

    if not prov_dir.exists():
        logger.info(f"Provenance directory does not exist: {prov_dir}")
        return 0

    # Show summary if requested
    if args.summary:
        summary = get_provenance_summary(str(prov_dir))
        print(f"\nProvenance Summary ({prov_dir})")
        print("=" * 50)
        print(f"Total outputs tracked: {summary['total_outputs']}")
        print(f"Created: {summary['created']}")
        print(f"Updated: {summary['updated']}")

        if summary['outputs']:
            print("\nTracked outputs:")
            for output in sorted(summary['outputs']):
                exists = "exists" if Path(output).exists() else "MISSING"
                print(f"  [{exists}] {output}")
        return 0

    # Find and optionally remove stale entries
    logger.info(f"Scanning provenance directory: {prov_dir}")

    # Determine which outputs currently exist
    manager = ProvenanceManager(str(prov_dir))
    existing_outputs = set()

    for output_path in manager.list_outputs():
        if Path(output_path).exists():
            existing_outputs.add(output_path)
            logger.debug(f"Output exists: {output_path}")
        else:
            logger.debug(f"Output missing: {output_path}")

    # Clean stale entries
    stale = clean_stale_provenance(
        prov_dir=str(prov_dir),
        existing_outputs=existing_outputs,
        dry_run=args.dry_run,
    )

    if stale:
        action = "Would remove" if args.dry_run else "Removed"
        logger.info(f"{action} {len(stale)} stale provenance entries:")
        for output in stale:
            print(f"  - {output}")
    else:
        logger.info("No stale provenance entries found")

    return 0


if __name__ == "__main__":
    sys.exit(main())
