# Using the CI triage action in your own repository

`docs/github-action.md` documents the triage workflow that runs inside the
PatchRail repository itself. This page is for the more common case: you
maintain a different repository and want the
[`patchrail/ci-triage-action`](https://github.com/patchrail/ci-triage-action)
step in your own workflow.

That published `@v1` drop-in is the version this page documents. It installs
`patchrail` from PyPI and needs nothing from the PatchRail repo. It is a
deliberately small wrapper: it classifies the log and links the matching
`/fix` guide. If you want the richer artifact surface (a `report-dir` with a
Markdown report and the `adoption-*` / `workflow-*` outputs), that is the
in-repo composite documented in
[`examples/ci-triage-action`](../examples/ci-triage-action/README.md) and
[`docs/github-action.md`](github-action.md), not this drop-in.

## 1. Capture the failing log to a file

The action reads a log file from disk — it does not capture your test
runner's output for you. Redirect or `tee` the command that can fail so a
`.log` file exists when the step runs:

```yaml
- name: Run tests
  run: pytest -q 2>&1 | tee test.log
```

`tee` keeps the log visible in the live job output while also writing it to
`test.log`, so `if: failure()` steps later in the job can read it.

## 2. Add the triage step

```yaml
- name: PatchRail CI triage
  if: failure()
  uses: patchrail/ci-triage-action@v1
  with:
    log-path: test.log
```

Inputs:

| Input | Required | Default | Description |
|-------|----------|---------|--------------|
| `log-path` | one of `log-path`/`log-text` | `''` | Path to the failed CI log inside the checked-out repository. |
| `log-text` | one of `log-path`/`log-text` | `''` | Raw log text, used when no log file is available. |
| `redact` | no | `true` | Redact secrets, emails, and local home paths before classifying. |
| `patchrail-version` | no | `''` (latest) | Pin a specific `patchrail` version from PyPI. |
| `python-version` | no | `3.x` | Python version used to run the classifier. |

`if: failure()` is what makes this a triage-on-red step: it only runs after
a prior step in the same job has failed, so `log-path` points at a log that
already contains the failure.

## 3. What you get on a red run

The action classifies the log locally and surfaces the result three ways: a
run annotation, a job-summary block, and step outputs. It also writes the
structured result to `patchrail-ci-result.json` in the workspace.

### Run annotation

The action emits a single `::warning` annotation that appears inline on the
run, so the failure class is visible without opening the job summary:

```text
python_dependency_resolution (confidence 0.89) — guide: https://getpatchrail.com/fix/python-dependency-resolution
```

### Step outputs

Reference these from a later step with
`${{ steps.<step-id>.outputs.<name> }}`:

| Output | Description |
|--------|--------------|
| `failure-class` | PatchRail failure class for the CI log (e.g. `python_dependency_resolution`). |
| `confidence` | Classifier confidence, `0`-`1`. |
| `guide-url` | PatchRail `/fix` remediation guide URL for the failure class. |

Give the step an `id` to reference these:

```yaml
- name: PatchRail CI triage
  id: triage
  if: failure()
  uses: patchrail/ci-triage-action@v1
  with:
    log-path: test.log

- name: Show the detected failure class
  if: failure()
  run: echo "Detected ${{ steps.triage.outputs.failure-class }} (confidence ${{ steps.triage.outputs.confidence }})"
```

### Job summary

The action appends a section to the job's `GITHUB_STEP_SUMMARY`, visible on
the workflow run page without opening any artifact:

```markdown
## PatchRail CI Triage

- **Root cause:** `python_dependency_resolution`
- **Confidence:** `0.89`
- **Subsystem:** Python dependency installation
- **Reproduce:** `python -m pip install -r requirements.txt`
- **Suggested action:** Pin or relax the conflicting dependency range, then rerun the same install command and the affected tests.
- **Remediation guide:** https://getpatchrail.com/fix/python-dependency-resolution

_Classified locally. No pull request, comment or external call was made._
```

### Result file

The structured classification is written to `patchrail-ci-result.json` in the
workspace — the `patchrail.ci_result.v1` result. See the
[jq cookbook](json-cookbook.md) for scripting against it. Upload it as a
workflow artifact if you want it downloadable from the run:

```yaml
- name: Upload PatchRail result
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: patchrail-ci-result
    path: patchrail-ci-result.json
```

> Note: this `@v1` drop-in does not write a Markdown report or a `report-dir`,
> and it does not emit `failure-slug`, `next-step`, `artifact-name`, the
> `adoption-*` outputs, or the `workflow-*` outputs. Those belong to the
> in-repo composite (`actions/ci-triage`) documented in
> [`examples/ci-triage-action`](../examples/ci-triage-action/README.md).

## 4. Permissions and privacy

The action only needs read access to the repository checkout it runs in:

```yaml
permissions:
  contents: read
```

It does not need `actions: read`, `issues: write`, `pull-requests: write`, or
any GitHub token beyond the default. Classification runs entirely on the
runner against the log file you point it at — nothing is uploaded to
PatchRail, no external model is called, and the action does not comment on
issues, open pull requests, or push commits. See `docs/threat-model.md` for
the full local trust boundary.

## Pinning the action version

Pin to a released tag (or a commit SHA, for maximum reproducibility) the same
way you would pin any other action:

```yaml
uses: patchrail/ci-triage-action@v1        # tag
uses: patchrail/ci-triage-action@<full-sha> # commit
```

Pinning the action ref pins the wrapper. If you also want to pin the exact
PatchRail CLI it installs from PyPI, set the `patchrail-version` input:

```yaml
- uses: patchrail/ci-triage-action@v1
  with:
    log-path: test.log
    patchrail-version: "0.2.0"
```

## Full example

```yaml
name: CI

on: [push, pull_request]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Run tests
        run: pytest -q 2>&1 | tee test.log
      - name: PatchRail CI triage
        id: triage
        if: failure()
        uses: patchrail/ci-triage-action@v1
        with:
          log-path: test.log
      - name: Upload PatchRail result
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: patchrail-ci-result
          path: patchrail-ci-result.json
```

See [`examples/ci-triage-action`](../examples/ci-triage-action/README.md) for
the artifact shapes of both the `@v1` drop-in and the richer in-repo composite,
and `docs/github-action.md` for how PatchRail uses the in-repo composite against
its own `CI` workflow.
