# Local Agent Control Plane Demo

This demo turns a local CI report into a reviewable queue item, records a local
patch proposal, captures human approval decisions, and exports the local audit
trail. It does not create pull requests, post comments, contact repositories,
call external models, require billing, or use network access.

Run it from the repository root:

```bash
python examples/local-agent-queue/run_demo.py --output .patchrail-demo --force
```

The script writes the same artifacts listed below plus
`.patchrail-demo/summary.json`. Its stable summary contract is documented in
[`demo-summary.expected.json`](demo-summary.expected.json), so maintainers can
use the demo as release evidence instead of relying on screenshots.

Manual equivalent:

```bash
mkdir -p .patchrail-demo

patchrail ci explain \
  --log examples/ci-triage/dependency-failure.log \
  --format markdown \
  --out .patchrail-demo/ci-report.md

patchrail ci classify \
  --log examples/ci-triage/dependency-failure.log \
  --format json \
  --out .patchrail-demo/ci-result.json

patchrail queue --db .patchrail-demo/queue.sqlite init \
  --out .patchrail-demo/init.json

patchrail queue --db .patchrail-demo/queue.sqlite add \
  --from-ci-result .patchrail-demo/ci-result.json \
  --payload-json '{"markdown_report": ".patchrail-demo/ci-report.md"}' \
  --out .patchrail-demo/item.json

ITEM_ID=$(python3 -c 'import json; print(json.load(open(".patchrail-demo/item.json"))["id"])')

patchrail queue --db .patchrail-demo/queue.sqlite show "$ITEM_ID" \
  --format markdown \
  --out .patchrail-demo/item.md

patchrail queue --db .patchrail-demo/queue.sqlite add \
  --kind ci_failure \
  --title "Review duplicate CI report" \
  --source local-demo \
  --payload-json '{"reason": "duplicate of approved local evidence"}' \
  --out .patchrail-demo/rejected-item.json

REJECTED_ITEM_ID=$(python3 -c 'import json; print(json.load(open(".patchrail-demo/rejected-item.json"))["id"])')

patchrail queue --db .patchrail-demo/queue.sqlite list \
  --approval-state pending \
  --format json \
  --out .patchrail-demo/queue-before-decisions.json

patchrail queue --db .patchrail-demo/queue.sqlite show "$REJECTED_ITEM_ID" \
  --format markdown \
  --out .patchrail-demo/rejected-item.md

patchrail queue --db .patchrail-demo/queue.sqlite proposal add \
  --item-id "$ITEM_ID" \
  --title "Pin compatible dependency range" \
  --summary "Adjust dependency constraints and re-run the affected CI matrix." \
  --patch-plan "1. Reproduce the dependency install failure.
2. Update the conflicting dependency range.
3. Re-run the failing Python CI matrix." \
  --risk-level low \
  --out .patchrail-demo/proposal.json

PROPOSAL_ID=$(python3 -c 'import json; print(json.load(open(".patchrail-demo/proposal.json"))["id"])')

patchrail queue --db .patchrail-demo/queue.sqlite proposal show "$PROPOSAL_ID" \
  --format markdown \
  --out .patchrail-demo/proposal.md

patchrail queue --db .patchrail-demo/queue.sqlite proposal add \
  --item-id "$REJECTED_ITEM_ID" \
  --title "Open a pull request immediately" \
  --summary "Too broad for the local evidence and would skip maintainer review." \
  --patch-plan "1. Generate a patch.
2. Open a pull request automatically.
3. Ask for review after the write action." \
  --risk-level high \
  --out .patchrail-demo/proposal-rejected.json

REJECTED_PROPOSAL_ID=$(python3 -c 'import json; print(json.load(open(".patchrail-demo/proposal-rejected.json"))["id"])')

patchrail queue --db .patchrail-demo/queue.sqlite proposal show "$REJECTED_PROPOSAL_ID" \
  --format markdown \
  --out .patchrail-demo/proposal-rejected.md

patchrail queue --db .patchrail-demo/queue.sqlite proposal approve "$PROPOSAL_ID" \
  --note "Maintainer approved the local patch plan." \
  --out .patchrail-demo/proposal-approved.json

patchrail queue --db .patchrail-demo/queue.sqlite proposal reject "$REJECTED_PROPOSAL_ID" \
  --note "Maintainer rejected the proposal because it attempted an automatic PR." \
  --out .patchrail-demo/proposal-rejected.json

patchrail queue --db .patchrail-demo/queue.sqlite approve "$ITEM_ID" \
  --note "Maintainer reviewed the local CI evidence and approved handoff." \
  --out .patchrail-demo/approved.json

patchrail queue --db .patchrail-demo/queue.sqlite reject "$REJECTED_ITEM_ID" \
  --note "Maintainer rejected the duplicate local queue item." \
  --out .patchrail-demo/rejected-item.json

patchrail queue --db .patchrail-demo/queue.sqlite export \
  --format jsonl \
  --out .patchrail-demo/queue.jsonl

patchrail queue --db .patchrail-demo/queue.sqlite audit \
  --format jsonl \
  --out .patchrail-demo/audit-events.jsonl
```

