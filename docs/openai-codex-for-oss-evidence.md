# Codex for Open Source Evidence

This page tracks the evidence PatchRail needs before applying to OpenAI's Codex
for Open Source program. Do not submit an application from placeholder metrics.

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
- Adopter list: [ADOPTERS.md](../ADOPTERS.md) is permission-only and currently
  has no public external adopters listed
- Public CI fixtures: 138 sanitized synthetic fixtures in the local benchmark
- Maintainer pilot path: [docs/pilot-guide.md](pilot-guide.md) documents a
  consent-only read-only trial flow for redacted CI logs and optional fixture
  contributions
- Consent-only pilot outcome example:
  [examples/pilot-outcome](../examples/pilot-outcome/README.md) shows the safe
  shape for a public pilot summary without raw logs or unapproved repo mentions
- Owned-repo consent-only pilot outcome:
  [patchrail-own-repo-20260603.md](../examples/pilot-outcome/patchrail-own-repo-20260603.md)
  records a maintainer-reviewed local pilot on `patchrail/patchrail`; this is
  public project evidence, not an external adopter signal
- Public maintenance workflow ledger:
  [docs/public-workflow-ledger.md](public-workflow-ledger.md) links owned-repo
  issues to focused pull requests and tracks focused maintainer PR evidence
  without claiming external adoption
- Public review packet:
  `patchrail evidence review-packet --format markdown` turns the workflow
  ledger into a local owned-repo review packet while explicitly leaving external
  adoption, formal Codex review links, PyPI downloads, and third-party write
  actions unclaimed
- Application gate:
  `patchrail evidence application-gate --format markdown` fails closed until
  PyPI telemetry, permissioned external evidence, and visible review links are
  real rather than placeholder-derived
- Pilot pack command: `patchrail ci pilot-pack` creates a local redacted review
  bundle with a manifest, report, result JSON, and no raw log copy
- Pilot summary command: `patchrail ci pilot-summary` turns a reviewed pack into
  a safe Markdown/JSON outcome and keeps repository names private unless
  `--repository-mention-approved yes` is set
- Pilot pack queue importer: `patchrail queue add --from-pilot-pack` turns that
  consent-only bundle into a pending Agent Control Plane item without raw logs
  or GitHub write permissions
- Public issue queue: launch issues for fixtures, contribution docs,
  release-prep evidence, CI maintenance, GitHub Actions artifacts, and the
  Agent Control Plane
