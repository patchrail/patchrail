# Real-world benchmark

The fixture zoo (`examples/ci-triage`, 223 logs) says PatchRail is right 223 times out of 223. That
number is worth exactly nothing to you: we wrote both the logs and the answers.

This page is the other benchmark. Twenty-two **real failed CI runs from public repositories** — pandas,
deno, svelte, Home Assistant, Prometheus, Grafana, ruff, PyTorch, Envoy, containerd, React, Symfony,
Discourse, Mastodon, Phoenix, Signal-Android, Jellyfin, cats, riverpod, cabal, crystal and dune — with their logs committed to
this repo unmodified, exactly as `gh run view --log-failed` returned them. Every verdict below is the
output of a command you can run yourself — including the ten where the honest answer is **`unknown`**,
one of them because the failure never made it into the log.

## Reproduce it

```bash
# the last release before these fixes
pip install patchrail==0.6.1
patchrail ci explain --log examples/real-world/pandas-29342614636.log --format json

# what this repo's main does with the same log
uv run patchrail ci explain --log examples/real-world/pandas-29342614636.log --format json
```

The logs are committed here on purpose. GitHub deletes Actions logs, and it has already deleted one
of these: the deno run below now returns `HTTP 404` from the API. A benchmark whose commands stop
working in ninety days is a claim, not evidence.

## Results

