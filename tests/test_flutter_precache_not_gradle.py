"""A cached "Gradle Wrapper" artifact is not a Gradle build.

Grounded in a real failed run of rrousselGit/riverpod (`build`, run 29573819047) — a Dart/Flutter
monorepo — whose `flutter analyze` step reported four lints and exited 1:

  Analyzing flutter_riverpod...
     info • Unnecessary use of 'unawaited'. ...
  4 issues found. (ran in 32.6s)
  ##[error]Process completed with exit code 1.

PatchRail reported `java_build_failure` at 0.53 — sending a Dart maintainer to `./gradlew`. Its one
and only witness in 972 lines was a single line from Flutter's `precache` step, which lists the SDK
artifacts the tool downloads and caches before it runs anything:

  [2/10] Gradle Wrapper                                                7ms

The Gradle Wrapper is one of those artifacts — fetched in 7ms, never run — exactly like apache/kafka's
runner image exporting `GRADLE_HOME`. A `[N/M] … <time>` progress line reports a step that completed,
not a tool that failed; a signal found nowhere else witnesses nothing. With no Dart/Flutter class, the
honest answer is `unknown`. The committed excerpt is at
examples/real-world/riverpod-29573819047-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "riverpod-29573819047-excerpt.log"
)

# The failure, reduced: Flutter caches its bundled Gradle Wrapper, then `flutter analyze` fails.
FLUTTER_ANALYZE_FAILED = """\
##[group]Run flutter pub get
[1/10] Material Fonts                                              186ms
[2/10] Gradle Wrapper                                                7ms
[3/10] Flutter SDK
##[endgroup]
##[group]Run flutter analyze
Analyzing flutter_riverpod...
   info • Unnecessary use of 'unawaited'. Try removing the use of 'unawaited'.
4 issues found. (ran in 32.6s)
##[error]Process completed with exit code 1.
"""


class ACachedGradleWrapperIsNotAGradleBuild(unittest.TestCase):
    def test_the_riverpod_run_is_not_a_java_build_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "java_build_failure")

    def test_the_riverpod_run_lands_on_unknown(self) -> None:
        # No Dart/Flutter class exists, so `unknown` is the honest ceiling — a maintainer sent
        # nowhere beats one sent to a Gradle build that never ran.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_analyze_failure_is_not_a_java_build_failure(self) -> None:
        result = classify_ci_log(FLUTTER_ANALYZE_FAILED)

        self.assertNotEqual(result["failure_class"], "java_build_failure")


class AGradleFailureThatActuallyHappenedIsUntouched(unittest.TestCase):
    """The guards. Discounting the precache listing must not blind the rule to real Gradle failures."""

    def test_a_failing_gradle_task_is_still_a_java_build_failure(self) -> None:
        log = (
            "> Task :app:compileDebugJavaWithJavac FAILED\n"
            "Execution failed for task ':app:compileDebugJavaWithJavac'.\n"
            "BUILD FAILED in 1m 3s\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "java_build_failure")

    def test_a_gradle_wrapper_line_next_to_a_real_failure_still_carries(self) -> None:
        # The precache line only loses its witness when it is the ONLY thing the rule has. A run
        # that both caches the wrapper AND fails a Gradle task is still a java_build_failure.
        log = (
            "[2/10] Gradle Wrapper                                                7ms\n"
            "> Task :app:test FAILED\n"
            "Execution failed for task ':app:test'.\n"
            "BUILD FAILED in 2m 1s\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "java_build_failure")


if __name__ == "__main__":
    unittest.main()
