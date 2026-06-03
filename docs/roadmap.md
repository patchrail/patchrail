# Roadmap

## v0.1

- Local CI failure classifier.
- Markdown, JSON, and text reports.
- Local redaction helper for shared logs.
- Fixture-backed tests.
- Local fixture benchmark command.
- Initial 40-fixture CI failure zoo, now expanded to 101 public benchmark fixtures.
- Safety, ethics, and security documentation.
- Release-prep evidence checklist for tests, lint, benchmark, doctor, package
  artifacts, safety review, and manual publish gates.

## v0.2

- Larger CI failure fixture set past the 100-case v0.2 benchmark bar.
- Expanded Node and TypeScript drift fixtures, including workspace, engine,
  route, overload, schema and import/type variants.
- Expanded Python dependency-resolution fixtures with pip, Poetry, pip-tools,
  uv, tox, marker, yanked, prerelease, platform wheel and transitive-conflict
  cases.
- GitHub Actions report artifact example.
- Reproducible `patchrail-ci-triage` artifact example with Markdown, JSON,
  benchmark and doctor outputs.
- Classifier fixture contribution flow.
- Maintainer pilot guide for consent-only, read-only CI log trials and optional
  sanitized fixture contributions.

## v0.3

- Experimental local SQLite queue for maintainer work items.
- Human approval states for local decisions.
- Exportable audit log.
- CI report to queue-item demo.
- Direct `ci-result.json` import into pending local queue items.
- Local audit event export for add, approve, reject, and handoff decisions.
- Local proposal records for reviewable patch plans linked to queue items.
- Proposal approval/rejection audit events without granting write permission.
- Local-only HTTP API for queue health, status, work items, proposals,
  approvals, and audit events.

## v0.4

- Experimental `patchrail funded-issues list/explain` over local JSON metadata.
- Safe-only filtering by default, with `--include-risky` limited to local output visibility.
- Contribution etiquette and anti-abuse guardrails.
- Risk explanations for ambiguous scope, spam-attractive work, and missing contribution guidelines.
- No automatic claims, comments, pull requests, maintainer contact, external API fetch, or model call.
