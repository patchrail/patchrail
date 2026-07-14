# Real-world CI logs

Failed CI runs from public repositories, fetched with `gh run view <id> --repo <repo> --log-failed`
on 2026-07-14 and committed **unmodified**. They are the evidence behind
[docs/real-world-benchmark.md](../../docs/real-world-benchmark.md), where each one is measured
against the version PyPI serves and against `main`.

| file | repo | run |
|---|---|---|
| `pandas-29342614636.log` | pandas-dev/pandas | [29342614636](https://github.com/pandas-dev/pandas/actions/runs/29342614636) |
| `deno-29349357779-excerpt.log` | denoland/deno | 29349357779 (deleted by GitHub; excerpt pinned by `tests/test_assertion_report_noise.py`) |
| `svelte-29330826741.log` | sveltejs/svelte | [29330826741](https://github.com/sveltejs/svelte/actions/runs/29330826741) |
| `home-assistant-29350290194.log` | home-assistant/core | [29350290194](https://github.com/home-assistant/core/actions/runs/29350290194) |
| `prometheus-29348880303.log` | prometheus/prometheus | [29348880303](https://github.com/prometheus/prometheus/actions/runs/29348880303) |
| `grafana-27635190952.log` | grafana/grafana | [27635190952](https://github.com/grafana/grafana/actions/runs/27635190952) |
| `ruff-29349828924.log` | astral-sh/ruff | [29349828924](https://github.com/astral-sh/ruff/actions/runs/29349828924) |
| `pytorch-29361968044-excerpt.log` | pytorch/pytorch | [29361968044](https://github.com/pytorch/pytorch/actions/runs/29361968044) (excerpt: the log is 3.5MB; the failing `jq` step and the CMake warning block are kept verbatim, and pinned by `tests/test_cmake_policy_notice.py`) |

These are **not** fixtures. They carry no expected-class labels and are not scored by
`patchrail ci benchmark`, which runs against the sanitized zoo in `examples/ci-triage/`. They exist
so that the claims in the benchmark page can be re-run by anyone, after GitHub expires the original
runs — as it already has for deno.

They are public CI output; GitHub masks secrets in logs at write time. Unlike the zoo, they have not
been put through PatchRail's redaction patterns, so they still contain runner paths such as
`/home/runner/work/...`.
