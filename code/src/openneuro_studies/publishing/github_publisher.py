"""GitHub repository publishing using PyGithub."""

import logging
import subprocess
from pathlib import Path

from github import Github, GithubException, UnknownObjectException

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Raised when publishing fails."""

    pass


class GitHubPublisher:
    """Publishes study repositories to GitHub organization.

    Uses PyGithub API to create repositories and git push to upload content.

    Attributes:
        github: PyGithub Github instance
        organization_name: GitHub organization name
        organization: PyGithub Organization object
    """

    def __init__(self, github_token: str, organization_name: str):
        """Initialize GitHub publisher.

        Args:
            github_token: GitHub personal access token
            organization_name: Name of GitHub organization (e.g., "OpenNeuroStudies")

        Raises:
            PublishError: If organization cannot be accessed
        """
        self.github = Github(github_token)
        self.organization_name = organization_name

        try:
            self.organization = self.github.get_organization(organization_name)
        except UnknownObjectException:
            raise PublishError(
                f"Organization '{organization_name}' not found. "
                f"Check organization name and ensure you have access."
            )
        except GithubException as e:
            raise PublishError(f"Failed to access organization '{organization_name}': {e}")

    def repository_exists(self, repo_name: str) -> bool:
        """Check if a repository exists in the organization.

        Args:
            repo_name: Repository name (e.g., "study-ds000001")

        Returns:
            True if repository exists, False otherwise
        """
        try:
            self.organization.get_repo(repo_name)
            return True
        except UnknownObjectException:
            return False
        except GithubException as e:
            logger.warning(f"Error checking repository {repo_name}: {e}")
            return False

    def get_remote_head_sha(self, repo_name: str) -> str | None:
        """Get the HEAD commit SHA of a remote repository.

        Args:
            repo_name: Repository name

        Returns:
            Commit SHA if found, None if repository doesn't exist or has no commits
        """
        try:
            repo = self.organization.get_repo(repo_name)
            # Get default branch HEAD
            try:
                branch = repo.get_branch(repo.default_branch)
                return branch.commit.sha
            except GithubException:
                # Repository exists but has no commits yet
                return None
        except UnknownObjectException:
            return None
        except GithubException as e:
            logger.warning(f"Error getting remote HEAD for {repo_name}: {e}")
            return None

    def create_repository(
        self,
        repo_name: str,
        description: str | None = None,
        private: bool = False,
    ) -> str:
        """Create a new repository in the organization.

        Args:
            repo_name: Repository name (e.g., "study-ds000001")
            description: Optional repository description
            private: Whether to make repository private (default: False = public)

        Returns:
            Clone URL of created repository

        Raises:
            PublishError: If repository creation fails
        """
        try:
            repo = self.organization.create_repo(
                name=repo_name,
                description=description or f"OpenNeuroStudies study dataset: {repo_name}",
                private=private,
                auto_init=False,  # Don't create README - we'll push our content
                has_issues=False,
                has_wiki=False,
                has_projects=False,
            )
            logger.info(f"Created repository: {repo.html_url}")
            return repo.clone_url
        except GithubException as e:
            raise PublishError(f"Failed to create repository '{repo_name}': {e}")

    def delete_repository(self, repo_name: str) -> None:
        """Delete a repository from the organization.

        Args:
            repo_name: Repository name to delete

        Raises:
            PublishError: If deletion fails
        """
        try:
            repo = self.organization.get_repo(repo_name)
            repo.delete()
            logger.info(f"Deleted repository: {self.organization_name}/{repo_name}")
        except UnknownObjectException:
            raise PublishError(f"Repository '{repo_name}' not found")
        except GithubException as e:
            raise PublishError(f"Failed to delete repository '{repo_name}': {e}")

    def get_local_head_sha(self, study_path: Path) -> str:
        """Get the HEAD commit SHA of a local git repository.

        Args:
            study_path: Path to local repository

        Returns:
            Commit SHA

        Raises:
            PublishError: If getting commit SHA fails
        """
        try:
            result = subprocess.run(
                ["git", "-C", str(study_path), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise PublishError(f"Failed to get local HEAD SHA for {study_path}: {e}")

    def push_to_github(
        self,
        study_path: Path,
        repo_url: str,
        force: bool = False,
    ) -> str:
        """Push local repository to GitHub.

        Args:
            study_path: Path to local study repository
            repo_url: GitHub repository URL
            force: Whether to force push (default: False)

        Returns:
            Commit SHA that was pushed

        Raises:
            PublishError: If push fails
        """
        try:
            # Get local HEAD SHA before pushing
            local_sha = self.get_local_head_sha(study_path)

            # Check if remote 'origin' exists
            result = subprocess.run(
                ["git", "-C", str(study_path), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                # Add remote
                subprocess.run(
                    ["git", "-C", str(study_path), "remote", "add", "origin", repo_url],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                logger.info(f"Added remote origin: {repo_url}")
            else:
                # Remote exists - verify it matches
                existing_url = result.stdout.strip()
                if existing_url != repo_url:
                    # Update remote URL
                    subprocess.run(
                        ["git", "-C", str(study_path), "remote", "set-url", "origin", repo_url],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    logger.info(f"Updated remote origin: {repo_url}")

            # Detect default branch (main or master)
            result = subprocess.run(
                ["git", "-C", str(study_path), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            )
            branch = result.stdout.strip()

            # Push to GitHub
            push_args = ["git", "-C", str(study_path), "push"]
            if force:
                push_args.append("--force")
            push_args.extend(["origin", branch])

            subprocess.run(
                push_args,
                check=True,
                capture_output=True,
                text=True,
            )
            logger.info(f"Pushed {study_path.name} to {repo_url} (branch: {branch})")

            return local_sha

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise PublishError(f"Failed to push {study_path.name}: {error_msg}")

    def publish_study(
        self,
        study_path: Path,
        force: bool = False,
    ) -> tuple[str, str, bool]:
        """Publish a study repository to GitHub.

        Creates repository if it doesn't exist, then pushes content.

        Args:
            study_path: Path to local study repository
            force: Whether to force push if remote differs (default: False)

        Returns:
            Tuple of (github_url, commit_sha, was_created)
            - github_url: Full URL to GitHub repository
            - commit_sha: Commit SHA that was pushed
            - was_created: True if repository was newly created, False if it existed

        Raises:
            PublishError: If publishing fails
        """
        study_id = study_path.name
        repo_name = study_id

        # Check if repository exists
        exists = self.repository_exists(repo_name)
        was_created = not exists

        if not exists:
            # Create repository
            repo_url = self.create_repository(repo_name)
        else:
            # Use existing repository
            repo_url = f"https://github.com/{self.organization_name}/{repo_name}.git"

            # Check if remote matches local
            if not force:
                remote_sha = self.get_remote_head_sha(repo_name)
                local_sha = self.get_local_head_sha(study_path)

                if remote_sha and remote_sha == local_sha:
                    logger.info(f"{repo_name} already up-to-date")
                    return (repo_url, local_sha, was_created)
                elif remote_sha and remote_sha != local_sha:
                    raise PublishError(
                        f"{repo_name} exists on GitHub with different content. "
                        f"Use --force to overwrite (local: {local_sha[:8]}, remote: {remote_sha[:8]})"
                    )

        # Push to GitHub
        commit_sha = self.push_to_github(study_path, repo_url, force=force)

        github_url = f"https://github.com/{self.organization_name}/{repo_name}"
        return (github_url, commit_sha, was_created)
