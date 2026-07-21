"""A terminal variable that is not set is not a secret that is not set.

`SCREAMING_CASE is not set` is how a job reports a missing credential, so
`secrets_or_permissions_failure` watches for it. Standard terminal and locale environment
variables announce themselves the same way, and headless CI runners leave them unset by
design -- so the rule read `debconf: (TERM is not set, ...)`, printed while apt provisioned a
build image, as a missing repository secret.

rails/rails run 29648807728 (the `rails-new-docker` job) failed on a Ruby SyntaxError in
`actionpack`, but its one witness for a SECRETS failure, at 0.53, was debconf's cosmetic
notice that `TERM` is unset on the headless runner. PatchRail would have sent a maintainer
hunting for a missing token over a line whose own message is that a dialog frontend is not
usable.

`TERM`, `DEBIAN_FRONTEND` and their siblings are excluded by name, so the benign apt/debconf
chatter carries no secrets witness -- while a credential that really is unset
(`GITHUB_TOKEN is not set`) still lands.

The debconf line below is verbatim from the committed
`runs/2026-07-20-2119-oss-dogfood-ext/logs/rails-29648807728.log`, kept in its
`gh run view --log-failed` wire form (job/step columns + ISO-8601 timestamp), because that
prefix is exactly what a line-anchored pattern has to survive.
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

DEBCONF_TERM_LINE = (
    "rails-new-docker\tUNKNOWN STEP\t2026-07-18T14:51:42.9276347Z "
    "debconf: (TERM is not set, so the dialog frontend is not usable.)\n"
)


class DebconfTermNoticeTests(unittest.TestCase):
    def test_debconf_term_notice_is_not_a_secrets_failure(self) -> None:
        result = classify_ci_log(DEBCONF_TERM_LINE)

        self.assertNotEqual(result["failure_class"], "secrets_or_permissions_failure")
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["signals"], [])
        jsonschema.validate(result, _SCHEMA)

    def test_terminal_and_locale_vars_alone_carry_no_verdict(self) -> None:
        """The env vars a headless runner leaves unset are noise, not credentials."""
        for line in (
            "debconf: (TERM is not set, so the dialog frontend is not usable.)\n",
            "DEBIAN_FRONTEND is not set\n",
            "LC_ALL is not set\n",
            "warning: LANG is not set\n",
        ):
            with self.subTest(line=line.strip()):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "unknown")

    def test_an_unset_secret_is_still_a_secrets_failure(self) -> None:
        """The cure must not eat the disease: a credential that really is unset still lands.

        `TERMINUS_TOKEN` guards the exclusion against a prefix collision -- it starts with
        `TERM` but is not the terminal variable, so it must not be swept up with it.
        """
        for line in (
            "Error: GITHUB_TOKEN is not set\n",
            "AWS_SECRET_ACCESS_KEY is not set\n",
            "STRIPE_SECRET_KEY is not set\n",
            "TERMINUS_TOKEN is not set\n",
        ):
            with self.subTest(line=line.strip()):
                result = classify_ci_log(line)

                self.assertEqual(result["failure_class"], "secrets_or_permissions_failure")
                self.assertTrue(result["signals"])


if __name__ == "__main__":
    unittest.main()
