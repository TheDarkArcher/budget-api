"""Tests for the build label script."""

import os
import subprocess
from pathlib import Path

import pytest
from build_label import build_label


def git_cmd(repo: Path, *args: str) -> str:
    # Fixed git arguments from these tests, never user input; git from PATH.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commit(repo: Path, message: str) -> None:
    git_cmd(repo, "commit", "--allow-empty", "-m", message)


def short_sha(repo: Path) -> str:
    return git_cmd(repo, "rev-parse", "--short=7", "HEAD")


@pytest.fixture(autouse=True)
def isolated_git(monkeypatch: pytest.MonkeyPatch) -> None:
    # Ignore the developer's git config, e.g. commit signing.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "Test")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "test@example.com")
    # Set when run from a git hook; they would point git at the real repo.
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git_cmd(tmp_path, "init", "--quiet")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.2.0"\n')
    git_cmd(tmp_path, "add", "pyproject.toml")
    commit(tmp_path, "First")
    return tmp_path


def test_counts_every_commit_when_there_is_no_release_tag(repo: Path) -> None:
    commit(repo, "Second")
    assert build_label(repo) == f"1.2.0-dev.2+{short_sha(repo)}"


def test_counts_commits_since_the_last_release_tag(repo: Path) -> None:
    git_cmd(repo, "tag", "-a", "v1.1.0", "-m", "Release 1.1.0")
    commit(repo, "Second")
    commit(repo, "Third")
    assert build_label(repo) == f"1.2.0-dev.2+{short_sha(repo)}"


def test_counts_from_the_most_recent_of_several_release_tags(repo: Path) -> None:
    git_cmd(repo, "tag", "-a", "v1.0.0", "-m", "Release 1.0.0")
    commit(repo, "Second")
    git_cmd(repo, "tag", "-a", "v1.1.0", "-m", "Release 1.1.0")
    commit(repo, "Third")
    assert build_label(repo) == f"1.2.0-dev.1+{short_sha(repo)}"


def test_counts_commits_since_a_release_candidate_tag(repo: Path) -> None:
    git_cmd(repo, "tag", "-a", "v1.2.0-rc.1", "-m", "Release 1.2.0-rc.1")
    commit(repo, "Second")
    commit(repo, "Third")
    assert build_label(repo) == f"1.2.0-dev.2+{short_sha(repo)}"


def test_counts_zero_commits_on_a_release_tag(repo: Path) -> None:
    git_cmd(repo, "tag", "-a", "v1.1.0", "-m", "Release 1.1.0")
    assert build_label(repo) == f"1.2.0-dev.0+{short_sha(repo)}"


@pytest.mark.parametrize("tag", ["experiment", "vnext"])
def test_ignores_tags_that_are_not_releases(repo: Path, tag: str) -> None:
    git_cmd(repo, "tag", tag)
    commit(repo, "Second")
    assert build_label(repo) == f"1.2.0-dev.2+{short_sha(repo)}"


def test_marks_uncommitted_changes_as_dirty(repo: Path) -> None:
    with (repo / "pyproject.toml").open("a") as pyproject:
        pyproject.write("# edited\n")
    assert build_label(repo) == f"1.2.0-dev.1+{short_sha(repo)}.dirty"


def test_marks_untracked_files_as_dirty(repo: Path) -> None:
    (repo / "notes.txt").write_text("Untracked\n")
    assert build_label(repo) == f"1.2.0-dev.1+{short_sha(repo)}.dirty"


def test_reads_the_version_from_the_working_tree(repo: Path) -> None:
    (repo / "pyproject.toml").write_text('[project]\nversion = "1.3.0"\n')
    assert build_label(repo).startswith("1.3.0-dev.")
