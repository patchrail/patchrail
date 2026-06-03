# Contributing

Thanks for helping improve PatchRail.

The easiest contribution is a sanitized CI failure fixture. If you are not sure
where to start, open the [CI failure fixture issue template](.github/ISSUE_TEMPLATE/ci_failure_fixture.md)
and include the smallest redacted log excerpt you can share. Maintainers who
want to try PatchRail before contributing can follow the
[maintainer pilot guide](docs/pilot-guide.md).

## Adding a CI fixture

1. Copy the smallest failing log excerpt that still shows the root cause.
2. Redact secrets, emails, private repo names, user names, and local home paths.
3. Add the fixture as `examples/ci-triage/<short-name>.log`.
4. Add the expected metadata as `examples/ci-triage/<short-name>.expected.json`.
5. Run the benchmark and tests before opening a pull request:

```bash
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
uv run --extra dev pytest -q
```

Expected metadata files use this shape:

```json
{
  "failure_class": "python_test_failure",
  "minimum_confidence": 0.7
}
```

If a real log cannot be safely redacted, create a minimal synthetic fixture that
preserves the error pattern without preserving private identifiers.

## Pull request checklist

- No secrets or raw private logs added.
- No new network access without explicit opt-in.
- No new write action without human approval.
- No bounty claiming or mass-commenting behavior.
- CLI examples still work.

## Development

```bash
python -m pip install -e ".[dev]"
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```
