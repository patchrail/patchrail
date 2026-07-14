"""An `unknown` verdict should still hand back the line the runner flagged.

The dead end this closes is a real one: `psf/requests` run 29295524780 failed with a
single `##[error]` line naming the cause outright, and `gh run view --log-failed |
patchrail ci explain` answered `unknown`, `signals: []`, "No high-confidence local
signal found." The maintainer who piped the log in learned nothing they could not have
learned by not running PatchRail at all.

The runner's own annotation is not a classification -- it says where the job died, not
why -- so it is reported as evidence and never promoted to a failure class.
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

# Trimmed from the real `gh run view 29295524780 --repo psf/requests --log-failed`:
# the `dessant/lock-threads` job, whose 46 lines are runner boilerplate plus one
# `##[error]`. Kept in its `gh` wire form -- job/step columns and timestamp -- because
# that prefix is exactly what defeats a `^`-anchored pattern.
REQUESTS_LOCK_THREADS_LOG = (
    "action\tUNKNOWN STEP\t﻿2026-07-14T00:17:41.2063988Z Current runner version: '2.335.1'\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.2110536Z ##[group]Operating System\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.2111619Z Ubuntu\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.2115149Z ##[group]Runner Image\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.7947450Z with:\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.7952316Z   github-token: ***\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.7956098Z ##[endgroup]\n"
    'action\tUNKNOWN STEP\t2026-07-14T00:17:41.9474342Z ##[error]"github-token" length '
    "must be less than or equal to 100 characters long\n"
    "action\tUNKNOWN STEP\t2026-07-14T00:17:41.9688844Z Cleaning up orphan processes\n"
)


class UnknownCarriesTheRunnersOwnError(unittest.TestCase):
    def test_real_gh_log_reports_the_error_actions_annotated(self) -> None:
        result = classify_ci_log(REQUESTS_LOCK_THREADS_LOG)

        # Still honestly unknown: no rule matched, so nothing is invented.
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["confidence"], 0.15)
        self.assertEqual(result["signals"], [])

        # ...but the shrug now carries the one line the maintainer needed.
        self.assertEqual(
            result["runner_errors"],
            ['"github-token" length must be less than or equal to 100 characters long'],
        )

    def test_unknown_result_with_runner_errors_still_matches_the_shipped_schema(
        self,
    ) -> None:
        result = classify_ci_log(REQUESTS_LOCK_THREADS_LOG)
        jsonschema.validate(instance=result, schema=_SCHEMA)

    def test_workflow_command_error_forms_are_read(self) -> None:
        # A step can annotate itself with the `::error::` workflow command, bare or with
        # file/line params -- whose values may themselves contain a colon.
        log = (
            "Run node scripts/check.js\n"
            "::error::config.json is not valid JSON\n"
            "::error file=app.js,line=1,title=Bad: thing::Missing semicolon\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(
            result["runner_errors"],
            ["config.json is not valid JSON", "Missing semicolon"],
        )

    def test_secrets_in_an_annotated_line_are_redacted(self) -> None:
        # Actions masks secrets on the way out, but a log saved to disk need not have
        # been. What we echo back gets the same treatment `patchrail redact` applies.
        log = "##[error]push rejected for token ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        result = classify_ci_log(log)
        self.assertEqual(result["runner_errors"], ["push rejected for token <github-token>"])

    def test_repeated_and_excess_annotations_are_deduplicated_and_capped(self) -> None:
        log = "".join(f"##[error]failure number {i}\n" for i in range(9))
        log += "##[error]failure number 0\n"  # a repeat, as re-run steps produce
        result = classify_ci_log(log)

        runner_errors = result["runner_errors"]
        self.assertEqual(len(runner_errors), 5)
        self.assertEqual(len(set(runner_errors)), 5)
        self.assertEqual(runner_errors[0], "failure number 0")

    def test_a_pathological_annotation_is_truncated(self) -> None:
        log = f"##[error]{'x' * 5000}\n"
        (message,) = classify_ci_log(log)["runner_errors"]
        self.assertEqual(len(message), 300)
        self.assertTrue(message.endswith("…"))

    def test_a_classified_log_is_unchanged(self) -> None:
        # The field belongs to the dead end. A log that classifies already explains
        # itself through `signals`, and its payload must not shift under consumers.
        log = (
            "##[error]Process completed with exit code 1.\n"
            "ERROR: Could not find a version that satisfies the requirement urllib3\n"
            "ERROR: ResolutionImpossible\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "python_dependency_resolution")
        self.assertNotIn("runner_errors", result)

    def test_an_unknown_log_with_no_annotation_omits_the_field(self) -> None:
        result = classify_ci_log("nothing here resembles a failure at all\n")
        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("runner_errors", result)


class BoilerplateAnnotationsAreNotEvidence(unittest.TestCase):
    """The runner's stock annotations say nothing, so they are not handed back.

    Found by piping real failing runs through `ci explain`: `Process completed with exit
    code N.` is in all twelve logs sampled, because the runner emits it for every failing
    step whatever the cause. Reported under "Errors the runner reported" it makes an empty
    answer look like a finding -- the dead end, wearing a suit.
    """

    def test_a_real_log_whose_only_annotations_are_boilerplate_says_nothing(self) -> None:
        # `cilium/cilium` run 29327782563, the job that exists to fail the workflow. Its
        # two `##[error]` lines are the whole of what the runner had to say, and neither
        # says anything. Kept in `gh` wire form, ANSI and all, as it arrives from the pipe.
        log = (
            "Merge Upload and Status / Fail job\tUNKNOWN STEP\t2026-07-14T11:13:20.8486558Z "
            '##[group]Run echo "::error::Workflow failed because one or more jobs failed"\n'
            "Merge Upload and Status / Fail job\tUNKNOWN STEP\t2026-07-14T11:13:20.8488444Z "
            '\x1b[36;1mecho "::error::Workflow failed because one or more jobs failed"\x1b[0m\n'
            "Merge Upload and Status / Fail job\tUNKNOWN STEP\t2026-07-14T11:13:20.9337749Z "
            "##[error]Workflow failed because one or more jobs failed\n"
            "Merge Upload and Status / Fail job\tUNKNOWN STEP\t2026-07-14T11:13:20.9354800Z "
            "##[error]Process completed with exit code 1.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("runner_errors", result)

    def test_any_exit_code_is_boilerplate_not_just_one(self) -> None:
        # `rails/rails` run 29326292505 died on exit code 125, not 1. The number carries no
        # more diagnosis than the word does.
        log = (
            "rails-new-docker\tBuild image\t2026-07-14T10:44:02.8267862Z "
            "##[error]Process completed with exit code 125.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("runner_errors", result)

    def test_boilerplate_does_not_crowd_out_the_line_that_names_the_failure(self) -> None:
        # The cap is five and de-duplication is by exact string, so a matrix of jobs each
        # exiting on a different code would fill it with noise and push the one useful
        # annotation out. The real annotation is `hashicorp/terraform` run 29324807060.
        real = (
            "Currently this PR would target a v1.16 release. Please add a changelog entry "
            "for in the .changes/v1.16 folder."
        )
        log = "".join(f"##[error]Process completed with exit code {code}.\n" for code in range(9))
        log += "##[error]Workflow failed because one or more jobs failed\n"
        log += f"##[error]{real}\n"

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["runner_errors"], [real])

    def test_an_annotation_that_merely_mentions_an_exit_code_is_still_evidence(self) -> None:
        # The filter is for the runner's stock line, not for any line with a number in it.
        # This one is real -- an `elastic/elasticsearch` runner reporting *which* step died
        # and how -- and a maintainer would want it back.
        real = (
            "failed to run script step: command terminated with non-zero exit code: "
            "error executing command [sh -e /__w/_temp/85eed260.sh], exit code 2"
        )
        result = classify_ci_log(f"##[error]{real}\n")

        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["runner_errors"], [real])


class SuccessAnnouncedThroughTheErrorChannelIsNotEvidence(unittest.TestCase):
    """A step is free to route a *success* through the error channel, and some do.

    `oven-sh/bun` run 29324834075 fails with exactly one `##[error]` in 4,709 lines, and
    that line says `✅ Autofix task started.` Reported back as somewhere to "start", it is
    the boilerplate dead end again, reached through content instead of the runner's own
    template. The verdict itself is right and stays put: `unknown` is honest for this log.
    """

    def test_the_real_bun_annotation_is_not_handed_back(self) -> None:
        # In `gh` wire form -- job/step columns and timestamp -- as it arrives from the pipe.
        log = (
            "Format\tUNKNOWN STEP\t2026-07-14T10:19:45.5693633Z ##[error]✅ Autofix task started.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("runner_errors", result)

    def test_a_success_mark_does_not_silence_an_annotation_that_names_a_failure(self) -> None:
        # The guard must not become a checkmark-shaped hole. An annotation that opens with a
        # tick but reports a failure anyway is precisely the line the maintainer needs, so
        # any hint of failure in the line keeps it.
        for real in (
            "✅ 2 passed, ❌ 1 failed",
            "✔ image built, but the upload failed",
            "✅ cache restored — the registry refused the push",
        ):
            with self.subTest(real):
                result = classify_ci_log(f"##[error]{real}\n")
                self.assertEqual(result["runner_errors"], [real])

    def test_a_tick_further_along_the_line_is_not_a_success_announcement(self) -> None:
        # Only a *leading* mark reads as "this line announces a success". A tick reporting
        # one green step inside a line about a red one is not the line announcing itself.
        real = "deploy ✅ staging, production rollout never became ready"
        result = classify_ci_log(f"##[error]{real}\n")

        self.assertEqual(result["runner_errors"], [real])

    def test_a_success_line_does_not_crowd_out_the_annotation_that_names_the_failure(
        self,
    ) -> None:
        real = "config.json is not valid JSON"
        log = f"##[error]✅ Autofix task started.\n##[error]{real}\n"
        result = classify_ci_log(log)

        self.assertEqual(result["runner_errors"], [real])


if __name__ == "__main__":
    unittest.main()
