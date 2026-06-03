# v0.2.0 Release Evidence

Status: release candidate evidence, not a published release.

This page records the current evidence for the CI Janitor v0.2 milestone. It is
safe to prepare and review locally. It does not bump the package version, create
or push tags, publish to PyPI, announce publicly, contact third-party
maintainers, or apply to external programs.

## Scope

v0.2.0 is the GitHub Actions integration and benchmark milestone from the OSS
plan. The current candidate evidence covers:

- CI fixture zoo expanded past the 100-case v0.2 bar.
- `patchrail ci benchmark` over 115 sanitized synthetic fixtures.
- `patchrail ci benchmark --summary-only` for short Markdown aggregate evidence.
- `patchrail ci fixture-check` as the pre-PR hygiene gate for fixture metadata,
  classifier agreement, confidence floors, and redaction checks.
- `patchrail ci pilot-pack` for a local redacted maintainer pilot bundle.
- Read-only GitHub Actions triage workflow and artifact example.
- Maintainer pilot guide for consent-only, local-first trials.
- Synthetic pilot outcome example for safe adopter feedback summaries.
- Permission-only `ADOPTERS.md` and public metrics tracker.
- No automatic pull requests, issue comments, funded issue claims, mass
  outreach, external model calls, billing, or GitHub write permissions.

## Local Evidence Commands

Run these commands from the repository root before tagging v0.2.0:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev patchrail ci fixture-check examples/ci-triage --format json
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
uv run --extra dev patchrail ci benchmark examples/ci-triage --format markdown --summary-only
uv run --extra dev patchrail ci pilot-pack --log examples/ci-triage/dependency-failure.log --out-dir .patchrail-pilot-pack-smoke
uv run --extra dev patchrail doctor --format json
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
```

Current evidence snapshot from 2026-06-03:

- Tests: 46 passed.
- Lint: all checks passed.
- Format: 19 files already formatted.
- Fixture hygiene: 115 / 115 fixtures passed.
- Benchmark: 115 total, 115 passed, 0 failed.
- Top-1 fixture accuracy: 1.0.
- Class coverage: 8 root-cause families.
- Pilot pack smoke: local redacted bundle generated without copying the raw log.
- Safety doctor: `status=ok`, `local_first=true`, and no billing, network,
  external model, or GitHub write permission required.
- v0.1.0 package artifacts already passed build, `twine check`, and wheel smoke;
  rebuild v0.2.0 artifacts after the maintainer version bump.

## Public Artifacts

- CI failure zoo: [docs/ci-failure-zoo.md](ci-failure-zoo.md)
- GitHub Action guide: [docs/github-action.md](github-action.md)
- Example triage artifact: [examples/github-action](../examples/github-action/README.md)
- Pilot guide: [docs/pilot-guide.md](pilot-guide.md)
- Pilot outcome example: [examples/pilot-outcome](../examples/pilot-outcome/README.md)
- Public workflow ledger: [docs/public-workflow-ledger.md](public-workflow-ledger.md)
- Metrics tracker: [docs/metrics.md](metrics.md)
- Adopter policy: [ADOPTERS.md](../ADOPTERS.md)
- OSS evidence tracker: [docs/oss-program-evidence.md](oss-program-evidence.md)

## Manual Gates Before Publishing

These actions remain maintainer gates:

- Bump `pyproject.toml` from `0.1.0` to `0.2.0`.
- Rebuild sdist and wheel after the version bump.
- Run wheel smoke from a fresh environment.
- Push a release-prep PR and wait for public CI success.
- Tag `v0.2.0` and create the GitHub Release.
- Publish to PyPI only when the maintainer has configured the credential.
- Announce or request external program review only with real, current metrics.

## Current Blockers

- PyPI publishing is blocked by missing local publishing credentials.
- External adoption evidence is still pending consent-only pilots.
- Owned-repo issue-to-PR evidence now exists in
  [docs/public-workflow-ledger.md](public-workflow-ledger.md); formal visible
  Codex review links remain pending.

These blockers do not prevent local v0.2.0 preparation, docs, tests, metrics, or
pilot-readiness work.
