# PatchRail

PatchRail is a local-first maintainer automation toolkit for open-source projects.
The first public release focuses on CI failure triage: it reads failed CI logs,
classifies the likely root cause, extracts evidence signals, and emits Markdown,
JSON, or plain text reports that maintainers can review.

PatchRail does not auto-submit pull requests, claim funded issues, or comment on
third-party repositories. It produces evidence and reviewable suggestions so
maintainers stay in control.

## Quickstart

Install the CLI:

```bash
pipx install patchrail
```

Run the local safety check and classify a failed CI log:

```bash
patchrail doctor
patchrail ci explain --log failed-github-actions.log
```

From a source checkout, use the bundled fixture:

```bash
uv run --extra dev patchrail doctor
uv run --extra dev patchrail ci explain --log examples/ci-triage/dependency-failure.log
```

Example output:

```markdown
# PatchRail CI Report

- Root cause: `python_dependency_resolution`
- Confidence: `0.89`
- Subsystem: Python dependency installation
- Reproduce: `python -m pip install -r requirements.txt`
- Suggested action: Pin or relax the conflicting dependency range, then rerun
  the same install command and the affected tests.
```

## Why maintainers use PatchRail

- Turn long CI logs into concise root-cause reports.
- Keep CI log processing local by default.
- Emit Markdown for humans and JSON for automation.
- Preserve a human approval boundary for write actions.
- Use the classifier as a building block for reviewable agent workflows.

## Current scope

| Area | Status | Notes |
| --- | --- | --- |
| CI failure triage | Beta | GitHub Actions-style logs and common OSS toolchains |
| Markdown/JSON reports | Beta | Suitable for local review or manually pasted reports |
| Local queue/control plane | Experimental | SQLite-backed work items with human approval states |
| Funded issue discovery | Planned | Read-only, later, and explicitly anti-abuse |

## Safety

PatchRail is local-first. The CI classifier does not require billing, a GitHub
App, repo write permissions, or an external model call. Write actions are outside
the v0.1 scope and must remain human-approved.

Redact logs before sharing fixtures or reports:

```bash
uv run --extra dev patchrail doctor --format markdown
uv run --extra dev patchrail redact --log failed.log > failed.redacted.log
uv run --extra dev patchrail ci explain --redact --log failed.log
uv run --extra dev patchrail ci pilot-pack --log failed.log --out-dir patchrail-pilot-pack
uv run --extra dev patchrail ci pilot-summary --pack patchrail-pilot-pack --ci-provider "GitHub Actions" --toolchain Python
uv run --extra dev patchrail schema ci-result > ci-result.schema.json
uv run --extra dev patchrail ci benchmark examples/ci-triage --format markdown
```

Run the public checks from a fresh checkout:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
uv run --extra dev patchrail evidence snapshot --format markdown
uv run --extra dev patchrail evidence application-gate --format markdown
uv run --extra dev patchrail evidence release-readiness --clean-dist --format markdown
```

See [ETHICS.md](ETHICS.md), [SECURITY.md](SECURITY.md), and
[docs/threat-model.md](docs/threat-model.md).

## Documentation

- [Quickstart](docs/quickstart.md)
- [CI Janitor](docs/ci-janitor.md)
- [CI Failure Zoo](docs/ci-failure-zoo.md)
- [Maintainer pilot guide](docs/pilot-guide.md)
- [Consent-only pilot request package](docs/pilot-request-package.md)
- [Consent-only pilot outcome example](examples/pilot-outcome/README.md)
- [Adopters](ADOPTERS.md)
- [Metrics](docs/metrics.md)
- [GitHub Actions CI triage](docs/github-action.md)
- [Agent Control Plane](docs/agent-control-plane.md)
- [API reference](docs/api-reference.md)
- [Codex workflows](docs/codex-workflows.md)
- [Reviewable automation workflows](docs/agent-workflows.md)
- [Public maintenance workflow ledger](docs/public-workflow-ledger.md)
- [Agent skills](.agents/skills)
- [Threat model](docs/threat-model.md)
- [Funded issue ethics](docs/funded-issues-ethics.md)
- [Roadmap](docs/roadmap.md)
- [Release process](docs/release-process.md)
- [v0.1.0 release evidence](docs/release-v0.1.0-evidence.md)
- [v0.2.0 release evidence](docs/release-v0.2.0-evidence.md)
- [v0.3.0 release evidence](docs/release-v0.3.0-evidence.md)
- [v0.4.0 release evidence](docs/release-v0.4.0-evidence.md)
- [Codex for Open Source evidence](docs/openai-codex-for-oss-evidence.md)
- [Open source evidence tracker](docs/oss-program-evidence.md)

## Contributing

The easiest contribution is a sanitized CI failure fixture. See
[CONTRIBUTING.md](CONTRIBUTING.md) and the
[maintainer pilot guide](docs/pilot-guide.md).
If you are not opening a pull request yet, use the
[CI failure fixture issue template](.github/ISSUE_TEMPLATE/ci_failure_fixture.md)
with a redacted log excerpt and the `fixture-check` result.

If you are testing PatchRail on a repository you maintain, use the adopter
report issue template. `patchrail ci pilot-pack` creates a local redacted pack
for that review path. `patchrail ci pilot-summary` creates a safe outcome
snippet and keeps repository names private unless
`--repository-mention-approved yes` is set. Public adopter listings require
explicit permission. The
[consent-only pilot request package](docs/pilot-request-package.md) has a
copyable maintainer checklist and intake rules for pilots that should become
public evidence.

When you have multiple reviewed summaries, aggregate them without exposing
private repository names:

```bash
uv run --extra dev patchrail ci pilot-metrics pilot-summary-*.json --format markdown
```

To refresh the local evidence view across CI Janitor, the read-only action,
Agent Control Plane, Funded Issue Scout, release evidence, and adopter gaps:

```bash
uv run --extra dev patchrail evidence snapshot --format markdown
```

Before drafting an external program application, run the fail-closed gate:

```bash
uv run --extra dev patchrail evidence application-gate --format markdown
```

The gate exits non-zero until PyPI telemetry, permissioned external evidence,
and visible review links are real rather than placeholder-derived.

## License

Apache-2.0.
