# Open Source Program Evidence

This page tracks public evidence needed before applying to selective open-source
support programs. Do not submit an application from placeholder metrics.

## Repository Role

Pablo Guillén is the primary maintainer of PatchRail.

## Usage Signals

- Repository: <https://github.com/patchrail/patchrail>
- GitHub stars: 0 on 2026-06-03, immediately after public launch
- Monthly PyPI downloads: pending first PyPI release
- External repositories using PatchRail: pending pilots
- External contributors: pending external contributions
- Public CI fixtures: 40 sanitized synthetic fixtures in the local benchmark
- Public issue queue: 5 launch issues for fixtures, contribution docs, release-prep evidence, and CI maintenance

## Maintenance Workflows

PatchRail's public safety posture is local-first and human-approved:

- CI failure triage produces Markdown, JSON or text reports.
- Redaction runs locally before fixture sharing.
- `patchrail doctor` reports that v0.1 requires no billing, network, external model, or GitHub write permission.
- Write actions are outside v0.1 scope.
- Future agent workflows must use human approval gates.

## Local Release Evidence

Last verified: 2026-06-03.

- Release-prep checklist: [docs/release-process.md](release-process.md) requires
  test, lint, benchmark, doctor, build, wheel smoke, safety, privacy, and public
  CI evidence before any publish step.
- Manual gates: release tags, PyPI publish, GitHub releases, public
  announcements, and external applications remain explicit maintainer actions.
- Tests: `uv run --extra dev pytest -q` -> 16 passed.
- Lint: `uv run --extra dev ruff check .` -> all checks passed.
- CI benchmark: `uv run --extra dev patchrail ci benchmark examples/ci-triage --format json` -> 101/101 fixtures passed.
- Queue demo: `uv run --extra dev patchrail queue --db /tmp/patchrail-demo.sqlite init` and `patchrail queue add/list/approve/export` run locally with no write actions.
- Agent Control Plane demo:
  [`examples/local-agent-queue`](../examples/local-agent-queue/README.md)
  links `ci explain` to `queue add`, `queue approve`, and `queue export`
  using only local files and SQLite.
- CI result importer: `patchrail queue add --from-ci-result ci-result.json`
  turns the read-only CI artifact JSON into a pending local queue item while
  keeping `write_actions_allowed=false`.
- Safety doctor: `uv run --extra dev patchrail doctor --format json` -> `status: ok`, `local_first: true`, and no billing, network, external model, or GitHub write permission required.
- Distribution check: `uv run --extra dev python -m build` produced wheel and sdist; `uv run --extra dev twine check dist/*` passed both artifacts.
- Public CI: <https://github.com/patchrail/patchrail/actions/workflows/ci.yml> runs tests, lint, benchmark and package smoke on every push to `main`.
- Public triage workflow: <https://github.com/patchrail/patchrail/actions/runs/26862165709> -> skipped because the triggering CI run succeeded.
- GitHub Actions artifact example:
  [`examples/github-action`](../examples/github-action/README.md) documents the
  read-only `patchrail-ci-triage` artifact with `ci-report.md`,
  `ci-result.json`, `fixture-benchmark.json`, and `doctor.json`.

## Public Launch Issues

- <https://github.com/patchrail/patchrail/issues/1> - add more Python dependency-resolution CI fixtures.
- <https://github.com/patchrail/patchrail/issues/2> - add Node and TypeScript CI drift fixtures.
- <https://github.com/patchrail/patchrail/issues/3> - document the contributor path for sanitized CI fixtures.
- <https://github.com/patchrail/patchrail/issues/4> - create the first release-prep evidence checklist.
- <https://github.com/patchrail/patchrail/issues/5> - review GitHub Actions Node 24 compatibility before the runner default changes.
- <https://github.com/patchrail/patchrail/issues/6> - add Agent Control Plane demo flow.

## Evidence To Add Before Applying

- PR review examples for parser, redaction or workflow changes.
- Issue triage examples for CI fixture requests.
- Release-prep examples showing changelog, version and quickstart checks.
- Links to releases, PyPI stats and adopter feedback.

## Safety Posture

- No automatic bounty claiming.
- No mass comments.
- No automatic pull requests to third-party repositories.
- Local CI log processing by default.
- Redaction guidance in README, quickstart and threat model.
