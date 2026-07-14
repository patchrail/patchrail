"""A container killed for memory is not the runner running out of it.

`runner_resource_exhaustion` is about the CI RUNNER -- the host machine -- exhausting
memory or disk: raise the runner class, free space, lower peak use. Its `OOMKilled`,
`Out of memory` and `exit code 137` patterns describe a process killed for memory but
never say WHOSE. A container runtime's own integration suite trips every one of them by
design: `oom_linux_test.go` creates eight containers and waits for the kernel to OOM-kill
them; an exec inside a container exits 137 and containerd logs it at `level=debug` with
`error <nil>`; the kernel prints `Memory cgroup out of memory` -- a cgroup hitting its
configured limit, which is the opposite of the host running dry.

containerd run 29358848438 failed a Go test -- `--- FAIL: TestContainerCgroupWritable` --
and `make: *** [Makefile:230: cri-integration] Error 1` killed the job. PatchRail 0.7.1
answered `runner_resource_exhaustion` at 0.89 on those three provoked-on-purpose kill
lines, and handed the maintainer `rerun the failing job while watching runner memory and
disk`. The same suite also logs `connection refused` from an upgrade test, so nudging the
verdict off the resource rule alone would only trade it for an equally wrong
`network_transient_failure`: both are ambiguous noise a deterministic failure throws off.
The concrete cause the log actually recorded -- the Go test -- is the honest answer.

The excerpt is verbatim from `gh run view 29358848438 --repo containerd/containerd
--log-failed`, kept in its `gh` wire form (job/step columns and timestamp) because that
prefix is exactly what a line-anchored pattern has to survive. It is committed at
`examples/real-world/containerd-29358848438-excerpt.log`.
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


class ContainerRuntimeOomNoiseTests(unittest.TestCase):
    def test_provoked_container_kills_do_not_outrank_the_test_that_failed(self) -> None:
        log = (
            _REPO_ROOT / "examples" / "real-world" / "containerd-29358848438-excerpt.log"
        ).read_text(encoding="utf-8")

        result = classify_ci_log(log)

        self.assertNotEqual(result["failure_class"], "runner_resource_exhaustion")
        # Nor the other ambiguous-noise rule the same suite also trips.
        self.assertNotEqual(result["failure_class"], "network_transient_failure")
        self.assertEqual(result["failure_class"], "go_test_failure")
        self.assertIn("go test", result["reproduction_command"])
        jsonschema.validate(result, _SCHEMA)

    def test_no_single_container_kill_line_outranks_a_real_failure(self) -> None:
        """Each false witness, on its own, must not beat a concrete failure beside it.

        The excerpt trips all three at once; this isolates them. Paired with the Go test
        that actually failed, not one of the three container-kill lines may carry the
        verdict back to `runner_resource_exhaustion`.
        """
        real_failure = "--- FAIL: TestContainerCgroupWritable (34.40s)\ngo test ./...\n"
        for witness in (
            "    oom_linux_test.go:93: Creating 8 running container and wait for them OOMKilled\n",
            '  time="..." level=debug msg="Exec process \\"abc\\" exits with exit code '
            '137 and error <nil>"\n',
            "[Tue Jul 14 19:05:42 2026] Memory cgroup out of memory: Killed process 197353 (dd)\n",
        ):
            with self.subTest(witness=witness.strip()[:48]):
                result = classify_ci_log(witness + real_failure)

                self.assertNotEqual(result["failure_class"], "runner_resource_exhaustion")
                self.assertEqual(result["failure_class"], "go_test_failure")

    def test_a_real_runner_exhaustion_is_still_runner_resource(self) -> None:
        """The cure must not eat the disease: a host that truly ran dry still lands.

        Each of these trips a TERMINAL signal outside the ambiguous set -- the runner's
        own exit-137 annotation, a full disk, a build process's own heap OOM -- so the
        deferral never fires and the resource verdict stands.
        """
        cases = {
            # The runner itself annotating a step it OOM-killed (128 + SIGKILL).
            "Building large image...\nKilled\n"
            "##[error]Process completed with exit code 137.\n": "runner_resource_exhaustion",
            # Disk, not memory, and unambiguously the host filesystem.
            "tar: write error: No space left on device\n"
            "##[error]Process completed with exit code 2.\n": "runner_resource_exhaustion",
            # A Node build whose OWN heap gave out -- a real limit to raise.
            "FATAL ERROR: Reached heap limit Allocation failed - "
            "JavaScript heap out of memory\n": "runner_resource_exhaustion",
            # A Go build process, likewise, out of memory in its own runtime.
            "fatal error: runtime: out of memory\n"
            "goroutine stack exceeds 1000000000-byte limit\n": "runner_resource_exhaustion",
        }
        for log, expected in cases.items():
            with self.subTest(log=log.split(chr(10))[0][:48]):
                result = classify_ci_log(log)

                self.assertEqual(result["failure_class"], expected)
                self.assertTrue(result["signals"])

    def test_a_pure_oom_log_with_no_alternative_still_stands(self) -> None:
        """Ambiguous signals with nothing concrete to defer to keep the resource rule.

        There is no better answer available, so the resource verdict is the only lead the
        log gives -- the deferral only moves a verdict, it never invents `unknown`.
        """
        result = classify_ci_log("Step: run\nOOMKilled\nContainer terminated: Out of memory\n")

        self.assertEqual(result["failure_class"], "runner_resource_exhaustion")


if __name__ == "__main__":
    unittest.main()
