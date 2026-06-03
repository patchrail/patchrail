# Open Source Program Evidence

This page tracks public evidence needed before applying to selective open-source
support programs. Do not submit an application from placeholder metrics.

## Repository Role

Pablo Guillén is the primary maintainer of PatchRail.

## Usage Signals

- Repository: <https://github.com/patchrail/patchrail>
- GitHub stars: 0 on 2026-06-03, immediately after public launch
- Monthly PyPI downloads: pending first PyPI release
- GitHub Release: <https://github.com/patchrail/patchrail/releases/tag/v0.1.0>
- External repositories using PatchRail: pending pilots
- External contributors: pending external contributions
- Public metrics tracker: [docs/metrics.md](metrics.md) records current public
  signals without placeholder promotion
- Local evidence snapshot: `patchrail evidence snapshot --format markdown`
  summarizes CI fixtures, read-only workflow posture, release evidence pages,
  Agent Control Plane demo, Funded Issue Scout demo, pilot summaries, and
  remaining evidence gaps without network or write actions
- Agent Control Plane evidence audit:
  `patchrail evidence control-plane --format markdown` verifies the checked-in
  local queue demo summary, required audit events, required artifacts, human
  approval gates, and risky proposal rejection without network or write actions
- Public CI artifact: the main CI workflow uploads `patchrail-oss-evidence`
  with `evidence-snapshot.json` and `evidence-snapshot.md` after tests,
  benchmark, and package smoke pass. This is project-health evidence only; it
  does not count as external adoption or PyPI download evidence.
- Adopter list: [ADOPTERS.md](../ADOPTERS.md) is permission-only and currently
  has no public external adopters listed
- Public CI fixtures: 132 sanitized synthetic fixtures in the local benchmark
- Fixture hygiene gate: `patchrail ci fixture-check examples/ci-triage --format json`
  validates 132 / 132 fixtures before sharing
- Maintainer pilot path: [docs/pilot-guide.md](pilot-guide.md) documents a
  consent-only read-only trial flow for redacted CI logs and optional fixture
  contributions
- Consent-only pilot request package:
  [docs/pilot-request-package.md](pilot-request-package.md) records the
  maintainer consent checklist, evidence intake rules, and `ADOPTERS.md`
  listing boundary before any external pilot is counted
- Consent-only pilot outcome example:
  [examples/pilot-outcome](../examples/pilot-outcome/README.md) shows how to
  summarize a pilot without raw logs or unapproved repository mentions
- Owned-repo consent-only pilot outcome:
  [patchrail-own-repo-20260603.md](../examples/pilot-outcome/patchrail-own-repo-20260603.md)
  records a maintainer-reviewed local pilot on `patchrail/patchrail`; this is
  public project evidence, not an external adopter signal
- Public maintenance workflow ledger:
  [docs/public-workflow-ledger.md](public-workflow-ledger.md) links owned-repo
  issues to focused pull requests and tracks focused maintainer PR evidence
  without claiming external adoption
- Public review packet:
  `patchrail evidence review-packet --format markdown` parses the workflow
  ledger into an owned-repo issue-to-PR and focused-maintainer-PR packet without
  network, GitHub write permission, external model calls, PyPI download claims,
  external-adopter claims, or formal Codex review claims
- Public issue queue: launch issues for fixtures, contribution docs,
  release-prep evidence, CI maintenance, GitHub Actions artifacts, the Agent
  Control Plane, and the read-only Funded Issue Scout
