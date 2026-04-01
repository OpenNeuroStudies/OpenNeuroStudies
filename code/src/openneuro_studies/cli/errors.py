#!/usr/bin/env python3
"""CLI commands for hierarchical error tracking.

Provides commands to query, analyze, and manage extraction errors
across all studies.
"""

import json
import logging
from pathlib import Path

import click

from openneuro_studies.lib.error_tracking import (
    ErrorCategory,
    ErrorLevel,
    ErrorRecord,
    garbage_collect,
    get_error_summary,
    mark_resolved,
)

logger = logging.getLogger(__name__)


@click.group()
def errors():
    """Manage hierarchical error tracking."""
    pass


@errors.command()
@click.option(
    "--study",
    "-s",
    help="Filter by study ID (e.g., study-ds001506)",
)
@click.option(
    "--dataset",
    "-d",
    help="Filter by dataset ID (e.g., ds001506)",
)
@click.option(
    "--category",
    "-c",
    type=click.Choice(
        ["missing_url", "network_error", "permission_error", "git_annex_error", "parse_error", "validation_error", "other"]
    ),
    help="Filter by error category",
)
@click.option(
    "--level",
    "-l",
    type=click.Choice(["study", "dataset", "subject", "session", "file"]),
    help="Filter by hierarchy level",
)
@click.option(
    "--resolved/--unresolved",
    default=None,
    help="Filter by resolution status",
)
@click.option(
    "--limit",
    type=int,
    default=50,
    help="Maximum number of errors to show (default 50)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json", "tsv"]),
    default="table",
    help="Output format (default table)",
)
def list(study, dataset, category, level, resolved, limit, output_format):
    """List errors across all studies."""
    # Find all error logs
    error_logs = sorted(Path(".").glob("study-*/sourcedata/errors.jsonl"))

    if not error_logs:
        click.echo("No error logs found.")
        return

    # Collect all matching errors
    all_errors = []
    for log_path in error_logs:
        try:
            with open(log_path) as f:
                for line in f:
                    if line.strip():
                        record = ErrorRecord.model_validate_json(line)

                        # Apply filters
                        if study and record.study_id != study:
                            continue
                        if dataset and record.dataset_id != dataset:
                            continue
                        if category and record.error_category != category:
                            continue
                        if level and record.level != level:
                            continue
                        if resolved is not None and record.resolved != resolved:
                            continue

                        all_errors.append(record)
        except Exception as e:
            logger.warning(f"Failed to read {log_path}: {e}")

    # Sort by last_seen (most recent first)
    all_errors.sort(key=lambda r: r.last_seen, reverse=True)

    # Limit results
    all_errors = all_errors[:limit]

    if not all_errors:
        click.echo("No errors found matching filters.")
        return

    # Output
    if output_format == "json":
        click.echo(json.dumps([r.model_dump() for r in all_errors], indent=2))
    elif output_format == "tsv":
        # Header
        click.echo(
            "study_id\tdataset_id\tlevel\tsubject_id\tsession_id\terror_category\t"
            "error_type\tcount\tresolved\tfirst_seen\tlast_seen\tmessage"
        )
        # Rows
        for r in all_errors:
            click.echo(
                f"{r.study_id}\t{r.dataset_id}\t{r.level}\t{r.subject_id or ''}\t"
                f"{r.session_id or ''}\t{r.error_category}\t{r.error_type}\t{r.count}\t"
                f"{r.resolved}\t{r.first_seen}\t{r.last_seen}\t{r.message[:100]}"
            )
    else:  # table
        click.echo(f"\nFound {len(all_errors)} errors:\n")
        click.echo(
            f"{'Study':<20} {'Dataset':<12} {'Level':<10} {'Category':<15} "
            f"{'Type':<12} {'Count':<6} {'Resolved':<10}"
        )
        click.echo("-" * 105)
        for r in all_errors:
            click.echo(
                f"{r.study_id:<20} {r.dataset_id:<12} {r.level:<10} "
                f"{r.error_category:<15} {r.error_type:<12} {r.count:<6} "
                f"{'Yes' if r.resolved else 'No':<10}"
            )


