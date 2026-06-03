# GitHub Actions Artifact Example

This directory shows the files uploaded by the read-only
`PatchRail CI Triage` workflow artifact.

The workflow uploads the directory as an artifact named
`patchrail-ci-triage`:

```text
patchrail-ci-triage/
|-- ci-report.md
|-- ci-result.json
|-- doctor.json
`-- fixture-benchmark.json
```

The example is generated from
`examples/ci-triage/dependency-failure.log` with local commands equivalent to
the workflow:

```bash
mkdir -p patchrail-report
uv run patchrail ci explain --redact --log examples/ci-triage/dependency-failure.log --format markdown --out patchrail-report/ci-report.md
uv run patchrail ci classify --redact --log examples/ci-triage/dependency-failure.log --format json --out patchrail-report/ci-result.json
uv run patchrail ci benchmark examples/ci-triage --format json --out patchrail-report/fixture-benchmark.json
uv run patchrail doctor --format json --out patchrail-report/doctor.json
```

## Copy The Workflow

Copy `.github/workflows/ci-triage.yml` into a repository you maintain, or into a
test branch first. The workflow only needs these repository permissions:

```yaml
permissions:
  contents: read
  actions: read
```

Run a manual smoke test from the GitHub CLI:

```bash
gh workflow run "PatchRail CI Triage" -f log-path=examples/ci-triage/dependency-failure.log
```

After the run finishes, download the artifact:

```bash
run_id="$(gh run list --workflow 'PatchRail CI Triage' --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run download "$run_id" --name patchrail-ci-triage --dir patchrail-ci-triage
```

Inspect the files locally:

```bash
sed -n '1,120p' patchrail-ci-triage/ci-report.md
python -m json.tool patchrail-ci-triage/ci-result.json
python -m json.tool patchrail-ci-triage/fixture-benchmark.json | sed -n '1,80p'
python -m json.tool patchrail-ci-triage/doctor.json
```

## Artifact Contents

- `ci-report.md`: Markdown summary for maintainers. It includes root cause,
  confidence, reproduction command, evidence signals, and the safety statement.
- `ci-result.json`: structured classifier output for local tools or queues. It
  records `schema_version`, `failure_class`, `confidence`, evidence signals, and
  requirements showing no billing, external model, webhook, GitHub App, or PR
  creation requirement.
- `fixture-benchmark.json`: benchmark result over the public CI Failure Zoo. The
  example records `115` total cases, `115` passed, `0` failed, top-1 fixture
  accuracy `1.0`, and per-class coverage for the supported root-cause families.
- `doctor.json`: local safety check. It records `status=ok`, `local_first=true`,
  and no billing, network, external model, or GitHub write permission required.

If you paste any result into an issue or pull request, use only redacted excerpts.
Do not paste raw CI logs, secrets, private paths, personal data, or access tokens.

## Safety Boundary

- The artifact is a report only.
- It does not comment on issues or pull requests.
- It does not open pull requests.
- It does not push commits.
- It does not call external models.
- It does not require billing, network access for classification, or GitHub
  write permissions.

`doctor.json` and `fixture-benchmark.json` use sanitized relative paths in this
example so the public fixture does not expose maintainer machine paths.
