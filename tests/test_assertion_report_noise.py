"""Output a test quoted back at you is the test's data, not the job's diagnostic.

Grounded in a real failed run of denoland/deno (`test specs (1/2) debug`, run 29349357779),
where the spec suite panicked and PatchRail reported `typescript_typecheck` at 0.95 confidence
instead -- telling the maintainer of a TypeScript runtime that their TypeScript was broken.

It was not. Deno's spec suite runs `deno check` against programs that are SUPPOSED to fail to
typecheck, and asserts that the diagnostics come out right. When a spec fails, the harness
prints both sides of the comparison, so the log fills with real-looking compiler output:

  ---- specs::check::check_deno_not_found ----
  output path /home/runner/work/deno/deno/tests/specs/check/.../main.out
  -- OUTPUT START --
  -- OUTPUT END --
  -- EXPECTED START --
  TS2304 [ERROR]: Cannot find name 'Deno'. ...
  error: Type checking failed.
  -- EXPECTED END --

Every TS diagnostic in that 30MB log -- 4899 of them -- sits inside a block like this one, or
inside the `Diff < left / right > :` that `pretty_assertions` prints for the harness's
`assertion failed: `(left == right)``. The `-- EXPECTED --` side is quite literally the
contents of a checked-in fixture file, named on the `output path` line above it.

What actually failed is in the log too, and says so plainly: `panicked at tests/specs/mod.rs`,
and the runner's `##[error]Process completed with exit code 101` -- 101 being what a Rust
process exits with when it panics. `rust_test_failure` is the true answer, and a useful one:
the spec asserted a type error and got an empty string back.
"""

from __future__ import annotations

import unittest

from patchrail.ci.classify import classify_ci_log

# The deno run, in the shape `gh run view --log-failed` serves it: a spec fails, the harness
# dumps what it got against what it expected, and `pretty_assertions` renders the same
# comparison a second time as a diff. Both quote the fixture's TypeScript diagnostics.
DENO_SPEC_SUITE = """\
Run cargo test --locked --lib --bins --tests
test specs::check::check_deno_not_found ... fail (1399ms)

failures:

---- specs::check::check_deno_not_found ----
command /home/runner/work/deno/deno/target/debug/deno check --quiet deno_not_found/main.ts
command cwd /home/runner/work/deno/deno/tests/specs/check/check_deno_not_found
output path /home/runner/work/deno/deno/tests/specs/check/check_deno_not_found/deno_not_found/main.out
-- OUTPUT START --

-- OUTPUT END --
-- EXPECTED START --
TS2304 [ERROR]: Cannot find name 'Deno'. Do you need to change your target library? Try changing the 'lib' compiler option to include 'deno.ns'.
Deno;
~~~~
    at file:///[WILDCARD]/deno_not_found/main.ts:4:1

error: Type checking failed.
-- EXPECTED END --
-- DEBUG START --
==== COULD NOT FIND SEARCH TEXT ====
TS2304·[ERROR]:·Cannot·find·name·'Deno'.
-- DEBUG END --

---- specs::check::compiler_options_paths ----
command /home/runner/work/deno/deno/target/debug/deno check --quiet main.ts

panicked at tests/specs/mod.rs:676:12:
assertion failed: `(left == right)`

Diff < left / right > :
<TS2307 [ERROR]: Cannot find module './src/qux.ts' or its corresponding type declarations.
<import type {} from "./src/qux.ts";
<                    ~~~~~~~~~~~~~~
<    at file:///home/runner/work/deno/deno/tests/specs/check/main.ts:1:22
<
<error: Type checking failed.
<

thread 'main' panicked at tests/specs/mod.rs:669:14:
1 test failed
##[error]Process completed with exit code 101.
"""


