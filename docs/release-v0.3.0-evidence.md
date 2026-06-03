# v0.3.0 Release Evidence

Status: release candidate evidence, not a published release.

This page records the current evidence for the local Agent Control Plane
milestone. It is safe to prepare and review locally. It does not bump the
package version, create or push tags, publish to PyPI, announce publicly,
contact third-party maintainers, or apply to external programs.

## Scope

v0.3.0 is the local agent queue milestone from the OSS plan. The current
candidate evidence covers:

- SQLite-backed work items for reviewable maintainer tasks.
- CI result import into pending local queue items.
- Pilot pack import into pending local queue items, including manifest
  validation that the raw CI log was not copied.
- Human approval and rejection states for work items.
- Local proposal records linked to queue items.
- Proposal approval and rejection audit events.
- Local audit summary for release-checkable human-gate coverage.
- JSON and JSONL exports for queue items, proposals, and audit events.
- Versioned queue JSON Schemas bundled in the package and mirrored in
  `schemas/`.
- Local-only HTTP API for status, health, work items, proposals, approvals, and
  audit events.
- Shared `patchrail.queue_status.v1` contract for `patchrail queue status`,
  `patchrail schema queue-status`, and `GET /status`.
- Shared `patchrail.queue_audit_summary.v1` contract for
  `patchrail queue audit-summary` and
  `patchrail schema queue-audit-summary`.
- Executable demo in `examples/local-agent-queue`.
- No pull request creation, issue comments, repository writes, external model
  calls, billing, or GitHub write permissions.

## Local Evidence Commands

Run these commands from the repository root before tagging v0.3.0:

```bash
uv run --extra dev pytest -q tests/test_queue_cli.py tests/test_queue_http_api.py tests/test_public_workflows.py
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev python examples/local-agent-queue/run_demo.py --output .patchrail-queue-demo --force
uv run --extra dev patchrail schema queue-work-item
uv run --extra dev patchrail schema queue-proposal
uv run --extra dev patchrail schema queue-audit-event
uv run --extra dev patchrail schema queue-audit-summary
uv run --extra dev patchrail schema queue-status
uv run --extra dev patchrail queue --db .patchrail-queue-demo/queue.sqlite audit-summary --format markdown
uv run --extra dev patchrail evidence control-plane --format markdown
uv run --extra dev patchrail evidence http-api --format markdown
uv run --extra dev patchrail ci pilot-pack --log examples/ci-triage/dependency-failure.log --out-dir .patchrail-pilot-pack-smoke
uv run --extra dev patchrail queue --db .patchrail-pilot.sqlite add --from-pilot-pack .patchrail-pilot-pack-smoke
uv run --extra dev patchrail serve --host 127.0.0.1 --port 8765 --db .patchrail-queue-demo/queue.sqlite
uv run --extra dev patchrail doctor --format json
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
```

Current evidence snapshot from 2026-06-03:

- Queue CLI coverage includes init, add, import from CI result, list, show,
  approve, reject, export, audit, and proposal operations.
- Queue HTTP API coverage includes local bind validation, health, status,
  work-item reads, approval decisions, proposal reads, proposal decisions, and
  audit event export.
- The local-agent-queue demo runs end-to-end and produces a stable
  `summary.json` matching
  [demo-summary.expected.json](../examples/local-agent-queue/demo-summary.expected.json).
- The same demo writes `audit-summary.json`; `patchrail queue audit-summary`
  reports `human_gates_exercised` only after required approval, rejection,
  proposal, and export events are present.
- `patchrail evidence control-plane --format markdown` reports
  `local_demo_ready` from the checked-in summary when required audit events,
  artifacts, source docs, human approval, proposal approval, risky-proposal
  rejection, and audit-summary gate coverage are all present.
- `patchrail evidence http-api --format markdown` starts an ephemeral
  `127.0.0.1` server, creates local work items and proposals, approves and
  rejects records, reads `/status`, lists queue/proposal state, exports
  `/audit-events`, and reports `local_http_api_ready` without printing local
  filesystem paths.
- Queue schemas are emitted from the CLI and bundled in the wheel under
  `patchrail/schemas/`.
- `patchrail queue status --format json` and `GET /status` share
  `patchrail.queue_status.v1`; the mirrored schema is available at
  [schemas/queue_status.schema.json](../schemas/queue_status.schema.json).
- `queue add --from-pilot-pack` links the v0.2 consent-only pilot pack to the
  v0.3 local queue while keeping `write_actions_allowed=false`.
- Safety boundary remains explicit: approving a work item or proposal records a
  local human decision only.

Recent owned-repo public PR evidence:

- [#84](https://github.com/patchrail/patchrail/pull/84) added local queue status
  summaries and passed public CI run
  [26894698571](https://github.com/patchrail/patchrail/actions/runs/26894698571).
- [#85](https://github.com/patchrail/patchrail/pull/85) shared the queue status
  contract between CLI and API and passed public CI run
  [26895362360](https://github.com/patchrail/patchrail/actions/runs/26895362360).

## Public Artifacts

- Agent Control Plane guide: [docs/agent-control-plane.md](agent-control-plane.md)
- API reference: [docs/api-reference.md](api-reference.md)
- Local queue demo: [examples/local-agent-queue](../examples/local-agent-queue/README.md)
- Queue status schema: [schemas/queue_status.schema.json](../schemas/queue_status.schema.json)
- Queue work item schema: [schemas/queue_work_item.schema.json](../schemas/queue_work_item.schema.json)
- Queue proposal schema: [schemas/queue_proposal.schema.json](../schemas/queue_proposal.schema.json)
- Queue audit event schema: [schemas/queue_audit_event.schema.json](../schemas/queue_audit_event.schema.json)
- Queue audit summary schema: [schemas/queue_audit_summary.schema.json](../schemas/queue_audit_summary.schema.json)
- Public workflow ledger: [docs/public-workflow-ledger.md](public-workflow-ledger.md)
- OSS evidence tracker: [docs/oss-program-evidence.md](oss-program-evidence.md)

## Manual Gates Before Publishing

These actions remain maintainer gates:

- Bump `pyproject.toml` to the intended v0.3.x version.
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

These blockers do not prevent local v0.3.0 preparation, docs, tests, schemas, or
demo hardening.