Optional local API demo:

```bash
patchrail serve --host 127.0.0.1 --port 8765 --db .patchrail-demo/queue.sqlite

curl -sS http://127.0.0.1:8765/health
curl -sS http://127.0.0.1:8765/status
curl -sS http://127.0.0.1:8765/work-items
curl -sS "http://127.0.0.1:8765/audit-events?work_item_id=$ITEM_ID"
```

Expected local artifacts:

- `.patchrail-demo/ci-report.md`: the local CI explanation.
- `.patchrail-demo/ci-result.json`: the machine-readable CI result.
- `.patchrail-demo/item.json`: the pending work item.
- `.patchrail-demo/item.md`: a human-readable queue item.
- `.patchrail-demo/rejected-item.json`: the rejected duplicate item decision.
- `.patchrail-demo/rejected-item.md`: a human-readable item before rejection.
- `.patchrail-demo/queue-before-decisions.json`: pending queue list before
  approval and rejection decisions.
- `.patchrail-demo/proposal.json`: the pending patch proposal.
- `.patchrail-demo/proposal.md`: a human-readable proposal record.
- `.patchrail-demo/proposal-approved.json`: the local proposal approval decision.
- `.patchrail-demo/proposal-rejected.json`: the local proposal rejection
  decision for a high-risk plan.
- `.patchrail-demo/proposal-rejected.md`: a human-readable proposal before
  rejection.
- `.patchrail-demo/approved.json`: the approval decision.
- `.patchrail-demo/queue.jsonl`: the exported work items.
- `.patchrail-demo/audit-events.jsonl`: the append-only local event trail for
  add, proposal, approve, and export decisions.
- `.patchrail-demo/summary.json`: stable demo summary matching
  `demo-summary.expected.json`.
- Local API responses expose the same local SQLite state for dashboard or demo
  use without GitHub write permissions or external model calls.

Check the safety boundary:

```bash
python3 - <<'PY'
import json
from pathlib import Path

item = json.loads(Path(".patchrail-demo/approved.json").read_text())
rejected_item = json.loads(Path(".patchrail-demo/rejected-item.json").read_text())
proposal = json.loads(Path(".patchrail-demo/proposal-approved.json").read_text())
rejected_proposal = json.loads(Path(".patchrail-demo/proposal-rejected.json").read_text())
pending_list = json.loads(Path(".patchrail-demo/queue-before-decisions.json").read_text())
assert item["approval_state"] == "approved"
assert item["write_actions_allowed"] is False
assert item["payload"]["failure_class"] == "python_dependency_resolution"
assert item["payload"]["ci_result"]["schema_version"] == "patchrail.ci_result.v1"
assert rejected_item["approval_state"] == "rejected"
assert rejected_item["write_actions_allowed"] is False
assert len(pending_list["work_items"]) == 2
assert proposal["approval_state"] == "approved"
assert proposal["risk_level"] == "low"
assert rejected_proposal["approval_state"] == "rejected"
assert rejected_proposal["risk_level"] == "high"

events = [json.loads(line) for line in Path(".patchrail-demo/audit-events.jsonl").read_text().splitlines()]
assert [event["event_type"] for event in events] == [
    "work_item_added",
    "work_item_added",
    "proposal_added",
    "proposal_added",
    "proposal_approved",
    "proposal_rejected",
    "work_item_approved",
    "work_item_rejected",
    "work_items_exported",
]
PY
```

Approval means a maintainer reviewed the local evidence and local patch plan.
It does not grant GitHub write permissions, open a pull request, post a comment,
or execute any agent action.
