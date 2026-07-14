"""One version, declared in four places, pinned nowhere.

`pyproject.toml`, `patchrail.__version__`, `uv.lock` and the `--version` example
in the README quickstart each spell the version out. Nothing tied them together,
and they drifted every time: the 0.3.1 release bumped `pyproject.toml` and left
`uv.lock` on 0.3.0 (so `uv lock --check` failed on main and every `uv sync`
dirtied the tree), and the README kept advertising a release that was two behind.

`uv lock --check` now guards the lockfile in CI. These tests guard the rest, and
fail in both directions: a bump that forgets a file is a bug, and so is a file
nobody reverted after a bump.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import patchrail

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")

README_VERSION_RE = re.compile(r"patchrail --version.*\n# patchrail (\d+\.\d+\.\d+)")


def test_package_version_matches_pyproject() -> None:
    assert patchrail.__version__ == PYPROJECT["project"]["version"]


def test_readme_quickstart_advertises_the_version_that_ships() -> None:
    # First command a maintainer runs after installing. If it prints something
    # other than what the README promised, the very first check they make fails.
    match = README_VERSION_RE.search(README)
    assert match is not None, "README quickstart no longer shows the `patchrail --version` output"
    assert match.group(1) == patchrail.__version__
