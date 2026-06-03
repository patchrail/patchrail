---
name: patchrail-review-guardrails
description: Use when reviewing changes that affect network access, GitHub write actions, funded issue discovery, log redaction, local queue approvals, or agent workflows.
---

# PatchRail Review Guardrails

Review PatchRail changes for maintainer control, local-first behavior, and
anti-abuse boundaries.

## P0 Findings

Flag a P0 if a change introduces any of these:

- unredacted log export;
- external model calls without explicit opt-in;
- network access without a clear opt-in flag;
- automatic bounty or funded-issue claiming;
- mass comments or automatic issue replies;
- automatic pull requests to third-party repositories;
- GitHub write actions without dry-run and human approval;
- queue approvals that execute code or grant write permissions by themselves.

## Review Flow

1. Inspect the diff and affected docs.
2. Check whether new commands preserve `--format json` or equivalent
   machine-readable output when relevant.
3. Verify docs state the human approval boundary.
4. Run focused tests, then the public workflow tests.
5. Report findings before summaries, with file and line references when
   available.

## Required Checks

```bash
uv run --extra dev pytest -q tests/test_public_workflows.py
uv run --extra dev ruff check .
```
