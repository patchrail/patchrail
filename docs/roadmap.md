# Roadmap

PatchRail keeps the roadmap auditable from local repository artifacts:

```bash
patchrail evidence roadmap --format markdown
patchrail evidence control-plane --format markdown
```

The audit reports progress for v0.1.0 through v0.4.0 and the 12-week OSS plan
without network access, billing, external models, GitHub write permission,
public announcements, or third-party repository actions. Treat it as a local
progress check. It does not replace public PyPI download telemetry, consented
external adopter evidence, or visible review links.

## v0.1

- Local CI failure classifier.
- Markdown, JSON, and text reports.
- Local redaction helper for shared logs.
- Fixture-backed tests.
- Local fixture benchmark command.
- Initial 40-fixture CI failure zoo, now expanded to 132 public benchmark fixtures.
- Safety, ethics, and security documentation.
- Release-prep evidence checklist for tests, lint, benchmark, doctor, package
  artifacts, safety review, and manual publish gates.
- v0.1.0 release evidence page with artifact manifest, wheel smoke result, and
  published GitHub Release. PyPI, announcements, and external applications stay
  separate manual gates.

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
- v0.2.0 release-candidate evidence page tying benchmark, fixture hygiene,
  GitHub Action artifact, pilot guide, metrics and remaining manual gates.
- Maintainer pilot guide for consent-only, read-only CI log trials and optional
  sanitized fixture contributions.
- Local `patchrail ci pilot-pack` command for redacted maintainer review bundles
  with no raw log copy, no network, and no repository write permission.
- Permissioned `ADOPTERS.md`, adopter-report issue template, and `docs/metrics.md`
  for tracking public adoption without inventing evidence.

## v0.3

- Agent Control Plane milestone for local, reviewable maintainer work.
- Experimental local SQLite queue for maintainer work items.
- Human approval states for local decisions.
- Exportable audit log.
- Public `.agents/skills` prompts for CI triage, release prep, and review
  guardrails.
- CI report to queue-item demo.
- Direct `ci-result.json` import into pending local queue items.
- Local audit event export for add, approve, reject, and handoff decisions.
- Local proposal records for reviewable patch plans linked to queue items.
- Proposal approval/rejection audit events without granting write permission.
- Local-only HTTP API for queue health, status, work items, proposals,
  approvals, and audit events.
- Local evidence audit command for the checked-in Agent Control Plane demo
  summary, required artifacts, audit events, and human approval gates.
- v0.3.0 release-candidate evidence page tying queue CLI/API, schemas, demo,
  audit exports, proposal gates, and remaining manual gates.

## v0.4

- Funded Issue Scout read-only milestone for sustainability metadata.
- Experimental `patchrail funded-issues list/explain` over local JSON metadata.
- Offline `patchrail funded-issues import` normalizes local provider exports for
  `algora`, `github`, `openpledge`, and `polar` into PatchRail's read-only schema.
- Safe-only filtering by default, with `--include-risky` limited to local output visibility.
- Contribution etiquette and anti-abuse guardrails.
- Risk explanations for ambiguous scope, spam-attractive work, and missing contribution guidelines.
- No automatic claims, comments, pull requests, maintainer contact, external API fetch, scraping,
  credential use, or model call.
- v0.4.0 release-candidate evidence page tying read-only local metadata,
  provider export import, ethics boundaries, demo output, and remaining manual gates.
