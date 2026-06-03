# CI Janitor

CI Janitor is PatchRail's first public module. It turns failed CI logs into:

- a failure class;
- confidence score;
- evidence signals;
- likely subsystem;
- reproduction command;
- minimal repair strategy;
- structured JSON for downstream tools.

## Supported early classes

- Python dependency resolution.
- Python test failures.
- Node dependency installation.
- TypeScript type checking.
- JavaScript or TypeScript linting.
- GitHub Actions workflow wiring.
- Docker and Docker Compose build/runtime setup.
- Playwright and Cypress browser test failures.
- Rust test failures.
- Go test failures.

## Output formats

```bash
patchrail ci classify --log failed.log --format json
patchrail ci explain --log failed.log --format markdown
patchrail ci explain --log failed.log --format text
patchrail ci explain --redact --log failed.log --format markdown
patchrail ci benchmark examples/ci-triage --format json
patchrail redact --log failed.log
patchrail schema ci-result
```

The JSON contract is versioned as `patchrail.ci_result.v1` and bundled with the
package. Downstream tools can fetch it locally with `patchrail schema ci-result`
without network access.

## Fixture benchmark

CI Janitor fixtures use a `.log` file plus a neighboring `.expected.json` file:

```text
examples/ci-triage/dependency-failure.log
examples/ci-triage/dependency-failure.expected.json
```

The expectation file declares the target `failure_class` and an optional
`minimum_confidence`. Run the local benchmark before changing classifier rules:

```bash
patchrail ci benchmark examples/ci-triage --format markdown
```

The fixture set contains 124 sanitized synthetic examples across eleven supported
root-cause families. The benchmark does not require network access, billing, a
GitHub App, or an external model. It exits non-zero when any fixture expectation
fails.

## Boundary

CI Janitor is advisory in v0.1. It does not push commits, open pull requests, or
send log contents to remote services.

## Redaction

CI logs can contain tokens, emails and local paths. PatchRail includes a local
redaction pass for common secret-shaped values and personal paths. Redaction is
deterministic and local; it does not upload logs or call an external model.
