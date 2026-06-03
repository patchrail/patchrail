---
name: patchrail-ci-triage
description: Use when a PatchRail CI classifier, CI fixture, or failed CI log needs root-cause analysis, evidence extraction, or regression coverage.
---

# PatchRail CI Triage

PatchRail CI triage is local-first. Produce evidence and reviewable suggestions;
do not perform write actions.

## Workflow

1. Inspect the failing log or sanitized fixture.
2. Identify the smallest root-cause category that explains the failure.
3. Check whether an existing fixture already covers the pattern.
4. If classifier logic changes, add or update a fixture and expected metadata.
5. Run the focused classifier tests and the public benchmark.
6. Summarize evidence lines, confidence, changed files, and commands run.

## Required Checks

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
```

## Safety

- Do not quote raw logs that may contain secrets.
- Redact logs before sharing fixtures or report excerpts.
- Do not send logs to external services unless the maintainer explicitly opts in.
- Do not open pull requests or comment on third-party repositories automatically.
