"""A PHPUnit assertion that failed is not a Composer failure.

Grounded in a real failed run of symfony/symfony (`Unit Tests (8.3)`, run 29551386048), where
`composer update` installed everything cleanly, the suite then ran, and one assertion in
src/Symfony/Component/ErrorHandler failed:

  Testing .../src/Symfony/Component/ErrorHandler
  There was 1 failure:
  1) Symfony\\Component\\ErrorHandler\\Tests\\Error\\FatalErrorTest::testGetTraceWithoutTraceArgs
  Failed asserting that an array has the key 'args'.
  FAILURES!
  Tests: 128, Assertions: 379, Failures: 1, Skipped: 2.
  ##[error]KO src/Symfony/Component/ErrorHandler
  ##[error]Process completed with exit code 1.

PatchRail reported `php_composer_failure` at 0.95 -- sending a maintainer to debug dependency
installation for a failed assertion. Composer never failed: it locked, installed and generated
the autoloader, all green. The rule was carrying PHPUnit's own verdict markers (`FAILURES!`,
`Failed asserting`, the `Tests: ... Failures:` summary) plus the bare `composer install` /
`composer update` commands, which run in nearly every PHP job whether or not anything breaks.

PatchRail has no PHP test-failure class, so the honest answer is `unknown` -- the same ceiling
it reports for the ruff grep-gate and the svelte updater. `unknown` is a limit, not a diagnosis,
and it does not send anyone to the wrong place. The committed excerpt of the run is at
examples/real-world/symfony-29551386048-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "symfony-29551386048-excerpt.log"
)

# The failure, reduced: composer succeeds, the suite runs, one assertion fails.
PHPUNIT_ASSERTION_FAILED = """\
##[group]composer update
  - Installing symfony/phpunit-bridge (9.6.99): Symlinking
Generating optimized autoload files
##[endgroup]
Testing src/Symfony/Component/ErrorHandler
There was 1 failure:
1) Symfony\\Component\\ErrorHandler\\Tests\\Error\\FatalErrorTest::testGetTraceWithoutTraceArgs
Failed asserting that an array has the key 'args'.
FAILURES!
Tests: 128, Assertions: 379, Failures: 1, Skipped: 2.
##[error]Process completed with exit code 1.
"""


class APhpunitAssertionIsNotAComposerFailure(unittest.TestCase):
    def test_the_symfony_run_is_not_a_php_composer_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "php_composer_failure")

    def test_the_symfony_run_lands_on_unknown(self) -> None:
        # Not merely "not composer": with no PHP test-failure class, `unknown` is the honest
        # ceiling -- and a maintainer sent nowhere is better than one sent to their lockfile.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_assertion_failure_is_not_a_composer_failure(self) -> None:
        result = classify_ci_log(PHPUNIT_ASSERTION_FAILED)

        self.assertNotEqual(result["failure_class"], "php_composer_failure")


class AComposerFailureThatActuallyHappenedIsUntouched(unittest.TestCase):
    """The guards. Narrowing the rule must not blind it to the dependency failures it is for."""

    def test_an_unresolvable_requirement_is_still_a_php_composer_failure(self) -> None:
        log = (
            "Run composer install --no-interaction --prefer-dist\n"
            "Your requirements could not be resolved to an installable set of packages.\n"
            "Problem 1\n"
            "  - Root composer.json requires php ^8.3 but your php version (8.2.14) does not "
            "satisfy that requirement.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "php_composer_failure")

    def test_a_lockfile_drift_is_still_a_php_composer_failure(self) -> None:
        log = (
            "Run composer install --no-interaction --prefer-dist\n"
            "Warning: The lock file is not up to date with the latest changes in composer.json.\n"
            '- Required package "symfony/console" is not present in the lock file.\n'
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "php_composer_failure")


if __name__ == "__main__":
    unittest.main()
