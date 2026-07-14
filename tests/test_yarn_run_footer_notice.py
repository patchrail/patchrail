"""A `yarn run` that failed is not a dependency install that failed.

yarn classic closes every command with `info Visit https://yarnpkg.com/en/docs/cli/<cmd>
for documentation about this command.`, and `node_dependency_install` watched for the bare
host `yarnpkg.com`. But that footer prints for `yarn run prettier`, `yarn lint` and
`yarn test` exactly as it does for `yarn install` -- so a formatting or test failure
scored a dependency-install verdict on a line that is only a documentation link.

facebook/react's "Run prettier" step in run 29335289512 failed because a file was not
formatted (`This project uses prettier to format all JavaScript code. Please run
yarn prettier-all ...`). PatchRail answered `node_dependency_install` at 0.53, on one
witness: the `/en/docs/cli/run` footer. It would have sent a maintainer to reconcile a
lockfile over a `prettier --check` diff.

With the footer pinned to the two subcommands that ARE a dependency operation
(`install`, `add`), the run footer no longer matches and the `prettier` witness the log
really carries wins, so it answers `javascript_lint` -- the honest verdict for a
formatting check that failed.

The lines below are verbatim from `gh run view 29335289512 --repo facebook/react
--log-failed`, kept in their `gh` wire form (job/step column and timestamp), because that
prefix is exactly what a pattern has to survive. The full excerpt is committed at
`examples/real-world/react-29335289512-excerpt.log`.
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

REACT_PRETTIER_LOG = (
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:09:46.1116231Z yarn run v1.22.22\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:09:46.1361827Z $ node ./scripts/prettier/index.js\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:11.4832433Z   "
    "This project uses prettier to format all JavaScript code.\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:11.4833760Z     "
    "Please run yarn prettier-all and add changes to files listed below to your commit:\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:11.4844700Z "
    "packages/react-reconciler/src/__tests__/useEffectEvent-test.js\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:17.7428646Z error Command failed with exit code 1.\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:17.7430460Z "
    "info Visit https://yarnpkg.com/en/docs/cli/run for documentation about this command.\n"
    "Run prettier\tUNKNOWN STEP\t2026-07-14T13:10:17.7532537Z "
    "##[error]Process completed with exit code 1.\n"
)


class YarnRunFooterNoticeTests(unittest.TestCase):
    def test_yarn_run_footer_is_not_a_dependency_install(self) -> None:
        result = classify_ci_log(REACT_PRETTIER_LOG)

        self.assertNotEqual(result["failure_class"], "node_dependency_install")
        self.assertEqual(result["failure_class"], "javascript_lint")
        self.assertIn("prettier", result["signals"])
        jsonschema.validate(result, _SCHEMA)

    def test_yarn_run_footer_line_alone_carries_no_dependency_verdict(self) -> None:
        """The single line that carried the wrong verdict, on its own."""
        result = classify_ci_log(
            "info Visit https://yarnpkg.com/en/docs/cli/run for documentation about this command.\n"
        )

        self.assertNotEqual(result["failure_class"], "node_dependency_install")
        self.assertEqual(result["failure_class"], "unknown")

    def test_a_real_yarn_install_footer_is_still_a_dependency_install(self) -> None:
        """The cure must not eat the disease: the install/add footers ARE dependency ops."""
        for footer in (
            "info Visit https://yarnpkg.com/en/docs/cli/install for documentation.\n",
            "info Visit https://yarnpkg.com/en/docs/cli/add for documentation about this command.\n",
            "info Visit https://yarnpkg.com/lang/en/docs/cli/install for documentation.\n",
        ):
            with self.subTest(footer=footer.strip()):
                result = classify_ci_log(footer)

                self.assertEqual(result["failure_class"], "node_dependency_install")
                self.assertTrue(result["signals"])


if __name__ == "__main__":
    unittest.main()