@errors.command()
@click.option(
    "--study",
    "-s",
    help="Filter by study ID",
)
@click.option(
    "--dataset",
    "-d",
    help="Filter by dataset ID",
)
def summary(study, dataset):
    """Show summary statistics for errors."""
    error_logs = sorted(Path(".").glob("study-*/sourcedata/errors.jsonl"))

    if not error_logs:
        click.echo("No error logs found.")
        return

    # Apply filters
    if study:
        error_logs = [p for p in error_logs if study in str(p)]
    if dataset:
        error_logs = [p for p in error_logs if dataset in str(p)]

    # Collect summaries
    total_errors = 0
    total_unresolved = 0
    total_resolved = 0
    by_category = {}
    by_type = {}
    by_level = {}

    for log_path in error_logs:
        summary = get_error_summary(log_path)
        total_errors += summary["total_errors"]
        total_unresolved += summary["unresolved_errors"]
        total_resolved += summary["resolved_errors"]

        for cat, count in summary["by_category"].items():
            by_category[cat] = by_category.get(cat, 0) + count
        for typ, count in summary["by_type"].items():
            by_type[typ] = by_type.get(typ, 0) + count
        for lvl, count in summary["by_level"].items():
            by_level[lvl] = by_level.get(lvl, 0) + count

    # Display summary
    click.echo("\n=== Error Summary ===\n")
    click.echo(f"Total errors: {total_errors}")
    click.echo(f"Unresolved: {total_unresolved}")
    click.echo(f"Resolved: {total_resolved}")

    click.echo("\n--- By Category ---")
    for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
        click.echo(f"{cat:.<30} {count}")

    click.echo("\n--- By Type ---")
    for typ, count in sorted(by_type.items(), key=lambda x: x[1], reverse=True):
        click.echo(f"{typ:.<30} {count}")

    click.echo("\n--- By Level ---")
    for lvl, count in sorted(by_level.items(), key=lambda x: x[1], reverse=True):
        click.echo(f"{lvl:.<30} {count}")


@errors.command()
@click.argument("study_id")
@click.argument("dataset_id")
@click.option(
    "--category",
    "-c",
    type=click.Choice(
        ["missing_url", "network_error", "permission_error", "git_annex_error", "parse_error", "validation_error", "other"]
    ),
    help="Resolve only this category",
)
@click.option(
    "--level",
    "-l",
    type=click.Choice(["study", "dataset", "subject", "session", "file"]),
    help="Resolve only this level",
)
@click.option(
    "--subject",
    "-s",
    help="Resolve only this subject",
)
def resolve(study_id, dataset_id, category, level, subject):
    """Mark errors as resolved."""
    error_log = Path(study_id) / "sourcedata" / "errors.jsonl"

    if not error_log.exists():
        click.echo(f"No error log found for {study_id}")
        return

    error_cat: ErrorCategory | None = category  # type: ignore
    error_lvl: ErrorLevel | None = level  # type: ignore

    count = mark_resolved(
        error_log_path=error_log,
        study_id=study_id,
        dataset_id=dataset_id,
        error_category=error_cat,
        level=error_lvl,
        subject_id=subject,
    )

    click.echo(f"Marked {count} errors as resolved in {study_id}/{dataset_id}")


@errors.command()
@click.option(
    "--days",
    "-d",
    type=int,
    default=30,
    help="Remove resolved errors older than N days (default 30)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be removed without actually removing",
)
def gc(days, dry_run):
    """Garbage collect old resolved errors."""
    error_logs = sorted(Path(".").glob("study-*/sourcedata/errors.jsonl"))

    if not error_logs:
        click.echo("No error logs found.")
        return

    total_removed = 0
    for log_path in error_logs:
        if dry_run:
            # Count what would be removed
            from datetime import datetime, timedelta

            cutoff = datetime.now() - timedelta(days=days)
            would_remove = 0

            with open(log_path) as f:
                for line in f:
                    if line.strip():
                        record = ErrorRecord.model_validate_json(line)
                        if record.resolved and record.resolved_at:
                            resolved_dt = datetime.fromisoformat(record.resolved_at)
                            if resolved_dt < cutoff:
                                would_remove += 1

            if would_remove > 0:
                click.echo(f"{log_path}: would remove {would_remove} errors")
                total_removed += would_remove
        else:
            # Actually remove
            removed = garbage_collect(log_path, days=days)
            if removed > 0:
                click.echo(f"{log_path}: removed {removed} errors")
                total_removed += removed

    if dry_run:
        click.echo(f"\nWould remove {total_removed} total errors (dry run)")
    else:
        click.echo(f"\nRemoved {total_removed} total errors")


