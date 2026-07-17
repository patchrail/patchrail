"""Crystal's `make std_spec` spec failure is neither a C/C++ build nor a Ruby suite.

Grounded in a real failed run of crystal-lang/crystal (`Linux CI`, run 29501393259) — Crystal
itself, whose standard-library specs are driven by a Makefile and whose Spec framework copies
RSpec's output verbatim. The job died on a socket bind inside a spec:

  Failures:
    1) Socket #bind using IPv4 binds to port using default IP
         Could not bind to '0.0.0.0:58249': Address already in use (Socket::BindError)
           from spec/std/socket/socket_spec.cr:164:9 in '->'
  18017 examples, 0 failures, 1 errors, 30 pending
  Failed examples:
  crystal spec spec/std/socket/socket_spec.cr:152 # Socket #bind using IPv4 ...
  make: *** [Makefile:140: std_spec] Error 1
  ##[error]Process completed with exit code 1.

There is no C/C++ compile anywhere in the log, yet PatchRail reported `cpp_build_failure` at
0.53 — its only witness the generic GNU make recipe line `make: *** [Makefile:140: std_spec]
Error 1`, which says a make TARGET failed and nothing about what it built. Neutralise that and
the RSpec-style summary line (`18017 examples, 0 failures`) hands the run to
`ruby_bundle_failure` — `bundle exec rake test` for a language whose specs live in `.cr` files.
Both witnesses are ecosystem-ambiguous: make drives specs/docs/linters in every language, and
Crystal's Spec prints RSpec's summary verbatim. With no Crystal class, the honest answer is
`unknown`. The committed excerpt is at
examples/real-world/crystal-29501393259-excerpt.log; see docs/real-world-benchmark.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "crystal-29501393259-excerpt.log"
)

# The failure, reduced: an RSpec-format summary from Crystal's Spec, then make reports the
# spec target failed. Neither line names C/C++ or Ruby.
CRYSTAL_SPEC_THEN_MAKE = """\
Failures:

  1) Socket #bind using IPv4 binds to port using default IP
       Could not bind to '0.0.0.0:58249': Address already in use (Socket::BindError)
         from spec/std/socket/socket_spec.cr:164:9 in '->'

18017 examples, 0 failures, 1 errors, 30 pending

Failed examples:

crystal spec spec/std/socket/socket_spec.cr:152 # Socket #bind using IPv4
make: *** [Makefile:140: std_spec] Error 1
##[error]Process completed with exit code 1.
"""


class CrystalSpecIsNotACppOrRubyFailure(unittest.TestCase):
    def test_the_crystal_run_is_not_a_cpp_build_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "cpp_build_failure")

    def test_the_crystal_run_is_not_a_ruby_bundle_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "ruby_bundle_failure")

    def test_the_crystal_run_lands_on_unknown(self) -> None:
        # No Crystal class exists, so `unknown` is the honest ceiling — a maintainer sent
        # nowhere beats one sent to `cmake --build build` or `bundle exec rake test`.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "unknown")

    def test_the_reduced_crystal_failure_lands_on_unknown(self) -> None:
        result = classify_ci_log(CRYSTAL_SPEC_THEN_MAKE)

        self.assertEqual(result["failure_class"], "unknown")


class RealCppAndRubyFailuresAreUntouched(unittest.TestCase):
    """The guards. Demoting the two ambiguous witnesses must not blind their rules to the
    genuine failures that carry a real toolchain/Ruby signal alongside them."""

    def test_a_real_cpp_build_with_the_make_line_still_classifies(self) -> None:
        # A CMake/gcc build that also emits the make recipe line: the compiler error carries it.
        log = (
            "src/widget.cpp:88:5: error: 'frobnicate' was not declared in this scope\n"
            "make[2]: *** [CMakeFiles/app.dir/build.make:76: src/widget.cpp.o] Error 1\n"
            "make: *** [Makefile:140: all] Error 2\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "cpp_build_failure")

    def test_a_real_rspec_failure_with_the_summary_line_still_classifies(self) -> None:
        # Genuine RSpec: the `.rb` rerun line carries the Ruby verdict, summary corroborates.
        log = (
            "Failures:\n"
            "  1) User is valid\n"
            "rspec ./spec/models/user_spec.rb:12 # User is valid\n"
            "5 examples, 1 failure\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "ruby_bundle_failure")


if __name__ == "__main__":
    unittest.main()
