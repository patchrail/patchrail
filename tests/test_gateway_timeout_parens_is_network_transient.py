"""A `Gateway Timeout (504)` with the code trailing in parentheses is a transient network failure.

Grounded in a real failed run of expressjs/express (`ci / coverage`, run 29218121905) — a Node.js
project whose coverage step posts to coveralls.io and hit an upstream gateway outage:

  🚀 Posting coverage data to https://coveralls.io/api/v1/jobs
  HTTP error:
  ---
  Error: Gateway Timeout (504)

The `network_transient_failure` class already carried a `504 Gateway Time-?out` pattern, but that
only matches the HTTP status-line ordering (`504 Gateway Timeout`). The coveralls reporter — like
many HTTP clients — prints the reason phrase first and the code trailing in parentheses, so this
textbook upstream 504 matched nothing and fell through to `unknown` (0.15). A maintainer probing
"does it catch my flake?" got no answer for a 504 of the book. The reverse-order phrasing is just as
terminal, so it now carries `network_transient_failure`. The committed excerpt is at
examples/real-world/express-29218121905-excerpt.log; see examples/real-world/README.md.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from patchrail.ci.classify import classify_ci_log

EXCERPT = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "real-world"
    / "express-29218121905-excerpt.log"
)

# The failure, reduced: a coverage upload to an upstream service times out at the gateway.
COVERAGE_UPLOAD_504 = """\
🚀 Posting coverage data to https://coveralls.io/api/v1/jobs
HTTP error:
---
Error: Gateway Timeout (504)
Message: <!DOCTYPE html>
"""


class AParenthesizedGatewayTimeoutIsNetworkTransient(unittest.TestCase):
    def test_the_express_run_is_a_network_transient_failure(self) -> None:
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertEqual(result["failure_class"], "network_transient_failure")

    def test_the_express_run_is_not_unknown(self) -> None:
        # The whole point: a textbook 504 must not fall through to `unknown` just because the code
        # trailed in parentheses instead of leading the status line.
        result = classify_ci_log(EXCERPT.read_text(encoding="utf-8"))

        self.assertNotEqual(result["failure_class"], "unknown")

    def test_the_reduced_coverage_upload_504_is_network_transient(self) -> None:
        result = classify_ci_log(COVERAGE_UPLOAD_504)

        self.assertEqual(result["failure_class"], "network_transient_failure")

    def test_parenthesized_502_and_503_are_also_network_transient(self) -> None:
        # The sibling gateway 5xx errors carry the identical justification and phrasing.
        for phrase in ("Bad Gateway (502)", "Service Unavailable (503)"):
            log = f"HTTP error:\nError: {phrase}\n"
            self.assertEqual(
                classify_ci_log(log)["failure_class"],
                "network_transient_failure",
                msg=f"{phrase!r} should classify as network_transient_failure",
            )


class TheStatusLineOrderingStillWorks(unittest.TestCase):
    """The guard. Recognising the parenthesised form must not lose the forward-order form."""

    def test_status_line_504_still_network_transient(self) -> None:
        log = (
            "curl: (22) The requested URL returned error: 504 Gateway Timeout\n"
            "Error: Process completed with exit code 22.\n"
        )

        self.assertEqual(classify_ci_log(log)["failure_class"], "network_transient_failure")


if __name__ == "__main__":
    unittest.main()
