# Real-world CI logs

Failed CI runs from public repositories, fetched with `gh run view <id> --repo <repo> --log-failed`
on 2026-07-14 (Symfony, Mastodon, Phoenix, Signal-Android, Jellyfin, cats and riverpod on 2026-07-17)
and committed **unmodified** — the one exception is ANSI color codes, which `gh` returned in caret
notation for Symfony, Phoenix, cats and riverpod, stripped for legibility. They are the evidence behind
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
| `envoy-29363920524-excerpt.log` | envoyproxy/envoy | [29363920524](https://github.com/envoyproxy/envoy/actions/runs/29363920524) (excerpt: the log is 590KB; the echoed `timeout-minutes` config and the coverage gate that actually failed are kept verbatim, and pinned by `tests/test_timeout_minutes_declaration.py`) |
| `containerd-29358848438-excerpt.log` | containerd/containerd | [29358848438](https://github.com/containerd/containerd/actions/runs/29358848438) (excerpt: the log is 9MB; the Go test that failed, the three provoked container-OOM/exit-137/cgroup lines, and the `make` error that ended the job are kept verbatim, and pinned by `tests/test_container_runtime_oom_noise.py`) |
| `react-29335289512-excerpt.log` | facebook/react | [29335289512](https://github.com/facebook/react/actions/runs/29335289512) (excerpt: the failing "Run prettier" step — the formatting message, the unformatted file, and the `yarn run` footer that carried the wrong verdict — kept verbatim, and pinned by `tests/test_yarn_run_footer_notice.py`) |
| `symfony-29551386048-excerpt.log` | symfony/symfony | [29551386048](https://github.com/symfony/symfony/actions/runs/29551386048) (excerpt: the 2.3MB `Unit Tests (8.3)` log's `composer update` success and the `ErrorHandler` assertion that actually failed kept verbatim, ANSI color codes stripped, and pinned by `tests/test_php_test_failure_not_composer.py`) |
| `discourse-29572043439-excerpt.log` | discourse/discourse | [29572043439](https://github.com/discourse/discourse/actions/runs/29572043439) (excerpt: the `Plugins QUnit` run's passing `ok` line with `insufficient permissions` in its title and the six `not ok` timeouts kept verbatim, and pinned by `tests/test_tap_pass_line_not_secrets.py`) |
| `mastodon-29561949942-excerpt.log` | mastodon/mastodon | [29561949942](https://github.com/mastodon/mastodon/actions/runs/29561949942) (excerpt: the `End to End testing (3.3)` RSpec run — the streaming system spec that timed out and the `26 examples, 1 failure` summary — kept verbatim; classified correctly, drove no fix) |
| `phoenix-28866117635-excerpt.log` | phoenixframework/phoenix | [28866117635](https://github.com/phoenixframework/phoenix/actions/runs/28866117635) (excerpt: the `test-elixir (1.12.1, …)` `mix test` run — the ExUnit failures and the `819 tests, 4 failures` summary — kept verbatim, ANSI color codes stripped; classified correctly, drove no fix) |
| `signal-android-28969358490-excerpt.log` | signalapp/Signal-Android | [28969358490](https://github.com/signalapp/Signal-Android/actions/runs/28969358490) (excerpt: the Gradle `build` job — the `validateDebugScreenshotTest` task that FAILED and `BUILD FAILED` — kept verbatim; classified correctly, drove no fix) |
| `jellyfin-29544616523-excerpt.log` | jellyfin/jellyfin | [29544616523](https://github.com/jellyfin/jellyfin/actions/runs/29544616523) (excerpt: the `run-tests (ubuntu-latest)` `dotnet test` job — dozens of `Passed!` suites and the one buried `error CS0117` that failed the build — kept verbatim; classified correctly, drove no fix) |
| `cats-29545595453-excerpt.log` | typelevel/cats | [29545595453](https://github.com/typelevel/cats/actions/runs/29545595453) (excerpt: the `catsNative` sbt run — the `welcome to sbt` banner and the `sbt.TestsFailedException` that ended it — kept verbatim, ANSI color codes stripped; classified correctly, drove no fix) |
| `riverpod-29573819047-excerpt.log` | rrousselGit/riverpod | [29573819047](https://github.com/rrousselGit/riverpod/actions/runs/29573819047) (excerpt: the `flutter_riverpod` build job — Flutter's `precache` artifact listing including `[2/10] Gradle Wrapper` and the `flutter analyze` lint failure — kept verbatim, ANSI color codes stripped, and pinned by `tests/test_flutter_precache_not_gradle.py`) |

These are **not** fixtures. They carry no expected-class labels and are not scored by
`patchrail ci benchmark`, which runs against the sanitized zoo in `examples/ci-triage/`. They exist
so that the claims in the benchmark page can be re-run by anyone, after GitHub expires the original
runs — as it already has for deno.

They are public CI output; GitHub masks secrets in logs at write time. Unlike the zoo, they have not
been put through PatchRail's redaction patterns, so they still contain runner paths such as
`/home/runner/work/...`.
