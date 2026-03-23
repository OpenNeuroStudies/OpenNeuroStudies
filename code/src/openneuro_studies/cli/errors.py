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
