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


class AProxyLoggingItsOwnClientDisconnectsIsNotAnOutage(unittest.TestCase):
    """A last-resort "the network flaked" must not outrank the runner naming the error.

    `istio/istio` run 29259965783 is a Dependabot job. It died because the updater errored,
    and the runner says so: `##[error]Dependabot encountered an error performing the update`.
    PatchRail answered `network_transient_failure` at 0.53 on one signal -- `connection reset
    by peer` -- logged thirteen times by the MITM proxy Dependabot runs *by design*, at its
    own client. Sandbox chatter, not the job's network failing.

    `AMBIGUOUS_NETWORK_PATTERNS` alone cannot catch it. The deferral finds an alternative and
    takes it: `node_dependency_install`, matched by the bare word `lockfile` inside the JSON
    config key `"gradle-lockfile-updater"` that Dependabot echoes. The noise guard then
    rejects that mention-only rule and bounces the verdict straight back to the network one,
    which stands. So the check runs last, on the settled verdict.
    """

    # Trimmed from the real `gh run view 29259965783 --repo istio/istio --log-failed`, kept in
    # `gh` wire form: the proxy's resets, the config key the deferral trips over, the ##[error].
    ISTIO_DEPENDABOT_LOG = (
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:08.6869343Z Pulling image "
        "ghcr.io/dependabot/proxy:v2.0.20260616220547\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:14.7172758Z updater | INFO <job_1458843111> "
        'Job definition: {"job":{"package-manager":"gradle-lockfile-updater"}}\n'
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:21.0246300Z   proxy | WARN: Cannot write TLS "
        "chunked EOF from mitm'd client: write tcp 172.19.0.2:1080->172.19.0.3:47950: write: "
        "connection reset by peer\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:25.2981138Z   proxy | WARN: Cannot write TLS "
        "response body from mitm'd client: write tcp 172.19.0.2:1080->172.19.0.3:36296: write: "
        "connection reset by peer\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:49.7351339Z ##[error]Dependabot encountered "
        "an error performing the update\n"
    )

    def test_the_real_istio_log_reports_the_error_the_runner_named(self) -> None:
        result = classify_ci_log(self.ISTIO_DEPENDABOT_LOG)

        # Not a network outage: the only network evidence is the proxy talking to itself.
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])

        # The line the maintainer would have scrolled to, handed back instead.
        self.assertEqual(
            result["runner_errors"],
            ["Dependabot encountered an error performing the update"],
        )

    def test_a_genuine_outage_is_not_downgraded_by_an_annotation(self) -> None:
        # The guard keys on signals that *cannot* prove an outage on their own. A real one
        # trips a terminal signal outside that set -- DNS here -- and keeps its verdict at
        # full confidence even though the runner annotated the failure too.
        log = (
            "##[error]The job failed\n"
            "curl: (6) Could not resolve host: proxy.golang.org\n"
            "Temporary failure in name resolution\n"
            "write: connection reset by peer\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "network_transient_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_ambiguous_signals_still_stand_when_the_runner_named_nothing(self) -> None:
        # Without an annotation to defer to, the transient verdict remains the best reading
        # of the log -- it is the only thing the log gave us. Boilerplate is not an
        # annotation for this purpose: it names no error, so it cannot displace one.
        for tail in ("", "##[error]Process completed with exit code 1.\n"):
            with self.subTest(tail=tail or "no annotation"):
                log = "connection reset by peer\ndial tcp 10.0.0.1:443: i/o timeout\n" + tail
                result = classify_ci_log(log)

                self.assertEqual(result["failure_class"], "network_transient_failure")

    def test_an_annotation_announcing_success_does_not_displace_the_verdict(self) -> None:
        # Composes with the guard above: `✅ Autofix task started.` is not the runner naming
        # an error, so it cannot turn a standing verdict into `unknown` either.
        log = "connection reset by peer\n##[error]✅ Autofix task started.\n"
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "network_transient_failure")


