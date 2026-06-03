# Funded Issues Read-Only Demo

This fixture shows the future funded issue scout boundary:

```bash
python examples/funded-issues-readonly/run_demo.py \
  --output .patchrail-funded-issues-demo \
  --force
```

The script writes a stable `.patchrail-funded-issues-demo/summary.json`
contract matching [`demo-summary.expected.json`](demo-summary.expected.json).
It demonstrates local provider import, safe-only listing, risky-item visibility
only with `--include-risky`, issue explanation, and blocked actions.

Manual equivalent:

```bash
patchrail funded-issues list --source examples/funded-issues-readonly/issues.json
patchrail funded-issues explain example/project#42 --source examples/funded-issues-readonly/issues.json
```

The command reads local JSON only. It does not claim rewards, post comments,
open pull requests, contact maintainers, or rank work by funding alone.

Provider exports can be normalized locally before listing:

```bash
patchrail funded-issues import \
  --provider github \
  --source examples/funded-issues-readonly/provider-github-export.json \
  --out .patchrail-funded-issues.json

patchrail funded-issues list --source .patchrail-funded-issues.json
```

The import command does not fetch APIs or scrape websites. It only transforms a
local JSON export into PatchRail's read-only funded issue schema.

Expected local artifacts:

- `.patchrail-funded-issues-demo/normalized-provider-export.json`: local
  provider export normalized into PatchRail's read-only schema.
- `.patchrail-funded-issues-demo/safe-list.json`: safe-only output with the
  high-risk issue filtered out.
- `.patchrail-funded-issues-demo/all-issues.json`: local output with
  `--include-risky`; still read-only and still blocks write actions.
- `.patchrail-funded-issues-demo/safe-explain.md`: maintainer-readiness note
  for the low-risk example.
- `.patchrail-funded-issues-demo/risky-explain.json`: blocked-action and risk
  explanation for the high-risk example.
- `.patchrail-funded-issues-demo/summary.json`: stable release-evidence summary.

Safety contract:

```bash
python3 - <<'PY'
import json
from pathlib import Path

summary = json.loads(Path(".patchrail-funded-issues-demo/summary.json").read_text())
assert summary["read_only"] is True
assert summary["safe_only_total_returned"] == 1
assert summary["include_risky_total_returned"] == 2
assert summary["risky_issue_risk_level"] == "high"
assert summary["requirements"]["network_required"] is False
assert summary["requirements"]["github_write_permission_required"] is False
assert "automatic_claims" in summary["blocked_actions"]
assert "automatic_issue_comments" in summary["blocked_actions"]
PY
```
