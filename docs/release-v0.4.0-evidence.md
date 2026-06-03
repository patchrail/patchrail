# v0.4.0 Release Evidence

Status: release candidate evidence, not a published release.

This page records the current evidence for the read-only funded issue discovery
milestone. It is safe to prepare and review locally. It does not bump the
package version, create or push tags, publish to PyPI, announce publicly,
contact third-party maintainers, claim funded issues, or apply to external
programs.

## Scope

v0.4.0 is the funded issue scout milestone from the OSS plan, implemented only
as local sustainability metadata. The current candidate evidence covers:

- `patchrail funded-issues list` over local JSON metadata.
- Safe-only filtering by default.
- `--include-risky` limited to local output visibility.
- `patchrail funded-issues explain` with recommendation, risk flags,
  contribution-readiness signals, and blocked actions.
- `patchrail funded-issues import` for local provider exports from `algora`,
  `github`, `openpledge`, and `polar`.
- Offline examples in `examples/funded-issues-readonly`.
- Explicitly blocked automatic claims, automatic pull requests, issue comments,
  mass outreach, and money-only ranking.
- No provider API fetch, scraping, credentials, billing, external model calls,
  or GitHub write permissions.

## Local Evidence Commands

Run these commands from the repository root before tagging v0.4.0:

```bash
uv run --extra dev pytest -q tests/test_funded_issues_cli.py tests/test_public_workflows.py
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev python examples/funded-issues-readonly/run_demo.py --output .patchrail-funded-demo --force
uv run --extra dev patchrail funded-issues list --source examples/funded-issues-readonly/issues.json --format json
uv run --extra dev patchrail funded-issues explain example/project#42 --source examples/funded-issues-readonly/issues.json --format markdown
uv run --extra dev patchrail funded-issues import --provider github --source examples/funded-issues-readonly/provider-github-export.json --format json
uv run --extra dev patchrail doctor --format json
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
```

Current evidence snapshot from 2026-06-03:

- Funded issue CLI tests cover safe-only defaults, risky visibility opt-in,
  explanation output, unknown-reference errors, provider export normalization,
  and demo artifacts.
- The funded-issues-readonly demo runs end-to-end and produces a stable
  `summary.json` matching
  [demo-summary.expected.json](../examples/funded-issues-readonly/demo-summary.expected.json).
- The default list view filters out high-risk metadata.
- High-risk metadata remains inspectable only when explicitly requested and
  never enables write actions.
- The ethics docs describe funded issues as sustainability metadata, not bounty
  farming or automation targets.

## Public Artifacts

- Funded issue ethics: [docs/funded-issues-ethics.md](funded-issues-ethics.md)
- Read-only demo: [examples/funded-issues-readonly](../examples/funded-issues-readonly/README.md)
- Public workflow ledger: [docs/public-workflow-ledger.md](public-workflow-ledger.md)
- OSS evidence tracker: [docs/oss-program-evidence.md](oss-program-evidence.md)
- Codex for OSS evidence: [docs/openai-codex-for-oss-evidence.md](openai-codex-for-oss-evidence.md)

## Manual Gates Before Publishing

These actions remain maintainer gates:

- Bump `pyproject.toml` to the intended v0.4.x version.
- Rebuild sdist and wheel after the version bump.
- Run wheel smoke from a fresh environment.
- Push a release-prep PR and wait for public CI success.
- Tag the release and create the GitHub Release.
- Publish to PyPI only when the maintainer has configured the credential.
- Announce or request external program review only with real, current metrics.

## Current Blockers

- PyPI publishing is blocked by missing local publishing credentials.
- External adoption evidence is still pending consent-only pilots.
- Owned-repo issue-to-PR evidence now exists in
  [docs/public-workflow-ledger.md](public-workflow-ledger.md); formal visible
  Codex review links remain pending.

These blockers do not prevent local v0.4.0 preparation, docs, tests, or read-only
demo hardening.
