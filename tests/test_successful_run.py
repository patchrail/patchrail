"""A log that plainly passed should be told apart from a failure PatchRail can't name.

The dead end this closes is a newcomer's first run. They pipe in whatever `gh run view`
hands back, or point `patchrail ci explain` at a build that passed -- before they have a
failure to triage. That log matches no failure rule, so it lands on `unknown` at 0.15: the
same answer a genuinely unrecognized *failure* gets, down to "Open a CI failure fixture
issue with a sanitized log." Inviting someone to file a fixture for a build that never
failed is worse than unhelpful -- it invites non-failures into the tracker.

A successful run is now recognized as such (`likely_successful_run`) and the report says so
instead. The detection is deliberately conservative: it fires only from the `unknown` path,
demands an explicit success announcement, and any failure tell vetoes it -- so a real
failure that slips past every rule keeps its plain `unknown` verdict and its fixture
invitation.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import jsonschema

from patchrail.cli import main
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

_FIXTURE_URL = "https://github.com/patchrail/patchrail/issues/new?template=ci_failure_fixture.md"

# A green pytest run in `gh run view` wire form: job/step columns and a timestamp on every
# line, exactly the prefix that would otherwise defeat matching.
PASSING_PYTEST_LOG = (
    "test\tRun tests\t2026-07-15T09:00:01.0Z ============================= test session starts\n"
    "test\tRun tests\t2026-07-15T09:00:02.0Z collected 322 items\n"
    "test\tRun tests\t2026-07-15T09:00:40.0Z ======================= 322 passed in 38.14s =======\n"
    "test\tRun tests\t2026-07-15T09:00:41.0Z Process completed with exit code 0.\n"
)

PASSING_MAVEN_LOG = (
    "build\tmvn verify\t2026-07-15T09:00:01.0Z [INFO] Building demo 1.0.0\n"
    "build\tmvn verify\t2026-07-15T09:00:30.0Z [INFO] BUILD SUCCESS\n"
    "build\tmvn verify\t2026-07-15T09:00:31.0Z [INFO] Total time:  29.501 s\n"
)


class SuccessfulRunClassificationTests(unittest.TestCase):
    def test_a_passing_pytest_log_is_flagged_as_a_successful_run(self) -> None:
        result = classify_ci_log(PASSING_PYTEST_LOG)
        self.assertEqual(result["failure_class"], "unknown")
        self.assertTrue(result.get("likely_successful_run"))
        self.assertNotIn("runner_errors", result)

    def test_a_flagged_result_still_matches_the_shipped_schema(self) -> None:
        jsonschema.validate(classify_ci_log(PASSING_PYTEST_LOG), _SCHEMA)
        jsonschema.validate(classify_ci_log(PASSING_MAVEN_LOG), _SCHEMA)

    def test_a_maven_build_success_is_a_successful_run(self) -> None:
        result = classify_ci_log(PASSING_MAVEN_LOG)
        self.assertEqual(result["failure_class"], "unknown")
        self.assertTrue(result.get("likely_successful_run"))

    def test_a_jest_all_pass_summary_is_a_successful_run(self) -> None:
        result = classify_ci_log("Test Suites: 12 passed, 12 total\nTests: 88 passed, 88 total\n")
        self.assertEqual(result["failure_class"], "unknown")
        self.assertTrue(result.get("likely_successful_run"))

    def test_all_checks_passed_is_a_successful_run(self) -> None:
        self.assertTrue(classify_ci_log("All checks passed\n").get("likely_successful_run"))

    def test_a_real_test_failure_is_never_called_a_success(self) -> None:
        # `1 failed, 322 passed` announces a pass AND a failure -- the classifier names the
        # failure, so it never reaches the success path in the first place.
        result = classify_ci_log("1 failed, 322 passed in 12.3s\n")
        self.assertEqual(result["failure_class"], "python_test_failure")
        self.assertNotIn("likely_successful_run", result)

    def test_a_runner_annotated_error_vetoes_it_even_beside_a_success_line(self) -> None:
        log = (
            "test\tRun\t2026-07-15T09:00:40.0Z 322 passed in 38.14s\n"
            "test\tRun\t2026-07-15T09:00:41.0Z ##[error]a later step blew up in a way no rule knows\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("likely_successful_run", result)
        # The runner said where it died; that is handed back, not a "successful run".
        self.assertIn("runner_errors", result)

    def test_a_nonzero_exit_code_vetoes_it(self) -> None:
        result = classify_ci_log(
            "Build succeeded for module A\nProcess completed with exit code 1.\n"
        )
        self.assertNotIn("likely_successful_run", result)

    def test_an_unrecognizable_failure_is_not_a_successful_run(self) -> None:
        # No success announcement anywhere -> stays a plain unknown that invites a fixture.
        result = classify_ci_log(
            "some totally unrecognizable output 12345\nnothing matches any known pattern zzzzz\n"
        )
        self.assertEqual(result["failure_class"], "unknown")
        self.assertNotIn("likely_successful_run", result)

    def test_a_classified_failure_is_untouched(self) -> None:
        result = classify_ci_log(
            "python -m pip install -r requirements.txt\n"
            "ERROR: Could not find a version that satisfies the requirement demo==99\n"
            "ResolutionImpossible\n"
        )
        self.assertEqual(result["failure_class"], "python_dependency_resolution")
        self.assertNotIn("likely_successful_run", result)


class SuccessfulRunReportTests(unittest.TestCase):
    def _explain(self, log_text: str, args: list[str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmpdir:
            log = Path(tmpdir) / "run.log"
            log.write_text(log_text, encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                exit_code = main(["ci", "explain", "--log", str(log), *args])
            return exit_code, stdout.getvalue()

    def test_a_passing_log_is_not_sent_to_the_fixture_template(self) -> None:
        for output_format in ("text", "markdown"):
            exit_code, report = self._explain(PASSING_PYTEST_LOG, ["--format", output_format])
            self.assertEqual(exit_code, 0)
            self.assertNotIn(_FIXTURE_URL, report)
            self.assertNotIn("CI failure fixture issue", report)
            self.assertIn("No failure detected", report)

    def test_json_carries_the_flag_and_stays_clean(self) -> None:
        exit_code, out = self._explain(PASSING_PYTEST_LOG, ["--format", "json"])
        payload = json.loads(out)
        self.assertEqual(exit_code, 0)
        self.assertTrue(payload["likely_successful_run"])
        self.assertNotIn(_FIXTURE_URL, out)

    def test_fail_on_unknown_does_not_fail_on_a_passing_run(self) -> None:
        exit_code, _ = self._explain(PASSING_PYTEST_LOG, ["--fail-on-unknown"])
        self.assertEqual(exit_code, 0)

    def test_fail_on_unknown_still_fails_on_an_unrecognized_failure(self) -> None:
        exit_code, report = self._explain(
            "some totally unrecognizable output 12345\n", ["--fail-on-unknown"]
        )
        self.assertEqual(exit_code, 1)
        self.assertIn("CI failure fixture issue", report)


if __name__ == "__main__":
    unittest.main()
