"""A limit a job declares is not a limit a job hit.

Every other `ci_job_timeout` pattern is a timeout that HAPPENED -- a runner killing a job,
an operation cancelled, a step that ran longer than its budget. `timeout-minutes` is none of
those: it is the field a workflow writes to set the budget, echoed back by Actions when it
prints the step config, on green runs too. Our own `docs/fix/ci-job-timeout.md` names it as
the knob you RAISE after a timeout -- which is precisely why it cannot be evidence of one.

envoyproxy/envoy's coverage run 29363920524 failed a coverage gate: one directory out of 430
slipped under its threshold (`source/common/quic: 93.2%`, threshold 93.5%), with overall
coverage at a healthy 96.7%. PatchRail answered `ci_job_timeout` at 0.53, on a single
witness -- the config line the runner echoed 16 minutes before the job died:

    timeout-minutes: 180

So a maintainer whose coverage had slipped by three tenths of a point was sent to go raise a
time limit their job never came near.

With the declaration no longer a witness, the log answers with the class it always had the
evidence for: `code_coverage_threshold`, on `coverage threshold`. Both classes had scored one
pattern each and the tie went to whichever was declared first in the rule table.

The lines below are verbatim from `gh run view 29363920524 --repo envoyproxy/envoy
--log-failed`, kept in their `gh` wire form (job/step columns and timestamp), because that
prefix is exactly what a line-anchored pattern has to survive. The full excerpt is committed
at `examples/real-world/envoy-29363920524-excerpt.log`.
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

_JOB = "Check (pr/45851/main@fa77139) / Coverage / ./ci/do_ci.sh coverage\tUNKNOWN STEP\t"

ENVOY_COVERAGE_LOG = (
    f"{_JOB}2026-07-14T19:59:44.8931887Z   timeout-minutes: 180\n"
    f"{_JOB}2026-07-14T19:59:44.8932240Z   trusted: false\n"
    f"{_JOB}2026-07-14T20:15:43.1029145Z FAILED: Directories not meeting coverage thresholds:\n"
    f"{_JOB}2026-07-14T20:15:43.1029532Z   ✗ source/common/quic: 93.2% (threshold: 93.5%)\n"
    f"{_JOB}2026-07-14T20:15:43.1030162Z Overall Coverage: 96.7%\n"
    f"{_JOB}2026-07-14T20:16:00.0150949Z Run failed\n"
    f"{_JOB}2026-07-14T20:16:00.0153862Z ##[error]Process completed with exit code 1.\n"
)


class TimeoutMinutesDeclarationTests(unittest.TestCase):
    def test_declared_timeout_does_not_outrank_the_failure_that_happened(self) -> None:
        result = classify_ci_log(ENVOY_COVERAGE_LOG)

        self.assertNotEqual(result["failure_class"], "ci_job_timeout")
        self.assertEqual(result["failure_class"], "code_coverage_threshold")
        jsonschema.validate(result, _SCHEMA)

    def test_the_config_echo_alone_carries_no_verdict(self) -> None:
        """The single line that carried the wrong verdict, on its own."""
        for line in (
            "  timeout-minutes: 180\n",
            "  timeout-minutes: 5\n",
            "    timeout-minutes: ${{ inputs.timeout }}\n",
        ):
            with self.subTest(line=line.strip()):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "unknown")
                self.assertEqual(result["signals"], [])

    def test_a_job_that_really_timed_out_is_still_a_timeout(self) -> None:
        """The cure must not eat the disease: a job that ran long still lands."""
        for line in (
            "The job running on runner GitHub Actions 12 has exceeded the maximum "
            "execution time of 360 minutes.\n",
            "##[error]The operation was canceled.\n",
            "ERROR: Job failed: execution took longer than 1h0m0s seconds\n",
            "Terminating due to timeout: ran longer than the maximum time of 90 minutes\n",
        ):
            with self.subTest(line=line.strip()[:48]):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "ci_job_timeout")
                self.assertTrue(result["signals"])

    def test_prose_about_timeout_minutes_still_counts(self) -> None:
        """Only the `key:` form is disqualified; a job talking about its limit is not."""
        result = classify_ci_log(
            "Build step hit the ceiling set by timeout-minutes and was killed\n"
        )

        self.assertEqual(result["failure_class"], "ci_job_timeout")
        self.assertEqual(result["signals"], [r"\btimeout-minutes\b(?!\s*:)"])


if __name__ == "__main__":
    unittest.main()
