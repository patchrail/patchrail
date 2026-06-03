# Quickstart

Install PatchRail:

```bash
pipx install patchrail
patchrail --help
```

Confirm the local installation and safety boundary:

```bash
patchrail doctor
```

Classify a failed CI log:

```bash
patchrail ci classify --log failed-github-actions.log --format json
```

Render a maintainer-readable report:

```bash
patchrail ci explain --log failed-github-actions.log --format markdown
```

Redact a log before sharing it:

```bash
patchrail redact --log failed-github-actions.log > failed-github-actions.redacted.log
```

Create a local pilot pack for maintainer review:

```bash
patchrail ci pilot-pack --log failed-github-actions.log --out-dir patchrail-pilot-pack
patchrail ci pilot-summary --pack patchrail-pilot-pack --ci-provider "GitHub Actions" --toolchain Python
```

From a source checkout, run the bundled fixture and benchmark:

```bash
uv run --extra dev patchrail ci explain --log examples/ci-triage/dependency-failure.log --format markdown
uv run --extra dev patchrail ci benchmark examples/ci-triage --format markdown
```

PatchRail v0.1 does not create pull requests, comments, funded issue claims, or
remote uploads. The command reads a local log file and writes a local report.
