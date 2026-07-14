"""A CMake policy that is not set is not a secret that is not set.

`SCREAMING_CASE is not set` is how a job reports a missing credential, so
`secrets_or_permissions_failure` watches for it. CMake announces its policies the same way,
and a policy id (`CMP0148`) is shaped exactly like an environment variable -- so the rule
read a warning CMake prints for developers to ignore as a missing repository secret.

pytorch/pytorch's lint run 29361968044 failed because lintrunner never wrote its report
(`jq: error: Could not open file lint.json`). PatchRail answered
`secrets_or_permissions_failure` at 0.53, on one witness: a `CMake Warning (dev)` raised
inside a vendored `third_party/NNPACK/CMakeLists.txt`. It would have sent a maintainer to
audit their secrets over a line whose own last sentence is "Use -Wno-dev to suppress it."

With the false witness gone the log carries no signal at all, so it answers `unknown` and
hands the failure back -- which is the honest verdict for a step that died in `jq`.

The lines below are verbatim from `gh run view 29361968044 --repo pytorch/pytorch
--log-failed`, kept in their `gh` wire form (job/step columns and timestamp), because that
prefix is exactly what a line-anchored pattern has to survive. The full excerpt is committed
at `examples/real-world/pytorch-29361968044-excerpt.log`.
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

PYTORCH_LINTRUNNER_LOG = (
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:25.8594068Z "
    "+ find torch -name '*.pyi' -exec git restore --staged -- '{}' +\n"
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:25.8596572Z "
    "jq: error: Could not open file lint.json: No such file or directory\n"
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:25.8596926Z + true\n"
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:25.8597094Z + exit 1\n"
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:26.1255389Z "
    "##[error][OSDC] Step script exited with code 1. This is a script/workflow error, "
    "not an infrastructure issue.\n"
    "lintrunner-pyrefly-all / lint\tUNKNOWN STEP\t2026-07-14T19:33:26.1265482Z "
    "##[error]Process completed with exit code 1.\n"
    "lintrunner-clang-all / lint\tUNKNOWN STEP\t2026-07-14T19:36:30.7507481Z "
    "CMake Warning (dev) at third_party/NNPACK/CMakeLists.txt:110 (FIND_PACKAGE):\n"
    "lintrunner-clang-all / lint\tUNKNOWN STEP\t2026-07-14T19:36:30.7508002Z "
    "  Policy CMP0148 is not set: The FindPythonInterp and FindPythonLibs modules\n"
    "lintrunner-clang-all / lint\tUNKNOWN STEP\t2026-07-14T19:36:30.7508520Z "
    '  are removed.  Run "cmake --help-policy CMP0148" for policy details.  Use\n'
    "lintrunner-clang-all / lint\tUNKNOWN STEP\t2026-07-14T19:36:30.7509012Z "
    "  the cmake_policy command to set the policy and suppress this warning.\n"
    "lintrunner-clang-all / lint\tUNKNOWN STEP\t2026-07-14T19:36:30.7509503Z "
    "This warning is for project developers.  Use -Wno-dev to suppress it.\n"
)


class CMakePolicyNoticeTests(unittest.TestCase):
    def test_cmake_policy_notice_is_not_a_secrets_failure(self) -> None:
        result = classify_ci_log(PYTORCH_LINTRUNNER_LOG)

        self.assertNotEqual(result["failure_class"], "secrets_or_permissions_failure")
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])
        jsonschema.validate(result, _SCHEMA)

    def test_cmake_policy_line_alone_carries_no_verdict(self) -> None:
        """The single line that carried the wrong verdict, on its own."""
        result = classify_ci_log(
            "  Policy CMP0148 is not set: The FindPythonInterp and FindPythonLibs modules\n"
        )

        self.assertEqual(result["failure_class"], "unknown")

    def test_an_unset_secret_is_still_a_secrets_failure(self) -> None:
        """The cure must not eat the disease: a credential that really is unset still lands."""
        for line in (
            "Error: GITHUB_TOKEN is not set\n",
            "AWS_SECRET_ACCESS_KEY is not set\n",
            "NPM_TOKEN is not set, skipping publish\n",
        ):
            with self.subTest(line=line.strip()):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "secrets_or_permissions_failure")
                self.assertTrue(result["signals"])


if __name__ == "__main__":
    unittest.main()
