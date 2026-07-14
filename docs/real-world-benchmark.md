# Real-world benchmark

The fixture zoo (`examples/ci-triage`, 221 logs) says PatchRail is right 221 times out of 221. That
number is worth exactly nothing to you: we wrote both the logs and the answers.

This page is the other benchmark. Seven **real failed CI runs from public repositories** — pandas,
deno, svelte, Home Assistant, Prometheus, Grafana, ruff — with their logs committed to this repo
unmodified, exactly as `gh run view --log-failed` returned them. Every verdict below is the output of
a command you can run yourself, including **the two where PatchRail is still wrong**.

## Reproduce it

```bash
# what PyPI serves today
pip install patchrail==0.6.1
patchrail ci explain --log examples/real-world/pandas-29342614636.log --format json

# what this repo's main does with the same log
uv run patchrail ci explain --log examples/real-world/pandas-29342614636.log --format json
```

The logs are committed here on purpose. GitHub deletes Actions logs, and it has already deleted one
of these: the deno run below now returns `HTTP 404` from the API. A benchmark whose commands stop
working in ninety days is a claim, not evidence.

## Results

`before` is patchrail 0.6.1, the version PyPI serves today. `after` is `main` at `68e552d`. (Both
report `0.6.1` to `--version`; the version bumps at release, so the commit is what distinguishes
them.)

