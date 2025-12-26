"""CLI command for migrating study structures to new naming conventions."""

import configparser
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import click

from openneuro_studies.organization import sanitize_name

logger = logging.getLogger(__name__)


def _parse_gitmodules(gitmodules_path: Path) -> dict[str, dict[str, str]]:
    """Parse .gitmodules file into a dictionary.

    Args:
        gitmodules_path: Path to .gitmodules file

    Returns:
        Dictionary mapping submodule name to its config (path, url, etc.)
    """
    if not gitmodules_path.exists():
        return {}

    config = configparser.ConfigParser()
    config.read(gitmodules_path)

    result = {}
    for section in config.sections():
        if section.startswith('submodule "'):
            name = section[11:-1]  # Extract name from 'submodule "name"'
            result[name] = dict(config[section])

    return result


def _get_dataset_id_from_url(url: str) -> Optional[str]:
    """Extract dataset ID from GitHub URL.

    Args:
        url: Git URL (e.g., https://github.com/OpenNeuroDatasets/ds000001.git)

    Returns:
        Dataset ID (e.g., ds000001) or None if not extractable
    """
    # Remove .git suffix and extract last path component
    url = url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url.split("/")[-1]


def _migrate_validation_output(
    study_path: Path,
    dry_run: bool = False,
) -> bool:
    """Migrate old validation outputs to new directory structure.

    Old format:
        derivatives/bids-validator.json
        derivatives/bids-validator.txt

    New format (FR-015):
        derivatives/bids-validator/version.txt
        derivatives/bids-validator/report.json
        derivatives/bids-validator/report.txt

    Args:
        study_path: Path to study directory
        dry_run: If True, only show what would be done

    Returns:
        True if migration was performed, False if nothing to migrate
    """
    derivatives_dir = study_path / "derivatives"
    old_json = derivatives_dir / "bids-validator.json"
    old_txt = derivatives_dir / "bids-validator.txt"

    # Check if old format exists
    has_old_json = old_json.exists()
    has_old_txt = old_txt.exists()

    if not has_old_json and not has_old_txt:
        return False

    new_dir = derivatives_dir / "bids-validator"

    if dry_run:
        click.echo("    Would migrate validation outputs:")
        if has_old_json:
            click.echo(f"      {old_json.relative_to(study_path)} -> bids-validator/report.json")
        if has_old_txt:
            click.echo(f"      {old_txt.relative_to(study_path)} -> bids-validator/report.txt")
        return True

    try:
        # Create new directory
        new_dir.mkdir(exist_ok=True)

        # Move files
        if has_old_json:
            new_json = new_dir / "report.json"
            old_json.rename(new_json)
            click.echo("    Moved: bids-validator.json -> bids-validator/report.json")

        if has_old_txt:
            new_txt = new_dir / "report.txt"
            old_txt.rename(new_txt)
            click.echo("    Moved: bids-validator.txt -> bids-validator/report.txt")

        # Stage changes
        subprocess.run(
            ["git", "-C", str(study_path), "add", "-A", "derivatives/"],
            check=True,
            capture_output=True,
        )

        return True

    except Exception as e:
        click.echo(f"    ERROR: Failed to migrate validation outputs: {e}", err=True)
        return False


def _rename_submodule_path(
    repo_path: Path,
    old_path: str,
    new_path: str,
    submodule_name: str,
    dry_run: bool = False,
) -> bool:
    """Rename a submodule path in .gitmodules and git index.

    Uses git mv to rename the submodule path, then updates .gitmodules.

    Args:
        repo_path: Path to git repository
        old_path: Current submodule path
        new_path: New submodule path
        submodule_name: Name of the submodule in .gitmodules
        dry_run: If True, only show what would be done

    Returns:
        True if renamed, False if skipped or failed
    """
    gitmodules_path = repo_path / ".gitmodules"
    new_dir = repo_path / new_path

    if dry_run:
        click.echo(f"    Would rename: {old_path} -> {new_path}")
        return True

    try:
        # 1. Create parent directory for new path if needed
        new_dir.parent.mkdir(parents=True, exist_ok=True)

        # 2. Use git mv to rename the submodule path in the index
        # This handles the gitlink rename properly
        subprocess.run(
            ["git", "-C", str(repo_path), "mv", old_path, new_path],
            check=True,
            capture_output=True,
            text=True,
        )

        # 3. Update .gitmodules to reflect the new path
        content = gitmodules_path.read_text()
        # Replace path = old_path with path = new_path
        # Use a more robust pattern that handles the multiline section
        updated_content = re.sub(
            rf"(path\s*=\s*){re.escape(old_path)}(\s*\n)",
            rf"\g<1>{new_path}\g<2>",
            content,
        )
        gitmodules_path.write_text(updated_content)

        # 4. Stage .gitmodules
        subprocess.run(
            ["git", "-C", str(repo_path), "add", ".gitmodules"],
            check=True,
            capture_output=True,
        )

        click.echo(f"    Renamed: {old_path} -> {new_path}")
        return True

    except subprocess.CalledProcessError as e:
        stderr = e.stderr if hasattr(e, "stderr") and e.stderr else str(e)
        logger.error(f"Failed to rename {old_path} -> {new_path}: {stderr}")
        click.echo(f"    ERROR: Failed to rename {old_path} -> {new_path}: {stderr}", err=True)
        return False