- Current evidence follow-up issues:
  [#67](https://github.com/patchrail/patchrail/issues/67) for PyPI publish,
  [#69](https://github.com/patchrail/patchrail/issues/69) for real adoption
  and ecosystem signal tracking
- Completed owned-repo pilot issue:
  [#68](https://github.com/patchrail/patchrail/issues/68) records the first
  consent-only pilot outcome on PatchRail's own public repository

## Codex Workflows In Use

Current public evidence is local, owned-repository, and preparatory:

- PR review: public own-repo PR history is tracked in
  [public-workflow-ledger.md](public-workflow-ledger.md); formal visible Codex
  review links are still pending. Recent owned-repo PR evidence includes
  [#83](https://github.com/patchrail/patchrail/pull/83),
  [#84](https://github.com/patchrail/patchrail/pull/84), and
  [#85](https://github.com/patchrail/patchrail/pull/85), with the current
  ledger extended through [#94](https://github.com/patchrail/patchrail/pull/94);
  all listed focused maintainer PRs were merged with public CI success.
- Issue triage: public own-repo issues are tracked in
  [public-workflow-ledger.md](public-workflow-ledger.md), including CI fixture,
  Agent Control Plane, security-boundary, and pilot-feedback work
- Release automation: release-prep checklists and evidence PRs are documented
  in [release-process.md](release-process.md) and
  [public-workflow-ledger.md](public-workflow-ledger.md); formal visible Codex
  release-prep links are still pending
- Agent skills: `.agents/skills/patchrail-ci-triage`,
  `.agents/skills/patchrail-release-captain`, and
  `.agents/skills/patchrail-review-guardrails` document bounded maintainer
  workflows for CI triage, release prep, and safety-sensitive review
- CI triage: public CI is green, and the read-only triage workflow is installed for failed CI runs
- Agent control plane: experimental local SQLite queue and `127.0.0.1` HTTP API
  added for human-gated maintainer work items, reviewable proposal records,
  approval decisions, status, and audit events
- Funded issue scout: experimental read-only `funded-issues` CLI now inspects
  local metadata with safe-only filtering, offline provider export import, and
  explicit anti-abuse blocked actions

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
  review, public CI run, and remaining manual gates.
- v0.2.0 release-candidate evidence:
  [docs/release-v0.2.0-evidence.md](release-v0.2.0-evidence.md) records the
  138-fixture CI Janitor benchmark, read-only GitHub Actions artifact, pilot
  guide, metrics tracker, and remaining manual gates.
- v0.3.0 release-candidate evidence:
  [docs/release-v0.3.0-evidence.md](release-v0.3.0-evidence.md) records the
  Agent Control Plane queue CLI/API, schemas, demo flow, approval gates, and
  remaining manual gates.
- v0.4.0 release-candidate evidence:
  [docs/release-v0.4.0-evidence.md](release-v0.4.0-evidence.md) records the
  funded issue read-only CLI, safe-only filters, offline provider export import,
  ethics boundary, demo output, and remaining manual gates.
- Published GitHub Release:
  <https://github.com/patchrail/patchrail/releases/tag/v0.1.0>
  targets `07b4934d91866c3ea2978c2aff265f923cd232bf` and includes checked
  sdist/wheel assets.
- Manual gates: PyPI publish, public announcements, and external applications
  remain explicit maintainer actions.
- Tests after the shared queue status contract: `uv run --extra dev pytest -q` -> 55 passed.
- Lint: `uv run --extra dev ruff check .` -> all checks passed.
- Format after the shared queue status contract: `uv run --extra dev ruff format --check .` -> 21 files already formatted.
- CI benchmark: `uv run --extra dev patchrail ci benchmark examples/ci-triage --format json` -> 138 / 138 fixtures passed.
- Consent-only pilot metrics: `uv run --extra dev patchrail ci pilot-metrics examples/pilot-outcome/*.summary.json --format json` separates owned-repo public mentions from external repository mentions so `patchrail/*` outcomes are not counted as external adopters.
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
- Pilot pack importer: `patchrail queue add --from-pilot-pack patchrail-pilot-pack`
  validates `pilot-manifest.json`, confirms the raw log was not copied, stores
  references to the redacted log/report/result, and keeps
  `write_actions_allowed=false`.
- Queue audit trail: `patchrail queue audit --format jsonl` exports local
  `work_item_added`, `work_item_approved`, `work_item_rejected`, and
  `work_items_exported` events without granting GitHub write permissions.
- Queue audit summary: `patchrail queue audit-summary --format json` emits
  `patchrail.queue_audit_summary.v1` and verifies the required local human-gate
  events without appending events or executing queued proposals.
- Proposal records: `patchrail queue proposal add/show/approve/reject` links a
  queued CI failure to a local patch plan and records `proposal_added`,
  `proposal_approved`, and `proposal_rejected` audit events without executing
  the plan.
- Local queue API: `patchrail serve --host 127.0.0.1 --port 8765` exposes
  `/health`, `/status`, `/work-items`, `/proposals`, and `/audit-events` for
  local dashboards/demos. The API rejects non-local bind hosts and reports no
  billing, external model, network, or GitHub write permission requirement.
- HTTP API evidence: `patchrail evidence http-api --format json` starts an
  ephemeral `127.0.0.1` server, exercises work-item/proposal create, approve,
  reject, status, list, and audit endpoints, and reports `local_http_api_ready`
  without exposing local temporary database paths. The artifact includes the
  `/status` human gate summary and verifies that write actions remain locked.
- Shared queue status contract: `patchrail queue status --format json` and
  `GET /status` both expose `patchrail.queue_status.v1`, with the schema
  available through `patchrail schema queue-status` and
  [schemas/queue_status.schema.json](../schemas/queue_status.schema.json).
- Safety doctor: `uv run --extra dev patchrail doctor --format json` -> `status: ok`, `local_first: true`, and no billing, network, external model, or GitHub write permission required.
- Distribution check: `uv run --extra dev python -m build` produced wheel and sdist; `uv run --extra dev twine check dist/*` passed both artifacts.
- Wheel smoke: installed `dist/patchrail-0.1.0-py3-none-any.whl` in a fresh `.pkg-smoke` virtual environment, then ran `patchrail doctor --format json` and `patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text`.
- Public CI: <https://github.com/patchrail/patchrail/actions/workflows/ci.yml> runs tests, lint, benchmark and package smoke on every push to `main`; the test matrix covers Python 3.11, 3.12, and 3.13.
- v0.1.0 release evidence PR: <https://github.com/patchrail/patchrail/pull/17>
  passed remote CI at <https://github.com/patchrail/patchrail/actions/runs/26869827161>.
- Agent skills are included in the source distribution so maintainers can review
  the same workflow prompts from a local checkout or packaged source artifact.
- Public triage workflow: <https://github.com/patchrail/patchrail/actions/runs/26862165709> -> skipped because the triggering CI run succeeded.
- GitHub Actions artifact example:
  [`examples/github-action`](../examples/github-action/README.md) documents the
  read-only `patchrail-ci-triage` artifact with `ci-report.md`,
  `ci-result.json`, `fixture-benchmark.json`, `fixture-benchmark-summary.md`,
  and `doctor.json`.
- Pilot pack smoke:
  `patchrail ci pilot-pack --log examples/ci-triage/dependency-failure.log --out-dir .patchrail-pilot-pack-smoke`
  creates a local redacted bundle with `pilot-manifest.json`, `patchrail-report.md`,
  `patchrail-result.json`, `failed-ci.redacted.log`, and no raw log copy.
- Owned-repo pilot outcome:
  [`examples/pilot-outcome/patchrail-own-repo-20260603.md`](../examples/pilot-outcome/patchrail-own-repo-20260603.md)
  and
  [`patchrail-own-repo-20260603.summary.json`](../examples/pilot-outcome/patchrail-own-repo-20260603.summary.json)
  record a `patchrail/patchrail` local pilot summary with
  `repository_mention_approved=true`, `raw_log_copied=false`,
  `external_model_required=false`, and `github_write_permission_required=false`.
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
- Consent-only pilot outcome example:
  [examples/pilot-outcome](../examples/pilot-outcome/README.md) gives maintainers
  a copyable safe summary that does not count as adoption evidence.
- Public maintenance workflow ledger:
  [docs/public-workflow-ledger.md](public-workflow-ledger.md) records issue-to-PR
  cycles for owned-repo work such as #59 -> #60, #57 -> #58, #55 -> #56,
  #53 -> #54, #51 -> #52, and #61 -> #62, plus recent focused maintainer PRs including
  [#83](https://github.com/patchrail/patchrail/pull/83),
  [#84](https://github.com/patchrail/patchrail/pull/84), and
  [#85](https://github.com/patchrail/patchrail/pull/85),
  [#86](https://github.com/patchrail/patchrail/pull/86), and
  [#87](https://github.com/patchrail/patchrail/pull/87), now extended through
  [#94](https://github.com/patchrail/patchrail/pull/94). These remain
  owned-repo workflow evidence, not external adoption.
- Public review packet smoke:
  `uv run --extra dev patchrail evidence review-packet --format json` reads the
  ledger locally and reports owned-repo review items without network, GitHub
  write permission, external model, billing, external-adopter claims, PyPI
  download claims, or formal review claims.
- Application gate smoke:
  `uv run --extra dev patchrail evidence application-gate --format json`
  currently returns `not_ready` and `do_not_apply_yet`; it keeps the external
  application blocked while PyPI telemetry, permissioned external adopters, and
  formal visible review links remain missing.

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
- <https://github.com/patchrail/patchrail/issues/68> - run the first consent-only CI pilot and record an approved outcome.
- <https://github.com/patchrail/patchrail/issues/69> - track real adoption and ecosystem signals before any external application.

## Safety Posture

- Human approval gates for write actions
- No automatic bounty claiming
- No mass comments
- No automatic pull requests to third-party repositories
- Funded issue discovery is read-only, safe-only by default, and local-source only,
  including provider export import
- Local CI log processing by default
- Redaction guidance in README, quickstart, and threat model

## Evidence To Add Before Applying

- Formal public PR links reviewed with Codex
- Formal public issues triaged with Codex
- Formal release-prep PR prepared with Codex
- PyPI release link after package index publish
- PyPI download stats
- External adopter feedback
- Pilot outcomes from maintainers who opted into read-only local trials
- External pilot outcome summaries that follow
  [examples/pilot-outcome](../examples/pilot-outcome/README.md)
- Permissioned adopter entries linked from `ADOPTERS.md`
