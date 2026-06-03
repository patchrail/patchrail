# GitHub Actions CI Triage

PatchRail includes a read-only CI triage workflow for maintainers who want
reviewable CI reports without automatic repository writes.

The workflow lives at `.github/workflows/ci-triage.yml`.

## What It Does

- Runs after the main `CI` workflow fails, or manually with `workflow_dispatch`.
- Installs PatchRail locally with `uv`.
- Selects a log from failed workflow artifacts when available.
- Falls back to the bundled demo fixture for manual smoke tests.
- Produces Markdown and JSON reports under `patchrail-report/`.
- Uploads those reports as a GitHub Actions artifact.

Example artifact contents live in
[`examples/github-action`](../examples/github-action/README.md). The uploaded
artifact is named `patchrail-ci-triage` and contains:

```text
patchrail-ci-triage/
|-- ci-report.md
|-- ci-result.json
|-- doctor.json
`-- fixture-benchmark.json
```

## What It Does Not Do

- It does not comment on issues or pull requests.
- It does not open pull requests.
- It does not push commits.
- It does not claim funded issues.
- It does not call external models.
- It does not require billing or write permissions.

## Permissions

The workflow requests only:

```yaml
permissions:
  contents: read
  actions: read
```

If a future integration needs write access, keep it in a separate workflow and
make the approval boundary explicit in the pull request that adds it.

## JavaScript Action Runtime Review

Reviewed on 2026-06-03 for GitHub's Node 24 action runtime transition.

| Workflow | Action | Ref | Declared runtime | Update needed |
| --- | --- | --- | --- | --- |
| `ci.yml` and `ci-triage.yml` | `actions/checkout` | `v6` | `node24` | No |
| `ci.yml` and `ci-triage.yml` | `actions/setup-python` | `v6` | `node24` | No |
| `ci.yml` and `ci-triage.yml` | `astral-sh/setup-uv` | `v8.1.0` | `node24` | No |
| `ci-triage.yml` | `actions/download-artifact` | `v4` | `node20` | No change for v0.2.0; keep monitored |
| `ci-triage.yml` | `actions/upload-artifact` | `v4` | `node20` | No change for v0.2.0; keep monitored |

The two PatchRail workflows also set:

```yaml
env:
  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"
```

That smoke-tests GitHub's Node 24 runner path while the CI triage workflow stays
read-only. The artifact actions remain on `v4` because that is the current
stable major in use by GitHub's artifact workflows; they do not change the
approval boundary and should be reviewed again before v0.2.0 is tagged.

## Supplying Real Logs

For best results, upload raw or redacted CI logs from the failing job as an
artifact with a `.log` or `.txt` extension. The triage workflow will download
artifacts from the failed run and classify the first matching log file.

Manual smoke test:

```bash
gh workflow run "PatchRail CI Triage" -f log-path=examples/ci-triage/dependency-failure.log
```

Local equivalent:

```bash
uv run patchrail ci explain --redact --log examples/ci-triage/dependency-failure.log --format markdown
uv run patchrail ci classify --redact --log examples/ci-triage/dependency-failure.log --format json
uv run patchrail ci benchmark examples/ci-triage --format json
```

To reproduce the artifact locally:

```bash
mkdir -p patchrail-report
uv run patchrail ci explain --redact --log examples/ci-triage/dependency-failure.log --format markdown --out patchrail-report/ci-report.md
uv run patchrail ci classify --redact --log examples/ci-triage/dependency-failure.log --format json --out patchrail-report/ci-result.json
uv run patchrail ci benchmark examples/ci-triage --format json --out patchrail-report/fixture-benchmark.json
uv run patchrail doctor --format json --out patchrail-report/doctor.json
```