@click.command()
@click.argument("study_ids", nargs=-1, required=False)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be migrated without making changes",
)
@click.option(
    "--commit/--no-commit",
    default=True,
    help="Commit changes after migration (default: commit)",
)
@click.pass_context
def migrate(
    ctx: click.Context,
    study_ids: tuple[str, ...],
    dry_run: bool,
    commit: bool,
) -> None:
    """Migrate study structures to new naming conventions.

    Updates existing studies to follow current spec requirements:

    Submodule naming (FR-003d, FR-003e, FR-003f):
    - Renames sourcedata/raw to sourcedata/{dataset_id}
    - Renames derivatives/Custom code-unknown to derivatives/custom-{dataset_id}
    - Sanitizes derivative directory names (replaces special chars with +)

    Validation output (FR-015):
    - Moves derivatives/bids-validator.json to derivatives/bids-validator/report.json
    - Moves derivatives/bids-validator.txt to derivatives/bids-validator/report.txt

    Arguments:
        STUDY_IDS: Optional list of study IDs to migrate. If not provided,
                   migrates all study-* directories.

    Examples:
        # Dry run to see what would change
        openneuro-studies migrate --dry-run

        # Migrate all studies
        openneuro-studies migrate

        # Migrate specific studies
        openneuro-studies migrate study-ds000001 study-ds006131
    """
    # Determine which studies to migrate
    if study_ids:
        studies = []
        for study_id in study_ids:
            study_path = Path(study_id)
            if not study_path.exists():
                click.echo(f"Warning: {study_id} not found, skipping", err=True)
                continue
            studies.append(study_path)
    else:
        studies = sorted(
            [p for p in Path(".").iterdir() if p.is_dir() and p.name.startswith("study-")]
        )

    if not studies:
        click.echo("No study directories found.")
        return

    if dry_run:
        click.echo("[DRY RUN] Showing what would be migrated:\n")

    migrated_count = 0
    skipped_count = 0

    for study_path in studies:
        study_id = study_path.name
        dataset_id = study_id[6:]  # Remove "study-" prefix

        gitmodules_path = study_path / ".gitmodules"
        if not gitmodules_path.exists():
            skipped_count += 1
            continue

        submodules = _parse_gitmodules(gitmodules_path)
        changes_made = False

        click.echo(f"\n{study_id}:")

        # Migrate validation output format (FR-015)
        if _migrate_validation_output(study_path, dry_run):
            changes_made = True

        for submodule_name, config in submodules.items():
            old_path = config.get("path", "")
            url = config.get("url", "")

            # Check for sourcedata/raw -> sourcedata/{dataset_id}
            if old_path == "sourcedata/raw":
                # Get the actual dataset ID from the URL
                source_dataset_id = _get_dataset_id_from_url(url) or dataset_id
                new_path = f"sourcedata/{source_dataset_id}"

                if old_path != new_path:
                    if _rename_submodule_path(
                        study_path, old_path, new_path, submodule_name, dry_run
                    ):
                        changes_made = True

            # Check for derivatives with "Custom code" or unsanitized names
            elif old_path.startswith("derivatives/"):
                deriv_dir = old_path[12:]  # Remove "derivatives/" prefix
                deriv_dataset_id = _get_dataset_id_from_url(url) or submodule_name

                # Check if it's "Custom code-unknown" or similar
                if deriv_dir.lower().startswith("custom code") or deriv_dir == "unknown":
                    new_deriv_dir = f"custom-{deriv_dataset_id}"
                    new_path = f"derivatives/{new_deriv_dir}"

                    if old_path != new_path:
                        if _rename_submodule_path(
                            study_path, old_path, new_path, submodule_name, dry_run
                        ):
                            changes_made = True
                else:
                    # Check if name needs sanitization
                    sanitized_dir = sanitize_name(deriv_dir)
                    if sanitized_dir != deriv_dir:
                        new_path = f"derivatives/{sanitized_dir}"

                        if _rename_submodule_path(
                            study_path, old_path, new_path, submodule_name, dry_run
                        ):
                            changes_made = True

        if changes_made and not dry_run:
            migrated_count += 1

            # Commit changes if requested
            if commit:
                try:
                    subprocess.run(
                        [
                            "git",
                            "-C",
                            str(study_path),
                            "commit",
                            "-m",
                            "Migrate to new spec conventions\n\n"
                            "- Renamed sourcedata/raw to sourcedata/{dataset_id} (FR-003d)\n"
                            "- Sanitized derivative directory names (FR-003e/f)\n"
                            "- Moved validation outputs to derivatives/bids-validator/ (FR-015)",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    click.echo("  ✓ Committed changes")
                except subprocess.CalledProcessError as e:
                    if b"nothing to commit" in e.stdout or b"nothing to commit" in e.stderr:
                        click.echo("  (no changes to commit)")
                    else:
                        click.echo(f"  ✗ Commit failed: {e.stderr.decode()}", err=True)
        elif not changes_made:
            click.echo("  (already up-to-date)")
            skipped_count += 1

    # Summary
    click.echo(f"\n{'='*60}")
    if dry_run:
        click.echo(f"[DRY RUN] Would migrate: {len(studies) - skipped_count} studies")
        click.echo(f"[DRY RUN] Already up-to-date: {skipped_count} studies")
    else:
        click.echo(f"Migrated: {migrated_count} studies")
        click.echo(f"Skipped (already up-to-date): {skipped_count} studies")
