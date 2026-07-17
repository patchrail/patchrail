"""Cabal's "Could not resolve dependencies:" is not a Maven build.

Grounded in a real failed run of haskell/cabal (`Validate`, run 29562439929) — Cabal itself, a
Haskell project with no mvn/gradle/sbt/jvm token anywhere in 141k lines. The job died on GHC:

  setup.hs:44:13: error: [GHC-88464]
  ##[error]    Data constructor not in scope: PreProcessorCustom :: FilePath -> t1
  Failed to build internal-preprocessor-test-0.1.0.0-inplace. ... during the configure step.
  ...
  UNEXPECTED FAIL: PackageTests/PreProcess/Basic/setup.test.hs ...
  Some tests failed
  ##[error]Process completed with exit code 1.

PatchRail reported `java_build_failure` at 0.53 — sending a Haskell maintainer to
`./gradlew test || mvn test || sbt test`. Its one and only witness was a line buried in a
cabal-testsuite golden output, where the solver's own diagnostic is the expected text:

  Could not resolve dependencies:
  [__0] trying: A-1 (user goal)
  [__1] fail (backjumping, conflict set: A, A.base)

Maven's phrasing is "Could not resolve dependencies **for project** <group>:<artifact>:jar:<ver>";
the bare "Could not resolve dependencies:" (trailing colon, no "for project") belongs to Cabal — and
pip, and npm. Keying on the Maven suffix keeps Maven and drops Cabal. With no Haskell class, the
honest answer is `unknown`. The committed excerpt is at
examples/real-world/cabal-29562439929-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "cabal-29562439929-excerpt.log"
)

# The failure, reduced: Cabal's solver prints its "Could not resolve dependencies:" diagnostic,
# then a GHC compile error fails the build.
CABAL_RESOLVE_THEN_GHC = """\
Could not resolve dependencies:
[__0] trying: A-1 (user goal)
[__1] fail (backjumping, conflict set: A, A.base)
setup.hs:44:13: error: [GHC-88464]
    Data constructor not in scope: PreProcessorCustom :: FilePath -> t1
Failed to build internal-preprocessor-test-0.1.0.0-inplace.
##[error]Process completed with exit code 1.
"""


class CabalResolveIsNotAJavaBuildFailure(unittest.TestCase):
    def test_the_cabal_run_is_not_a_java_build_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "java_build_failure")

    def test_the_cabal_run_lands_on_unknown(self) -> None:
        # No Haskell/Cabal class exists, so `unknown` is the honest ceiling — a maintainer sent
        # nowhere beats one sent to a Gradle/Maven build that never ran.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_cabal_failure_is_not_a_java_build_failure(self) -> None:
        result = classify_ci_log(CABAL_RESOLVE_THEN_GHC)

        self.assertNotEqual(result["failure_class"], "java_build_failure")


class AMavenResolutionFailureThatActuallyHappenedIsUntouched(unittest.TestCase):
    """The guard. Dropping Cabal's phrasing must not blind the rule to real Maven failures."""

    def test_maven_could_not_resolve_dependencies_for_project_still_carries(self) -> None:
        # Maven's own wording keeps the "for project" suffix and must still classify as JVM,
        # even without the "Failed to execute goal" banner that usually accompanies it.
        log = (
            "[ERROR] Failed to collect dependencies at org.example:lib:jar:1.0\n"
            "[ERROR] Could not resolve dependencies for project com.example:app:jar:1.0: "
            "The following artifacts could not be resolved: org.example:lib:jar:1.0\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "java_build_failure")


if __name__ == "__main__":
    unittest.main()
