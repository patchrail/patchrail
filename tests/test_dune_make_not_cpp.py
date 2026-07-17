"""ocaml/dune's `make: *** [test] Error 1` is its cram suite, not a C/C++ build.

Grounded in a real failed run of ocaml/dune (`CI`, run 29585452292) — dune itself, whose
blackbox/cram tests run under `make test`. The job died on a test-case diff, not a compile:

  --- a/.../pkg/bin-narrowing/lockdir-deps.t
  +++ b/.../pkg/bin-narrowing/lockdir-deps.t.corrected
  -  $SH: mybin: not found
  +  /bin/sh: mybin: not found
  make: *** [test] Error 1
  ##[error]Process completed with exit code 2.

There is no C/C++ error anywhere in the log, yet PatchRail reported `cpp_build_failure` at
0.53 — its only witness the generic GNU make recipe line `make: *** [test] Error 1`, which
says a make TARGET failed and nothing about what it built.

This is the crystal case (test_crystal_spec_make_not_cpp) reached by a different route, and it
slipped past that fix. The make-only `cpp_build_failure` never became the *best* rule: the same
run twice logged the benign cache save-warning `##[warning]Failed to save: Unable to reserve
cache ...`, which gave `artifact_or_cache_failure` two matched signals to cpp's one. So the
make-recipe deferral — which only runs while `cpp_build_failure` is best — was skipped, and the
downstream benign-warning handoff then resurrected that same make-only rule as the verdict. With
no OCaml class and no real toolchain error, the honest answer is `unknown`. The committed
excerpt is at examples/real-world/dune-29585452292-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "dune-29585452292-excerpt.log"
)

# The failure, reduced: a cram test-case diff, a benign cache save-warning that outscores the
# make rule, then make reports the `test` target failed. No line names a C/C++ compile.
DUNE_CRAM_THEN_CACHE_WARNING_THEN_MAKE = """\
--- a/_build/default/test/blackbox-tests/test-cases/pkg/bin-narrowing/lockdir-deps.t
+++ b/_build/default/test/blackbox-tests/test-cases/pkg/bin-narrowing/lockdir-deps.t.corrected
-  $SH: mybin: not found
+  /bin/sh: mybin: not found
##[warning]Failed to save: Unable to reserve cache with key v3-setup-ocaml-opam, another job may be creating this cache.
make: *** [test] Error 1
##[error]Process completed with exit code 2.
"""


class DuneMakeTestIsNotACppBuildFailure(unittest.TestCase):
    def test_the_dune_run_is_not_a_cpp_build_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "cpp_build_failure")

    def test_the_dune_run_lands_on_unknown(self) -> None:
        # No OCaml/dune class exists and the log shows no C/C++ error, so `unknown` is the
        # honest ceiling — a maintainer sent nowhere beats one sent to `cmake --build build`
        # for a cram test-case diff.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_dune_failure_lands_on_unknown(self) -> None:
        result = classify_ci_log(DUNE_CRAM_THEN_CACHE_WARNING_THEN_MAKE)

        self.assertEqual(result["failure_class"], "unknown")


class RealCppFailuresBesideACacheWarningAreUntouched(unittest.TestCase):
    """The guard. The make-recipe rule must still lose to `unknown` when it is all that
    matched — even when a benign cache warning outscored it — WITHOUT blinding a genuine
    C/C++ build that happens to log the same cache warning alongside a real compile error."""

    def test_a_real_cpp_build_still_classifies_despite_a_cache_save_warning(self) -> None:
        # A gcc error and the make line, next to the very cache save-warning that reroutes the
        # dune case: the compiler error carries the verdict, so cpp keeps winning.
        log = (
            "##[warning]Failed to save: Unable to reserve cache with key v3-cc, "
            "another job may be creating this cache.\n"
            "src/widget.cpp:88:5: error: 'frobnicate' was not declared in this scope\n"
            "make[2]: *** [CMakeFiles/app.dir/build.make:76: src/widget.cpp.o] Error 1\n"
            "make: *** [Makefile:140: all] Error 2\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "cpp_build_failure")


if __name__ == "__main__":
    unittest.main()