@errors.command(name="analyze-quality")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "tsv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    type=click.Path(),
    default="logs/extraction_quality.tsv",
    help="Output TSV file path",
)
def analyze_quality(output_format, output):
    """Analyze extraction quality across all studies.

    Shows which datasets have incomplete imaging metrics (n/a values)
    indicating missing remote URLs or other extraction issues.

    Categories:
      - complete: All imaging metrics extracted
      - partial_imaging_metrics: Some metrics missing
      - missing_imaging_metrics: All metrics missing (likely no remote URLs)
      - no_bold: No BOLD data in dataset

    Example:
        openneuro-studies errors analyze-quality
        openneuro-studies errors analyze-quality --format tsv --output quality.tsv
    """
    import json

    # Find all extraction JSON files
    json_files = sorted(Path(".snakemake/extracted").glob("study-*.json"))
    logger.debug(f"Found {len(json_files)} extraction JSON files")

    if not json_files:
        click.echo("No extraction JSON files found in .snakemake/extracted/")
        click.echo("Run 'make extract' first to generate metadata.")
        return

    # Analyze all studies
    results = []
    for json_path in json_files:
        try:
            with open(json_path) as f:
                data = json.load(f)

            study_id = json_path.stem

            # Check for n/a values in imaging metrics
            imaging_fields = [
                "bold_voxels_total",
                "bold_voxels_mean",
                "bold_duration_total",
                "bold_duration_mean",
            ]

            missing_imaging = sum(1 for field in imaging_fields if data.get(field) == "n/a")
            has_bold = data.get("bold_num", "n/a") != "n/a" and data.get("bold_num", 0) > 0

            # Determine status
            if missing_imaging == len(imaging_fields) and has_bold:
                status = "missing_imaging_metrics"
            elif missing_imaging > 0 and has_bold:
                status = "partial_imaging_metrics"
            elif not has_bold:
                status = "no_bold"
            else:
                status = "complete"

            results.append(
                {
                    "study_id": study_id,
                    "status": status,
                    "subjects_num": data.get("subjects_num", "n/a"),
                    "bold_num": data.get("bold_num", "n/a"),
                    "t1w_num": data.get("t1w_num", "n/a"),
                    "bold_voxels_mean": data.get("bold_voxels_mean", "n/a"),
                    "bold_duration_mean": data.get("bold_duration_mean", "n/a"),
                    "missing_count": missing_imaging,
                }
            )
        except Exception as e:
            click.echo(f"Warning: Failed to analyze {json_path}: {e}", err=True)

    if not results:
        click.echo("No valid extraction results found.")
        return

    # Group by status - use regular dict instead of defaultdict
    # (defaultdict causes issues with Click's command processing)
    by_status = {}
    for r in results:
        status_key = r["status"]
        if status_key not in by_status:
            by_status[status_key] = []
        by_status[status_key].append(r)

    # Output
    if output_format == "table":
        click.echo(f"\nAnalyzed {len(results)} studies\n")

        click.echo("## Summary by Status\n")
        click.echo(f"{'Status':<30} {'Count':<10}")
        click.echo("-" * 40)
        for status in [
            "complete",
            "partial_imaging_metrics",
            "missing_imaging_metrics",
            "no_bold",
        ]:
            count = len(by_status.get(status, []))
            if count > 0:
                click.echo(f"{status:<30} {count:<10}")

        # Show datasets with missing imaging metrics
        if by_status.get("missing_imaging_metrics"):
            click.echo(
                f"\n## Datasets Missing Imaging Metrics ({len(by_status['missing_imaging_metrics'])})\n"
            )
            click.echo("These likely have 'No remote URL' errors for all BOLD files:\n")
            click.echo(
                f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'T1w Files':<10}"
            )
            click.echo("-" * 67)

            for r in sorted(by_status.get("missing_imaging_metrics", []), key=lambda x: x["study_id"]):
                click.echo(
                    f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                    f"{str(r['bold_num']):<12} {str(r['t1w_num']):<10}"
                )

        # Show datasets with partial metrics
        if by_status.get("partial_imaging_metrics", []):
            click.echo(
                f"\n## Datasets with Partial Imaging Metrics ({len(by_status['partial_imaging_metrics'])})\n"
            )
            click.echo("Some BOLD files have remote URLs, others don't:\n")
            click.echo(
                f"{'Study':<25} {'Subjects':<10} {'BOLD Files':<12} {'Missing Fields':<15}"
            )
            click.echo("-" * 72)

            for r in sorted(by_status.get("partial_imaging_metrics", []), key=lambda x: x["study_id"]):
                click.echo(
                    f"{r['study_id']:<25} {str(r['subjects_num']):<10} "
                    f"{str(r['bold_num']):<12} {r['missing_count']}/4"
                )

    # Write TSV
    output_path = Path(output)
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        f.write(
            "study_id\tstatus\tsubjects_num\tbold_num\tt1w_num\t"
            "bold_voxels_mean\tbold_duration_mean\n"
        )
        for r in sorted(results, key=lambda x: x["study_id"]):
            f.write(
                f"{r['study_id']}\t{r['status']}\t{r['subjects_num']}\t"
                f"{r['bold_num']}\t{r['t1w_num']}\t{r['bold_voxels_mean']}\t"
                f"{r['bold_duration_mean']}\n"
            )

    click.echo(f"\n✓ Detailed report written to: {output_path}")


