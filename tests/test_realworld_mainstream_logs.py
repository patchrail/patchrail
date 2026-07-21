"""Real CI logs from mainstream repositories keep classifying the way they should.

These are not distilled snippets: each file under ``tests/data/realworld/`` is the raw
``gh run view --log-failed`` output PatchRail was dogfooded against, kept verbatim (job/step
columns + ISO-8601 timestamps and all) so the guard exercises the classifier over the same
hundreds of kilobytes a maintainer would actually paste. The point is a behaviour lock, not a
new failure class -- every log here already classifies correctly today, and this test fails
loudly if a future rule change drifts one of them.

  * spring-projects/spring-boot run 29780604983 (Java/Gradle): the ``checkFormatDockerTest``
    Gradle task really breaks (``Execution failed for task`` / ``BUILD FAILED``), so the honest
    answer is ``java_build_failure`` with a strong confidence.
  * apache/kafka run 29805964231 (governance gate): the run failed on ``check-pr-labels`` -- a
    PR missing a required label, not a build or a test -- so the honest answer is a low-
    confidence ``unknown`` decline rather than a hallucinated class. Declining safely on a
    governance failure is exactly the behaviour worth locking down.
  * rails/rails run 29648807728 (Ruby): a ``SyntaxError`` in ``actionpack`` aborts
    ``bin/rails``, and no failure class covers it -- the only signals in the log are Bundler
    INVOCATIONS. The class still reads ``ruby_bundle_failure``, but the confidence must stay
    in the low band: an invocation proves a tool ran, never that it failed.

These live under ``tests/data/realworld/`` on purpose: they are *not* part of the
``examples/ci-triage`` fixture zoo and must never be counted by ``ci benchmark`` (still 223).
This is a regression guard over real-world input, not another zoo fixture.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from patchrail.ci.classify import classify_ci_log

_ROOT = Path(__file__).resolve().parents[1]
_DATA = _ROOT / "tests" / "data" / "realworld"
_SCHEMA = json.loads(
    (_ROOT / "src" / "patchrail" / "schemas" / "ci-result.v1.schema.json").read_text(
        encoding="utf-8"
    )
)


def _classify(filename: str) -> dict:
    log = (_DATA / filename).read_text(encoding="utf-8", errors="replace")
    result = classify_ci_log(log)
    jsonschema.validate(result, _SCHEMA)
    return result


class RealWorldMainstreamLogTests(unittest.TestCase):
    def test_spring_boot_gradle_build_is_java_build_failure(self) -> None:
        """A broken Gradle task on spring-boot lands as a high-confidence java build failure."""
        result = _classify("springboot-29780604983.log")

        self.assertEqual(result["failure_class"], "java_build_failure")
        # A genuine ``BUILD FAILED`` should read as a strong, but not fabricated-perfect, hit.
        self.assertGreaterEqual(result["confidence"], 0.80)
        self.assertLessEqual(result["confidence"], 0.95)
        self.assertTrue(result["signals"], "a real build failure must cite its signals")

    def test_kafka_governance_gate_declines_to_unknown(self) -> None:
        """A missing-PR-label governance gate is not a build; PatchRail declines, not guesses."""
        result = _classify("kafka-29805964231.log")

        self.assertEqual(result["failure_class"], "unknown")
        # A safe decline stays in the low-confidence band -- never a confident wrong class.
        self.assertLessEqual(result["confidence"], 0.30)

    def test_rails_invocation_only_verdict_is_not_confident(self) -> None:
        """A verdict held up by invocations alone must read as a lead, not a diagnosis."""
        result = _classify("rails-29648807728.log")

        # What actually broke is a Ruby ``SyntaxError`` in ``actionpack`` that blows up
        # ``bin/rails aborted!`` -- no failure class covers it, and inventing one would be
        # breadth-farming. Bundler is the only thing we recognise, and only because the job
        # RAN it: ``bundle install`` (which succeeded), ``bundle exec``, ``bundler``. So the
        # verdict is unchanged and openly a guess. This pins the confidence, not the class.
        self.assertEqual(result["failure_class"], "ruby_bundle_failure")
        self.assertLessEqual(
            result["confidence"],
            0.35,
            "an invocation-only verdict must not be sold at diagnosis confidence",
        )
        self.assertTrue(
            all("bundle" in signal or "bundler" in signal for signal in result["signals"]),
            "the guard is about invocation-only evidence; these signals are the evidence",
        )


if __name__ == "__main__":
    unittest.main()
