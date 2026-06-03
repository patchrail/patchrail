# Codex Workflows

PatchRail's public workflow stance is evidence first, human approval second, and
write actions only after review.

The v0.1 release does not require Codex or any external model. The CI classifier
runs locally and emits Markdown, JSON, or text reports that maintainers can
inspect before asking an agent to propose code.

## PR Review

Use Codex review for changes that touch classifier logic, redaction, GitHub
Actions, release automation, or safety policy.

Maintainer checklist:

1. Run `uv run --extra dev pytest -q`.
2. Run `uv run --extra dev ruff check .`.
3. Run `uv run --extra dev patchrail ci benchmark examples/ci-triage --format json`.
4. Review Codex suggestions manually before merge.

## Issue Triage

Use Codex to summarize fixture requests or classifier bugs, not to close issues
automatically.

Suggested triage output:

- summary;
- likely area;
- missing reproduction details;
- suggested labels;
- next maintainer action.

## CI Failure Repair

PatchRail should classify the failed log first. A maintainer can then ask Codex
for a minimal patch using the report as context.

The local Agent Control Plane demo makes that handoff concrete without granting
write permissions:

```bash
python examples/local-agent-queue/run_demo.py --output .patchrail-demo --force
```

It creates a CI report, imports the machine-readable result into the local
SQLite queue, records a reviewable patch proposal, captures maintainer approval,
and exports the audit trail.

Safety boundary:

- no automatic pull requests;
- no issue or pull request comments from the workflow;
- no raw logs sent to external services unless a maintainer explicitly opts in;
- no third-party repository work without maintainer permission.

## Release Prep

Codex can help check changelog, version metadata, README quickstart drift, docs
links, and package build output. It must not publish to PyPI, create tags, push
release commits, or announce releases without maintainer approval.

See [Release process](release-process.md).

## Agent Skills

PatchRail ships maintainer-facing agent skill prompts under `.agents/skills/`.
They are part of the public evidence pack because they make the human approval
boundary reviewable in the repository:

- `patchrail-ci-triage` for classifier, fixture, and failed-log work;
- `patchrail-release-captain` for release-prep checks and evidence pages;
- `patchrail-review-guardrails` for safety-sensitive review of network access,
  GitHub writes, funded issue discovery, redaction, and approval gates.

The skills do not grant permissions. They document review workflows and checks
that maintainers can apply before any external write action.
