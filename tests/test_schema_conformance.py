"""Guard against silent drift between src/patchrail/schemas/*.v1.schema.json
and the payloads the CLI actually emits.

The schemas under src/patchrail/schemas/ are served verbatim by
`patchrail ci schema <name>` and documented in docs/api-reference.md, but
until now nothing validated real output against them: `_load_schema()` in
cli.py only reads the schema file as text to print it, it never parses it as
JSON Schema or checks a payload against it. A field could be renamed, added,
or dropped in a payload builder without any test catching the schema going
stale.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest

from patchrail.cli import _build_parser
from patchrail.cli import _load_schema as _cli_schema_text
from patchrail.ci.classify import RULES, classify_ci_log, list_failure_classes

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS_DIR = ROOT / "src" / "patchrail" / "schemas"
FIXTURES_DIR = ROOT / "examples" / "ci-triage"


def _load_schema(name: str, version: str = "v1") -> dict:
    return json.loads((SCHEMAS_DIR / f"{name}.{version}.schema.json").read_text(encoding="utf-8"))


def _schema_choices() -> list[str]:
    """The schema names `patchrail schema` advertises, read off the real parser."""
    subparsers = next(
        action
        for action in _build_parser()._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    schema_parser = subparsers.choices["schema"]
    positional = next(
        action for action in schema_parser._actions if action.dest == "schema" and action.choices
    )
    return list(positional.choices)


def _served_schema(name: str) -> dict:
    """The schema `patchrail schema <name>` actually serves, parsed.

    Going through the CLI's own registry rather than globbing the directory is
    what makes the schema_version guard below binding: a payload can only pass
    if the schema a user can fetch describes it.
    """
    return json.loads(_cli_schema_text(name))


def _run_json(*args: str) -> dict:
    # Some commands (e.g. `ci fixture-check`) exit non-zero when cases fail
    # without that affecting whether the emitted JSON is well-formed and
    # schema-valid, which is all this helper needs to check.
    proc = subprocess.run(
        [sys.executable, "-m", "patchrail", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.stdout, proc.stderr
    return json.loads(proc.stdout)


CI_RESULT_SCHEMA = _load_schema("ci-result")
FIXTURE_LOGS = sorted(FIXTURES_DIR.glob("*.log"))


@pytest.mark.parametrize("log_path", FIXTURE_LOGS, ids=lambda p: p.stem)
def test_classify_ci_log_output_matches_ci_result_schema(log_path: Path) -> None:
    result = classify_ci_log(log_path.read_text(encoding="utf-8", errors="replace"))
    jsonschema.validate(instance=result, schema=CI_RESULT_SCHEMA)


def test_ci_benchmark_output_matches_schema() -> None:
    payload = _run_json("ci", "benchmark", "examples/ci-triage", "--format", "json")
    jsonschema.validate(instance=payload, schema=_load_schema("ci-benchmark"))


def test_ci_fixture_check_output_matches_schema() -> None:
    payload = _run_json("ci", "fixture-check", "examples/ci-triage", "--format", "json")
    jsonschema.validate(instance=payload, schema=_load_schema("ci-fixture-check"))


def test_ci_classes_output_matches_schema() -> None:
    payload = _run_json("ci", "classes", "--format", "json")
    jsonschema.validate(instance=payload, schema=_served_schema("ci-classes"))


def test_ci_classes_schema_version_is_the_one_the_shipped_schema_describes() -> None:
    """The guard the 0.4.0 contract break got through.

    `ci classes` moved from `patchrail.ci_classes.v1` to `.v2` in a minor
    release. Nothing here failed, because the command had no schema and no
    conformance test — so the break reached consumers (including this project's
    own GitHub Action) silently. Changing the contract now means shipping the
    schema that describes it, under its own version, or this goes red.
    """
    emitted = list_failure_classes()["schema_version"]
    described = _served_schema("ci-classes")["properties"]["schema_version"]["const"]
    assert emitted == described, (
        f"ci classes emits {emitted!r} but the schema `patchrail schema ci-classes` "
        f"serves describes {described!r}. Add "
        f"src/patchrail/schemas/ci-classes.<version>.schema.json for the new contract "
        f"and point the CLI registry at it."
    )


def test_ci_classes_keeps_the_unknown_sentinel_out_of_the_denominator() -> None:
    """`unknown` is what `ci explain` returns when no rule matches, so a coverage
    script dividing by `count` must not have it in the denominator."""
    payload = list_failure_classes()
    names = [entry["failure_class"] for entry in payload["classes"]]

    assert "unknown" not in names
    assert payload["fallback"]["failure_class"] == "unknown"
    assert payload["count"] == len(payload["classes"])


def test_ci_classes_lists_every_classifier_rule() -> None:
    """Derived from RULES, not a hand-kept list: a new rule that never reaches
    the inventory (or an entry with no rule behind it) fails here."""
    payload = list_failure_classes()
    assert [entry["failure_class"] for entry in payload["classes"]] == [
        rule["failure_class"] for rule in RULES
    ]


def test_every_schema_the_cli_offers_resolves_to_a_file() -> None:
    """`patchrail schema <name>` advertises its names in argparse `choices`; the
    files live in a separate dict. Offering a name whose file is missing (or was
    renamed on a version bump) is a crash in a user's hands, not a test failure."""
    for name in _schema_choices():
        assert json.loads(_cli_schema_text(name)), f"schema {name} served empty"
