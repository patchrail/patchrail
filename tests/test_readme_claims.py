"""The numbers the README advertises must be the numbers the code ships.

Every count in the "Why maintainers use it" section is a claim a maintainer can
check in one command. When a claim drifts from the code it reads as sloppiness
at exactly the moment someone is deciding whether to trust the classifier.

The fixture count was already pinned elsewhere in the suite and stayed honest.
The class and redaction counts were pinned nowhere, and both drifted. So derive
all three from the source of truth and fail in *both* directions: a stale README
is a bug, and so is a README nobody updated after adding a rule.
"""

from __future__ import annotations

import re
from pathlib import Path

from patchrail.ci.classify import REDACTION_PATTERNS, RULES

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")

FAILURE_CLASSES_RE = re.compile(r"\*\*(\d+) failure classes\*\*")
FIXTURES_RE = re.compile(r"\*\*(\d+) sanitized CI log fixtures\*\*")
REDACTION_RE = re.compile(r"\*\*(\d+) secret-redaction patterns\*\*")
SUPPORT_TABLE_RE = re.compile(r"\|\s*(\d+) failure classes for GitHub Actions-style logs")


def _claim(pattern: re.Pattern[str]) -> int:
    match = pattern.search(README)
    assert match is not None, f"README no longer states the claim matched by {pattern.pattern!r}"
    return int(match.group(1))


def test_readme_failure_class_count_matches_the_rule_table() -> None:
    assert _claim(FAILURE_CLASSES_RE) == len(RULES)


def test_readme_support_table_agrees_with_the_headline_claim() -> None:
    # Two places in the README quote the class count; they drift independently.
    assert _claim(SUPPORT_TABLE_RE) == len(RULES)


def test_readme_fixture_count_matches_the_zoo_on_disk() -> None:
    fixtures = list((ROOT / "examples" / "ci-triage").glob("*.log"))
    assert _claim(FIXTURES_RE) == len(fixtures)


def test_readme_redaction_pattern_count_matches_the_redaction_table() -> None:
    assert _claim(REDACTION_RE) == len(REDACTION_PATTERNS)


def test_unknown_is_not_advertised_as_a_supported_failure_class() -> None:
    # `unknown` is what `ci explain` returns when nothing matched. Counting it as
    # a class inflates the README's headline number by one and, worse, puts an
    # unreachable entry in the denominator of the coverage check the README tells
    # people to script (`ci classes --format json`).
    assert "unknown" not in {rule["failure_class"] for rule in RULES}
