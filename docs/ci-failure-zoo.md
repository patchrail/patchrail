# CI Failure Zoo

PatchRail v0.1 ships a small, synthetic CI failure zoo so classifier changes can
be reviewed with evidence instead of intuition. Each case has two files:

- `*.log`: an anonymized, minimal CI log.
- `*.expected.json`: the expected `failure_class` and minimum confidence.

The fixture set is intentionally local-first. It does not require network
access, repository write permissions, billing, or an external model call.

## Current Coverage

The fixture zoo currently contains 115 cases across these root-cause families:

- `github_actions_workflow`
- `go_test_failure`
- `javascript_lint`
- `node_dependency_install`
- `python_dependency_resolution`
- `python_test_failure`
- `rust_test_failure`
- `typescript_typecheck`

Node and TypeScript coverage includes lockfile drift, peer dependency conflicts,
immutable install drift, workspace protocol drift, engine mismatch, import/type
drift, JSX prop mismatches, route parameter type narrowing, overload errors and
schema drift.

Python dependency-resolution coverage includes missing distributions,
conflicting constraints, Python version markers, yanked releases, Poetry solver
conflicts, pip-tools conflicts, uv resolution failures, extras conflicts, tox
constraint drift, build dependency misses, prerelease ranges, platform wheel
selectors and transitive solver conflicts.

The current set also includes additional Go, Rust, JavaScript lint, GitHub
Actions workflow, and Python test variants so the benchmark crosses the v0.2
100-fixture bar without needing external logs or private repository data.

Run the benchmark:

```bash
patchrail ci benchmark examples/ci-triage --format markdown
patchrail ci benchmark examples/ci-triage --format json
patchrail ci fixture-check examples/ci-triage --format json
```

The command exits with status `0` only when every fixture matches its expected
classification and confidence floor.

`fixture-check` is the pre-PR hygiene gate for new fixtures. It checks that each
`.log` file has a neighboring `.expected.json`, that the expected class and
confidence floor still match the local classifier, and that the redactor does
not see obvious secrets, emails, or home paths in the fixture text.

## Adding A Fixture

1. Redact the log before committing it.
2. Remove tokens, emails, private repository names, user names, and local home
   paths.
3. Reduce the log to the shortest evidence that still represents the failure.
4. Add the log under `examples/ci-triage/<name>.log`.
5. Add `examples/ci-triage/<name>.expected.json`.
6. Run `patchrail ci fixture-check examples/ci-triage --format json`.
7. Run `patchrail ci benchmark examples/ci-triage --format json`.
8. Include the evidence lines, fixture-check result, and benchmark result in the
   pull request.

Expected files use this shape:

```json
{
  "failure_class": "python_test_failure",
  "minimum_confidence": 0.7
}
```

## Redaction Rules

Do not commit raw CI logs that contain secrets, personal data, private paths, or
customer/repository identifiers. Use the local redactor first:

```bash
patchrail redact --log failed.log > failed.redacted.log
patchrail ci explain --redact --log failed.log
```

If a log cannot be safely reduced or redacted, do not add it as a public
fixture. Create a minimal synthetic reproduction instead.

Use the [CI failure fixture issue template](../.github/ISSUE_TEMPLATE/ci_failure_fixture.md)
when requesting or proposing a new fixture.

Maintainers who want to test PatchRail before contributing a fixture can follow
the [maintainer pilot guide](pilot-guide.md). The pilot path is read-only:
redact a log, classify it locally, review the report, and share only safe
evidence or a sanitized fixture.

## Non-Goals

The fixture zoo is not a leaderboard and does not justify automatic write
actions. It exists to improve local classification quality and to make
maintainer review easier.