class AnInstallSummaryIsNotAFailedSecurityScan(unittest.TestCase):
    """npm's post-install audit tally is not a scanner, and a named tool is not a failure.

    `withastro/astro` run 29312523125 dies in a build script on Windows -- the runner says
    `##[error]@benchmark/timer#build: command ... exited (-1073741502)` -- and PatchRail
    answered `security_scan_failure` at 0.71. The whole of the evidence was the block npm
    prints at the end of a *successful* install:

        1 high severity vulnerability
        To address all issues, run:
          npm audit fix --force

    No scan ran. `npm audit` was suggested, never invoked, and the tally counts advisories
    in the dependency tree -- it is what a green install looks like.

    Silencing that block alone is not enough, and the log proves why: the verdict fell
    straight through to `javascript_lint` at 0.89, on `eslint`, `biome` and `prettier` read
    off pnpm's install listing (`+ eslint 10.4.0 (10.7.0 is available)`). Those linters were
    downloaded, not run. A rule that never watched its tool fail is a last resort, and a last
    resort is not worth making when the runner has already named what broke.
    """

    # Trimmed from the real `gh run view 29312523125 --repo withastro/astro --log-failed`,
    # kept in `gh` wire form -- job/step columns and timestamp -- because that prefix is
    # exactly what defeats a `^`-anchored pattern. Four things in order: npm's audit tally,
    # pnpm's install listing, turbo's script echo, and the error the runner actually reported.
    ASTRO_SMOKE_LOG = (
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:53:43.5Z "
        "added 1 package, and audited 2 packages in 8s\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:53:43.5Z "
        "1 high severity vulnerability\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:53:43.5Z "
        "To address all issues, run:\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:53:43.5Z "
        "  npm audit fix --force\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:53:43.5Z "
        "Run `npm audit` for details.\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:55:01.1Z "
        "+ @biomejs/biome 2.4.10 (2.5.3 is available)\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:55:01.1Z "
        "+ eslint 10.4.0 (10.7.0 is available)\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:55:01.1Z "
        "+ prettier 3.9.0 (3.9.5 is available)\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:56:12.3Z "
        "##[group]@astrojs/yaml2ts:build\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:56:12.3Z $ tsc -b\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:57:09.4Z "
        "##[error]@benchmark/timer#build: command (D:\\a\\astro\\astro\\benchmark\\packages"
        "\\timer) pnpm.CMD run build exited (-1073741502)\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:57:09.5Z "
        "[ELIFECYCLE] Command failed with exit code 3221225794.\n"
        "Test (Smoke): windows-2025 (node@22)\tUNKNOWN STEP\t2026-07-14T06:57:09.5Z "
        "##[error]Process completed with exit code 127.\n"
    )

    def test_the_real_astro_log_reports_the_error_the_runner_named(self) -> None:
        result = classify_ci_log(self.ASTRO_SMOKE_LOG)

        # Neither a failed scan nor a lint failure: nothing in this log ever ran either one.
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])

        # The line the maintainer would have scrolled to, handed back instead. The runner's
        # stock `exit code 127` line is boilerplate and stays filtered out.
        self.assertEqual(
            result["runner_errors"],
            [
                "@benchmark/timer#build: command (D:\\a\\astro\\astro\\benchmark\\packages"
                "\\timer) pnpm.CMD run build exited (-1073741502)"
            ],
        )

    def test_a_scan_that_really_ran_and_failed_keeps_its_verdict(self) -> None:
        # The guard is for the tally, not for the scanners. Each of these is a scan that ran
        # and failed -- off the install block, and with the runner annotating the job too --
        # and each must still come back a failed scan.
        for real in (
            "Found known vulnerabilities in 3 packages",
            "CRITICAL: Vulnerability found in openssl",
            "trivy: Severity: HIGH  Package: libssl3",
        ):
            with self.subTest(real):
                result = classify_ci_log(f"##[error]The job failed\n{real}\n")

                self.assertEqual(result["failure_class"], "security_scan_failure")

    def test_a_scanners_own_finding_is_not_mistaken_for_npms_tally(self) -> None:
        # npm's tally is the whole line -- a count and nothing else. A scanner reporting a
        # finding says more than that on the same line, and is still a failed scan at full
        # confidence: the count line is anchored, so this never reads as the tally.
        log = "##[error]The job failed\nHigh severity vulnerability found in openssl (CVE-2026-1234)\n"
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "security_scan_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_a_typecheck_that_really_failed_still_wins_over_the_annotation(self) -> None:
        # The `$ tsc -b` echo is an invocation, so the rule may still stand on it as a last
        # resort -- but when tsc actually fails, it witnesses off the echo and the runner's
        # annotation cannot displace it.
        log = (
            "$ tsc -b\n"
            "src/index.ts(3,7): error TS2345: Argument of type 'string' is not assignable.\n"
            "##[error]Process completed with exit code 2.\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "typescript_typecheck")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_a_last_resort_verdict_still_stands_when_the_runner_named_nothing(self) -> None:
        # The new guard defers to the runner, so with no annotation to defer to the last
        # resort remains the best reading of the log -- it is the only thing the log gave us.
        # Boilerplate names no error, so it cannot displace one either.
        for tail in ("", "##[error]Process completed with exit code 1.\n"):
            with self.subTest(tail=tail or "no annotation"):
                log = "Run eslint .\n+ eslint 10.4.0\n" + tail
                result = classify_ci_log(log)

                self.assertEqual(result["failure_class"], "javascript_lint")


class AnAuditThatFailedIsAScanAndNotABrokenInstall(unittest.TestCase):
    """npm reports a failed audit through its error channel, and never says `npm audit`.

    The mirror image of the tally above. There, a scan that never ran was read as one that
    failed; here, a scan that really ran and really failed was read as a broken install.

    npm's audit-error path (`lib/utils/audit-error.js`) logs the registry's reply and then
    dies with `audit endpoint returned an error`. The code comes back as an `EAUDIT*`, the
    detail as `npm ERR! audit ...` (npm <=9) or `npm error audit ...` (npm >=10). Not one of
    those lines contains the words `npm audit`, which was the only npm signal
    `security_scan_failure` knew -- so the only rule left matching was the bare `npm ERR!`
    of `node_dependency_install`, at 0.53. A private registry that cannot serve audit
    requests -- Artifactory, Verdaccio, GitHub Packages, the ordinary reason this fails in
    CI -- was handed back to the maintainer as a dependency install they needed to fix.

    pnpm fails the same way and lost for a different reason: `ERR_PNPM_AUDIT_NO_LOCKFILE`
    was claimed by the install rule's broad `ERR_PNPM` prefix, which then outscored the
    scanner two signals to one -- the second being `lockfile`, the bare noun that is already
    mention-only precisely because it asserts nothing. With the prefix no longer claiming
    the audit family, the tie falls to the rule that watched something fail.

    The logs below are the tools' own output -- npm 11.12.1 and pnpm 11.0.8, run against a
    registry with no audit endpoint -- and the npm <=9 wording as reported in #335, wrapped
    in the runner's wire form (job/step columns and timestamp), because that prefix is
    exactly what defeats a `^`-anchored pattern.
    """

    NPM_LEGACY = (
        "audit\taudit\t2026-07-14T10:31:02.1234567Z ##[group]Run npm audit --audit-level=high\n"
        "audit\taudit\t2026-07-14T10:31:04.9876543Z npm WARN audit 404 Not Found - POST "
        "https://npm.pkg.github.com/-/npm/v1/security/advisories/bulk\n"
        "audit\taudit\t2026-07-14T10:31:04.9976543Z npm ERR! code EAUDIT\n"
        "audit\taudit\t2026-07-14T10:31:05.0012345Z npm ERR! audit Your configured registry "
        "does not support audit requests\n"
        "audit\taudit\t2026-07-14T10:31:05.1122334Z ##[error]Process completed with exit code 1.\n"
    )

    NPM_CURRENT = (
        "audit\taudit\t2026-07-14T16:14:02.0020000Z npm warn audit 404 Not Found - POST "
        "https://registry.npmjs.org/-/no-such-registry/-/npm/v1/security/advisories/bulk\n"
        "audit\taudit\t2026-07-14T16:14:02.0030000Z npm error audit endpoint returned an error\n"
        "audit\taudit\t2026-07-14T16:14:02.0040000Z ##[error]Process completed with exit code 1.\n"
    )

    PNPM = (
        "audit\taudit\t2026-07-14T10:31:02.1000000Z ##[group]Run pnpm audit --audit-level=high\n"
        "audit\taudit\t2026-07-14T10:31:04.2000000Z [ERR_PNPM_AUDIT_NO_LOCKFILE] No "
        "pnpm-lock.yaml found: Cannot audit a project without a lockfile\n"
        "audit\taudit\t2026-07-14T10:31:04.3000000Z ##[error]Process completed with exit code 1.\n"
    )

    def test_a_failed_audit_is_a_failed_security_scan(self) -> None:
        for name, log in (
            ("npm <=9 (EAUDIT)", self.NPM_LEGACY),
            ("npm >=10 (audit endpoint returned an error)", self.NPM_CURRENT),
            ("pnpm (ERR_PNPM_AUDIT_NO_LOCKFILE)", self.PNPM),
        ):
            with self.subTest(client=name):
                result = classify_ci_log(log)

                self.assertEqual(result["failure_class"], "security_scan_failure")

    def test_a_broken_install_is_still_a_broken_install(self) -> None:
        # The narrowness this fix has to keep: `npm ERR!` on its own means what it has always
        # meant. Only npm's *audit* channel was taken away from it, and the install codes --
        # including every pnpm code that is not an audit -- are untouched.
        for name, log in (
            (
                "npm ERESOLVE",
                "install\tinstall\t2026-07-14T10:00:00.0000000Z npm ERR! code ERESOLVE\n"
                "install\tinstall\t2026-07-14T10:00:00.1000000Z npm ERR! ERESOLVE unable to "
                "resolve dependency tree\n",
            ),
            (
                "pnpm frozen lockfile",
                "install\tinstall\t2026-07-14T10:00:00.0000000Z ERR_PNPM_OUTDATED_LOCKFILE "
                'Cannot install with "frozen-lockfile" because pnpm-lock.yaml is not up to '
                "date\n",
            ),
            (
                "pnpm peer deps",
                "install\tinstall\t2026-07-14T10:00:00.0000000Z ERR_PNPM_PEER_DEP_ISSUES Unmet "
                "peer dependencies\n",
            ),
        ):
            with self.subTest(case=name):
                result = classify_ci_log(log)

                self.assertEqual(result["failure_class"], "node_dependency_install")

    def test_an_install_that_merely_suggests_an_audit_is_not_a_failed_scan(self) -> None:
        # The #327 guard, restated from the other side: npm's post-install tally suggests
        # `npm audit fix` on an install that then failed for an unrelated reason. Suggesting a
        # scan is not running one, and teaching the scanner npm's error channel must not
        # resurrect the tally -- `npm warn audit` is npm reporting a scan it SKIPPED.
        log = (
            "install\tinstall\t2026-07-14T10:00:00.0000000Z npm warn audit 1 high severity "
            "vulnerability\n"
            "install\tinstall\t2026-07-14T10:00:00.1000000Z 1 high severity vulnerability\n"
            "install\tinstall\t2026-07-14T10:00:00.2000000Z To address all issues, run:\n"
            "install\tinstall\t2026-07-14T10:00:00.3000000Z   npm audit fix --force\n"
            "install\tinstall\t2026-07-14T10:00:00.4000000Z npm ERR! code ERESOLVE\n"
            "install\tinstall\t2026-07-14T10:00:00.5000000Z npm ERR! ERESOLVE unable to resolve "
            "dependency tree\n"
        )
        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "node_dependency_install")


