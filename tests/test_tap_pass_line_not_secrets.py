"""A phrase read off a PASSING TAP line is not evidence of a secrets failure.

Grounded in a real failed run of discourse/discourse (`Plugins QUnit`, run 29572043439). Six
chat-component assertions timed out and the suite reported `# fail  6`, but PatchRail answered
`secrets_or_permissions_failure` at 0.53. Its one and only witness was a test that PASSED:

  ok 1523 [564 ms] - poll - Acceptance: Poll Builder - polls are disabled:
    regular user - insufficient permissions

`insufficient permissions` is the scenario that test asserts the poll UI handles gracefully --
the title of a green `ok` line, not a credential the job lacked. Reported verbatim it sent a
maintainer to audit repository secrets over a passing test.

PatchRail has no browser-QUnit test-failure class, so the honest answer is `unknown` -- the same
ceiling it reports for the ruff grep-gate, the svelte updater and the symfony assertion. The
committed excerpt of the run is at examples/real-world/discourse-29572043439-excerpt.log; see
docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "discourse-29572043439-excerpt.log"
)

# The failure, reduced to TAP: several tests pass (one of them named after an "insufficient
# permissions" scenario), then real assertions fail, and the summary counts the failures.
TAP_WITH_PASSING_PERMISSIONS_TITLE = """\
ok 1521 [42 ms] - poll - Acceptance: Poll Builder - a regular user can create a poll
ok 1523 [564 ms] - poll - Acceptance: Poll Builder - polls are disabled: regular user - insufficient permissions
not ok 818 [60064 ms] - chat - Component | ChatChannel | screen reader announcements
not ok 1541 [60057 ms] - chat - Unit | Components | presence gating: own messages
# tests 1559
# pass  1551
# fail  6
"""


class APassingTapTitleIsNotASecretsFailure(unittest.TestCase):
    def test_the_discourse_run_is_not_a_secrets_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "secrets_or_permissions_failure")

    def test_the_discourse_run_lands_on_unknown(self) -> None:
        # Not merely "not secrets": with no browser-QUnit test class, `unknown` is the honest
        # ceiling -- and a maintainer sent nowhere beats one sent to `gh secret list`.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_tap_report_is_not_a_secrets_failure(self) -> None:
        result = classify_ci_log(TAP_WITH_PASSING_PERMISSIONS_TITLE)

        self.assertNotEqual(result["failure_class"], "secrets_or_permissions_failure")


class ASecretsFailureThatActuallyHappenedIsUntouched(unittest.TestCase):
    """The guard. Discounting a green TAP title must not blind the rule to real ones."""

    def test_insufficient_permissions_on_an_error_line_still_fires(self) -> None:
        log = (
            "##[error] The token provided has insufficient permissions to read "
            "the repository.\n"
            "Error: Process completed with exit code 1.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "secrets_or_permissions_failure")

    def test_a_denied_github_actions_push_is_still_a_secrets_failure(self) -> None:
        log = "##[error]remote: Permission to org/repo.git denied to github-actions[bot].\n"

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "secrets_or_permissions_failure")


if __name__ == "__main__":
    unittest.main()
