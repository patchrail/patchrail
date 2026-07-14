"""Downloading a linter is not running one, and running one is not failing one.

`go_lint` watches for `golangci-lint`. An action that *ships* the linter says its name five
times before it inspects a single file -- it looks the version up, hits its cache, installs
the binary, echoes the command line in brackets, and times the run -- so any job that merely
declares `golangci/golangci-lint-action` handed `go_lint` two witnesses for free, whatever
actually broke.

grafana/grafana's `lint-go` job 27635190952 did not fail a lint check. It failed to compile:
`config.ApplyOverrides` had grown a parameter and eight call sites in
`pkg/services/frontend/request_config_test.go` had not. golangci-lint reported them as
typecheck errors, with no `(linter)` suffix and no lint finding anywhere in the log. PatchRail
answered `go_lint` at 0.71 -- "apply the reported lint correction" -- and there was no lint
correction to apply. Every one of its witnesses came off an install line.

Shipping a tool is not running it, and running it is not failing it. The five provisioning
lines become mere mentions, which can carry nothing; `##[group]run golangci-lint` stays an
invocation, which corroborates but never carries. So the only rule left witnessing an actual
failure is the one reading the Go compiler's own diagnostic, and the log lands on
`go_test_failure`, whose repair strategy -- "the smallest compile or runtime fix in that
package" -- is what the maintainer actually did. `undefined:` already sat in that rule, so a
Go build error landing there is the classifier's existing answer, not a new one.

The cure must not eat the disease, and prometheus/prometheus 29348880303 is the disease: the
same action, the same install lines, but a real finding (`(gci)`) on a real `##[error]` line.
It stays `go_lint`. Note it only ever scored on the boilerplate by luck -- the finding it was
right about matched no pattern until the noise was cleared out from under it.

Lines are verbatim from `gh run view --log-failed`, kept in their `gh` wire form (job/step
columns and timestamp), because that prefix is what a line-anchored pattern has to survive.
Full logs are committed at `examples/real-world/grafana-27635190952.log` and
`examples/real-world/prometheus-29348880303.log`.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from patchrail.ci.classify import classify_ci_log

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCHEMA = json.loads(
    (_REPO_ROOT / "src" / "patchrail" / "schemas" / "ci-result.v1.schema.json").read_text(
        encoding="utf-8"
    )
)

_P = "lint-go\tUNKNOWN STEP\t2026-06-16T17:20:57.4471548Z "

# The action SHIPPING the linter: fetched, cached, probed, installed, timed. Every line names
# the tool; not one of them is the tool inspecting a file, let alone finding fault with one.
GRAFANA_TOOL_SHIPPING = (
    f"{_P}Download action repository 'golangci/golangci-lint-action@1e7e51e771db61008b38414a'\n"
    f"{_P}Cache hit for: golangci-lint.cache-Linux-2945-ef22d35ffdb71feb588be681ff7a1bd6\n"
    f"{_P}Restored cache for golangci-lint from key 'golangci-lint.cache-Linux-2945' in 19112ms\n"
    f"{_P}Finding needed golangci-lint version...\n"
    f"{_P}Installing golangci-lint binary v2.12.2...\n"
    f"{_P}Installed golangci-lint into /home/ubuntu/golangci-lint-2.12.2-linux-amd64 in 1002ms\n"
    f'{_P}level=info msg="golangci-lint has version 2.12.2 built with go1.26.2"\n'
    f"{_P}Ran golangci-lint in 160898ms\n"
)

# The linter really was invoked here. An invocation corroborates, it never carries -- so these
# two lines are why the answer below is `go_test_failure` rather than `unknown`.
GRAFANA_INVOCATION = (
    f"{_P}##[group]run golangci-lint\n"
    f"{_P}Running [/home/ubuntu/golangci-lint-2.12.2-linux-amd64/golangci-lint run  --verbose "
    "$(go list -m -f '{{.Dir}}')] in [/opt/actions-runner/_work/grafana/grafana] ...\n"
)

GRAFANA_PROVISIONING = GRAFANA_TOOL_SHIPPING + GRAFANA_INVOCATION

# What actually broke: a signature grew a parameter, its call sites did not.
GRAFANA_LINT_GO_LOG = GRAFANA_PROVISIONING + (
    f"{_P}##[error]pkg/services/frontend/request_config_test.go:22:34: not enough arguments "
    "in call to config.ApplyOverrides\n"
    f"{_P}##[error]pkg/services/frontend/request_config_test.go:46:34: not enough arguments "
    "in call to config.ApplyOverrides\n"
    f"{_P}##[error]issues found\n"
)

# The disease: the same action, provisioned the same way, reporting a real lint finding.
PROMETHEUS_GOLANGCI_LOG = (
    "golangci-lint\tLint\t2026-07-14T16:17:09.7391090Z ##[error]tsdb/shard_bucket_postings_test"
    ".go:548:1: File is not properly formatted (gci)\n"
    "golangci-lint\tLint\t2026-07-14T16:17:09.7458534Z ##[error]issues found\n"
)


class GolangciProvisioningNoticeTests(unittest.TestCase):
    def test_a_compile_error_under_a_lint_job_is_not_a_lint_failure(self) -> None:
        result = classify_ci_log(GRAFANA_LINT_GO_LOG)

        self.assertNotEqual(result["failure_class"], "go_lint")
        self.assertEqual(result["failure_class"], "go_test_failure")
        self.assertIn("go test", result["reproduction_command"])
        jsonschema.validate(result, _SCHEMA)

    def test_shipping_the_tool_carries_no_verdict(self) -> None:
        """The lines that carried the wrong verdict, with nothing failing anywhere."""
        result = classify_ci_log(GRAFANA_TOOL_SHIPPING)

        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])

    def test_each_provisioning_line_alone_is_never_a_lint_failure(self) -> None:
        for line in (
            "Finding needed golangci-lint version...\n",
            "Installing golangci-lint binary v2.12.2...\n",
            "Installed golangci-lint into /home/ubuntu/golangci-lint-2.12.2-linux-amd64\n",
            "Cache hit for: golangci-lint.cache-Linux-2945-ef22d35ffdb71feb588be681ff7a1bd6\n",
            "Restored cache for golangci-lint from key 'golangci-lint.cache-Linux-2945'\n",
            "Ran golangci-lint in 160898ms\n",
            "Running [/home/ubuntu/golangci-lint-2.12.2/golangci-lint run] in [/src] ...\n",
            'level=info msg="golangci-lint has version 2.12.2 built with go1.26.2"\n',
        ):
            with self.subTest(line=line.strip()):
                self.assertNotEqual(classify_ci_log(line)["failure_class"], "go_lint")

    def test_a_real_lint_finding_is_still_a_lint_failure(self) -> None:
        """The cure must not eat the disease: a linter that really reported still lands."""
        result = classify_ci_log(PROMETHEUS_GOLANGCI_LOG)

        self.assertEqual(result["failure_class"], "go_lint")
        self.assertTrue(result["signals"])

    def test_a_real_lint_finding_survives_its_own_install_lines(self) -> None:
        result = classify_ci_log(GRAFANA_PROVISIONING + PROMETHEUS_GOLANGCI_LOG)

        self.assertEqual(result["failure_class"], "go_lint")

    def test_the_committed_real_logs_classify_as_measured(self) -> None:
        """Pinned against the logs the published benchmark quotes."""
        for name, expected in (
            ("grafana-27635190952", "go_test_failure"),
            ("prometheus-29348880303", "go_lint"),
        ):
            with self.subTest(log=name):
                log = (_REPO_ROOT / "examples" / "real-world" / f"{name}.log").read_text(
                    encoding="utf-8", errors="replace"
                )

                self.assertEqual(classify_ci_log(log)["failure_class"], expected)

    def test_a_go_call_site_mismatch_is_a_go_failure(self) -> None:
        for line in (
            "main.go:31:9: not enough arguments in call to newServer\n",
            "main.go:31:9: too many arguments in call to newServer\n",
        ):
            with self.subTest(line=line.strip()):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "go_test_failure")
                self.assertTrue(result["signals"])


if __name__ == "__main__":
    unittest.main()
