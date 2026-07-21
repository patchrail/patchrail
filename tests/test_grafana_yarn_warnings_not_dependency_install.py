"""A yarn install that finishes with warnings did not fail, and a checkout that recovered
did not fail either.

grafana/grafana's lint-knip job (run 29806261731) installed its workspace cleanly -- yarn
Berry printed `YN0000: Done with warnings` and `Completed`, with peer-dependency *warnings*
(`YN0086`, `YN0002`, `YN0060`) along the way -- and then failed on `knip` (unused
dependencies) and a `yarn constraints` check. Two of those signals used to carry a verdict on
their own:

  * `YN\\d{4}`, read off the benign peer warnings, plus `peer dep`, scored
    `node_dependency_install` at 0.71 -- handing the maintainer `corepack pnpm install` (the
    wrong package manager) to reproduce a working install.
  * `error: pathspec '...' did not match`, from a fork/enterprise dual-checkout that missed
    the PR branch and fell back to `main` ("Checkout succeeded, breaking retry loop"), scored
    `git_checkout_failure` -- a checkout that succeeded.

Both are now discounted: a bare `YNxxxx` code is a benign warning that cannot stand once the
runner annotated a failure or the run announced success, and a pathspec miss the log recovers
from does not witness. The real cause is handed back through the runner's own annotation.

The lines below are in the `gh run view --log-failed` wire form (job/step columns + ISO-8601
timestamp) the classifier has to survive, distilled from the committed
`runs/2026-07-21-0943-oss-dogfood-ext2/logs/grafana-lint-29806261731.log`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from patchrail.ci.classify import classify_ci_log

_SCHEMA = json.loads(
    (
        Path(__file__).resolve().parents[1]
        / "src"
        / "patchrail"
        / "schemas"
        / "ci-result.v1.schema.json"
    ).read_text(encoding="utf-8")
)

GRAFANA_LINT_KNIP = (
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:24.9114158Z Cloning into '../grafana-enterprise'...\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:30.9181199Z Clone succeeded on attempt 1\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:30.9266291Z error: pathspec "
    "'hugoh/add-enable-disable-app-plugin-e2e-tests' did not match any file(s) known to git\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:31.1650481Z Already on 'main'\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:31.1656459Z checked out main\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:31.1657181Z Checkout succeeded, breaking retry loop\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:46.8121647Z YN0086: Some peer dependencies are "
    "incorrectly met by your project; run yarn explain peer-requirements for details.\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:12:46.7300317Z YN0000: Completed in 0s 791ms\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:13:28.5276227Z YN0000: Done with warnings in 42s 603ms\n"
    "lint-knip\tUNKNOWN STEP\t2026-07-21T06:13:47.2943048Z ##[error]Process completed with exit code 1.\n"
    "Validate yarn install\tUNKNOWN STEP\t2026-07-21T06:14:41.6277104Z YN0000: Done with warnings in 2m 16s\n"
    "Validate yarn install\tUNKNOWN STEP\t2026-07-21T06:14:43.6235373Z ##[error]Yarn constraints check "
    "failed. Run 'yarn constraints --fix' locally, commit the changes, and push again.\n"
    "Validate yarn install\tUNKNOWN STEP\t2026-07-21T06:14:43.6237469Z ##[error]Process completed with exit code 1.\n"
)


class GrafanaYarnWarningsTests(unittest.TestCase):
    def test_grafana_yarn_warnings_and_recovered_checkout_are_unknown(self) -> None:
        result = classify_ci_log(GRAFANA_LINT_KNIP)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotEqual(result["failure_class"], "node_dependency_install")
        self.assertNotEqual(result["failure_class"], "git_checkout_failure")
        # The honest answer hands back the runner's own verdict rather than a guess.
        self.assertIn("runner_errors", result)
        self.assertTrue(any("constraints" in line for line in result["runner_errors"]))
        jsonschema.validate(result, _SCHEMA)

    def test_bare_yarn_warning_codes_alone_carry_no_install_verdict(self) -> None:
        """`YNxxxx` warnings beside a runner-annotated failure are noise, not a broken install."""
        log = (
            "YN0002: missing peer dep for @types/react\n"
            "YN0060: react is listed by your project with version 19.0.0\n"
            "YN0000: Done with warnings\n"
            "##[error]Process completed with exit code 1.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "unknown")

    def test_recovered_pathspec_checkout_does_not_witness_a_failure(self) -> None:
        """A checkout that misses a ref then recovers cannot carry a verdict once the runner
        names the real cause elsewhere (grafana's `Yarn constraints check failed`).

        The recovery guard stops the pathspec miss from *witnessing*, so the unwitnessed
        `git_checkout_failure` yields to the runner's own annotation instead of standing.
        """
        for recovery in (
            "Already on 'main'",
            "Switched to branch 'main'",
            "HEAD is now at 1a2b3c4 fix",
            "Checkout succeeded, breaking retry loop",
        ):
            log = (
                "error: pathspec 'feature/x' did not match any file(s) known to git\n"
                f"{recovery}\n"
                "##[error]knip found unused dependencies; run knip --fix.\n"
                "##[error]Process completed with exit code 1.\n"
            )
            with self.subTest(recovery=recovery):
                self.assertEqual(classify_ci_log(log)["failure_class"], "unknown")

    def test_a_real_yarn_install_failure_still_lands(self) -> None:
        """The cure must not eat the disease: a frozen-lockfile break still classifies."""
        log = (
            "yarn install v3.6.0\n"
            "YN0028: The lockfile would have been modified by this install, "
            "which is explicitly forbidden.\n"
            "##[error]Process completed with exit code 1.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "node_dependency_install")
        self.assertTrue(result["signals"])

    def test_a_hard_fail_checkout_still_lands(self) -> None:
        """A pathspec miss with no recovery line after it still witnesses a checkout failure."""
        log = (
            "running git checkout v9.9.9\n"
            "error: pathspec 'v9.9.9' did not match any file(s) known to git\n"
            "##[error]Process completed with exit code 1.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "git_checkout_failure")
        self.assertTrue(result["signals"])


if __name__ == "__main__":
    unittest.main()
