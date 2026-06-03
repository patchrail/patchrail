# v0.1.0 Release Evidence

This page records the release evidence for PatchRail v0.1.0.

The GitHub Release is published with package artifacts. PyPI publication,
announcements, and external applications remain separate steps.

## Scope

v0.1.0 is the first public CI Janitor release candidate:

- local CI failure explanation and classification;
- Markdown, JSON, and text report output;
- local redaction helper;
- 124 sanitized benchmark fixtures;
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

Reusable local evidence command:

```bash
uv run --extra dev python scripts/release_readiness.py --clean-dist
```

The command builds the local sdist/wheel, runs `twine check`, installs the wheel
into a fresh local virtual environment, verifies `patchrail doctor`, and
classifies the dependency fixture. It does not publish to PyPI, create a tag,
announce the release, contact third parties, or require GitHub write permission.

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
- Benchmark: 124 total, 124 passed, 0 failed.
- Doctor: `status=ok`, `local_first=true`, no billing, network, external model,
  or GitHub write permission required.
- Build: produced `patchrail-0.1.0.tar.gz` and
  `patchrail-0.1.0-py3-none-any.whl`.
- Twine: both artifacts passed.
- Diff whitespace check: passed.

Re-verified before GitHub Release publication:

- Tests: 34 passed.
- Lint: all checks passed.
- Format: 18 files already formatted.
- Benchmark: 124 total, 124 passed, 0 failed.
- Doctor: `status=ok`, `local_first=true`, no billing, network, external model,
  or GitHub write permission required.
- Build: produced `patchrail-0.1.0.tar.gz` and
  `patchrail-0.1.0-py3-none-any.whl`.
- Twine: both artifacts passed.
- Wheel smoke: installed `patchrail-0.1.0` from the local wheel on Python 3.14
  and verified `doctor`, `ci explain`, `funded-issues list`, and `queue init`.

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
- manual maintainer gate remains for PyPI publishing, public announcements, and
  external applications.

## Public CI Evidence

Release-prep pull request:
<https://github.com/patchrail/patchrail/pull/17>

GitHub Actions run:
<https://github.com/patchrail/patchrail/actions/runs/26869827161>

Remote jobs passed:

- `test (3.11)`;
- `test (3.12)`;
- `test (3.13)`;
- `package-smoke`.

## GitHub Release

Published release:
<https://github.com/patchrail/patchrail/releases/tag/v0.1.0>

Release target:
`07b4934d91866c3ea2978c2aff265f923cd232bf`

Release assets:

- `patchrail-0.1.0.tar.gz`
  - SHA256: `1e8381b6f9a47cfcbae9ca66e2773c2bbd4f40029deb4c4d8c97b25ce2e40223`
- `patchrail-0.1.0-py3-none-any.whl`
  - SHA256: `5f1f91e36fce4197a6cf8405da2ac5bfcbb6cefa1cb393464349c868e9719dfd`

## Manual Gates Remaining

These steps remain intentionally separate:

- publish the package to PyPI when package index credentials are available;
- announce the release publicly;
- submit the Codex for Open Source application.

## Next Evidence To Add

- first PyPI release URL after manual publish;
- install verification from PyPI after publish;
- external maintainer pilot outcomes;
- real adoption metrics, without placeholder inflation.
