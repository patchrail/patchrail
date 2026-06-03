# v0.1.0 Release Evidence

This page records the release-prep evidence for PatchRail v0.1.0.

It is intentionally a prep artifact only. It does not create a tag, publish to
PyPI, create a GitHub Release, announce the project, or submit any external
application. Those actions stay behind a manual maintainer gate.

## Scope

v0.1.0 is the first public CI Janitor release candidate:

- local CI failure explanation and classification;
- Markdown, JSON, and text report output;
- local redaction helper;
- 101 sanitized benchmark fixtures;
- read-only GitHub Actions triage artifact workflow;
- experimental local SQLite queue and human approval states;
- experimental read-only funded issue metadata over local JSON;
- Apache-2.0 licensing and safety documentation.

## Artifact Manifest

Generated on 2026-06-03 from the public repository checkout:

```text
dist/patchrail-0.1.0.tar.gz
dist/patchrail-0.1.0-py3-none-any.whl
```

Validated package metadata:

```text
Checking dist/patchrail-0.1.0-py3-none-any.whl: PASSED
Checking dist/patchrail-0.1.0.tar.gz: PASSED
```

## Local Verification

Commands run:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
uv run --extra dev patchrail doctor --format json
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
git diff --check
```

Results:

- Tests: 32 passed.
- Lint: all checks passed.
- Format: 17 files already formatted.
- Benchmark: 101 total, 101 passed, 0 failed.
- Doctor: `status=ok`, `local_first=true`, no billing, network, external model,
  or GitHub write permission required.
- Build: produced `patchrail-0.1.0.tar.gz` and
  `patchrail-0.1.0-py3-none-any.whl`.
- Twine: both artifacts passed.
- Diff whitespace check: passed.

## Wheel Smoke Test

The wheel was installed into a fresh temporary virtual environment:

```bash
python3 -m venv .release-smoke
. .release-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install dist/patchrail-0.1.0-py3-none-any.whl
patchrail doctor --format json
patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text
```

Smoke result:

- Installed `patchrail-0.1.0` from the local wheel.
- `patchrail doctor --format json` returned `status=ok`.
- `patchrail ci explain` classified the fixture as
  `python_dependency_resolution` with confidence `0.95`.

## Safety Review

Release-prep preserved the public safety boundary:

- no third-party repository write automation;
- no automatic pull requests;
- no issue or pull-request comments;
- no funded issue claims;
- no mass outreach;
- no external model calls by default;
- no billing, KYC, payment, or payout setup;
- local-first CI log processing;
- manual maintainer gate for tags, PyPI publishing, GitHub Releases, public
  announcements, and external applications.

## Manual Gates Remaining

These steps are intentionally not performed by automation:

- create or push a `v0.1.0` tag;
- publish the package to PyPI;
- create a GitHub Release;
- announce the release publicly;
- submit the Codex for Open Source application.

## Next Evidence To Add

- public CI run URL for the release-prep pull request;
- first PyPI release URL after manual publish;
- install verification from PyPI after publish;
- external maintainer pilot outcomes;
- real adoption metrics, without placeholder inflation.
