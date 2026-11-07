"""Print the build label for the current commit, e.g. ``0.2.0-dev.47+1a2b3c4``.

The label is ``<version>-dev.<N>+<sha>``: the version from ``pyproject.toml``,
the number of commits since the last ``v*`` release tag (or since the first
commit if there are no tags yet) and the short commit SHA, with ``.dirty``
appended when the working tree has uncommitted changes. See DESIGN.md §9
Versioning.
"""

import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _git(repo: Path, *args: str) -> str:
    # Fixed git arguments from this script, never user input; git from PATH.
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def commits_since_tag(repo: Path) -> int:
    """Count the commits since the last release tag.

    Args:
        repo: Root of the git repository.

    Returns:
        Commits since the most recent ``v*`` tag, or since the first commit
        if there are no tags yet.
    """
    try:
        described = _git(repo, "describe", "--tags", "--long", "--match", "v[0-9]*")
    except subprocess.CalledProcessError:
        return int(_git(repo, "rev-list", "--count", "HEAD"))
    # e.g. v0.1.0-5-g1a2b3c4: the count is the second-to-last part.
    return int(described.rsplit("-", 2)[1])


def build_label(repo: Path = ROOT) -> str:
    """Build the label for the commit checked out in ``repo``.

    Args:
        repo: Root of the git repository, which holds ``pyproject.toml``.

    Returns:
        The build label, e.g. ``0.2.0-dev.47+1a2b3c4`` or
        ``0.2.0-dev.47+1a2b3c4.dirty``.
    """
    pyproject = tomllib.loads((repo / "pyproject.toml").read_text())
    version = pyproject["project"]["version"]
    sha = _git(repo, "rev-parse", "--short=7", "HEAD")
    dirty = ".dirty" if _git(repo, "status", "--porcelain") else ""
    return f"{version}-dev.{commits_since_tag(repo)}+{sha}{dirty}"


if __name__ == "__main__":
    sys.stdout.write(f"{build_label()}\n")
