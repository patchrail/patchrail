# Codex for Open Source Evidence

This page tracks the evidence PatchRail needs before applying to OpenAI's Codex
for Open Source program. Do not submit an application from placeholder metrics.

## Repository Role

Pablo Guillén is the primary maintainer of PatchRail.

## Usage Signals

- Repository: <https://github.com/patchrail/patchrail>
- GitHub stars: 0 on 2026-06-03, immediately after public launch
- Monthly PyPI downloads: pending first PyPI release
- External repositories using PatchRail: pending pilots
- External contributors: pending external contributions
- Public CI fixtures: 101 sanitized synthetic fixtures in the local benchmark
- Maintainer pilot path: [docs/pilot-guide.md](pilot-guide.md) documents a
  consent-only read-only trial flow for redacted CI logs and optional fixture
  contributions
- Public issue queue: launch issues for fixtures, contribution docs,
  release-prep evidence, CI maintenance, GitHub Actions artifacts, and the
  Agent Control Plane

## Codex Workflows In Use

Current public evidence is local and preparatory:

- PR review: pending public PR history
- Issue triage: launch issue queue created for fixture and docs work
- Release automation: first release-prep checklist is documented in
  [release-process.md](release-process.md); public PR history is pending
- CI triage: public CI is green, and the read-only triage workflow is installed for failed CI runs
- Agent control plane: experimental local SQLite queue and `127.0.0.1` HTTP API
  added for human-gated maintainer work items, reviewable proposal records,
  approval decisions, status, and audit events
- Funded issue scout: experimental read-only `funded-issues` CLI now inspects
  local metadata with safe-only filtering and explicit anti-abuse blocked actions

PatchRail's intended Codex usage is bounded to maintainer-approved work:

- PR review for parser, redaction, workflow, and release changes
- issue triage for CI classifier bugs and fixture requests
- CI-failure fix proposals after PatchRail emits a local report
- release-prep checks for changelog, version, docs, and package artifacts

## Local Release Evidence

Last verified: 2026-06-03.

- Release-prep checklist: [docs/release-process.md](release-process.md) now
  requires test, lint, benchmark, doctor, build, wheel smoke, safety, privacy,
  and public CI evidence before any publish step.
- v0.1.0 release-prep artifact:
  [docs/release-v0.1.0-evidence.md](release-v0.1.0-evidence.md) records the
  checked sdist/wheel names, local command results, wheel smoke test, safety
  review, and remaining manual gates.
- Manual gates: release tags, PyPI publish, GitHub releases, public
  announcements, and external applications remain explicit maintainer actions.
- Tests: `uv run --extra dev pytest -q` -> 32 passed.
- Lint: `uv run --extra dev ruff check .` -> all checks passed.
- Format: `uv run --extra dev ruff format --check .` -> 17 files already formatted.
- CI benchmark: `uv run --extra dev patchrail ci benchmark examples/ci-triage --format json` -> 101/101 fixtures passed.
- Queue demo: `uv run --extra dev patchrail queue --db /tmp/patchrail-demo.sqlite init` and `patchrail queue add/list/approve/export` run locally with no write actions.
- Agent Control Plane demo:
  [`examples/local-agent-queue`](../examples/local-agent-queue/README.md)
  links `ci explain` to `queue add`, `queue approve`, and `queue export`
  using only local files and SQLite.
- Executable Agent Control Plane evidence:
  `python examples/local-agent-queue/run_demo.py --output .patchrail-demo --force`
  produces `summary.json` matching
  [`demo-summary.expected.json`](../examples/local-agent-queue/demo-summary.expected.json).
- CI result importer: `patchrail queue add --from-ci-result ci-result.json`
  turns the read-only CI artifact JSON into a pending local queue item while
  keeping `write_actions_allowed=false`.
- Queue audit trail: `patchrail queue audit --format jsonl` exports local
  `work_item_added`, `work_item_approved`, `work_item_rejected`, and
  `work_items_exported` events without granting GitHub write permissions.