@errors.command(name="analyze-legacy")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "tsv"]),
    default="table",
    help="Output format",
)
@click.option(
    "--output",
    type=click.Path(),
    default="logs/extraction_errors.tsv",
    help="Output TSV file path",
)
def analyze_legacy(output_format, output):
    """Analyze legacy extraction_errors.log files.

    Summarizes errors from old-format extraction_errors.log files
    across all studies. This command helps transition from legacy
    error logging to the new hierarchical error tracking system.

    Once all studies have errors.jsonl files, use 'errors summary'
    instead of this command.

    Example:
        openneuro-studies errors analyze-legacy
        openneuro-studies errors analyze-legacy --format tsv
    """
    import re
    from collections import defaultdict

    # Find all extraction_errors.log files
    error_logs = sorted(Path(".").glob("study-*/sourcedata/extraction_errors.log"))

    if not error_logs:
        click.echo("No extraction_errors.log files found.")
        click.echo("Either errors haven't occurred or you're using the new errors.jsonl format.")
        click.echo("Try 'openneuro-studies errors summary' instead.")
        return

    # Parse all logs
    results = []
    for log_path in error_logs:
        study_id = log_path.parts[0]

        try:
            with open(log_path) as f:
                content = f.read()

            # Parse header - format: "Extraction Errors (N total)"
            errors_match = re.search(r"Extraction Errors \((\d+) total\)", content)
            total_errors = int(errors_match.group(1)) if errors_match else 0

            # Extract dataset ID from study directory name
            # study-dsXXXXXX -> dsXXXXXX
            study_id_match = re.match(r"study-(ds\d+)", study_id)
            if study_id_match:
                dataset_id = study_id_match.group(1)
            else:
                # Try to extract from error messages
                dataset_match = re.search(r"sourcedata/(ds\d+)", content)
                dataset_id = dataset_match.group(1) if dataset_match else "unknown"

            # Subject count not available in legacy logs
            total_subjects = 0
            error_rate = 0.0

            # Extract first few errors
            first_errors = []
            for line in content.split("\n"):
                if "Failed to extract" in line:
                    first_errors.append(line.strip())
                    if len(first_errors) >= 5:
                        break

            results.append(
                {
                    "study_id": study_id,
                    "dataset_id": dataset_id,
                    "total_errors": total_errors,
                    "total_subjects": total_subjects,
                    "error_rate": error_rate,
                    "first_errors": first_errors,
                    "log_path": str(log_path),
                }
            )
        except Exception as e:
            click.echo(f"Warning: Failed to parse {log_path}: {e}", err=True)

    if not results:
        click.echo("No valid error logs found.")
        return

    # Sort by total errors
    results.sort(key=lambda x: x["total_errors"], reverse=True)

    # Output
    if output_format == "table":
        click.echo(f"\nFound {len(error_logs)} studies with extraction errors\n")

        click.echo("## Studies with Errors (sorted by count)\n")
        click.echo(f"{'Study':<25} {'Dataset':<15} {'Errors':<10}")
        click.echo("-" * 55)

        total_errors_all = 0
        for r in results:
            click.echo(
                f"{r['study_id']:<25} {r['dataset_id']:<15} {r['total_errors']:<10}"
            )
            total_errors_all += r["total_errors"]

        click.echo()
        click.echo(f"Total errors across all studies: {total_errors_all}")

        # Categorize errors
        all_first_errors = []
        for r in results:
            all_first_errors.extend(r["first_errors"])

        categories = defaultdict(int)
        for error in all_first_errors:
            if "No remote URL found" in error:
                categories["missing_remote_url"] += 1
            elif "Network" in error or "Connection" in error:
                categories["network_error"] += 1
            elif "Permission denied" in error:
                categories["permission_error"] += 1
            elif "git-annex" in error:
                categories["git_annex_error"] += 1
            else:
                categories["other"] += 1

        if categories:
            click.echo("\n## Error Breakdown by Type\n")
            for category, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                click.echo(f"{category:.<30} {count}")

        # Show top problematic datasets
        click.echo("\n## Top 5 Most Problematic Datasets\n")
        for i, r in enumerate(results[:5], 1):
            click.echo(f"{i}. {r['study_id']} ({r['dataset_id']})")
            click.echo(f"   Total errors: {r['total_errors']}")
            click.echo(f"   Log: {r['log_path']}")
            if r["first_errors"]:
                click.echo(f"   First error: {r['first_errors'][0][:100]}...")
            click.echo()

    # Write TSV
    output_path = Path(output)
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        f.write("study_id\tdataset_id\ttotal_errors\tlog_path\tfirst_error\n")
        for r in results:
            first_error = r['first_errors'][0] if r['first_errors'] else ""
            f.write(
                f"{r['study_id']}\t{r['dataset_id']}\t{r['total_errors']}\t"
                f"{r['log_path']}\t{first_error}\n"
            )

    click.echo(f"\n✓ Detailed summary written to: {output_path}")