- Current evidence follow-up issues:
  [#67](https://github.com/patchrail/patchrail/issues/67) for PyPI publish,
  [#69](https://github.com/patchrail/patchrail/issues/69) for real adoption
  and ecosystem signal tracking
- Completed owned-repo pilot issue:
  [#68](https://github.com/patchrail/patchrail/issues/68) records the first
  consent-only pilot outcome on PatchRail's own public repository

## Maintenance Workflows

PatchRail's public safety posture is local-first and human-approved:

- CI failure triage produces Markdown, JSON or text reports.
- Redaction runs locally before fixture sharing.
- `patchrail ci fixture-check` verifies neighboring expected metadata,
  classifier agreement, confidence floors, and redaction hygiene before a
  fixture is proposed.
- `patchrail doctor` reports that v0.1 requires no billing, network, external model, or GitHub write permission.
- GitHub Actions triage produces a read-only artifact and does not comment,
  open pull requests, call external models, or request write permissions.
- [Public maintenance workflow ledger](public-workflow-ledger.md) records
  owned-repo issue-to-PR cycles separately from external adoption metrics.
- `patchrail queue add --from-pilot-pack` validates a consent-only pilot pack
  and imports it as a pending local work item without copying raw logs or
  granting write permissions.
- Agent Control Plane work items, proposal records, approval decisions, and
  audit events stay local in SQLite unless a maintainer exports them.
- Funded Issue Scout is read-only, safe-only by default, and local-source only
  for the public demo; it blocks automatic claims, comments, pull requests,
  mass outreach, and money-only ranking.
- Any future write action must use human approval gates.

## Local Release Evidence

Last verified: 2026-06-03.

- Release-prep checklist: [docs/release-process.md](release-process.md) requires
  test, lint, benchmark, doctor, build, wheel smoke, safety, privacy, and public
  CI evidence before any publish step.
- Published GitHub Release:
  <https://github.com/patchrail/patchrail/releases/tag/v0.1.0>
- v0.1.0 release-prep artifact:
  [docs/release-v0.1.0-evidence.md](release-v0.1.0-evidence.md) records the
  checked sdist/wheel names, local command results, wheel smoke test, safety
  review, public CI run, and remaining manual gates.
- v0.2.0 release-candidate artifact:
  [docs/release-v0.2.0-evidence.md](release-v0.2.0-evidence.md) records the
  132-fixture benchmark, fixture hygiene gate, read-only GitHub Action artifact,
  pilot/adopter evidence surfaces, and remaining manual gates before any version
  bump, tag, PyPI publish, announcement, or external application.
- Manual gates: PyPI publish, public announcements, and external applications
  remain explicit maintainer actions.
- Tests: `uv run --extra dev pytest -q` -> 55 passed.
- Lint: `uv run --extra dev ruff check .` -> all checks passed.
- Format: `uv run --extra dev ruff format --check .` -> 21 files already formatted.
- Fixture hygiene: `uv run --extra dev patchrail ci fixture-check examples/ci-triage --format json` -> 132 / 132 fixtures passed.
- CI benchmark: `uv run --extra dev patchrail ci benchmark examples/ci-triage --format json` -> 132 / 132 fixtures passed, top-1 fixture accuracy 1.0, and 12 root-cause families covered.
- Consent-only pilot metrics: `uv run --extra dev patchrail ci pilot-metrics examples/pilot-outcome/*.summary.json --format json` separates owned-repo public mentions from external repository mentions so `patchrail/*` outcomes are not counted as external adopters.
- Queue demo: `uv run --extra dev patchrail queue --db /tmp/patchrail-demo.sqlite init` and `patchrail queue add/list/approve/export` run locally with no write actions.
- Agent Control Plane demo:
  [`examples/local-agent-queue`](../examples/local-agent-queue/README.md)
  links `ci explain` to `queue add`, `queue approve`, and `queue export`
  using only local files and SQLite.
- Agent Control Plane evidence command:
  `patchrail evidence control-plane --format markdown` reports
  `local_demo_ready` from
  [`demo-summary.expected.json`](../examples/local-agent-queue/demo-summary.expected.json)
  when the demo artifacts, audit events, approval gate, proposal gate, and
  risky-proposal rejection are all present.
- CI result importer: `patchrail queue add --from-ci-result ci-result.json`
  turns the read-only CI artifact JSON into a pending local queue item while
  keeping `write_actions_allowed=false`.
- Pilot pack importer: `patchrail queue add --from-pilot-pack patchrail-pilot-pack`
  validates `pilot-manifest.json`, confirms the raw log was not copied, stores
  references to the redacted log/report/result, and keeps
  `write_actions_allowed=false`.
- Pilot summary command: `patchrail ci pilot-summary --pack patchrail-pilot-pack`
  creates a safe Markdown/JSON outcome record and suppresses repository names
  unless public mention was explicitly approved.
- Owned-repo pilot outcome:
  [`examples/pilot-outcome/patchrail-own-repo-20260603.md`](../examples/pilot-outcome/patchrail-own-repo-20260603.md)
  and
  [`patchrail-own-repo-20260603.summary.json`](../examples/pilot-outcome/patchrail-own-repo-20260603.summary.json)
  record a `patchrail/patchrail` local pilot summary with
  `repository_mention_approved=true`, `raw_log_copied=false`,
  `external_model_required=false`, and `github_write_permission_required=false`.
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
- Shared queue status contract: `patchrail queue status --format json` and
  `GET /status` both expose `patchrail.queue_status.v1`; the public schema is
  available through `patchrail schema queue-status` and
  [schemas/queue_status.schema.json](../schemas/queue_status.schema.json).
- Safety doctor: `uv run --extra dev patchrail doctor --format json` -> `status: ok`, `local_first: true`, and no billing, network, external model, or GitHub write permission required.
- Distribution check: `uv run --extra dev python -m build` produced wheel and sdist; `uv run --extra dev twine check dist/*` passed both artifacts.
- Wheel smoke: installed `dist/patchrail-0.1.0-py3-none-any.whl` in a fresh
  `.pkg-smoke` virtual environment, then ran `patchrail doctor --format json`
  and `patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text`.
- Public CI: <https://github.com/patchrail/patchrail/actions/workflows/ci.yml> runs tests, lint, benchmark and package smoke on every push to `main`.
- Public triage workflow: <https://github.com/patchrail/patchrail/actions/runs/26862165709> -> skipped because the triggering CI run succeeded.
- GitHub Actions artifact example:
  [`examples/github-action`](../examples/github-action/README.md) documents the
  read-only `patchrail-ci-triage` artifact with `ci-report.md`,
  `ci-result.json`, `fixture-benchmark.json`, `fixture-benchmark-summary.md`,
  and `doctor.json`.
- Funded issue read-only demo:
  [`examples/funded-issues-readonly`](../examples/funded-issues-readonly/README.md)
  shows `patchrail funded-issues list/explain` over local JSON and
  `patchrail funded-issues import` over a synthetic GitHub export. The commands
  report blocked actions including automatic claims, comments, pull requests,
  mass outreach, and money-only ranking, while reporting no network, billing,
  model, or GitHub write-permission requirement.
- Maintainer pilot guide: [docs/pilot-guide.md](pilot-guide.md) gives external
  maintainers a no-write-access path to run `doctor`, `redact`, `ci explain`,
  `ci classify`, optional local queue import, and fixture contribution.
- Pilot request package: [docs/pilot-request-package.md](pilot-request-package.md)
  gives maintainers copyable local instructions while preserving the rule that
  PatchRail does not open pull requests, comment on issues, claim funded issues,
  contact maintainers automatically, or count unapproved repository names.
- Consent-only pilot outcome example:
  [examples/pilot-outcome](../examples/pilot-outcome/README.md) is synthetic and
  does not count as adoption evidence.
- Public maintenance workflow ledger:
  [docs/public-workflow-ledger.md](public-workflow-ledger.md) records owned-repo
  maintenance cycles such as #59 -> #60, #57 -> #58, #55 -> #56, #53 -> #54,
  #51 -> #52, and #61 -> #62, plus recent focused PR evidence including
  [#83](https://github.com/patchrail/patchrail/pull/83),
  [#84](https://github.com/patchrail/patchrail/pull/84), and
  [#85](https://github.com/patchrail/patchrail/pull/85),
  [#86](https://github.com/patchrail/patchrail/pull/86), and
  [#87](https://github.com/patchrail/patchrail/pull/87), each with public CI
  success. These PRs are owned-repo workflow evidence, not external adoption.
- Public review packet: `uv run --extra dev patchrail evidence review-packet --format json`
  reports owned-repo review evidence from the ledger while keeping external
  adoption, formal Codex review, PyPI downloads, and third-party write-action
  claims set to false.

## Public Launch Issues

- <https://github.com/patchrail/patchrail/issues/27> - add more Python dependency-resolution CI fixtures.
- <https://github.com/patchrail/patchrail/issues/28> - add Node and TypeScript CI drift fixtures.
- <https://github.com/patchrail/patchrail/issues/29> - document the contributor path for sanitized CI fixtures.
- <https://github.com/patchrail/patchrail/issues/30> - create the first release-prep evidence checklist.
- <https://github.com/patchrail/patchrail/issues/31> - review GitHub Actions Node 24 compatibility before the runner default changes.
- <https://github.com/patchrail/patchrail/issues/32> - add Agent Control Plane demo flow.
- <https://github.com/patchrail/patchrail/issues/33> - add GitHub Actions triage artifact example.
- <https://github.com/patchrail/patchrail/issues/34> - import CI result JSON into the local queue.
- <https://github.com/patchrail/patchrail/issues/35> - export queue audit events for Agent Control Plane.
- <https://github.com/patchrail/patchrail/issues/36> - add proposal records for the local Agent Control Plane.
- <https://github.com/patchrail/patchrail/issues/37> - add read-only funded issue scout.

## Active Evidence Follow-Up Issues

- <https://github.com/patchrail/patchrail/issues/67> - publish v0.1.0 to PyPI and verify the public install path.
- <https://github.com/patchrail/patchrail/issues/69> - track real adoption and ecosystem signals before any external application.

## Evidence To Add Before Applying

- Formal PR review examples for parser, redaction or workflow changes.
- Formal issue triage examples for CI fixture requests.
- Formal release-prep examples showing changelog, version and quickstart checks.
- PyPI release link after package index publish.
- PyPI download stats.
- External adopter feedback and permissioned adopter entries.
- External pilot outcomes from maintainers who opted into read-only local trials.
- Permissioned pilot request package outcomes that pass the public listing rule.
- Pilot outcome summaries following
  [examples/pilot-outcome](../examples/pilot-outcome/README.md).

## Safety Posture

- No automatic bounty claiming.
- No mass comments.
- No automatic pull requests to third-party repositories.
- Funded issue discovery is read-only, safe-only by default, and local-source only,
  including provider export import.
- Local CI log processing by default.
- Redaction guidance in README, quickstart and threat model.
