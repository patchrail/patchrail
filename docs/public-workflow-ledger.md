# Public Maintenance Workflow Ledger

This ledger tracks public PatchRail maintenance cycles that are useful evidence
for open-source support programs. It is intentionally narrow:

- it only lists work in repositories maintained by PatchRail;
- it does not claim external adoption;
- it does not claim formal Codex review unless a visible review link exists;
- it does not imply PyPI publish, public announcements, or external application
  submission.

Use this page to show that PatchRail is maintained in public with small,
reviewable issues, pull requests, tests, and CI evidence.

## Current Evidence Boundary

As of 2026-06-03:

- repository: <https://github.com/patchrail/patchrail>;
- public GitHub release: <https://github.com/patchrail/patchrail/releases/tag/v0.1.0>;
- public issue-to-PR cycles: active and linkable in this ledger;
- external adopters: pending consent-only pilots;
- PyPI publication: pending maintainer credential gate;
- formal Codex review examples: pending visible review links.

## Issue-To-PR Cycles

| Area | Issue | Pull request | Evidence type |
| --- | --- | --- | --- |
| Public workflow evidence ledger | [#61](https://github.com/patchrail/patchrail/issues/61) | [#62](https://github.com/patchrail/patchrail/pull/62) | evidence tracking |
| Consent-only pilot outcome example | [#59](https://github.com/patchrail/patchrail/issues/59) | [#60](https://github.com/patchrail/patchrail/pull/60) | adopter evidence surface |
| Pilot-pack importer API reference | [#57](https://github.com/patchrail/patchrail/issues/57) | [#58](https://github.com/patchrail/patchrail/pull/58) | Agent Control Plane docs |
| Pilot-pack threat boundary | [#55](https://github.com/patchrail/patchrail/issues/55) | [#56](https://github.com/patchrail/patchrail/pull/56) | security and privacy docs |
| Pilot packs into local queue | [#53](https://github.com/patchrail/patchrail/issues/53) | [#54](https://github.com/patchrail/patchrail/pull/54) | Agent Control Plane CLI |
| CI pilot pack command | [#51](https://github.com/patchrail/patchrail/issues/51) | [#52](https://github.com/patchrail/patchrail/pull/52) | CI Janitor pilot workflow |
| Benchmark summary artifact | [#49](https://github.com/patchrail/patchrail/issues/49) | [#50](https://github.com/patchrail/patchrail/pull/50) | GitHub Action artifact |
| Python dependency fixtures | [#27](https://github.com/patchrail/patchrail/issues/27) | [#47](https://github.com/patchrail/patchrail/pull/47) | CI Failure Zoo fixtures |
| Node and TypeScript fixtures | [#28](https://github.com/patchrail/patchrail/issues/28) | [#46](https://github.com/patchrail/patchrail/pull/46) | CI Failure Zoo fixtures |
| Funded issue scout boundary | [#37](https://github.com/patchrail/patchrail/issues/37) | [#43](https://github.com/patchrail/patchrail/pull/43) | read-only funded issue demo |
| Agent Control Plane demo | [#32](https://github.com/patchrail/patchrail/issues/32) | [#42](https://github.com/patchrail/patchrail/pull/42) | local queue demo |
| GitHub Actions triage artifact | [#33](https://github.com/patchrail/patchrail/issues/33) | [#41](https://github.com/patchrail/patchrail/pull/41) | read-only CI artifact |
| Node 24 action runtime review | [#31](https://github.com/patchrail/patchrail/issues/31) | [#40](https://github.com/patchrail/patchrail/pull/40) | workflow maintenance |
| Sanitized fixture contributor path | [#29](https://github.com/patchrail/patchrail/issues/29) | [#39](https://github.com/patchrail/patchrail/pull/39) | contributor docs |
| Public launch issue evidence | [#30](https://github.com/patchrail/patchrail/issues/30) | [#38](https://github.com/patchrail/patchrail/pull/38) | program evidence docs |

## How To Read This Ledger

These links demonstrate that PatchRail can run a disciplined maintenance loop:

1. Open a scoped issue in the PatchRail-owned repo.
2. Land one focused pull request.
3. Keep write actions inside the owned repo.
4. Verify through local tests and GitHub Actions.
5. Update public evidence only with facts that are already linkable.

This is not a substitute for external adoption. Before applying to external
support programs, PatchRail still needs permissioned pilots, real download
metrics, and visible examples of formal review/triage workflows where applicable.
