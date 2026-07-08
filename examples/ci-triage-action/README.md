# CI Triage Action artifact shapes

PatchRail ships its "triage a failed CI log on the runner" step in **two**
forms, and they expose different artifacts. Pick the `uses:` reference that
matches the outputs you actually want — this page documents both so a snippet
copied from here never promises outputs the referenced version does not emit.

| | In-repo composite (`actions/ci-triage`) | Published drop-in (`patchrail/ci-triage-action@v1`) |
| --- | --- | --- |
| `uses:` | `./actions/ci-triage` (workflows in this repo) | `patchrail/ci-triage-action@v1` (any repo) |
| Install source | the checked-out repo (`$GITHUB_ACTION_PATH/../..`) | `patchrail` from PyPI |
| Report files | `report-dir/ci-report.md` + `report-dir/ci-result.json` | `patchrail-ci-result.json` (JSON only) |
| Step outputs | full reusable set (see below) | `failure-class`, `confidence`, `guide-url` |
| Run surface | step outputs + `$GITHUB_STEP_SUMMARY` | `::warning` annotation + `$GITHUB_STEP_SUMMARY` |

Both variants classify locally on the runner. Neither one does anything else:
it does not open pull requests, post comments, claim funding, or send the log to
an external service.

## In-repo composite — `actions/ci-triage`

This is the richer variant PatchRail runs against its own `CI` workflow (see
[docs/github-action.md](../../docs/github-action.md)). It installs PatchRail from
the checked-out repository, so reference it from a workflow that has this repo
(or a vendored copy) checked out:

```yaml
- name: PatchRail CI triage
  if: failure()
  uses: ./actions/ci-triage
  with:
    log-path: test.log
    report-dir: patchrail-ci-triage
```

It reads the log path you pass in and writes:

- `patchrail-ci-triage/ci-report.md`
- `patchrail-ci-triage/ci-result.json`

Its reusable step outputs are `failure-class`, `failure-slug`, `confidence`,
`json-result`, `markdown-report`, `summary-line`, `redacted-categories`,
`artifact-name`, `adoption-key`, `adoption-event-id`, `adoption-event-json`,
`workflow-repository`, `workflow-run-url`, `workflow-run-host`, `next-step`,
and `reproduction-command`, so a downstream workflow can route the failure to a
maintainer or attach the local report to an internal ticket. `adoption-key` is
stable across runs of the same failure class; `adoption-event-id` is stable per
GitHub Actions run and job when workflow context is available, which makes
real workflow usage countable without parsing URLs. `adoption-event-json` is a
single-line event that can be appended directly to an evidence ledger artifact,
including the consumer workflow run URL and host when the action runs inside
GitHub Actions. The full input/output contract lives in
[`actions/ci-triage/action.yml`](../../actions/ci-triage/action.yml).

The reproducible sample below is this composite's artifact shape.

## Published drop-in — `patchrail/ci-triage-action@v1`

For a **different** repository, use the marketplace drop-in, which installs
`patchrail` from PyPI and needs nothing from this repo:

```yaml
- name: PatchRail CI triage
  if: failure()
  uses: patchrail/ci-triage-action@v1
  with:
    log-path: test.log
```

The `@v1` drop-in exposes a smaller contract on purpose:

- Step outputs: `failure-class`, `confidence`, `guide-url` — nothing else.
- It surfaces the result as a `::warning` run annotation plus a
  `$GITHUB_STEP_SUMMARY` block, and writes the structured result to
  `patchrail-ci-result.json`.
- It does **not** take `report-dir`, write a Markdown report, or emit any of the
  `adoption-*`, `artifact-name`, `next-step`, or `workflow-*` outputs listed for
  the in-repo composite above. If you need those, use the in-repo composite.

Its inputs (`log-path`, `log-text`, `redact`, `patchrail-version`,
`python-version`), the full outputs table, and a complete workflow are in
[docs/using-the-action.md](../../docs/using-the-action.md).

## Reproducible sample

This sample is the **in-repo composite** artifact shape. It uses
`examples/ci-triage/dependency-failure.log` and stores the same files the
composite writes in a workflow:

- [sample/ci-result.json](sample/ci-result.json)
- [sample/ci-report.md](sample/ci-report.md)
- [sample/github-output.txt](sample/github-output.txt)
- [sample/step-summary.md](sample/step-summary.md)

Regenerate it from the repository root:

```sh
uv run patchrail ci classify \
  --log examples/ci-triage/dependency-failure.log \
  --format json \
  --out examples/ci-triage-action/sample/ci-result.json

uv run patchrail ci explain \
  --log examples/ci-triage/dependency-failure.log \
  --format markdown \
  --out examples/ci-triage-action/sample/ci-report.md

: > examples/ci-triage-action/sample/github-output.txt
: > examples/ci-triage-action/sample/step-summary.md
uv run python actions/ci-triage/scripts/ci_triage_action_outputs.py \
  --result examples/ci-triage-action/sample/ci-result.json \
  --report examples/ci-triage-action/sample/ci-report.md \
  --output examples/ci-triage-action/sample/github-output.txt \
  --summary examples/ci-triage-action/sample/step-summary.md
```

The step-by-step remediation write-up for the detected failure class lives in
the free fix guides:

- Fix guide: [docs/fix/python-dependency-resolution.md](../../docs/fix/python-dependency-resolution.md)
- All fix guides: [docs/fix/](../../docs/fix/README.md)
