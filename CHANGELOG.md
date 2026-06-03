# Changelog

## 0.2.0 - draft

- Prepared the CI Janitor v0.2 evidence bundle around the 138-case fixture zoo,
  `fixture-check`, read-only GitHub Actions triage artifact, maintainer pilot
  guide, and public metrics/adopter surfaces.
- Added .NET/NuGet/C# and xUnit fixture coverage for `dotnet restore`,
  `dotnet build`, and `dotnet test` failure modes.
- v0.2 remains a maintainer-gated release candidate until the maintainer
  explicitly bumps `pyproject.toml`, tags the release, publishes package
  artifacts, and records final CI/PyPI evidence.

## 0.1.0 - 2026-06-02

- Initial public CI Janitor snapshot.
- Added `patchrail ci explain` and `patchrail ci classify`.
- Added local Markdown, JSON, and text reports.
- Added Apache-2.0 license and safety/ethics documentation.
- Added fixture-backed tests, local benchmark command, and GitHub Actions CI.
- Expanded the initial CI fixture zoo to 101 sanitized synthetic examples across
  Python, Node, TypeScript, Go, Rust, and GitHub Actions failure modes.
- Added a read-only GitHub Actions triage artifact workflow.
- Added the experimental local Agent Control Plane queue with SQLite-backed
  work items, approval states, audit export, CI result import, and proposal
  records.
- Added the experimental read-only `funded-issues` CLI over local metadata,
  with safe-only filtering and explicit anti-abuse blocked actions.
- Added permission-only adopter reporting and a public metrics tracker for
  pilot outcomes, adoption signals, and Codex for OSS evidence gaps.
- Added release-prep evidence docs, package smoke checks, and manual publish
  gates. Release tags, PyPI publishing, GitHub Releases, and public
  announcements remain maintainer actions.
