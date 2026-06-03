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
uv run --extra dev patchrail schema ci-result > ci-result.schema.json
uv run --extra dev patchrail ci benchmark examples/ci-triage --format markdown
```

Run the public checks from a fresh checkout:

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
```

See [ETHICS.md](ETHICS.md), [SECURITY.md](SECURITY.md), and
[docs/threat-model.md](docs/threat-model.md).

## Documentation

- [Quickstart](docs/quickstart.md)
- [CI Janitor](docs/ci-janitor.md)
- [CI Failure Zoo](docs/ci-failure-zoo.md)
- [Maintainer pilot guide](docs/pilot-guide.md)
- [Adopters](ADOPTERS.md)
- [Metrics](docs/metrics.md)
- [GitHub Actions CI triage](docs/github-action.md)
- [Agent Control Plane](docs/agent-control-plane.md)
- [API reference](docs/api-reference.md)
- [Codex workflows](docs/codex-workflows.md)
- [Reviewable automation workflows](docs/agent-workflows.md)
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
report issue template. Public adopter listings require explicit permission.

## License

Apache-2.0.
