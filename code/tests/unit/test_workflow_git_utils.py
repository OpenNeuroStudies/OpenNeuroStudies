"""Unit tests for workflow/lib/git_utils.py.

All tests build an isolated git repository hierarchy under tmp_path.
No real repo state, real submodules, or network access required.
"""

import subprocess
from pathlib import Path

import pytest

from workflow.lib.git_utils import (
    clear_sha_cache,
    get_file_blob_sha,
    get_gitlink_sha,
    get_head_sha,
    get_sourcedata_shas,
    get_tree_sha,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    """Run a git command inside repo; return stripped stdout."""
    return subprocess.check_output(
        ["git", "-C", str(repo)] + list(args),
        text=True,
        stderr=subprocess.DEVNULL,
    ).strip()


def _make_repo(path: Path, name: str = "repo") -> Path:
    """Create a minimal committed git repo with two files."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README.md").write_text(f"# {name}\n")
    (path / "data.tsv").write_text("col\tvalue\n")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")
    return path


def _add_submodule(parent: Path, sub_repo: Path, sub_name: str) -> None:
    """Add sub_repo as a named submodule inside parent and commit.

    Uses ``-c protocol.file.allow=always`` because modern git blocks the
    ``file://`` transport by default; plain absolute paths require the same
    override.
    """
    subprocess.check_call(
        [
            "git",
            "-C",
            str(parent),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            str(sub_repo),
            sub_name,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _git(parent, "commit", "-m", f"add submodule {sub_name}")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_repo(tmp_path) -> Path:
    """A minimal committed git repo under tmp_path."""
    return _make_repo(tmp_path / "repo")


@pytest.fixture
def repo_with_submodule(tmp_path) -> tuple[Path, Path, str]:
    """Parent repo containing one committed submodule.

    Returns (parent, sub_repo, sub_name).
    """
    sub = _make_repo(tmp_path / "sub")
    parent = _make_repo(tmp_path / "parent")
    sub_name = "my-submodule"
    _add_submodule(parent, sub, sub_name)
    return parent, sub, sub_name


@pytest.fixture
def repo_with_two_submodules(tmp_path) -> tuple[Path, list[str]]:
    """Parent repo with two committed submodules.

    Returns (parent, [sub_name_a, sub_name_b]).
    """
    parent = _make_repo(tmp_path / "parent")
    names = ["sub-alpha", "sub-beta"]
    for name in names:
        sub = _make_repo(tmp_path / name, name)  # distinct name → distinct content → distinct SHA
        _add_submodule(parent, sub, name)
    return parent, names


@pytest.fixture
def study_with_sourcedata(tmp_path) -> tuple[Path, str, list[str]]:
    """Parent repo + study submodule that itself has sourcedata submodules.

    Structure on disk after fixture setup::

        parent/
          study-fake/          ← checked-out study submodule
            sourcedata/
              ds000001/        ← checked-out sourcedata submodule
              ds000002/        ← checked-out sourcedata submodule

    Returns (parent, study_name, [source_names]).
    """
    source_names = ["ds000001", "ds000002"]
    sources = {n: _make_repo(tmp_path / n, n) for n in source_names}

    # Build the study repo with sourcedata submodules
    study_repo = _make_repo(tmp_path / "study_repo", "study")
    (study_repo / "sourcedata").mkdir()
    for name, src in sources.items():
        _add_submodule(study_repo, src, f"sourcedata/{name}")

    # Build the parent repo and add the study as a submodule
    study_name = "study-fake"
    parent = _make_repo(tmp_path / "parent", "parent")
    _add_submodule(parent, study_repo, study_name)

    # Initialise the nested sourcedata submodules so dirs exist on disk
    subprocess.check_call(
        [
            "git",
            "-C",
            str(parent / study_name),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "update",
            "--init",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return parent, study_name, source_names


@pytest.fixture(autouse=True)
def clear_caches():
    """Clear lru_cache state before and after every test."""
    clear_sha_cache()
    yield
    clear_sha_cache()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetGitlinkSha:
    def test_returns_40char_hex(self, repo_with_submodule):
        parent, _, sub_name = repo_with_submodule
        sha = get_gitlink_sha(sub_name, str(parent))
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_matches_git_ls_tree(self, repo_with_submodule):
        """Cross-check against raw git ls-tree output."""
        parent, _, sub_name = repo_with_submodule
        sha = get_gitlink_sha(sub_name, str(parent))
        raw = _git(parent, "ls-tree", "HEAD", sub_name)
        # "160000 commit <sha>\t<name>"
        assert sha in raw

    def test_stable_across_calls(self, repo_with_submodule):
        """Cached result is identical on second call."""
        parent, _, sub_name = repo_with_submodule
        assert get_gitlink_sha(sub_name, str(parent)) == get_gitlink_sha(sub_name, str(parent))

    def test_two_submodules_differ(self, repo_with_two_submodules):
        parent, names = repo_with_two_submodules
        sha_a = get_gitlink_sha(names[0], str(parent))
        sha_b = get_gitlink_sha(names[1], str(parent))
        assert sha_a != sha_b

    def test_invalid_path_raises(self, simple_repo):
        with pytest.raises((subprocess.CalledProcessError, ValueError)):
            get_gitlink_sha("nonexistent-path", str(simple_repo))


@pytest.mark.unit
class TestGetTreeSha:
    def test_root_returns_40char_hex(self, simple_repo):
        sha = get_tree_sha(".", str(simple_repo))
        assert len(sha) == 40

    def test_subdir_returns_sha(self, repo_with_submodule):
        parent, _, sub_name = repo_with_submodule
        sha = get_tree_sha(sub_name, str(parent))
        assert len(sha) == 40

    def test_root_and_subdir_differ(self, repo_with_submodule):
        parent, _, sub_name = repo_with_submodule
        assert get_tree_sha(".", str(parent)) != get_tree_sha(sub_name, str(parent))

    def test_invalid_path_raises(self, simple_repo):
        with pytest.raises(subprocess.CalledProcessError):
            get_tree_sha("nonexistent", str(simple_repo))


@pytest.mark.unit
class TestGetFileBlobSha:
    def test_known_file_returns_40char_hex(self, simple_repo):
        sha = get_file_blob_sha("README.md", str(simple_repo))
        assert len(sha) == 40

    def test_different_files_differ(self, simple_repo):
        sha_a = get_file_blob_sha("README.md", str(simple_repo))
        sha_b = get_file_blob_sha("data.tsv", str(simple_repo))
        assert sha_a != sha_b

    def test_invalid_path_raises(self, simple_repo):
        with pytest.raises((subprocess.CalledProcessError, ValueError)):
            get_file_blob_sha("no-such-file.txt", str(simple_repo))


@pytest.mark.unit
class TestGetSourcedataShas:
    def test_returns_dict(self, study_with_sourcedata):
        parent, study_name, _ = study_with_sourcedata
        result = get_sourcedata_shas(study_name, str(parent))
        assert isinstance(result, dict)

    def test_all_sources_present(self, study_with_sourcedata):
        parent, study_name, source_names = study_with_sourcedata
        result = get_sourcedata_shas(study_name, str(parent))
        for name in source_names:
            assert name in result

    def test_source_shas_are_40char_hex(self, study_with_sourcedata):
        parent, study_name, _ = study_with_sourcedata
        result = get_sourcedata_shas(study_name, str(parent))
        for sha in result.values():
            assert len(sha) == 40
            assert all(c in "0123456789abcdef" for c in sha)

    def test_nonexistent_study_returns_empty(self, simple_repo):
        result = get_sourcedata_shas("study-doesnotexist", str(simple_repo))
        assert result == {}

    def test_multiple_sources_count(self, study_with_sourcedata):
        parent, study_name, source_names = study_with_sourcedata
        result = get_sourcedata_shas(study_name, str(parent))
        assert len(result) == len(source_names)


@pytest.mark.unit
class TestGetHeadSha:
    def test_returns_40char_hex(self, simple_repo):
        sha = get_head_sha(str(simple_repo))
        assert len(sha) == 40

    def test_parent_and_submodule_differ(self, repo_with_submodule):
        parent, _, sub_name = repo_with_submodule
        parent_sha = get_head_sha(str(parent))
        sub_sha = get_head_sha(str(parent / sub_name))
        assert parent_sha != sub_sha