class ADependencyNamedInDependabotsJobDefinitionWasNeverRun(unittest.TestCase):
    """The updater's own bookkeeping names half the dependency tree. None of it ran.

    `sveltejs/svelte` run 29330826741 is a Dependabot security update. It died inside the
    updater, and the runner named the error outright: `##[error]Dependabot encountered an
    error performing the update`. PatchRail answered `javascript_lint` at 0.71 and told the
    Svelte maintainers to go run `pnpm lint`.

    No linter ran. `eslint` matched 59 times in that log and 58 were already discounted --
    registry URLs the MITM proxy fetched, which read as path tokens. The 59th was the
    updater's JOB DEFINITION: one line of JSON, echoed at startup, listing every dependency
    the updater may touch and every PR already open (`{"pr-number":17594,"dependencies":
    [{"dependency-name":"eslint",...}]}`). One witness is all it takes to carry a verdict.

    It is the same blob #333 found `lockfile` inside, which it treated one failure class at a
    time -- so this is treated where the evidence is read instead: a record the updater files
    under its own job id is bookkeeping, and `never_invoked` answers `unknown`, which hands
    the runner's line back.

    The guards below are the reason this is not a filter for the word `updater`: what the
    updater FORWARDS from a subprocess (`npm ERR! ERESOLVE`) carries no job id, and a record
    it files at an error level is an error it is reporting. Both still witness.
    """

    # Trimmed from the real `gh run view 29330826741 --repo sveltejs/svelte --log-failed`, kept
    # in `gh` wire form (job/step columns and timestamp): the job definition, two of the proxy's
    # registry fetches, and the way the updater actually died.
    SVELTE_DEPENDABOT_LOG = (
        "Dependabot\tUNKNOWN STEP\t﻿2026-07-14T11:59:23.4463381Z Current runner version: "
        "'2.335.1'\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:49.9174780Z updater | 2026/07/14 11:59:49 "
        'INFO <job_1460286594> Job definition: {"job":{"command":"security","allowed-updates":'
        '[{"dependency-type":"direct","update-type":"all"}],"dependencies":["postcss"],'
        '"existing-pull-requests":[{"pr-number":16988,"dependencies":[{"dependency-name":'
        '"playwright","dependency-version":"1.55.1","directory":"/"}]},{"pr-number":17594,'
        '"dependencies":[{"dependency-name":"eslint","dependency-version":"9.26.0","directory":'
        '"/"}]}],"experiments":{"gradle-lockfile-updater":true},"package-manager":'
        '"npm_and_yarn","security-updates-only":true}}\n'
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:49.9201110Z updater | 2026/07/14 11:59:49 "
        "INFO <job_1460286594> Detected package manager: pnpm\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:58.2852552Z   proxy | 2026/07/14 11:59:58 "
        "[117] GET https://registry.npmjs.org:443/eslint\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:58.3633599Z   proxy | 2026/07/14 11:59:58 "
        "[127] GET https://registry.npmjs.org:443/prettier\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:04.6492421Z Dependabot encountered '1' "
        "error(s) during execution, please check the logs for more details.\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:07.2301415Z ##[error]Dependabot encountered "
        "an error performing the update\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:07.2419112Z Post job cleanup.\n"
    )

    # The same rendering istio's updater uses -- a level and a job id, no clock (#333).
    ISTIO_STYLE_RECORD = (
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:14.7172758Z updater | INFO "
        '<job_1458843111> Job definition: {"dependency-name":"eslint","experiments":'
        '{"gradle-lockfile-updater":true}}\n'
        "Dependabot\tUNKNOWN STEP\t2026-07-13T14:55:21.0246300Z ##[error]Dependabot encountered "
        "an error performing the update\n"
    )

    # What the updater FORWARDS from the package manager it drives: no job id, so it stands.
    FORWARDED_SUBPROCESS_FAILURE = (
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:49.9174780Z updater | 2026/07/14 11:59:49 "
        "INFO <job_1460286594> Starting job processing\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:01.1000000Z updater | npm ERR! code "
        "ERESOLVE\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:01.2000000Z updater | npm ERR! ERESOLVE "
        "unable to resolve dependency tree\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:07.2301415Z ##[error]Dependabot encountered "
        "an error performing the update\n"
    )

    # A failure the updater files ITSELF, at an error level. Reporting, not enumerating.
    UPDATER_FILES_AN_ERROR = (
        "Dependabot\tUNKNOWN STEP\t2026-07-14T11:59:49.9174780Z updater | 2026/07/14 11:59:49 "
        'INFO <job_1460286594> Job definition: {"dependency-name":"eslint"}\n'
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:04.6000000Z updater | 2026/07/14 12:00:04 "
        "ERROR <job_1460286594> eslint reported errors: no-unused-vars\n"
        "Dependabot\tUNKNOWN STEP\t2026-07-14T12:00:07.2301415Z ##[error]Dependabot encountered "
        "an error performing the update\n"
    )

    # A linter that really failed, in an ordinary job. Nothing here changes for it.
    GENUINE_LINT_FAILURE = (
        "lint\tlint\t2026-07-14T09:00:00.0000000Z ##[group]Run pnpm lint\n"
        "lint\tlint\t2026-07-14T09:00:04.0000000Z /home/runner/work/app/src/main.ts\n"
        "lint\tlint\t2026-07-14T09:00:04.1000000Z   12:5  error  'x' is assigned a value but "
        "never used  no-unused-vars\n"
        "lint\tlint\t2026-07-14T09:00:04.2000000Z eslint found 1 error\n"
        "lint\tlint\t2026-07-14T09:00:04.3000000Z ##[error]Process completed with exit code 1.\n"
    )

    def test_the_job_definition_does_not_carry_a_lint_verdict(self) -> None:
        result = classify_ci_log(self.SVELTE_DEPENDABOT_LOG)
        jsonschema.validate(instance=result, schema=_SCHEMA)
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])

    def test_the_runners_own_error_is_handed_back_instead(self) -> None:
        result = classify_ci_log(self.SVELTE_DEPENDABOT_LOG)
        self.assertEqual(
            result["runner_errors"],
            ["Dependabot encountered an error performing the update"],
        )

    def test_the_clockless_rendering_is_bookkeeping_too(self) -> None:
        result = classify_ci_log(self.ISTIO_STYLE_RECORD)
        self.assertEqual(result["failure_class"], "unknown")

    def test_a_subprocess_the_updater_forwards_still_witnesses(self) -> None:
        result = classify_ci_log(self.FORWARDED_SUBPROCESS_FAILURE)
        self.assertEqual(result["failure_class"], "node_dependency_install")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_an_error_the_updater_files_still_witnesses(self) -> None:
        result = classify_ci_log(self.UPDATER_FILES_AN_ERROR)
        self.assertEqual(result["failure_class"], "javascript_lint")

    def test_a_linter_that_really_failed_is_untouched(self) -> None:
        result = classify_ci_log(self.GENUINE_LINT_FAILURE)
        self.assertEqual(result["failure_class"], "javascript_lint")
        self.assertGreaterEqual(result["confidence"], 0.7)


if __name__ == "__main__":
    unittest.main()
