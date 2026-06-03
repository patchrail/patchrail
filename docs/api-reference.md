# PatchRail API Reference

PatchRail exposes a local HTTP API for the Agent Control Plane. It is intended
for local dashboards, demos, and handoffs where a maintainer wants to inspect
queue state without granting repository write permissions.

The API is local-first:

- it binds to `127.0.0.1` or `localhost`;
- it stores state in a local SQLite database;
- it does not require billing, network access, external models, or GitHub write
  permission;
- new work items and proposals start with `approval_state=pending`;
- approval records a maintainer decision but does not execute a write action.

## Start The Server

```bash
patchrail serve --host 127.0.0.1 --port 8765 --db .patchrail/queue.sqlite
```

The server rejects non-local hosts such as `0.0.0.0`:

```bash
patchrail serve --host 0.0.0.0
# PatchRail queue API is local-only; use host 127.0.0.1 or localhost
```

## Response Envelope

Every endpoint returns JSON with UTF-8 encoding. Safety metadata appears on
health and status responses:

```json
{
  "local_first": true,
  "requirements": {
    "billing_required": false,
    "external_model_required": false,
    "github_write_permission_required": false,
    "network_required": false,
    "write_actions_allowed_by_default": false
  }
}
```

Errors use an `error` field:

```json
{
  "error": "unknown work item: prq_missing"
}
```

## Public Schemas

The queue records have versioned JSON Schema contracts. They are available from
the CLI so local dashboards, tests, demos, and handoff tools can validate
PatchRail output without importing private runtime code:

```bash
patchrail schema queue-work-item
patchrail schema queue-proposal
patchrail schema queue-audit-event
```

The same schema files are mirrored in `schemas/` for repository consumers:

- `schemas/queue_work_item.schema.json`
- `schemas/queue_proposal.schema.json`
- `schemas/queue_audit_event.schema.json`

The schemas preserve the human-approval boundary: work items require
`write_actions_allowed=false`, proposals are local patch-plan records, and audit
events are local append-only records of queue operations.

## Local Evidence Audit

PatchRail also exposes a local evidence command for the Agent Control Plane
demo:

```bash
patchrail evidence control-plane --format markdown
```

It validates `examples/local-agent-queue/demo-summary.expected.json`, confirms
the required audit events and artifacts are present, and reports whether the
human approval, proposal approval, and risky-proposal rejection gates were
exercised. It is a local release guardrail: it does not bind a server, contact
GitHub, call external models, require billing, or grant repository write
permission.

## Health And Status

### `GET /health`

Returns server readiness and the local-first requirements.

```bash
curl -sS http://127.0.0.1:8765/health
```

### `GET /status`

Returns queue counts, schema version, database path, and the same safety
requirements.

```bash
curl -sS http://127.0.0.1:8765/status
```

## Work Items

### `GET /work-items`

Lists work items. Optional filters:

- `status`
- `approval_state`

```bash
curl -sS 'http://127.0.0.1:8765/work-items?approval_state=pending'
```

### `POST /work-items`

Creates a pending local work item.

Required fields:

- `kind`
- `title`

Optional fields:

- `source`
- `payload`

```bash
curl -sS -X POST http://127.0.0.1:8765/work-items \
  -H 'Content-Type: application/json' \
  -d '{
    "kind": "ci_failure",
    "title": "Review failed dependency install",
    "source": "local-demo",
    "payload": {
      "report": "patchrail-ci-result.json"
    }
  }'
```

Created items always include `write_actions_allowed=false` unless a future
maintainer-reviewed execution layer explicitly changes that policy.

## CLI Queue Imports

The HTTP API creates generic work items. The CLI also exposes import helpers
that turn local CI artifacts into the same queue schema without granting
repository write permissions.

### `patchrail queue add --from-ci-result`

Imports a local `patchrail-result.json` produced by `patchrail ci classify` and
creates a pending `ci_failure` work item.

```bash
patchrail queue --db patchrail-pilot.sqlite add \
  --from-ci-result patchrail-result.json
```

The imported payload includes:

- `failure_class`
- `ci_result.schema_version`
- `ci_result.requirements`
- local report or result references supplied by the caller

### `patchrail queue add --from-pilot-pack`

Imports a consent-only pilot pack created by `patchrail ci pilot-pack`. The
argument may be either the pack directory or its `pilot-manifest.json` file.

