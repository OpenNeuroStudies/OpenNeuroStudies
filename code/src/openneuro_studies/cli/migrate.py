"""CLI command for migrating study structures to new naming conventions."""

import configparser
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

import click

from openneuro_studies.organization import get_derivative_dir_name, sanitize_name

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


def _rename_submodule_path(
    repo_path: Path,
    old_path: str,
    new_path: str,
    submodule_name: str,
    dry_run: bool = False,
) -> bool:
    """Rename a submodule path in .gitmodules and git index.

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
    old_dir = repo_path / old_path
    new_dir = repo_path / new_path

    if dry_run:
        click.echo(f"    Would rename: {old_path} -> {new_path}")
        return True

    try:
        # 1. Update .gitmodules
        content = gitmodules_path.read_text()
        # Replace path = old_path with path = new_path
        content = re.sub(
            rf'(\[submodule "{re.escape(submodule_name)}"\][^\[]*path\s*=\s*){re.escape(old_path)}',
            rf"\g<1>{new_path}",
            content,
        )
        gitmodules_path.write_text(content)

        # 2. Remove old gitlink from index
        subprocess.run(
            ["git", "-C", str(repo_path), "rm", "--cached", old_path],
            check=True,
            capture_output=True,
        )

        # 3. Get the commit SHA from the old entry (need to retrieve before removal)
        # We can get this from git ls-tree
        result = subprocess.run(
            ["git", "-C", str(repo_path), "ls-tree", "HEAD", old_path],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Try from index
            result = subprocess.run(
                ["git", "-C", str(repo_path), "ls-files", "--stage", old_path],
                capture_output=True,
                text=True,
            )

        # Parse: 160000 <sha> 0\t<path>
        commit_sha = None
        for line in result.stdout.strip().split("\n"):
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    commit_sha = parts[1] if parts[0] == "160000" else parts[1]
                    break

        if not commit_sha:
            logger.warning(f"Could not find commit SHA for {old_path}")
            return False

        # 4. Create new directory if needed
        new_dir.mkdir(parents=True, exist_ok=True)

        # 5. Add new gitlink with same commit SHA
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "update-index",
                "--add",
                "--cacheinfo",
                f"160000,{commit_sha},{new_path}",
            ],
            check=True,
            capture_output=True,
        )

        # 6. Stage .gitmodules
        subprocess.run(
            ["git", "-C", str(repo_path), "add", ".gitmodules"],
            check=True,
            capture_output=True,
        )

        # 7. Remove old empty directory if it exists
        if old_dir.exists() and old_dir.is_dir():
            try:
                old_dir.rmdir()
            except OSError:
                pass  # Directory not empty or other issue

        return True

    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to rename {old_path} -> {new_path}: {e}")
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

    Updates existing studies to follow FR-003d, FR-003e, and FR-003f:
    - Renames sourcedata/raw to sourcedata/{dataset_id}
    - Renames derivatives/Custom code-unknown to derivatives/custom-{dataset_id}
    - Sanitizes derivative directory names (replaces special chars with +)

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
                            "Migrate to new naming conventions (FR-003d/e/f)\n\n"
                            "- Renamed sourcedata/raw to sourcedata/{dataset_id}\n"
                            "- Sanitized derivative directory names",
                        ],
                        check=True,
                        capture_output=True,
                    )
                    click.echo(f"  ✓ Committed changes")
                except subprocess.CalledProcessError as e:
                    if b"nothing to commit" in e.stdout or b"nothing to commit" in e.stderr:
                        click.echo(f"  (no changes to commit)")
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
