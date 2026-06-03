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
- public issue-to-PR cycles and focused maintainer PRs: active and linkable in this ledger;
- external adopters: pending consent-only pilots;
- PyPI publication: pending maintainer credential gate;
- formal Codex review examples: pending visible review links.

## Review And Triage Boundary

The rows below are public, owned-repository maintenance evidence. They show
scoped triage, reviewable pull requests, CI checks, and documented outcomes in
PatchRail-owned infrastructure. They do not claim:

- third-party adoption;
- maintainer permission outside the PatchRail-owned repo;
- formal Codex review unless a public review link is listed;
- PyPI download telemetry.

## Issue-To-PR Cycles

| Area | Issue | Pull request | Evidence type |
| --- | --- | --- | --- |
| OSS evidence artifact maintenance | [#69](https://github.com/patchrail/patchrail/issues/69) | [#79](https://github.com/patchrail/patchrail/pull/79) | workflow runtime review |
| OSS evidence artifact publication | [#69](https://github.com/patchrail/patchrail/issues/69) | [#78](https://github.com/patchrail/patchrail/pull/78) | CI artifact evidence |
| Evidence snapshot command | [#69](https://github.com/patchrail/patchrail/issues/69) | [#77](https://github.com/patchrail/patchrail/pull/77) | program evidence automation |
| Consent-only pilot request package | [#69](https://github.com/patchrail/patchrail/issues/69) | [#76](https://github.com/patchrail/patchrail/pull/76) | adopter readiness docs |
| Own-repo CI pilot outcome | [#68](https://github.com/patchrail/patchrail/issues/68) | [#75](https://github.com/patchrail/patchrail/pull/75) | own-repo triage evidence |
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

## Focused Maintainer PR Evidence

The rows below are recent owned-repository maintenance PRs that were merged
with public CI evidence. They are useful maintainer-workflow evidence but do not
count as issue-to-PR cycles because no public issue was linked by the PR.

| Area | Pull request | Public CI evidence | Evidence type |
| --- | --- | --- | --- |
| CI Janitor Docker/browser coverage | [#83](https://github.com/patchrail/patchrail/pull/83) | [CI run 26893931040](https://github.com/patchrail/patchrail/actions/runs/26893931040) | classifier and benchmark expansion |
| Agent Control Plane queue status CLI | [#84](https://github.com/patchrail/patchrail/pull/84) | [CI run 26894698571](https://github.com/patchrail/patchrail/actions/runs/26894698571) | local control-plane observability |
| Shared queue status CLI/API contract | [#85](https://github.com/patchrail/patchrail/pull/85) | [CI run 26895362360](https://github.com/patchrail/patchrail/actions/runs/26895362360) | versioned status schema and API parity |
| Recent owned workflow evidence | [#86](https://github.com/patchrail/patchrail/pull/86) | [CI run 26896092846](https://github.com/patchrail/patchrail/actions/runs/26896092846) | public evidence ledger maintenance |
| Pilot metrics evidence boundary | [#87](https://github.com/patchrail/patchrail/pull/87) | [CI run 26896840989](https://github.com/patchrail/patchrail/actions/runs/26896840989) | owned-repo vs external-adopter boundary |
| Owned review evidence packet | [#88](https://github.com/patchrail/patchrail/pull/88) | [CI run 26897513539](https://github.com/patchrail/patchrail/actions/runs/26897513539) | reproducible review-packet evidence |
| CI Janitor Java coverage | [#89](https://github.com/patchrail/patchrail/pull/89) | [CI run 26898070805](https://github.com/patchrail/patchrail/actions/runs/26898070805) | classifier and benchmark expansion |
| CI Janitor Ruby coverage | [#90](https://github.com/patchrail/patchrail/pull/90) | [CI run 26898756284](https://github.com/patchrail/patchrail/actions/runs/26898756284) | classifier and benchmark expansion |
| CI Janitor PHP coverage | [#91](https://github.com/patchrail/patchrail/pull/91) | [CI run 26899367260](https://github.com/patchrail/patchrail/actions/runs/26899367260) | classifier and benchmark expansion |
| Queue audit summary gate | [#92](https://github.com/patchrail/patchrail/pull/92) | [CI run 26900396583](https://github.com/patchrail/patchrail/actions/runs/26900396583) | Agent Control Plane audit evidence |
| CI Janitor .NET coverage | [#93](https://github.com/patchrail/patchrail/pull/93) | [CI run 26901089624](https://github.com/patchrail/patchrail/actions/runs/26901089624) | classifier and benchmark expansion |
| HTTP API evidence smoke test | [#94](https://github.com/patchrail/patchrail/pull/94) | [CI run 26901794678](https://github.com/patchrail/patchrail/actions/runs/26901794678) | local control-plane API evidence |
| Public workflow ledger refresh | [#95](https://github.com/patchrail/patchrail/pull/95) | [CI run 26902859853](https://github.com/patchrail/patchrail/actions/runs/26902859853) | public evidence ledger maintenance |
| Queue handoff bundle | [#96](https://github.com/patchrail/patchrail/pull/96) | [CI run 26904444855](https://github.com/patchrail/patchrail/actions/runs/26904444855) | Agent Control Plane handoff evidence |
| Queue skip and artifact schemas | [#97](https://github.com/patchrail/patchrail/pull/97) | [CI run 26905840189](https://github.com/patchrail/patchrail/actions/runs/26905840189) | skip-state schema evidence |
| Release readiness evidence CLI | [#98](https://github.com/patchrail/patchrail/pull/98) | [CI run 26907134911](https://github.com/patchrail/patchrail/actions/runs/26907134911) | release-readiness gate evidence |
| CI benchmark coverage gate | [#99](https://github.com/patchrail/patchrail/pull/99) | [CI run 26908510850](https://github.com/patchrail/patchrail/actions/runs/26908510850) | benchmark coverage guardrail |
| Queue human gate status summary | [#100](https://github.com/patchrail/patchrail/pull/100) | [CI run 26909277529](https://github.com/patchrail/patchrail/actions/runs/26909277529) | human approval gate observability |
| HTTP API human gate evidence | [#101](https://github.com/patchrail/patchrail/pull/101) | [CI run 26910720452](https://github.com/patchrail/patchrail/actions/runs/26910720452) | local API human-gate evidence |
| Application evidence gate | [#102](https://github.com/patchrail/patchrail/pull/102) | [CI run 26911478559](https://github.com/patchrail/patchrail/actions/runs/26911478559) | fail-closed application readiness evidence |

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

## Local Review Packet

Maintainers can turn this ledger into a reproducible local evidence packet:

```bash
patchrail evidence review-packet --format markdown
```

The command parses this file only. It does not call GitHub, request write
permissions, count external adopters, claim PyPI downloads, or claim formal
Codex review links.
