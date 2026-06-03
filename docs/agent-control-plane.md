# Agent Control Plane

PatchRail's agent control plane is an experimental local queue for reviewable
maintainer work. It is designed to turn reports, release tasks, and future
agent proposals into auditable work items before any write action happens.

The queue is local-first:

- storage is SQLite on the maintainer's machine;
- new work items start with `approval_state=pending`;
- approving an item records a maintainer decision but does not execute a write
  action;
- proposal records link a work item to a reviewable patch plan before handoff;
- export is JSON or JSONL for audit, handoff, or demos;
- audit events are local, append-only SQLite records for queue add, approve,
  reject, proposal, and export decisions;
- an optional HTTP API binds to `127.0.0.1` by default for local dashboards,
  demos, and handoffs;
- no command posts comments, opens pull requests, contacts third-party repos,
  claims funding, or calls an external model.

## Quickstart

Create a local queue:

```bash
patchrail queue init
```

Add a work item from a local pilot pack:

```bash
patchrail ci pilot-pack \
  --log examples/ci-triage/dependency-failure.log \
  --out-dir patchrail-pilot-pack

patchrail queue add \
  --from-pilot-pack patchrail-pilot-pack
```

The pilot-pack importer reads `pilot-manifest.json`, validates that the raw log
was not copied, loads `patchrail-result.json`, and stores references to the
redacted log and Markdown report in the local work item payload.

You can also add a work item from a standalone CI result:

```bash
patchrail ci classify \
  --log examples/ci-triage/dependency-failure.log \
  --format json \
  --out patchrail-ci-result.json

patchrail queue add \
  --from-ci-result patchrail-ci-result.json
```

Manual work items are still supported:

```bash
patchrail queue add \
  --kind ci_failure \
  --title "Investigate failing dependency install" \
  --source patchrail-ci-report.md \
  --payload-json '{"report": "patchrail-ci-report.md"}'
```

List pending items:

```bash
patchrail queue list --approval-state pending
```

Inspect one item:

```bash
patchrail queue show prq_example --format markdown
```

Create a local proposal record for maintainer review:

```bash
patchrail queue proposal add \
  --item-id prq_example \
  --title "Pin compatible dependency range" \
  --summary "Adjust dependency constraints and re-run the affected CI matrix." \
  --patch-plan "1. Reproduce the failure.
2. Update dependency bounds.
3. Re-run the failing CI matrix." \
  --risk-level low
```

Inspect and approve the proposal:

```bash
patchrail queue proposal show prp_example --format markdown
patchrail queue proposal approve prp_example --note "Plan reviewed locally."
```

Reject a proposal that skips review or attempts a write action too early:

```bash
patchrail queue proposal reject prp_risky --note "Rejected: automatic PRs stay gated."
```

Record a maintainer decision:

```bash
patchrail queue approve prq_example --note "Reviewed local evidence."
patchrail queue reject prq_example --note "Needs a smaller reproduction."
```

Export the local audit trail:

```bash
patchrail queue export --format jsonl > patchrail-queue.jsonl
patchrail queue audit --format jsonl > patchrail-audit-events.jsonl
```

Run the local-only HTTP API:

```bash
patchrail serve --host 127.0.0.1 --port 8765 --db .patchrail/queue.sqlite
```

Example local API calls:

```bash
curl -sS http://127.0.0.1:8765/health
curl -sS http://127.0.0.1:8765/status
curl -sS http://127.0.0.1:8765/work-items
curl -sS http://127.0.0.1:8765/proposals
curl -sS http://127.0.0.1:8765/audit-events
```

See [`docs/api-reference.md`](api-reference.md) for the endpoint contract,
request fields, filters, and approval boundary.

Create and approve local records through the API:

```bash
curl -sS -X POST http://127.0.0.1:8765/work-items \
  -H 'Content-Type: application/json' \
  -d '{"kind":"ci_failure","title":"Review failed dependency install","source":"local-demo"}'

curl -sS -X POST http://127.0.0.1:8765/work-items/prq_example/approve \
  -H 'Content-Type: application/json' \
  -d '{"note":"Maintainer reviewed the local evidence."}'
```

For a complete local demo that starts from a CI report and ends with an
approved queue export, see
[`examples/local-agent-queue`](../examples/local-agent-queue/README.md).
The demo includes `run_demo.py`, which produces a stable `summary.json`
contract for release evidence and CI checks.

Audit that demo as local Agent Control Plane evidence:

```bash
patchrail evidence control-plane --format markdown
```

The command reads the checked-in demo summary, verifies the required queue
events and artifacts, and reports whether the human approval and rejection gates
were exercised. It does not use network access, billing, external models,
GitHub write permission, or repository write actions.

## Custom Database Path

By default PatchRail stores the queue in `.patchrail/queue.sqlite` in the current
checkout. Use `--db` to keep a queue next to a demo, release, or test fixture:

```bash
patchrail queue --db /tmp/patchrail-demo.sqlite init
patchrail queue --db /tmp/patchrail-demo.sqlite list --format json
```

## Approval Boundary

Approval state is deliberately separate from execution. `patchrail queue approve`
means a maintainer reviewed the local item. It does not grant GitHub write
permissions, push commits, open a pull request, post a comment, or contact
anyone.

Proposal decisions are equally bounded. `patchrail queue proposal approve`
records that a maintainer accepted a local patch plan for handoff.
`patchrail queue proposal reject` records that a plan was declined, for example
because it tried to skip review or automate a write action. Neither decision
executes the plan or authorizes repository writes.

That boundary is the product value: maintainers can structure work for coding
agents while keeping write actions explicit, reviewable, and human-approved.

## Current Scope

The current queue is enough for local demos and release evidence:

- initialize SQLite;
- add work items manually or from `patchrail.ci_result.v1` JSON;
- list and show items;
- approve or reject items;
- add, list, show, approve, and reject local proposal records;
- run a local HTTP API for `health`, `status`, work items, proposals,
  approval decisions, and audit events;
- export work items;
- export audit events for item creation, proposals, maintainer decisions, and
  handoffs.