- Proposal records: `patchrail queue proposal add/show/approve/reject` links a
  queued CI failure to a local patch plan and records `proposal_added`,
  `proposal_approved`, and `proposal_rejected` audit events without executing
  the plan.
- Local queue API: `patchrail serve --host 127.0.0.1 --port 8765` exposes
  `/health`, `/status`, `/work-items`, `/proposals`, and `/audit-events` for
  local dashboards/demos. The API rejects non-local bind hosts and reports no
  billing, external model, network, or GitHub write permission requirement.
- Safety doctor: `uv run --extra dev patchrail doctor --format json` -> `status: ok`, `local_first: true`, and no billing, network, external model, or GitHub write permission required.
- Distribution check: `uv run --extra dev python -m build` produced wheel and sdist; `uv run --extra dev twine check dist/*` passed both artifacts.
- Wheel smoke: installed `dist/patchrail-0.1.0-py3-none-any.whl` in a fresh `.pkg-smoke` virtual environment, then ran `patchrail doctor --format json` and `patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text`.
- Public CI: <https://github.com/patchrail/patchrail/actions/workflows/ci.yml> runs tests, lint, benchmark and package smoke on every push to `main`; the test matrix covers Python 3.11, 3.12, and 3.13.
- Public triage workflow: <https://github.com/patchrail/patchrail/actions/runs/26862165709> -> skipped because the triggering CI run succeeded.
- GitHub Actions artifact example:
  [`examples/github-action`](../examples/github-action/README.md) documents the
  read-only `patchrail-ci-triage` artifact with `ci-report.md`,
  `ci-result.json`, `fixture-benchmark.json`, and `doctor.json`.
- Funded issue read-only demo:
  [`examples/funded-issues-readonly`](../examples/funded-issues-readonly/README.md)
  shows `patchrail funded-issues list/explain` over local JSON. The command
  reports blocked actions including automatic claims, comments, pull requests,
  mass outreach, and money-only ranking.
- Maintainer pilot guide: [docs/pilot-guide.md](pilot-guide.md) gives external
  maintainers a no-write-access path to run `doctor`, `redact`, `ci explain`,
  `ci classify`, optional local queue import, and fixture contribution.

## Public Launch Issues

- <https://github.com/patchrail/patchrail/issues/1> - add more Python dependency-resolution CI fixtures.
- <https://github.com/patchrail/patchrail/issues/2> - add Node and TypeScript CI drift fixtures.
- <https://github.com/patchrail/patchrail/issues/3> - document the contributor path for sanitized CI fixtures.
- <https://github.com/patchrail/patchrail/issues/4> - create the first release-prep evidence checklist.
- <https://github.com/patchrail/patchrail/issues/5> - review GitHub Actions Node 24 compatibility before the runner default changes.
- <https://github.com/patchrail/patchrail/issues/6> - add Agent Control Plane demo flow.
- <https://github.com/patchrail/patchrail/issues/7> - add GitHub Actions triage artifact example.
- <https://github.com/patchrail/patchrail/issues/8> - import CI result JSON into the local queue.
- <https://github.com/patchrail/patchrail/issues/9> - export queue audit events for Agent Control Plane.
- <https://github.com/patchrail/patchrail/issues/10> - add proposal records for the local Agent Control Plane.
- <https://github.com/patchrail/patchrail/issues/11> - add read-only funded issue scout.

## Safety Posture

- Human approval gates for write actions
- No automatic bounty claiming
- No mass comments
- No automatic pull requests to third-party repositories
- Funded issue discovery is read-only, safe-only by default, and local-source only
- Local CI log processing by default
- Redaction guidance in README, quickstart, and threat model

## Evidence To Add Before Applying

- Public PR links reviewed with Codex
- Public issues triaged with Codex
- Release-prep PR prepared with Codex
- Release links
- PyPI download stats
- External adopter feedback
- Pilot outcomes from maintainers who opted into read-only local trials
