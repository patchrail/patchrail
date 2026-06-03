# Metrics

PatchRail tracks adoption and quality metrics so public claims stay verifiable.
Do not use placeholders as evidence for applications, release posts, or funding
requests.

Last updated: 2026-06-03.

## Public Signals

| Metric | Current value | Source |
| --- | ---: | --- |
| GitHub repository | `patchrail/patchrail` | <https://github.com/patchrail/patchrail> |
| GitHub stars | 0 | Fresh public launch snapshot |
| Monthly PyPI downloads | Pending first PyPI release | PyPI returned `Not Found` on 2026-06-03 |
| Public external adopters | 0 | [ADOPTERS.md](../ADOPTERS.md) |
| External contributors | 0 | GitHub contributors |
| Public releases | 1 | <https://github.com/patchrail/patchrail/releases/tag/v0.1.0> |
| Public CI fixtures | 115 | `examples/ci-triage` benchmark |
| Fixture hygiene gate | 115 / 115 passing | `patchrail ci fixture-check examples/ci-triage --format json` |
| Supported benchmark categories | Python, Node, TypeScript, Go, Rust, GitHub Actions | `docs/ci-failure-zoo.md` |
| Agent Control Plane demos | 1 | `examples/local-agent-queue` |
| Funded issue read-only demos | 1 | `examples/funded-issues-readonly` |
| Consent-only pilot outcome examples | 1 | `examples/pilot-outcome` |
| Active evidence follow-up issues | 3 | [#67](https://github.com/patchrail/patchrail/issues/67), [#68](https://github.com/patchrail/patchrail/issues/68), [#69](https://github.com/patchrail/patchrail/issues/69) |

## Quality Gates

Before increasing a metric in public docs:

- link the source;
- verify it from a public page, command output, or repository artifact;
- avoid counting private runs as adoption;
- avoid counting unapproved pilot names as adopters;
- keep funded issue metrics separate from CI triage usefulness;
- never report payouts, bounty value, or money-ranked opportunity counts as the
  primary project metric.

## Weekly Snapshot Template

```markdown
## YYYY-Www

- GitHub stars:
- PyPI downloads, last 30 days:
- External repos testing PatchRail:
- External contributors:
- New sanitized fixtures:
- Fixture-check total / passed:
- Benchmark total / passed:
- Issues opened / closed:
- PRs opened / merged:
- Codex-reviewed PRs:
- Codex-triaged issues:
- Release or package status:
- Notable maintainer feedback:
```

## Evidence Before Applying

PatchRail should not apply to external programs from placeholder metrics. The
current evidence gaps are:

- first PyPI release and download telemetry;
- external maintainer pilots with permission to cite outcomes;
- safe pilot summaries based on [examples/pilot-outcome](../examples/pilot-outcome/README.md);
- permissioned pilot fixture submissions that pass `fixture-check`;
- public PRs reviewed with Codex;
- public issues triaged with Codex;
- real adopter entries approved for [ADOPTERS.md](../ADOPTERS.md).

Active follow-up issues:

- [#67](https://github.com/patchrail/patchrail/issues/67) for PyPI publication and clean install verification.
- [#68](https://github.com/patchrail/patchrail/issues/68) for the first consent-only maintainer pilot.
- [#69](https://github.com/patchrail/patchrail/issues/69) for verified adoption and ecosystem signal tracking.