| repo (run) | what actually failed | before | after | |
|---|---|---|---|---|
| [pandas](https://github.com/pandas-dev/pandas/actions/runs/29342614636) | nothing legible — the log has no error line at all | `artifact_or_cache_failure` 0.89 | `python_test_failure` 0.53 | ⚠️ still wrong ([#347](https://github.com/patchrail/patchrail/issues/347)) |
| deno (29349357779) | Rust harness panic, exit code 101 | `typescript_typecheck` 0.89 | `rust_test_failure` 0.71 | ✅ fixed |
| [svelte](https://github.com/sveltejs/svelte/actions/runs/29330826741) | Dependabot's updater died | `javascript_lint` 0.71 | `unknown` 0.15 | ✅ fixed |
| [home-assistant](https://github.com/home-assistant/core/actions/runs/29350290194) | a pytest snapshot assertion | `python_test_failure` 0.95 | `python_test_failure` 0.95 | ✅ correct |
| [prometheus](https://github.com/prometheus/prometheus/actions/runs/29348880303) | golangci-lint: file not gofmt'd | `go_lint` 0.89 | `go_lint` 0.89 | ✅ correct |
| [grafana](https://github.com/grafana/grafana/actions/runs/27635190952) | the package does not compile | `go_lint` 0.71 | `go_lint` 0.71 | ⚠️ right job, wrong nature |
| [ruff](https://github.com/astral-sh/ruff/actions/runs/29349828924) | the repo's own `grep`-based gate | `unknown` 0.15 | `unknown` 0.15 | ✅ honest |

Four of the seven were classified identically before and after. That is the point of showing them:
the three fixes below were narrow enough not to disturb the logs that already worked.

## Where PatchRail is still wrong

### pandas — a package list is not a test run

`Doc Build and Upload` failed. The log GitHub hands back for it contains **zero** `##[error]` lines,
zero tracebacks and zero `exit code` lines. The failure is simply not in it.

0.6.1 answered `artifact_or_cache_failure` at **0.89** anyway, on the strength of this:

```
##[warning]Failed to save: Unable to reserve cache with key micromamba-environment--linux-64-test
```

That is a warning, emitted during `Post job cleanup`, long after the job was already dead. In
`actions/cache`, a failed save is reported through `core.warning` and never `core.setFailed` — a
cache that could not be saved *cannot* be why a job failed. `eb355b7` fixed that.

Today `main` says `python_test_failure` at **0.53**, and that is still not the right answer. Its one
signal is `\bpytest\b`, and every line it matches looks like this:

```
  pytest                            9.0.3              pyhc364b38_1          conda-forge
  pytest-cov                        7.1.0              pyhcf101f3_0          conda-forge
```

A conda package table. There is no pytest invocation anywhere in the log, and PatchRail still tells
you to run `python -m pytest -q`. The correct answer is `unknown`, which would at least hand back the
runner's own error lines. Tracked in [#347](https://github.com/patchrail/patchrail/issues/347).

What changed is not that PatchRail got this log right. It's that a confident wrong answer became a
weak wrong one. That is worth something — 0.89 sends a maintainer to debug a healthy cache — but it
is not a fix, and we are not going to describe it as one.

### grafana — a compile error is not a lint failure

PatchRail says `go_lint` at 0.71 and tells you to run `golangci-lint run ./...`. That command does
reproduce the failure, and golangci-lint is genuinely what failed. But what it reported is:

```
pkg/services/frontend/request_config_test.go:22:34: not enough arguments in call to config.ApplyOverrides
```

The package does not compile. A maintainer reading "lint" may reach for a formatter when the real job
is to fix a call site. Right job, wrong nature of the failure.

## The three fixes, and the logs that forced them

### deno — `typescript_typecheck` → `rust_test_failure` ([#343](https://github.com/patchrail/patchrail/issues/343), `00d4f9e`)

PatchRail told the maintainers of a TypeScript runtime that their TypeScript was broken. It wasn't.

deno's spec suite runs `deno check` against programs that are *supposed* to fail type checking, and
asserts the diagnostics come out right. When a spec fails, the harness prints both sides of the
comparison, so the log fills with compiler diagnostics that were never emitted by a compiler running
over deno's code — they are the contents of a fixture file:

```
---- specs::check::check_deno_not_found ----
-- OUTPUT START --
-- OUTPUT END --
-- EXPECTED START --
TS2304 [ERROR]: Cannot find name 'Deno'.
error: Type checking failed.
-- EXPECTED END --
```

What actually failed said so plainly, in the same log: `thread 'main' panicked at
tests/specs/mod.rs:669` and `##[error]Process completed with exit code 101` — 101 being what a Rust
process returns when it panics. The fix bounds these machine-rendered, delimited report blocks: a
signal that falls inside one no longer testifies to a failure.

The original run's logs (30 MB) have since been deleted by GitHub — `gh api
repos/denoland/deno/actions/runs/29349357779` returns 404 — so what is committed here is the excerpt
pinned by `tests/test_assertion_report_noise.py`. It reproduces the defect: 0.89 before, 0.71 after.
The full log measured 0.95 at the time (recorded in #343).

### svelte — `javascript_lint` → `unknown` ([#345](https://github.com/patchrail/patchrail/issues/345), `68e552d`)

A Dependabot security update that died inside the updater. The runner says so in one line:

```
##[error]Dependabot encountered an error performing the update
```

PatchRail sent Svelte's maintainers to run `pnpm lint`. It now returns `unknown` and hands back that
error line. `unknown` is not a diagnosis, and PatchRail has no class for a Dependabot updater
failure. It is the honest answer, and honest beats confident.

### httpx and prefect — pytest's own verdict ([#320](https://github.com/patchrail/patchrail/pull/320), `93b6391`)

Not in the table above (we no longer hold those logs), but the same shape and the reason two of the
rules above exist: CI shells run under `set -x` and echo every command whether it passes or fails,
and pip announces every dependency it resolves. httpx's log contains `+ ruff check httpx tests` from
a linter that **passed**; prefect's contains `Collecting mypy==1.17.1` from a job that never ran
mypy. Both outranked the real cause. A rule whose signals appear *only* in a `set -x` echo, a `Run …`
header or a pip install line has watched a tool be *named*, never fail — it now yields to the rule
that matched a real error.

## Method, and what it does not tell you

- Logs fetched with `gh run view <id> --repo <repo> --log-failed`, committed unmodified. They are
  public CI output; GitHub masks secrets in logs at write time.
- `--log-failed` returns the failed job's steps, and — as pandas shows — sometimes the failure is not
  in them. PatchRail cannot classify what it was not given, and should say `unknown` when that
  happens. Today, for pandas, it doesn't.
- Seven logs is not a statistic. It is a set of cases you can check by hand, chosen because they were
  the failed runs sitting in these repos on 2026-07-14, not because they flattered the tool.
- Every number here is the output of a command in this page, against a file in this repo. When a fix
  lands for #347, this page changes with it.
