"""A `mypy` listed in a pixi/conda dependency manifest is not a type-check failure.

Grounded in a real failed run of pandas-dev/pandas (`Unit Tests / Pyarrow Nightly`, run
29719453153) — a Python monorepo whose per-environment `pixi` resolve prints one bill-of-materials
line per environment before any job runs:

  Dependencies: python, numpy, pytest, ..., pre-commit, ipython, mypy, scipy-stubs, ...

`mypy` is one declared dev dependency in that list — pandas resolves ~20 such lines, and never
invokes it here. The job that actually failed was the `pixi` env update itself:

  Error:   × Failed to update PyPI packages for environment 'pyarrow-nightly'
    ╰─▶ HTTP status client error (404 Not Found) ...
  ##[error]The process '/home/runner/.pixi/bin/pixi' failed with exit code 1

PatchRail reported `python_type_check` at 0.53 — sending a pandas maintainer to `mypy . || pyright`.
Its one and only witness was `\bmypy\b`, matched off that manifest line: a bill of materials, not an
event, exactly like conda's `- mypy=1.17.1` env.yml spec that the classifier already discounts. With
the failing subsystem being a dependency download, `unknown` (decline to auto-repair) is the honest
answer — a maintainer sent nowhere beats one sent to a type checker that never ran. The committed
excerpt is at examples/real-world/pandas-29719453153-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "pandas-29719453153-excerpt.log"
)

# The failure, reduced: a pixi env resolve lists mypy as a dependency, then the update fails.
PIXI_ENV_UPDATE_FAILED = """\
       Dependencies: python, numpy, pytest, hypothesis, pre-commit, ipython, mypy, scipy-stubs
Error:   × Failed to update PyPI packages for environment 'pyarrow-nightly'
  ╰─▶ HTTP status client error (404 Not Found) for url
##[error]The process '/home/runner/.pixi/bin/pixi' failed with exit code 1
"""


class AMypyInADependencyManifestIsNotATypeCheckFailure(unittest.TestCase):
    def test_the_pandas_run_is_not_a_python_type_check(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "python_type_check")

    def test_the_pandas_run_lands_on_unknown(self) -> None:
        # mypy was only ever declared, never invoked — so the type-check rule watched a tool that
        # never ran, and `unknown` is the honest ceiling.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_pixi_failure_is_not_a_python_type_check(self) -> None:
        result = classify_ci_log(PIXI_ENV_UPDATE_FAILED)

        self.assertNotEqual(result["failure_class"], "python_type_check")

    def test_a_pypi_dependencies_manifest_line_is_also_discounted(self) -> None:
        # pixi also prints `PyPI Dependencies: <pkg>` single-package listings; those name a tool
        # without running it just the same.
        log = (
            "  PyPI Dependencies: mypy\n"
            "##[error]The process '/home/runner/.pixi/bin/pixi' failed with exit code 1\n"
        )

        self.assertNotEqual(classify_ci_log(log)["failure_class"], "python_type_check")


class AMypyThatActuallyRanIsUntouched(unittest.TestCase):
    """The guard. Discounting the manifest line must not blind the rule to real type errors."""

    def test_a_real_mypy_error_is_still_a_python_type_check(self) -> None:
        log = (
            "Run mypy .\n"
            'src/pkg/mod.py:12: error: Incompatible return value type (got "int", '
            'expected "str")  [return-value]\n'
            "Found 1 error in 1 file (checked 20 source files)\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "python_type_check")

    def test_a_manifest_line_next_to_a_real_mypy_failure_still_carries(self) -> None:
        # The manifest line only loses its witness when it is the ONLY thing the rule has. A run
        # that both declares mypy AND fails a real type check is still a python_type_check.
        log = (
            "       Dependencies: python, numpy, mypy, scipy-stubs\n"
            'src/pkg/mod.py:8: error: Need type annotation for "items"  [var-annotated]\n'
            "Found 1 error in 1 file (checked 12 source files)\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "python_type_check")


if __name__ == "__main__":
    unittest.main()