class OutputATestQuotedBackIsNotTheJobsDiagnostic(unittest.TestCase):
    def test_the_deno_spec_suite_is_not_a_typescript_typecheck_failure(self) -> None:
        result = classify_ci_log(DENO_SPEC_SUITE)

        self.assertNotEqual(result["failure_class"], "typescript_typecheck")

    def test_the_rust_tests_that_actually_panicked_are_the_answer(self) -> None:
        # Not merely "not TypeScript": the log says what broke, and a maintainer sent to
        # `tests/specs/mod.rs` is being sent somewhere true.
        result = classify_ci_log(DENO_SPEC_SUITE)

        self.assertEqual(result["failure_class"], "rust_test_failure")

    def test_a_fixture_the_harness_expected_cannot_be_evidence_of_anything(self) -> None:
        # The whole failure, reduced: the ONLY TypeScript in the log is the text a fixture
        # file was expected to contain. Nothing typechecked, so nothing can have failed to.
        log = (
            "Run cargo test\n"
            "---- specs::check::missing_name ----\n"
            "output path tests/specs/check/missing_name/main.out\n"
            "-- EXPECTED START --\n"
            "TS2304 [ERROR]: Cannot find name 'Deno'.\n"
            "error: Type checking failed.\n"
            "-- EXPECTED END --\n"
            "thread 'main' panicked at tests/specs/mod.rs:669:14:\n"
            "##[error]Process completed with exit code 101.\n"
        )

        result = classify_ci_log(log)

        self.assertNotEqual(result["failure_class"], "typescript_typecheck")

    def test_a_truncated_block_is_still_a_block(self) -> None:
        # `gh` cuts the log off mid-report often enough that the last block has no END marker.
        # An unterminated quotation is still a quotation, and runs to the end of the text.
        log = (
            "Run cargo test\n"
            "thread 'main' panicked at tests/specs/mod.rs:669:14:\n"
            "-- EXPECTED START --\n"
            "TS2304 [ERROR]: Cannot find name 'Deno'.\n"
            "error: Type checking failed.\n"
        )

        result = classify_ci_log(log)

        self.assertNotEqual(result["failure_class"], "typescript_typecheck")


class ATypecheckThatActuallyRanIsUntouched(unittest.TestCase):
    """The guards. A quotation is discounted because of where it sits, not what it says --
    so the same words, emitted by a tool that really ran, still carry the verdict."""

    def test_a_real_tsc_failure_is_still_a_typescript_typecheck_failure(self) -> None:
        log = (
            "Run npm run typecheck\n"
            "> tsc --noEmit\n"
            "src/api/client.ts(42,7): error TS2322: Type 'string' is not assignable to "
            "type 'number'.\n"
            "error: Type checking failed.\n"
            "##[error]Process completed with exit code 2.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "typescript_typecheck")

    def test_a_real_tsc_failure_survives_a_spec_suite_quoting_fixtures(self) -> None:
        # Both in one job: the specs quote their fixtures, and `tsc` separately falls over on
        # the repo's own source. The real diagnostic is outside the blocks, and still wins.
        log = (
            "Run cargo test\n"
            "---- specs::check::missing_name ----\n"
            "-- EXPECTED START --\n"
            "TS2304 [ERROR]: Cannot find name 'Deno'.\n"
            "-- EXPECTED END --\n"
            "Run npm run typecheck\n"
            "> tsc --noEmit\n"
            "src/api/client.ts(42,7): error TS2322: Type 'string' is not assignable to "
            "type 'number'.\n"
            "Argument of type 'string' is not assignable to parameter of type 'number'.\n"
            "##[error]Process completed with exit code 2.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "typescript_typecheck")

    def test_ordinary_log_lines_are_not_swallowed_by_a_diff_that_ended(self) -> None:
        # The diff body ends at the first blank line. What follows is the job talking again,
        # and it is allowed to witness -- otherwise one `pretty_assertions` diff would mute
        # every error under it.
        log = (
            "Run cargo test\n"
            "assertion failed: `(left == right)`\n"
            "Diff < left / right > :\n"
            "<expected output\n"
            ">actual output\n"
            "\n"
            "> tsc --noEmit\n"
            "src/api/client.ts(42,7): error TS2322: Type 'string' is not assignable to "
            "type 'number'.\n"
            "##[error]Process completed with exit code 2.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "typescript_typecheck")


if __name__ == "__main__":
    unittest.main()
