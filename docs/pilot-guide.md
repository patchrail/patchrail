# Maintainer Pilot Guide

PatchRail pilots are consent-only, local-first trials for maintainers who want
to understand failed CI faster. A pilot does not give PatchRail write access to
your repository, does not open pull requests, does not comment on issues, and
does not call external models by default.

The goal is simple: run PatchRail against one failed CI log, inspect the report,
and optionally contribute a sanitized fixture so the public benchmark improves.

## Pilot Scope

A good first pilot has:

- one failed CI log from GitHub Actions, GitLab CI, CircleCI, or another CI
  system;
- one clear toolchain, such as Python, Node, TypeScript, Go, Rust, or
  JavaScript linting;
- no raw secrets, personal data, customer names, private paths, or private
  repository identifiers;
- a maintainer who can say whether the reported root cause and suggested action
  were useful.

Keep the first run read-only. PatchRail should produce evidence and suggestions,
not modify code.

## Run A Local Pilot

Install PatchRail:

```bash
pipx install patchrail
```

Check the local safety posture:

```bash
patchrail doctor --format markdown
```

Redact the failing log before sharing it or turning it into a fixture:

```bash
patchrail redact --log failed-ci.log > failed-ci.redacted.log
```

Classify the redacted log locally:

```bash
patchrail ci explain --log failed-ci.redacted.log --format markdown > patchrail-report.md
patchrail ci classify --log failed-ci.redacted.log --format json > patchrail-result.json
```

Or generate the same review bundle in one local command:

```bash
patchrail ci pilot-pack --log failed-ci.log --out-dir patchrail-pilot-pack
patchrail ci pilot-summary --pack patchrail-pilot-pack --ci-provider "GitHub Actions" --toolchain Python > pilot-summary.md
```

The pack contains:

- `failed-ci.redacted.log`;
- `patchrail-report.md`;
- `patchrail-result.json`;
- `pilot-manifest.json`;
- `README.md`.

It does not copy the raw log into the output directory. Review the redacted log
manually before sharing the pack or citing the result publicly.

`patchrail ci pilot-summary` turns the pack into a short Markdown or JSON
outcome summary for an adopter-report issue. It defaults to `--repository-mention-approved no`,
so a repository name passed on the command line is not printed unless the
maintainer explicitly approved public listing:

```bash
patchrail ci pilot-summary \
  --pack patchrail-pilot-pack \
  --repository owner/repo \
  --repository-mention-approved yes \
  --ci-provider "GitHub Actions" \
  --toolchain Python \
  --classification-correct yes \
  --maintainer-action-useful yes
```

Use `--format json` if you want structured evidence for local records. The
summary still does not copy raw logs, open pull requests, post comments, call
external models, claim funding, or request write access.

Aggregate multiple reviewed summaries into safe adoption metrics with:

```bash
patchrail ci pilot-metrics pilot-summary-*.json --format markdown
```

The aggregate counts public repository mentions only when each summary was
created with `--repository-mention-approved yes`. Private or unapproved
repository names remain excluded from the public list.

Review the report manually. Useful pilot notes are:

- whether the root cause was correct;
- which evidence lines helped;
- which suggested action was wrong, missing, or too vague;
- whether the log needed more redaction before it could be shared.

## Optional Queue Demo

If you want to test the Agent Control Plane locally, import the CI result into a
SQLite queue:

```bash
patchrail queue --db patchrail-pilot.sqlite init
patchrail queue --db patchrail-pilot.sqlite add --from-pilot-pack patchrail-pilot-pack
patchrail queue --db patchrail-pilot.sqlite list
patchrail queue --db patchrail-pilot.sqlite audit --format jsonl
```

The queue stores a pending local work item with references to
`failed-ci.redacted.log`, `patchrail-report.md`, `patchrail-result.json`, and
`pilot-manifest.json`.

The importer validates that the manifest did not copy the raw log. Approval
records do not open pull requests, do not comment on issues, and do not grant
repository write permissions.

If you are not using a pilot pack, a standalone classifier JSON is still
accepted:

```bash
patchrail queue --db patchrail-pilot.sqlite add --from-ci-result patchrail-result.json
```

## Contribute A Fixture

The easiest contribution is a sanitized CI fixture:

1. Reduce the log to the shortest excerpt that still shows the failure.
2. Run `patchrail redact` and review the output manually.
3. Remove secrets, emails, user names, private repo names, and local home paths.
4. Add `examples/ci-triage/<short-name>.log`.
5. Add `examples/ci-triage/<short-name>.expected.json`.
6. Run the fixture hygiene check and benchmark:

```bash
patchrail ci fixture-check examples/ci-triage --format json
patchrail ci benchmark examples/ci-triage --format json
```

Expected metadata files use this shape:

```json
{
  "failure_class": "python_test_failure",
  "minimum_confidence": 0.7
}
```

If a real log cannot be safely redacted, create a minimal synthetic fixture that
preserves the error pattern without preserving private identifiers.

## Evidence To Share

Useful pilot evidence is small and reviewable:

- the PatchRail version;
- the CI provider and toolchain;
- the `pilot-manifest.json` from `patchrail ci pilot-pack`, if used;
- the `patchrail ci fixture-check` result if a fixture is proposed;
- the redacted report, if safe to share;
- whether the classification was correct;
- whether the suggested maintainer action was useful;
- any fixture pull request or issue link.

Do not share raw logs that contain secrets or personal data. Do not grant write
permissions for a pilot.

## Example Outcome

See [examples/pilot-outcome](../examples/pilot-outcome/README.md) for a
synthetic, copyable pilot outcome. It shows how to summarize a useful read-only
pilot while keeping raw logs private, marking repository public mention as
unapproved, and avoiding any claim that PatchRail opened a pull request,
commented on an issue, contacted a maintainer, or used external models.

## Non-Goals

PatchRail pilots are not bounty automation, mass outreach, or automatic
contribution workflows. The pilot path is for maintainers who opt in to a
read-only local trial.
