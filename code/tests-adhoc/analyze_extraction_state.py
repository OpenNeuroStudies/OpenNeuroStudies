#!/usr/bin/env python3
"""Analyze the current state of metadata extraction.

This script checks:
- How many studies have real metadata vs "n/a"
- How many subdatasets are actually initialized (with files)
- Statistics on extraction success rates
"""

import csv
import json
import subprocess
import sys
from pathlib import Path
from collections import Counter


def check_subdataset_initialized(subdataset_path: Path) -> dict:
    """Check if subdataset is properly initialized with files.

    Returns:
        dict with keys: has_git, is_own_repo, has_files, initialized
    """
    result = {
        "has_git": False,
        "is_own_repo": False,
        "has_files": False,
        "initialized": False,
    }

    if not subdataset_path.exists():
        return result

    git_path = subdataset_path / ".git"
    result["has_git"] = git_path.exists()

    if not result["has_git"]:
        return result

    # Check if this is its own repository
    try:
        proc = subprocess.run(
            ["git", "-C", str(subdataset_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            timeout=5,
            check=True,
            text=True,
        )
        git_root = Path(proc.stdout.strip()).resolve()
        subdataset_resolved = subdataset_path.resolve()
        result["is_own_repo"] = (git_root == subdataset_resolved)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass

    # Check for files (excluding .git)
    try:
        items = list(subdataset_path.iterdir())
        non_hidden = [
            item for item in items
            if not item.name.startswith(".")
        ]
        result["has_files"] = len(non_hidden) > 0
    except OSError:
        pass

    result["initialized"] = (
        result["has_git"] and
        result["is_own_repo"] and
        result["has_files"]
    )

    return result


def analyze_studies_tsv(tsv_path: Path) -> dict:
    """Analyze studies.tsv for metadata completeness.

    Returns statistics on how many studies have real vs "n/a" values.
    """
    if not tsv_path.exists():
        return {"error": "studies.tsv not found"}

    with open(tsv_path, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        rows = list(reader)

    stats = {
        "total_studies": len(rows),
        "fields": {},
    }

    # Key fields to check
    key_fields = [
        "subjects_num",
        "bold_num",
        "t1w_num",
        "datatypes",
        "extraction_version",
    ]

    for field in key_fields:
        na_count = sum(1 for r in rows if r.get(field, "n/a") == "n/a")
        zero_count = sum(1 for r in rows if r.get(field, "n/a") == "0")
        real_count = len(rows) - na_count - zero_count

        stats["fields"][field] = {
            "n/a": na_count,
            "zero": zero_count,
            "real": real_count,
            "pct_real": round(100 * real_count / len(rows), 1) if rows else 0,
        }

    return stats


def analyze_subdatasets() -> dict:
    """Analyze subdataset initialization status.

    Checks sourcedata subdatasets in all studies.
    """
    study_dirs = sorted(Path(".").glob("study-ds*"))

    stats = {
        "total_studies": len(study_dirs),
        "with_sourcedata": 0,
        "subdatasets": {
            "total": 0,
            "has_git": 0,
            "is_own_repo": 0,
            "has_files": 0,
            "fully_initialized": 0,
        },
        "examples": {
            "initialized": [],
            "not_initialized": [],
        },
    }

    for study_dir in study_dirs:
        sourcedata_dir = study_dir / "sourcedata"
        if not sourcedata_dir.exists():
            continue

        stats["with_sourcedata"] += 1

        for subdataset_path in sourcedata_dir.iterdir():
            if not subdataset_path.is_dir():
                continue

            stats["subdatasets"]["total"] += 1
            check = check_subdataset_initialized(subdataset_path)

            if check["has_git"]:
                stats["subdatasets"]["has_git"] += 1
            if check["is_own_repo"]:
                stats["subdatasets"]["is_own_repo"] += 1
            if check["has_files"]:
                stats["subdatasets"]["has_files"] += 1
            if check["initialized"]:
                stats["subdatasets"]["fully_initialized"] += 1

                # Record examples
                if len(stats["examples"]["initialized"]) < 3:
                    stats["examples"]["initialized"].append(str(subdataset_path))
            else:
                if len(stats["examples"]["not_initialized"]) < 3:
                    stats["examples"]["not_initialized"].append({
                        "path": str(subdataset_path),
                        "has_git": check["has_git"],
                        "is_own_repo": check["is_own_repo"],
                        "has_files": check["has_files"],
                    })

    return stats


def analyze_extracted_jsons() -> dict:
    """Analyze .snakemake/extracted/*.json files."""
    extracted_dir = Path(".snakemake/extracted")
    if not extracted_dir.exists():
        return {"error": ".snakemake/extracted/ not found"}

    json_files = list(extracted_dir.glob("study-*.json"))

    stats = {
        "total_files": len(json_files),
        "extraction_versions": Counter(),
        "sample_metadata": {},
    }

    for json_file in json_files:
        try:
            with open(json_file) as f:
                data = json.load(f)

            version = data.get("extraction_version", "unknown")
            stats["extraction_versions"][version] += 1

            # Sample first 3 studies
            if len(stats["sample_metadata"]) < 3:
                stats["sample_metadata"][data["study_id"]] = {
                    "subjects_num": data.get("subjects_num", "n/a"),
                    "bold_num": data.get("bold_num", "n/a"),
                    "extraction_version": version,
                }

        except (json.JSONDecodeError, KeyError, OSError):
            pass

    return stats


def main():
    """Run analysis and print report."""
    print("=" * 80)
    print("EXTRACTION STATE ANALYSIS")
    print("=" * 80)

    # Analyze studies.tsv
    print("\n📊 STUDIES.TSV ANALYSIS")
    print("-" * 80)
    tsv_stats = analyze_studies_tsv(Path("studies.tsv"))

    if "error" in tsv_stats:
        print(f"❌ {tsv_stats['error']}")
    else:
        print(f"Total studies: {tsv_stats['total_studies']}")
        print("\nField completeness:")
        for field, data in tsv_stats["fields"].items():
            print(f"  {field:20} → {data['pct_real']:5.1f}% real "
                  f"({data['real']} real, {data['n/a']} n/a, {data['zero']} zero)")

    # Analyze subdatasets
    print("\n📁 SUBDATASET INITIALIZATION ANALYSIS")
    print("-" * 80)
    subds_stats = analyze_subdatasets()

    print(f"Total studies: {subds_stats['total_studies']}")
    print(f"Studies with sourcedata/: {subds_stats['with_sourcedata']}")
    print(f"\nSubdataset status:")
    print(f"  Total subdatasets: {subds_stats['subdatasets']['total']}")
    print(f"  Has .git: {subds_stats['subdatasets']['has_git']}")
    print(f"  Is own repo: {subds_stats['subdatasets']['is_own_repo']}")
    print(f"  Has files: {subds_stats['subdatasets']['has_files']}")
    print(f"  Fully initialized: {subds_stats['subdatasets']['fully_initialized']}")

    if subds_stats["subdatasets"]["total"] > 0:
        pct_init = 100 * subds_stats["subdatasets"]["fully_initialized"] / subds_stats["subdatasets"]["total"]
        print(f"\n  Initialization rate: {pct_init:.1f}%")

    print("\nExample initialized subdatasets:")
    for path in subds_stats["examples"]["initialized"]:
        print(f"  ✓ {path}")

    print("\nExample NOT initialized subdatasets:")
    for item in subds_stats["examples"]["not_initialized"]:
        print(f"  ✗ {item['path']}")
        print(f"    has_git={item['has_git']}, is_own_repo={item['is_own_repo']}, has_files={item['has_files']}")

    # Analyze extracted JSONs
    print("\n📄 EXTRACTED JSON ANALYSIS")
    print("-" * 80)
    json_stats = analyze_extracted_jsons()

    if "error" in json_stats:
        print(f"❌ {json_stats['error']}")
    else:
        print(f"Total extracted JSONs: {json_stats['total_files']}")
        print("\nExtraction versions:")
        for version, count in json_stats["extraction_versions"].most_common():
            print(f"  {version}: {count} studies")

        print("\nSample metadata:")
        for study_id, data in json_stats["sample_metadata"].items():
            print(f"  {study_id}:")
            print(f"    subjects_num: {data['subjects_num']}")
            print(f"    bold_num: {data['bold_num']}")
            print(f"    extraction_version: {data['extraction_version']}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if "error" not in tsv_stats:
        subjects_pct = tsv_stats["fields"]["subjects_num"]["pct_real"]
        if subjects_pct < 10:
            print("❌ CRITICAL: <10% of studies have real subjects_num metadata")
            print("   → Subdataset initialization is likely broken")
        elif subjects_pct < 50:
            print("⚠️  WARNING: <50% of studies have real metadata")
            print("   → Partial subdataset initialization")
        else:
            print(f"✓ GOOD: {subjects_pct:.1f}% of studies have real metadata")

    if subds_stats["subdatasets"]["total"] > 0:
        init_pct = 100 * subds_stats["subdatasets"]["fully_initialized"] / subds_stats["subdatasets"]["total"]
        if init_pct < 10:
            print(f"❌ CRITICAL: Only {init_pct:.1f}% of subdatasets fully initialized")
        elif init_pct < 50:
            print(f"⚠️  WARNING: Only {init_pct:.1f}% of subdatasets fully initialized")
        else:
            print(f"✓ GOOD: {init_pct:.1f}% of subdatasets fully initialized")

    print("\nNext steps:")
    if subds_stats["subdatasets"]["has_git"] > 0 and subds_stats["subdatasets"]["has_files"] == 0:
        print("  1. Fix is_subdataset_initialized() - detecting false positives")
        print("  2. Subdatasets have .git but no files → initialization incomplete")
        print("  3. Run: make full-clean && duct make metadata analyze-state CORES=6")
    elif "error" not in tsv_stats and tsv_stats["fields"]["subjects_num"]["pct_real"] < 50:
        print("  1. Review subdataset initialization logs")
        print("  2. Check if git submodule update --init is working")
        print("  3. Verify extraction code handles initialized subdatasets")

    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