`before` is patchrail 0.6.1, the last release that predates these fixes. `after` is `main`. PyPI
serves **0.7.5** today and ships every fix below. The six that `main` still held when this table was
last measured — the pandas fix (#347), the Symfony fix (#377), the Discourse fix (#379), the riverpod
fix, the cabal fix and the crystal fix — were cut into 0.7.4 on 2026-07-22, so no row is a case where
`main` is ahead of `pip install patchrail`. The `after` column was measured against `main` on
2026-07-17; the classifier fixes merged since (#390–#395, each of which removes a false positive on a
log that is not in this table) have not been re-measured here.

| repo (run) | what actually failed | before | after | |
|---|---|---|---|---|
| [pandas](https://github.com/pandas-dev/pandas/actions/runs/29342614636) | nothing legible — the log has no error line at all | `artifact_or_cache_failure` 0.89 | `unknown` 0.15 | ✅ fixed ([#347](https://github.com/patchrail/patchrail/issues/347)) |
| deno (29349357779) | Rust harness panic, exit code 101 | `typescript_typecheck` 0.89 | `rust_test_failure` 0.71 | ✅ fixed |
| [svelte](https://github.com/sveltejs/svelte/actions/runs/29330826741) | Dependabot's updater died | `javascript_lint` 0.71 | `unknown` 0.15 | ✅ fixed |
| [home-assistant](https://github.com/home-assistant/core/actions/runs/29350290194) | a pytest snapshot assertion | `python_test_failure` 0.95 | `python_test_failure` 0.95 | ✅ correct |
| [prometheus](https://github.com/prometheus/prometheus/actions/runs/29348880303) | golangci-lint: file not gofmt'd | `go_lint` 0.89 | `go_lint` 0.89 | ✅ correct |
| [grafana](https://github.com/grafana/grafana/actions/runs/27635190952) | the package does not compile | `go_lint` 0.71 | `go_test_failure` 0.53 | ✅ fixed |
| [ruff](https://github.com/astral-sh/ruff/actions/runs/29349828924) | the repo's own `grep`-based gate | `unknown` 0.15 | `unknown` 0.15 | ✅ honest |
| [pytorch](https://github.com/pytorch/pytorch/actions/runs/29361968044) | lintrunner's `jq` step — `lint.json` was never written | `secrets_or_permissions_failure` 0.53 | `unknown` 0.15 | ✅ fixed |
| [envoy](https://github.com/envoyproxy/envoy/actions/runs/29363920524) | one directory under its coverage threshold | `ci_job_timeout` 0.53 | `code_coverage_threshold` 0.53 | ✅ fixed |
| [containerd](https://github.com/containerd/containerd/actions/runs/29358848438) | a Go integration test failed (`TestContainerCgroupWritable`) | `runner_resource_exhaustion` 0.89 | `go_test_failure` 0.71 | ✅ fixed |
| [React](https://github.com/facebook/react/actions/runs/29335289512) | a file was not `prettier`-formatted | `node_dependency_install` 0.53 | `javascript_lint` 0.53 | ✅ fixed |
| [Symfony](https://github.com/symfony/symfony/actions/runs/29551386048) | a PHPUnit assertion in `ErrorHandler`, after `composer` had succeeded | `php_composer_failure` 0.95 | `unknown` 0.15 | ✅ fixed ([#377](https://github.com/patchrail/patchrail/issues/377)) |
| [Discourse](https://github.com/discourse/discourse/actions/runs/29572043439) | six QUnit chat tests timed out (`# fail  6`) | `secrets_or_permissions_failure` 0.53 | `unknown` 0.15 | ✅ fixed ([#379](https://github.com/patchrail/patchrail/issues/379)) |
| [Mastodon](https://github.com/mastodon/mastodon/actions/runs/29561949942) | one RSpec system spec timed out (`26 examples, 1 failure`) | `ruby_bundle_failure` 0.71 | `ruby_bundle_failure` 0.71 | ✅ correct |
| [Phoenix](https://github.com/phoenixframework/phoenix/actions/runs/28866117635) | four ExUnit assertions failed, `mix test` exit 1 (`819 tests, 4 failures`) | `elixir_mix_failure` 0.71 | `elixir_mix_failure` 0.71 | ✅ correct |
| [Signal-Android](https://github.com/signalapp/Signal-Android/actions/runs/28969358490) | a Gradle screenshot-test task failed (`BUILD FAILED`) | `java_build_failure` 0.89 | `java_build_failure` 0.89 | ✅ correct |
| [Jellyfin](https://github.com/jellyfin/jellyfin/actions/runs/29544616523) | a C# compile error (`CS0117`) in a test project, buried among 30+ passing suites | `dotnet_build_failure` 0.89 | `dotnet_build_failure` 0.89 | ✅ correct |
| [cats](https://github.com/typelevel/cats/actions/runs/29545595453) | an sbt test run failed (`sbt.TestsFailedException`) | `java_build_failure` 0.71 | `java_build_failure` 0.71 | ✅ correct |
| [riverpod](https://github.com/rrousselGit/riverpod/actions/runs/29573819047) | `flutter analyze` reported 4 lints, exit 1 — a Dart run, not a JVM build | `java_build_failure` 0.53 | `unknown` 0.15 | ✅ fixed |
| [cabal](https://github.com/haskell/cabal/actions/runs/29562439929) | a GHC compile error failed Cabal's own test suite (`Some tests failed`, exit 1) — a Haskell build, not a JVM one | `java_build_failure` 0.53 | `unknown` 0.15 | ✅ fixed |
| [crystal](https://github.com/crystal-lang/crystal/actions/runs/29501393259) | a Crystal stdlib spec errored on a socket bind (`Socket::BindError`), `make std_spec` exit 1 — a Crystal spec, not a C/C++ compile | `cpp_build_failure` 0.53 | `unknown` 0.15 | ✅ fixed |
| [dune](https://github.com/ocaml/dune/actions/runs/29585452292) | a cram test-case diff failed dune's own `make test` (`make: *** [test] Error 1`) — an OCaml test run; 0.6.1 blamed a benign cache-budget warning, later builds the bare make line | `artifact_or_cache_failure` 0.71 | `unknown` 0.15 | ✅ fixed |

Eight of the twenty were classified identically before and after. Three — Home Assistant, Prometheus and
ruff — because the fixes below were narrow enough not to disturb the logs that already worked. Five —
Mastodon, Phoenix, Signal-Android, Jellyfin and cats — because Ruby/RSpec, Elixir/ExUnit, Kotlin/Gradle,
.NET and Scala/sbt were never misread here in the first place; they are in the table to show the tool holds
across ecosystems it was already right about, not only the ones that forced a fix.

## Where PatchRail stops at `unknown`

As of this measurement, none is confidently wrong. Ten answer `unknown` — ruff, svelte,
Symfony, Discourse, riverpod, cabal, crystal and dune because PatchRail has no class for what broke, pytorch because a lint
runner never wrote the report its `jq` step then failed to read, and pandas because the failure is not in the
log at all. `unknown` there is a limit, not a diagnosis, and the honest thing to say.

### pandas — a package list is not a test run ([#347](https://github.com/patchrail/patchrail/issues/347))

`Doc Build and Upload` failed. The log GitHub hands back for it contains **zero** `##[error]` lines,
zero tracebacks and zero `exit code` lines — the excerpt is cut off mid-`Post job cleanup`, `Successfully
built`, having captured only the micromamba env build. The failure is simply not in it.

Two different rules mistook that env build for a failure, and PatchRail wore both verdicts in turn:

0.6.1 answered `artifact_or_cache_failure` at **0.89**, on a `Post job cleanup` warning
(`##[warning]Failed to save: Unable to reserve cache with key ...`). That is a warning, long after the
job was already dead; in `actions/cache`, a failed save is reported through `core.warning` and never
`core.setFailed`, so a cache that could not be saved *cannot* be why a job failed. With that suppressed,
the next-loudest match took over: `python_test_failure` at **0.53**, whose one signal `\bpytest\b`
matched the conda solver's package table —

```
  pytest                            9.0.3              pyhc364b38_1          conda-forge
  pytest-cov                        7.1.0              pyhcf101f3_0          conda-forge
```

— a `pytest` installed as a doc-build dependency, never run. `\b` treats `-`, `<`, `>`, `=` as
boundaries, so the same signal also read `pytest-cov` and the `pytest<9.1` version pin as invocations.
The pattern now requires that a `pytest` match not be a package spec, so the dependency listing carries
nothing; and a benign cache warning is suppressed not only when the runner annotated a *different* error
but also when the log plainly reports success and shows no failure at all — which is exactly this
truncated excerpt.

Left with no real signal, `main` answers `unknown` at **0.15** with `likely_successful_run`, and hands
the log back. That is the honest ceiling: PatchRail cannot diagnose a failure it was never given, and
now says so instead of inventing one.

## The fixes, and the logs that forced them

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

### grafana — `go_lint` → `go_test_failure` ([#352](https://github.com/patchrail/patchrail/issues/352))

A compile error, reported by the linter, read as a lint failure — on evidence that was never
evidence at all.

Grafana's `lint-go` job did not fail a lint check. `config.ApplyOverrides` had grown a parameter and
eight call sites in one test file had not:

```
##[error]pkg/services/frontend/request_config_test.go:22:34: not enough arguments in call to config.ApplyOverrides
```

There is no lint finding anywhere in that log — not one `(gofmt)`, `(revive)` or `(errcheck)`. Yet
PatchRail answered `go_lint` at 0.71 and advised "apply the reported lint correction", because
`golangci-lint-action` names its tool five times while merely *shipping* it: it looks the version
up, hits its cache, installs the binary, echoes its own command line, and times the run. Both
witnesses came off install lines. Any job that so much as declares the action got a confident lint
verdict for free, whatever actually broke.

Downloading a linter is not running one, and running one is not failing one. Those lines are now
mere mentions, which carry nothing; the invocation echo still corroborates but cannot carry a rule
on its own. What is left witnessing a failure is the Go compiler's own diagnostic, so the log lands
on `go_test_failure`: reproduce with `go test ./...`, and make "the smallest compile or runtime fix
in that package" — which is what the maintainers did.

The cure did not eat the disease, and prometheus above is the proof: the same action, the same
install lines, but a real `(gci)` finding on a real error line. It stays `go_lint` at 0.89 — and it
now scores on the finding it was right about, which until this fix had matched no pattern at all.

### envoy — `ci_job_timeout` → `code_coverage_threshold` ([#354](https://github.com/patchrail/patchrail/issues/354))

A limit a job *declares* is not a limit a job *hit*.

Envoy's coverage job ran for sixteen minutes under a 180-minute ceiling and failed a coverage gate.
One directory out of 430 had slipped three tenths of a point:

```
FAILED: Directories not meeting coverage thresholds:
  ✗ source/common/quic: 93.2% (threshold: 93.5%)
Overall Coverage: 96.7%
```

PatchRail answered `ci_job_timeout` at 0.53 and sent the maintainer off to compare step durations
against their time limit. Its one and only witness was a line Actions had echoed from the workflow
config, before the job ran a single test:

```
  timeout-minutes: 180
```

Every other pattern in that class is a timeout that *happened* — `has exceeded the maximum execution
time of 360 minutes`, `The operation was canceled`, `execution took longer than`. `timeout-minutes`
is the field you write to *set* the budget, and the runner prints it on green runs too. Our own
[fix guide](fix/ci-job-timeout.md) calls it the knob you raise *after* a timeout, which is exactly
why it cannot be proof of one.

The declaration no longer counts as a witness (a mention in prose still does). The log then lands on
the class it had the evidence for all along — `coverage threshold`, right there in the failing line.
Both classes had scored one pattern each, and the tie had been going to whichever rule was declared
first.

A job that really does run long is untouched: the runner says so in words, and those words are still
`ci_job_timeout` at full confidence.

### containerd — `runner_resource_exhaustion` → `go_test_failure` ([#357](https://github.com/patchrail/patchrail/issues/357))

A container killed for memory is not the *runner* running out of it.

containerd's integration job failed a Go test — `--- FAIL: TestContainerCgroupWritable` — and
`make: *** [Makefile:230: cri-integration] Error 1` ended the job. PatchRail answered
`runner_resource_exhaustion` at 0.89 and told the maintainer to `rerun the failing job while watching
runner memory and disk`. Its three witnesses were all things the suite does *on purpose*:

```
    oom_linux_test.go:93: Creating 8 running container and wait for them OOMKilled
    ... level=debug msg="Exec process ... exits with exit code 137 and error <nil>"
[Tue Jul 14 19:05:42 2026] Memory cgroup out of memory: Killed process 197353 (dd)
```

A test that provokes the OOM killer, an exec that exits 137 by design (logged at `level=debug`, with
`error <nil>`), and a *cgroup* hitting its configured limit — the opposite of the host running dry.
`OOMKilled`, `Out of memory` and `exit code 137` describe a process killed for memory but never say
whose. Nudging the verdict off the resource rule alone would only trade it for
`network_transient_failure`: the same suite logs `connection refused` from an upgrade test, and that
is ambiguous noise too. So a resource match built *entirely* from those symptom signals now defers to
the concrete cause the log recorded — the Go test — skipping the equally-ambiguous network rule on
the way. A real runner exhaustion is untouched: it trips a terminal signal (the runner's own
`Process completed with exit code 137`, `No space left on device`, a build's `JavaScript heap out of
memory`) outside the ambiguous set, and keeps its verdict.

### React — `node_dependency_install` → `javascript_lint` ([#359](https://github.com/patchrail/patchrail/issues/359))

A `yarn run` that failed is not a `yarn install` that failed.

yarn classic ends every command with the same footer — `info Visit
https://yarnpkg.com/en/docs/cli/<cmd> for documentation about this command.` — and
`node_dependency_install` watched for the bare host `yarnpkg.com`. On React's "Run prettier" step
(run 29335289512) a file simply was not formatted:

```
This project uses prettier to format all JavaScript code.
    Please run yarn prettier-all and add changes to files listed below to your commit:
error Command failed with exit code 1.
info Visit https://yarnpkg.com/en/docs/cli/run for documentation about this command.
```

The subcommand in that footer is `run`, not `install`, but the pattern ignored the path — so a
formatting diff scored a dependency verdict and the maintainer was told to reconcile a lockfile.
`node_dependency_install` and `javascript_lint` each matched exactly one witness here (the footer vs
`prettier`), and the dependency rule won the tie on rule order. Pinning the footer to `install` and
`add` — the only two subcommands that *are* a dependency operation — drops the `run`/`lint`/`test`
footers, so the `prettier` witness the log actually carries wins and it answers `javascript_lint`. A
real `yarn install` failure is untouched: its `/cli/install` footer still matches, and it rarely
rests on the footer alone — `yarn install v1.x`, `error An unexpected error occurred`, and the
lockfile / registry messages carry it.

### pytorch — `secrets_or_permissions_failure` → `unknown` ([#349](https://github.com/patchrail/patchrail/issues/349), `e6ff9c6`)

A warning a compiler prints for developers to ignore is not a missing repository secret.

PyTorch's `lintrunner-clang-all` job failed for a reason with nothing to do with credentials:
lintrunner never wrote its report, so the `jq` step that reads it died —

```
jq: error: Could not open file lint.json: No such file or directory
##[error]Process completed with exit code 1.
```

— and PatchRail answered `secrets_or_permissions_failure` at 0.53. `SCREAMING_CASE is not set` is how
a job reports a missing credential, so the rule watched for it; but CMake announces its policies the
same way, and a policy id is shaped exactly like an environment variable:

```
CMake Warning (dev) at third_party/NNPACK/CMakeLists.txt:110 (FIND_PACKAGE):
  Policy CMP0148 is not set: The FindPythonInterp and FindPythonLibs modules
  are removed.  Run "cmake --help-policy CMP0148" for policy details.
This warning is for project developers.  Use -Wno-dev to suppress it.
```

Its own last line is "Use `-Wno-dev` to suppress it," it comes from a vendored third-party
`CMakeLists.txt`, and it was the whole case for auditing PyTorch's secrets. The fix pins the rule so
the subject of `is not set` may not be a policy CMake introduced — `Policy CMP0148` no longer
matches, while a token that really is unset (`GITHUB_TOKEN is not set`) still does, because nothing
precedes it. Left with no witness, the log answers `unknown` and hands the `jq` failure back: honest,
because PatchRail has no class for a lint runner that never produced its report.

### Symfony — `php_composer_failure` → `unknown` ([#377](https://github.com/patchrail/patchrail/issues/377))

A PHPUnit assertion that failed is not a Composer that failed.

Symfony's `Unit Tests (8.3)` job locked, installed and autoloaded its dependencies cleanly, ran the
suite, and one assertion in `src/Symfony/Component/ErrorHandler` came out wrong:

```
Testing src/Symfony/Component/ErrorHandler
There was 1 failure:
1) Symfony\Component\ErrorHandler\Tests\Error\FatalErrorTest::testGetTraceWithoutTraceArgs
Failed asserting that an array has the key 'args'.
FAILURES!
Tests: 128, Assertions: 379, Failures: 1, Skipped: 2.
##[error]KO src/Symfony/Component/ErrorHandler
```

PatchRail answered `php_composer_failure` at **0.95** — telling a maintainer whose `composer update`
had gone green to go debug dependency installation. The rule was carrying PHPUnit's own verdict
markers — `FAILURES!`, `Failed asserting`, the `Tests: … Failures:` summary — as if a failing test
were a failing install, and it also counted the bare `composer install` / `composer update` commands,
which nearly every PHP job runs whether or not anything breaks (Symfony echoes both as setup).

None of those is a Composer failure. The rule now witnesses only genuine dependency errors — an
unresolvable requirement, a platform mismatch, a lockfile that has drifted — and the autoload
`Class … not found`. With the test-verdict markers and the setup commands gone, a plain assertion
failure carries nothing here and the log answers `unknown`: PatchRail has no PHP test-failure class,
so `unknown` is the honest ceiling, the same one ruff and svelte land on. A real composer failure is
untouched — `Your requirements could not be resolved`, `requires php`, the lockfile-drift warning all
still carry the rule at full confidence, and the five committed composer fixtures still pass.

### Discourse — `secrets_or_permissions_failure` → `unknown` ([#379](https://github.com/patchrail/patchrail/issues/379))

A phrase in the title of a test that PASSED is not a secret the job was missing.

Discourse's `Plugins QUnit` job ran 1,559 browser assertions; six chat components timed out at 60s
each and the suite ended `# fail  6`. PatchRail answered `secrets_or_permissions_failure` at 0.53. Its
one and only witness was a test that went green:

```
ok 1523 [564 ms] - poll - Acceptance: Poll Builder - polls are disabled: regular user - insufficient permissions
```

`insufficient permissions` is the scenario that poll test asserts the UI handles gracefully — the
description on an `ok` line, TAP for "this passed." Read verbatim it sent a maintainer to audit their
repository secrets over the title of a passing test. A TAP report prints one `ok N` line per passing
assertion, and its description is application vocabulary, not a runner diagnostic; a phrase matched only
there now witnesses nothing. The run's real failures start `not ok` and carry nothing this rule keys
on, so — with no browser-QUnit test class — the log answers `unknown`, the same ceiling ruff, svelte and
Symfony land on. A genuine permissions failure is untouched: `insufficient permissions` on an error line,
`Resource not accessible by integration`, a `Permission … denied to github-actions` all still carry the
rule, because none of them arrives on a green TAP line.

### riverpod — `java_build_failure` → `unknown`

The word "gradle" in a progress bar is not a Gradle build.

rrousselGit/riverpod is a Dart/Flutter monorepo. Its `build` job ran `flutter analyze`, which reported
four lint findings and exited 1:

```
Analyzing flutter_riverpod...
   info • Unnecessary use of 'unawaited'. ...
4 issues found. (ran in 32.6s)
##[error]Process completed with exit code 1.
```

That is a Dart analyzer run. PatchRail answered `java_build_failure` at 0.53, and its one and only
witness in 972 lines was a single line from Flutter's `precache` step, which lists the SDK artifacts the
tool downloads and caches before it does anything:

```
[2/10] Gradle Wrapper                                                7ms
```

The Gradle Wrapper is one of those artifacts — cached in 7ms, never run. This is the same failure mode
as apache/kafka's env dump exporting `GRADLE_HOME`: a tool named in passing, on a line that reports it
being fetched, not failing. A `[N/M] … <time>` line is a completed step in a progress listing; a signal
found nowhere else now witnesses nothing. PatchRail has no Dart/Flutter class, so the honest answer is
`unknown`, the ceiling ruff, svelte and Symfony share. A real Gradle failure is untouched: Signal-Android
above trips `Execution failed for task` and `BUILD FAILED` on their own lines and still lands
`java_build_failure` at 0.89.

### cabal — `java_build_failure` → `unknown`

A dependency-resolver diagnostic printed by a test is not a Maven build.

haskell/cabal is Cabal itself — a Haskell project. Its `Validate` job died on GHC: a `setup.hs`
would not compile, so Cabal's own test suite recorded `UNEXPECTED FAIL` and the job exited 1:

```
setup.hs:44:13: error: [GHC-88464]
##[error]    Data constructor not in scope: PreProcessorCustom :: FilePath -> t1
Failed to build internal-preprocessor-test-0.1.0.0-inplace. ... during the configure step.
UNEXPECTED FAIL: PackageTests/PreProcess/Basic/setup.test.hs ...
Some tests failed
##[error]Process completed with exit code 1.
```

There is no `mvn`, `gradle`, `sbt` or JVM token anywhere in the 141k-line log. PatchRail answered
`java_build_failure` at 0.53, and its one and only witness was a line buried inside a cabal-testsuite
*golden output*, where the solver's diagnostic is the text the test expects to see:

```
Could not resolve dependencies:
[__0] trying: A-1 (user goal)
[__1] fail (backjumping, conflict set: A, A.base)
```

Maven's phrasing is `Could not resolve dependencies for project <group>:<artifact>:jar:<version>`; the
bare `Could not resolve dependencies:` — trailing colon, no "for project" — is Cabal's, and pip's, and
npm's. The rule now keys on the Maven suffix, so Cabal's line carries nothing. PatchRail has no Haskell
class, so the honest answer is `unknown`, the ceiling ruff, svelte, Symfony, Discourse and riverpod share.
A real Maven failure is untouched: `Could not resolve dependencies for project com.example:app:jar:1.0`
still lands `java_build_failure`.

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
  happens. For pandas, it now does ([#347](https://github.com/patchrail/patchrail/issues/347)).
- Twenty logs is not a statistic. It is a set of cases you can check by hand, chosen because they
  were the failed runs sitting in these repos on 2026-07-14 (and Symfony, Discourse, Mastodon, Phoenix,
  Signal-Android, Jellyfin, cats, riverpod, cabal, crystal and dune on 2026-07-17), not because they flattered the tool.
- Every number here is the output of a command in this page, against a file in this repo. Re-run them.