```bash
patchrail queue --db patchrail-pilot.sqlite add \
  --from-pilot-pack patchrail-pilot-pack
```

Importer contract:

- requires `schema_version=patchrail.ci_pilot_pack.v1`;
- rejects manifests where `source.raw_log_copied` is not `false`;
- loads `patchrail-result.json` from the local pack;
- stores references to `failed-ci.redacted.log`, `patchrail-report.md`,
  `patchrail-result.json`, `pilot-manifest.json`, and `README.md`;
- creates a pending `ci_failure` work item;
- keeps `write_actions_allowed=false`.

The importer does not read or store the original raw CI log, does not call
external models, does not contact GitHub, and does not create pull requests,
comments, branches, funded issue actions, or billing events.

## CLI Pilot Metrics

### `patchrail ci pilot-metrics`

Aggregates one or more `patchrail ci pilot-summary --format json` outputs into
safe adoption metrics for local records or public evidence docs.

```bash
patchrail ci pilot-metrics pilot-summary-*.json --format markdown
```

Metric contract:

- counts total pilot summaries;
- counts public repository mentions only when each summary has
  `repository_mention_approved=true`;
- keeps private or unapproved repository names out of the public list;
- counts maintainer-reviewed `classification_correct` and
  `maintainer_action_useful` outcomes;
- verifies each input used `schema_version=patchrail.ci_pilot_summary.v1`;
- requires no network, external model, billing, or GitHub write permission.

### `GET /work-items/<id>`

Fetches one work item.

```bash
curl -sS http://127.0.0.1:8765/work-items/prq_example
```

### `POST /work-items/<id>/approve`

Records maintainer approval for a local work item.

```bash
curl -sS -X POST http://127.0.0.1:8765/work-items/prq_example/approve \
  -H 'Content-Type: application/json' \
  -d '{"note":"Reviewed local evidence."}'
```

Approval does not open a pull request, post a comment, push commits, contact a
third party, or claim funding.

### `POST /work-items/<id>/reject`

Records maintainer rejection.

```bash
curl -sS -X POST http://127.0.0.1:8765/work-items/prq_example/reject \
  -H 'Content-Type: application/json' \
  -d '{"note":"Needs a smaller reproduction."}'
```

## Proposals

Proposal records attach a reviewable patch plan to a work item. They are local
handoff records, not execution requests.

### `GET /proposals`

Lists proposals. Optional filters:

- `work_item_id`
- `approval_state`

```bash
curl -sS 'http://127.0.0.1:8765/proposals?approval_state=pending'
```

### `POST /proposals`

Creates a pending proposal.

Required fields:

- `work_item_id`
- `title`
- `summary`
- `patch_plan`

Optional field:

- `risk_level`

```bash
curl -sS -X POST http://127.0.0.1:8765/proposals \
  -H 'Content-Type: application/json' \
  -d '{
    "work_item_id": "prq_example",
    "title": "Pin compatible dependency range",
    "summary": "Adjust dependency constraints and re-run CI.",
    "patch_plan": "1. Reproduce the failure.\n2. Update dependency bounds.\n3. Re-run CI.",
    "risk_level": "low"
  }'
```

### `GET /proposals/<id>`

Fetches one proposal.

```bash
curl -sS http://127.0.0.1:8765/proposals/prp_example
```

### `POST /proposals/<id>/approve`

Records maintainer approval for a local patch plan.

```bash
curl -sS -X POST http://127.0.0.1:8765/proposals/prp_example/approve \
  -H 'Content-Type: application/json' \
  -d '{"note":"Plan accepted for manual handoff."}'
```

### `POST /proposals/<id>/reject`

Records maintainer rejection for a local patch plan.

```bash
curl -sS -X POST http://127.0.0.1:8765/proposals/prp_example/reject \
  -H 'Content-Type: application/json' \
  -d '{"note":"Risk is too high for this release."}'
```

## Audit Events

### `GET /audit-events`

Exports local audit events for queue creation, proposals, decisions, and
handoffs. Optional filter:

- `work_item_id`

```bash
curl -sS http://127.0.0.1:8765/audit-events
curl -sS 'http://127.0.0.1:8765/audit-events?work_item_id=prq_example'
```

## Compatibility

The current API schema is `patchrail.queue_api.v1`, backed by
`patchrail.queue.v1` SQLite records. v0.x releases may add fields, but should
not remove the local-first requirements, pending-by-default work items, or
human approval boundary.
