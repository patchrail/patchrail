# Changelog

## 0.7.3 - 2026-07-16

### Fixed

- **Piping a CI log that isn't clean UTF-8 no longer crashes with a raw `UnicodeDecodeError`.** The
  headline one-liner `gh run view <run-id> --log-failed | patchrail ci explain` feeds raw log bytes
  to stdin, and real CI logs frequently carry bytes that aren't valid UTF-8 — a latin-1 accent in a
  test name, stray ANSI/control bytes, a truncated multibyte sequence. Reading stdin in text mode
  decoded those with the strict locale codec, so a single stray byte raised an uncaught
  `UnicodeDecodeError` and dumped a Python traceback on the *primary documented flow* — even though
  the exact same bytes passed via `--log <file>` classified fine (that path already decoded with
  `errors="replace"`). `explain`, `classify`, `pilot-pack` and `redact` now read the stdin pipe as
  bytes and decode it with `errors="replace"` too, so the piped one-liner is as forgiving as the
  file path and reaches the same verdict instead of crashing a first-timer.
- **`patchrail ci explain` with no `--log` in a terminal no longer hangs on a frozen screen.** When
  `--log` is omitted PatchRail reads the log from stdin, which is right for the piped one-liner
  (`gh run view <run-id> --log-failed | patchrail ci explain`). But a first-timer who just runs
  `patchrail ci explain` in a terminal — forgetting `--log`, with nothing piped in — used to hit a
  blocking `stdin.read()` that waited forever with zero output: the program looked frozen or
  crashed, with no hint that it wanted input. `explain`, `classify`, `pilot-pack` and `redact` now
  detect an interactive terminal on stdin and fail fast with `no log to read from stdin: pass --log
  <file>, or pipe a CI log in (e.g. \`gh run view <run-id> --log-failed | patchrail ci explain\`)`
  on stderr and exit 2 — the same clean contract as the other bad-input cases. A real pipe or file
  redirect is untouched (its stdin is not a TTY), so the documented one-liner keeps working.
- **Pointing `--log` at a directory (or an unreadable file) now fails with a clear message instead
  of a Python traceback.** A first run often means tab-completing a path, and it's easy to land on a
  folder — `patchrail ci explain --log logs/` — or a file the shell can't read. Only a missing file
  was handled; a directory raised a raw `IsADirectoryError` and a permission problem raised
  `PermissionError`, both leaking a stack trace and exiting 1. `explain`, `classify`, `pilot-pack`
  and `redact` now report `log path is a directory, not a file: logs/ (point --log at a single CI
  log file)` — or `log file is not readable (permission denied): …` — on stderr and exit 2, the same
  clean contract as the missing-file case.
- **A passing CI log is no longer reported as an unrecognized failure that you should file a
  fixture for.** A newcomer's first run is often a green one — they pipe in whatever `gh run view`
  hands back, or try `patchrail ci explain` on a build that passed. That log matched no failure
  rule, so it landed on `unknown` at 0.15 — the *same* answer a genuinely unrecognized failure gets,
  down to "Open a CI failure fixture issue with a sanitized log." Nudging someone to open a fixture
  issue for a build that never failed is worse than unhelpful: it invites non-failures into the
  tracker. PatchRail now recognizes a log that plainly announces success and betrays no failure
  (`BUILD SUCCESS`, `all checks passed`, `322 passed`, `process completed with exit code 0`, …),
  flags it as `likely_successful_run` in the JSON result, and replies "No failure detected — point
  me at the failed run" instead of the fixture invitation. The detection is conservative: it fires
  only from the `unknown` path, still demands an explicit success announcement, and any failure tell
  (a runner-annotated error, a non-zero exit, `3 failed`, a traceback) vetoes it — so a real failure
  that slips past every rule keeps its plain `unknown` verdict and its fixture invitation.
  `patchrail ci explain --fail-on-unknown` also stops exiting non-zero on a log that plainly passed:
  there is no failure to fail on.

## 0.7.2 - 2026-07-15

### Fixed

- **A Flyway migration that fails at runtime is now recognised as a database migration failure, not
  `unknown`.** `database_migration_failure` advertised Flyway support, but only for checksum and
  validation errors — a migration that reached the database and failed *there* fell through to
  `unknown` at 0.15, so `patchrail ci explain` had nothing to say about the most common Flyway
  failure of all. On a `flyway migrate` step that hit `ERROR: Migration V2__add_users.sql failed`
  with `SQL State : 42S01` (table already exists), the log now answers `database_migration_failure`
  at 0.71 and points you at the SQL error to fix. It reads two witnesses the driver prints on a real
  failure — the `Migration V<n>__<name>.sql failed` line and a non-success `SQL State` code — and a
  successful run is unaffected: the `SQL State : 00000` success code is explicitly excluded. Thanks
  to @hkJerryLeung for the fix (#361, closing #265) — PatchRail's first merged external contribution.
- **A failed `yarn` script — `prettier`, `lint`, `test` — is no longer reported as a dependency
  install.** yarn classic ends *every* command with `info Visit https://yarnpkg.com/en/docs/cli/<cmd>
  for documentation about this command.`, and `node_dependency_install` was matching the bare host —
  so a `yarn run prettier` that failed on a formatting diff was sent back to reconcile a lockfile. On
  facebook/react's "Run prettier" step (run 29335289512) the footer was `/cli/run`, not `/cli/install`;
  the log's real witness was `prettier`. The footer is now pinned to the two subcommands that *are* a
  dependency operation (`install`, `add`), so that log answers `javascript_lint` — the class its
  evidence supported. A real `yarn install` failure is unaffected: it keeps the `/cli/install` footer
  and its other signals (`yarn install v1.x`, `error An unexpected error occurred`, lockfile and
  registry messages).
- **A container killed for memory is no longer reported as the *runner* running out of it.**
  `runner_resource_exhaustion` is about the CI machine hitting a host limit — free disk, raise the
  runner class. But `OOMKilled`, `Out of memory` and `exit code 137` describe a process killed for
  memory without saying *whose*, and a container runtime's own tests trip all three on purpose: a
  test that provokes the OOM killer, an exec that exits 137 by design, a *cgroup* reaching its
  configured limit. On containerd/containerd's integration run 29358848438 a Go test failed
  (`TestContainerCgroupWritable`) and PatchRail sent the maintainer to go watch runner memory and
  disk. A resource verdict built *only* from those symptom signals now defers to the concrete cause
  the log recorded — here `go_test_failure`, reproduced with `go test ./...` — and skips the equally
  ambiguous `network_transient_failure` the same suite also trips (`connection refused` from an
  upgrade test). A real exhaustion is unaffected: it also trips a terminal signal (the runner's own
  `Process completed with exit code 137`, `No space left on device`, a build's `JavaScript heap out
  of memory`), and keeps its verdict.

## 0.7.1 - 2026-07-14

### Fixed

- **A job that declares `timeout-minutes` is no longer reported as a job that timed out.** Actions
  echoes your step config into the log — `timeout-minutes: 180` — on green runs and red ones alike.
  PatchRail was reading that declaration as evidence the limit had been *hit*, so a job that set a
  timeout and then failed for an unrelated reason could be sent back with `ci_job_timeout` and told
  to go raise it. On envoyproxy/envoy's coverage run 29363920524 the job never came near its
  180-minute ceiling: one directory out of 430 had slipped three tenths of a point under its
  coverage threshold. That log now answers `code_coverage_threshold` — the class its evidence
  supported all along. A job that really did run long is unaffected: the runner says so in words
  (`has exceeded the maximum execution time of 360 minutes`, `The operation was canceled`), and
  those still land as `ci_job_timeout` at full confidence.
- **A Go job that fails to compile is no longer reported as a lint failure.** If your workflow
  uses `golangci-lint-action`, the action names its tool five times just to *ship* it — it looks
  the version up, hits its cache, installs the binary, echoes its own command line, and times the
  run. PatchRail was reading those install lines as proof the linter had failed, so any Go job that
  merely declared the action got a confident `go_lint` verdict — "apply the reported lint
  correction" — whatever had actually broken. On grafana/grafana's `lint-go` run 27635190952 there
  was no lint finding at all: a function had grown a parameter and eight call sites in one test file
  had not. That log now answers `go_test_failure`, reproduces with `go test ./...`, and tells you to
  fix the call site. A linter that really did report something (`(gofmt)`, `(gci)`, `(revive)`) is
  still `go_lint` at full confidence.
- **Go call-site mismatches are recognised.** `not enough arguments in call to` and `too many
  arguments in call to` — the compiler's own words — no longer pass unread, alongside `undefined:`.

## 0.7.0 - 2026-07-14

Nine misreadings, all of one kind. Every fix below started as a real failing run at a real
project — pandas, deno, svelte, istio, astro, ruff, prometheus, pytorch — where PatchRail
answered confidently and answered wrong, and every one of them was wrong the same way: it
mistook a line that merely *named* a tool for a line proving that tool had *failed*. An
install listing, an echoed script, a suppressible warning, a cache cleaning up after a job
that was already dead, a test quoting a compiler back at itself. A verdict that no signal
ever witnessed failing now yields to what the runner actually flagged — and when nothing is
left, the honest answer is `unknown` and the failing line handed back.

### Added

- **[`docs/real-world-benchmark.md`](docs/real-world-benchmark.md) — the classifier measured
  against seven real CI logs, misses included.** For each one: what actually broke, what
  PatchRail said before, what it says now, and the command that reproduces it. The logs
  themselves are committed verbatim under `examples/real-world/`, so every number can be
  checked rather than taken on trust. The misses are in the table, not in a footnote — pandas
  still lands on `python_test_failure` at 0.53 rather than naming the crash, and grafana calls
  a compile error `go_lint`. Four of the seven verdicts are identical before and after, which
  is the point: these fixes are narrow.
  ([#348](https://github.com/patchrail/patchrail/pull/348))

### Fixed

- **A CMake policy that is not set is no longer read as a repository secret that is not set.**
  `SCREAMING_CASE is not set` is how a job announces a missing credential, so PatchRail watched
  for it — but CMake announces its *policies* the same way, and a policy id (`CMP0148`) is shaped
  exactly like an environment variable. pytorch/pytorch's lint job failed because lintrunner never
  wrote its report (`jq: error: Could not open file lint.json`), and PatchRail answered
  **`secrets_or_permissions_failure` at 0.53 confidence** — on a single witness: a
  `CMake Warning (dev)` raised inside a vendored `third_party/NNPACK/CMakeLists.txt`, whose own
  closing line reads *"This warning is for project developers. Use -Wno-dev to suppress it."* A
  maintainer would have gone to audit their repository secrets over a suppressible warning. A
  policy CMake names is never a credential, so it no longer witnesses; the log now answers
  `unknown` and hands the failure back. A token that really is unset (`GITHUB_TOKEN is not set`,
  `AWS_SECRET_ACCESS_KEY is not set`) still classifies at full confidence.
- **A dependency Dependabot merely listed is no longer mistaken for a tool that ran and failed.**
  Dependabot opens every update by echoing its *job definition* — one line of JSON naming every
  dependency it may touch and every pull request already open. sveltejs/svelte's security update
  died inside the updater, and the runner said so (`##[error]Dependabot encountered an error
  performing the update`), but PatchRail told the Svelte maintainers their linter had failed, at
  **0.71 confidence**, and sent them off to run `pnpm lint`. No linter ran: `eslint` matched 59
  times in that log, 58 of them registry URLs the sandbox proxy fetched, and the 59th was the
  entry `{"pr-number":17594,"dependencies":[{"dependency-name":"eslint",…}]}` inside that JSON.
  A record the updater files under its own job id is bookkeeping, not a diagnostic, so the answer
  is now `unknown` and it hands back the line the runner flagged. Anything the updater *forwards*
  from the package manager it drives (`npm ERR! ERESOLVE`) carries no job id and still classifies
  at full confidence, as does an error the updater files itself.
- **Output a test quoted back at you is no longer read as the job's own diagnostic.** When a
  test suite asserts on the output of a tool, that tool's diagnostics become the test's *data* —
  and a failing assertion prints them right back, actual against expected. denoland/deno's spec
  suite (30MB, 1553 failing specs) carried 4899 TypeScript diagnostics of exactly this kind, and
  PatchRail told the maintainers of a TypeScript runtime that their TypeScript was broken, at
  **0.95 confidence**. It was not: deno's specs typecheck deliberately-broken programs and assert
  the errors come out right, so every one of those diagnostics was the contents of a fixture file
  (`-- EXPECTED START --`, named on the `output path` line above it) or a `pretty_assertions`
  diff of one. What had actually failed said so plainly — `panicked at tests/specs/mod.rs:669`,
  exit code 101 — and now that is the answer: `rust_test_failure`, pointing at the spec that
  asserted a type error and got an empty string back. A diagnostic the job itself emitted sits
  outside those blocks by construction and still carries the verdict as before, including a real
  `tsc` failure in a job that also runs specs.
- **A cache that could not save, and a tool the job merely installed, no longer decide the
  verdict.** pandas-dev/pandas's doc build died on a Sphinx crash and PatchRail called it an
  `artifact_or_cache_failure` at **0.89 confidence**, sending a maintainer to debug a cache
  that was working perfectly. Three signals carried that verdict and not one of them had
  witnessed a failure:

  ```
  Download action repository 'actions/upload-artifact@bbbca2dd...'
  ##[warning]Failed to save: Unable to reserve cache with key micromamba-downloads--linux-64,
      another job may be creating this cache.
  ```

  The first is the runner booting, printed by every run that uses the action — the green ones
  too. The other two are `Post job cleanup`, 2,000 lines *after* the job had already died,
  reporting that two matrix jobs raced for one cache key. `actions/cache` settles it in its
  own source: `saveImpl` wraps the save in `try { … } catch { logWarning(…) }`, so a save
  error goes out through `core.warning` and never `core.setFailed`. **A cache that failed to
  save cannot be why a job failed.** Once the runner has annotated an error — proof that some
  step exited non-zero — a rule carried by nothing but benign warnings now stands down.

  The same log also named `mypy` six times without ever running it: as the `environment.yml`
  spec, through conda's transaction table, `Linking mypy-1.17.1-…`, the package tables and
  `conda list`. pip's half of this was already handled (`Collecting`, `Downloading`); conda's
  was not, so a bare `mypy` read off an install plan was enough to return `python_type_check`.
  A conda listing is a bill of materials, not an event.

  Deliberately narrow, and the guards are pinned by tests: a genuine artifact or cache failure
  still wins at full confidence (`Failed to CreateArtifact`, `Cache service responded with
  500`, `an artifact with this name already exists`), a warning in a log with **no** runner
  error at all is still the one lead available and still stands, and a `mypy` that actually
  ran and failed is still a `python_type_check`. All 221 fixtures pass unchanged.

- **A failed `npm audit` is now reported as a failed security scan, not a broken dependency
  install.** When a registry cannot serve audit requests — Artifactory, Verdaccio and GitHub
  Packages all commonly cannot, which is the ordinary reason this fails in CI — npm exits
  non-zero through its own audit error channel:

  ```
  npm ERR! code EAUDIT
  npm ERR! audit Your configured registry does not support audit requests
  ```

  None of that says the words `npm audit`, which was the only npm signal the scanner rule
  knew. So the only rule still matching was the bare `npm ERR!` of `node_dependency_install`,
  and a maintainer whose audit step failed was told to go fix an install that was never
  broken. The scanner now knows npm's audit error channel — `EAUDIT*`, `npm ERR! audit …`,
  and npm 10+'s `npm error audit endpoint returned an error` — and pnpm's
  (`ERR_PNPM_AUDIT_*`), which the install rule's broad `ERR_PNPM` prefix had been claiming.

  Deliberately narrow: `npm ERR!` on its own still means a broken install, every pnpm code
  that is not an audit is untouched, and `npm warn audit …` — npm reporting a scan it
  *skipped* — is still not a failure. All 221 fixtures pass unchanged.
  ([#335](https://github.com/patchrail/patchrail/issues/335))

- **A tie between two failure classes now goes to the one that watched something fail,
  not to whichever was written first.** Found dogfooding against real failing runs:
  `prometheus/prometheus` — a Go repo, whose Go tests failed — was reported as
  `javascript_lint` at 0.89, and its maintainers were handed `pnpm lint` as the way to
  reproduce a Go test failure.

  Both classes matched exactly three signals, so the verdict came down to declaration order
  in the rule list, and `javascript_lint` happens to be written first. That is a coin flip,
  and the log had already settled the question: `javascript_lint`'s three were `eslint` and
  `prettier`, read off pnpm's listing of the web UI's *installed packages*, plus
  `no-unused-vars`, read off an eslint **warning** printed by a build that exited 0.
  `go_test_failure`'s three were `--- FAIL:`, `FAIL <pkg>` and `go test` — the test that
  actually died.

  So a tie is now broken by the signals that *carry*: the ones that matched away from an
  echo or install line, and that are not just a tool's bare name (a name is corroboration
  next to a real error, never a verdict on its own). Scoring itself is unchanged — a rule
  that wins on signal count outright still wins, so no genuine verdict moves, and all 221
  fixtures keep top-1 accuracy of 1.0.
  ([#338](https://github.com/patchrail/patchrail/issues/338))

- **The source of a step, echoed before it runs, is no longer read as the step's output.**
  GitHub Actions prints every line of a `run:` step's script — in cyan-bold — before executing
  it. Those lines are the step's *program text*: they say what it *would* print, not what
  happened. PatchRail was reading them as output. `astral-sh/ruff`'s benchmark job died on a
  Rust panic (`exit code: 101`) and came out **`python_test_failure`**, carried by a single
  line: an error branch, belonging to a CodSpeed installer download that had *succeeded*, in
  which `FAILED .*::` matched pytest's short-summary format off the text
  `Failed to install CodSpeed CLI::`. That panic is now reported as `rust_test_failure`.

  No rule was safe from this: of ten real failing logs sampled, seven echo a step body, and
  those bodies say `pnpm run lint`, `bail() {`, `exit 1`. An echoed line now corroborates but
  can never carry a verdict — the same standing as `Run mypy .`. A tool that genuinely failed
  also fails somewhere off the listing, so a real pytest failure still wins at full confidence
  even when the script that ran it is echoed above.
  ([#336](https://github.com/patchrail/patchrail/issues/336))

- **npm's post-install audit tally is no longer read as a failed security scan.** Found
  dogfooding against real failing runs: `withastro/astro`'s Windows smoke job was reported
  as `security_scan_failure` at 0.71. The whole of the evidence was the block npm prints at
  the end of a *successful* install — `1 high severity vulnerability`, `npm audit fix
  --force`. No scan ran; `npm audit` was suggested, never invoked, and the tally counts
  advisories in the dependency tree. The job had actually died in a build script, and the
  runner said so: `##[error]@benchmark/timer#build: command … exited (-1073741502)`.

  Two changes, one idea — *a tool that gets named is not a tool that failed*. npm's audit
  summary no longer witnesses a failure, and a verdict left standing as a **last resort** —
  one whose signals never watched anything fail — now yields to the runner's own annotation
  when there is one. On this log that mattered twice: silencing the audit tally alone just
  handed the verdict to `javascript_lint` at 0.89, on `eslint`, `biome` and `prettier` read
  off pnpm's install listing. Both linters and scanners that genuinely run and genuinely
  fail are untouched — they witness a failure off those lines and keep full confidence, and
  a scanner's own finding (`High severity vulnerability found in openssl (CVE-…)`) is never
  mistaken for npm's tally, which is matched only when the count is the whole line.
  ([#327](https://github.com/patchrail/patchrail/issues/327))

- **A proxy logging its own client disconnects is no longer read as a network outage.**
  Found dogfooding against real failing runs: `istio/istio`'s failing Dependabot job was
  reported as `network_transient_failure` at 0.53. The only evidence was `connection reset
  by peer` — logged thirteen times by the MITM proxy Dependabot runs *by design*, at its
  own client. Meanwhile the runner had said outright what went wrong, and PatchRail threw
  it away: `##[error]Dependabot encountered an error performing the update`.

  A transient-network verdict carried *only* by signals that cannot prove an outage on
  their own (`connection reset by peer`, `dial tcp`, `i/o timeout`, `context deadline
  exceeded`…) now yields to the runner's own annotation, and you get that line back under
  *"the CI runner did annotate these lines as errors"* instead of a network red herring.
  A genuine outage is untouched: it trips a terminal signal — DNS, TLS, rate limit,
  gateway — outside that set, and keeps classifying at full confidence.
  ([#326](https://github.com/patchrail/patchrail/issues/326))

## 0.6.1 - 2026-07-14

### Fixed

- **A success announced through the error channel is no longer reported as somewhere to
  "start".** Found dogfooding the 0.6.0 wheel against real failing runs: `oven-sh/bun`'s
  failing run carries exactly one runner annotation in 4,709 lines, and the workflow emits
  a success through it — `##[error]✅ Autofix task started.` The `unknown` verdict handed
  that line straight back under *"the CI runner did annotate these lines as errors — start
  there"*, pointing the maintainer at a line saying everything went fine.

  The verdict itself was, and stays, correct: `unknown` is honest for that log. Only the
  evidence changes. An annotation is now dropped when it *opens* with a success mark and
  names no failure anywhere in the line. The guard is deliberately lopsided towards
  keeping — `✅ 2 passed, ❌ 1 failed` and `✔ image built, but the upload failed` both
  survive, and a tick further along a line never counts — because a puzzling line a
  maintainer dismisses in a second costs far less than a real error swallowed on their
  behalf. ([#329](https://github.com/patchrail/patchrail/issues/329))

## 0.6.0 - 2026-07-14

### Added

- **An `unknown` verdict now hands back the line the runner itself flagged.** Found the
  same way as the 0.5.0 fixes — running `ci explain` over real failing runs from public
  repositories. psf/requests run 29295524780 failed on a single, self-explanatory line,
  `##[error]"github-token" length must be less than or equal to 100 characters long`, and
  PatchRail answered `unknown`, no signals, "No high-confidence local signal found." The
  maintainer who piped that log in learned nothing they would not have learned by never
  running PatchRail at all.

  A log no rule matches usually still names its own failure: the Actions runner annotates
  the failing line for the web UI (`##[error]…`), and a step can emit the `::error::`
  workflow command itself. Those annotations are now reported on an `unknown` result — in
  `runner_errors` (JSON), under "Errors the runner reported" (Markdown), and as
  `Runner reported:` (text) — redacted with the same patterns `patchrail redact` applies,
  de-duplicated, and capped.

  It stays evidence and nothing more. An annotation says *where* the job died, not *why*,
  so the class stays `unknown` and the confidence stays at 0.15: PatchRail still does not
  pretend to recognize a log it does not recognize. A log that *does* classify is
  unchanged — its `signals` already explain it, and its payload does not shift.

  Only annotations that *say* something are reported. The runner marks up every failing
  step alike — `Process completed with exit code 1.` is in all twelve failing runs sampled
  across `cilium`, `rails`, `dotnet/runtime` and others, because it is emitted whatever the
  cause — and the workflow-level `Workflow failed because one or more jobs failed` merely
  restates that something failed. Reported back, those lines would dress an empty answer up
  as a finding, and, each exit code being a distinct string, a matrix build's worth of them
  would fill the cap ahead of the annotation that names the failure. They are dropped: an
  `unknown` log now either hands back a line worth reading — `hashicorp/terraform` asking
  for a changelog entry — or says nothing at all.

### Fixed

- **A tool named inside a filename is no longer a diagnosis.** A CI log in a monorepo is
  mostly filenames, and a rule could be carried, start to finish, by a word that only ever
  appeared inside one. `oven-sh/bun`'s formatter listed every file it checked and left
  *unchanged*; two of them sit under a directory called `lockfile/`, and that was the entire
  case for telling a Zig and JavaScript runtime that its pnpm lockfile was out of date, with
  `corepack pnpm install --frozen-lockfile` offered as the way to reproduce it. In the same
  log, `test/cli/install/GHSA-pfwx-36v6-832x.test.ts` — a regression test *named after* the
  advisory it covers — was reported as a failed security scan. No scan ran. The file was
  passing, and was never opened.

  Three of eight failing runs sampled across `denoland/deno`, `oven-sh/bun`, `istio/istio`,
  `withastro/astro`, `apache/airflow`, `envoyproxy/envoy`, `astral-sh/ruff` and
  `pydantic/pydantic` were wrong this way, each pointing at the wrong ecosystem entirely.
  `istio/istio` — a Go repo — was a Java build *and* a Node install, because Dependabot
  echoes its configuration as one 2,929-character JSON line and the keys
  `"gradle-lockfile-updater"` and `"lockfile-only"` are in it. The only thing that actually
  failed was the Dependabot updater, which said so in as many words.

  A signal now has to match *somewhere other than* inside a path token to carry a verdict,
  the bare tool names we recognize (`eslint`, `prettier`, `jest`, `bundler`, `gradle`,
  `trivy`, `snyk`, …) join `docker build` and `clippy` as invocations that corroborate a
  failure but never constitute one, and `lockfile` and `peer dep` — nouns that name a thing
  without asserting anything about it, and which also match `--no-frozen-lockfile`, the flag
  that *permits* the change — cannot stand alone either. An error that cites a path is
  untouched, because the match has to *start* inside the path to be discounted:
  `error[E0277]` in `src/main.rs:12:5` still witnesses its failure, and `FAIL tests/foo.ts`
  still witnesses on `FAIL`. Genuine lockfile breaks keep classifying, and yarn's and bun's
  — which say neither `npm ERR!` nor `ERR_PNPM` — now do so on a message of their own
  (`Your lockfile needs to be updated`) rather than on the bare noun. All 221 fixtures
  classify exactly as before.

## 0.5.0 - 2026-07-14

### Fixed

- **A tool the job merely *named* can no longer outrank the one that failed.** Found by
  running `ci explain` over real failing runs from public repositories. Three of nine —
  encode/httpx, prefecthq/prefect and home-assistant/core — were decided by the job's cast
  list rather than its cause of death:
  - `scripts/check`-style CI shells run under `set -x`, so every command is echoed into
    the log, passing or not. httpx's echo of `ruff check` (a run that *passed*), plus
    `F401` quoted inside ruff's non-fatal warning about a malformed noqa directive, made a
    plain `1 failed, 1416 passed` pytest failure come out as `python_lint` at 0.71.
  - pip announces every dev dependency it resolves, so `Collecting mypy==1.17.1` puts
    `mypy` in the log of a job that never type-checked anything. Prefect's pytest
    collection error came out as `python_type_check`.

  Signals are now judged by the *line* they land on: a rule whose every signal appears
  only on a `set -x` echo, an Actions step header (`Run …`) or a pip install line has
  watched a tool get named, never fail, and defers to a rule that matched a real error.
  Scoring itself is unchanged, so an invocation sitting next to a genuine error still
  corroborates it and keeps it at full confidence — a real dotnet, helm or php failure
  scores exactly as before. This generalises `INVOCATION_ONLY_PATTERNS`, which had to name
  every tool one pattern at a time and switched itself off entirely as soon as a single
  signal fell outside the list.
- **`python_test_failure` now recognises pytest's own verdict.** The rule could match a
  *named* failing test (`FAILED x::y`) or a bare `pytest` invocation, but not
  `===== 1 failed, 1416 passed in 18.37s =====`, `short test summary info`, or a
  collection error (`ERROR tests/x.py - ValueError`). A run that reported the count and
  not the names — `-q`, or any plugin that rewrites the summary — was therefore carried by
  its invocation alone and lost to whatever tool the job had merely mentioned. The `=`
  run and the `in 12.3s` tail are pytest's summary line and not jest's, so node test
  failures are unaffected.
- **ANSI colour codes no longer hide the failure.** CI tools colour their output and CI
  keeps the colour on (Airflow runs pytest with `--color=yes`, cargo honours
  `CARGO_TERM_COLOR=always`, jest and eslint colour by default), and the GitHub log API
  serves those escapes back with the ESC byte written out as the two literal characters
  `^[`. The colour reset lands *inside* the failure line — `^[[31mFAILED^[[0m tests/…::…`
  — so `FAILED .*::` and every other pattern spanning a coloured token silently stopped
  matching. A real apache/airflow test failure was reported as `artifact_or_cache_failure`
  because the only signal left uncoloured was the bare `pytest` invocation. Both
  encodings (real `\x1b` and literalised `^[`) are now stripped before matching; the strip
  is anchored to the escape introducer, so `error[E0277]`, `[ERROR]` and ordinary
  indexing are untouched.
- **Post-failure cleanup noise no longer outranks the real cause.** `actions/upload-artifact`
  appears in every job that uploads anything, and "No files were found with the provided
  path" is a *warning* it emits when its glob matches nothing (it says so itself: "No
  artifacts will be uploaded"). Together they fire on the commonest shape in CI — a test
  fails, and the `if: failure()` step uploading logs for diagnosis finds nothing — which
  tied the real cause and beat it on declaration order. A rule carried only by such
  signals now defers to one that matched an actual error. A genuine artifact or cache
  failure is unaffected: it trips a terminal signal ("Failed to CreateArtifact",
  "Unable to download artifact", "Cache service responded with 500").
- The classifier no longer reads a command that merely *ran* as the failure. Three
  bugs of the same shape, all found by running `ci explain` over real failing runs
  from public repositories rather than over the fixture zoo:
  - `\btsc\b` matched the x86 **time stamp counter** in the `flags :` line of
    `/proc/cpuinfo`, which perf-sensitive projects dump into their log preamble.
    A real rust-lang/rust build failure came back as `typescript_typecheck` on the
    strength of a CPU feature name. `tsc` now only counts in command position
    (`pnpm tsc`, `> tsc --noEmit`, `npx tsc`, `tsc -p …`) or before a flag/verb.
  - `docker build` / `docker buildx build` / `docker compose` appear in every job
    that builds a container as a setup step, and `cargo test` / `clippy` appear in
    the command line of every Rust CI job, passing or not. A rule matching *only*
    such signals now defers to a rule that matched an actual error, reusing the
    deferral already in place for ambiguous network signals. They still count
    toward confidence when a real error sits beside them, so a genuine docker or
    clippy failure is unchanged.
  - Because scoring is by matched-pattern count, one bogus signal was enough to tie
    the rule that matched the real error and beat it on declaration order alone.
    The zoo missed all of this: its fixtures are clean, and a real log is not — the
    same `error[E0277]` that a fixture classifies correctly was misread in the wild
    because the job also happened to run `docker buildx build`.
  No fixture changes classification or confidence (221 fixtures, top-1 1.0).

### Added

- `patchrail schema ci-classes` now serves a published schema for
  `ci classes --format json`, and the suite validates real output against it.
  It was the one JSON command with no schema, no conformance test and no
  cookbook entry — which is why 0.4.0 could move it from
  `patchrail.ci_classes.v1` to `.v2` in a minor bump without anything going
  red, and why the break reached consumers (this project's own GitHub Action
  among them) silently. Changing the contract now means shipping the schema
  that describes it: `test_schema_conformance.py` compares the `schema_version`
  the CLI emits against the `const` in the schema a user can fetch, so the two
  cannot drift apart again. The schema also encodes the v2 rule itself —
  `unknown` is valid under `fallback` and rejected inside `classes` — so
  putting the sentinel back into the denominator fails validation.
- `docs/json-cookbook.md` documents the `ci classes` payload with a coverage
  recipe (which supported classes has a log corpus never exercised?), and its
  sample output is pinned to the code by `test_readme_claims.py` in both
  directions, like the README's counts.

## 0.4.0 - 2026-07-14

Minor bump rather than a patch: `ci classes --format json` changes its contract.
`schema_version` is now `patchrail.ci_classes.v2` and `unknown` left `classes`
and `count` (see Fixed). Scripts pinned to the v1 shape need a one-line update.

### Fixed

- `patchrail ci classes` no longer counts `unknown` as a supported failure
  class. It reported "41 supported failure classes" and listed `unknown` — with
  a reproduction command — alongside the 40 real ones, contradicting the README,
  the docs and the fixture benchmark, all of which say 40. `unknown` is what
  `ci explain` returns when *no* rule matches, so a coverage script following the
  README (`ci classes --format json`) was dividing by a denominator containing an
  entry it could never cover. The sentinel is still reported, under a new
  `fallback` key, and named in the text and markdown output; it is just out of
  `classes` and `count`. JSON consumers: `schema_version` is now
  `patchrail.ci_classes.v2`.
- README: the redaction bullet advertised 23 secret-redaction patterns; the
  shipped table has 24. The class, fixture and redaction counts the README
  advertises are now derived from the code by `tests/test_readme_claims.py`, so
  they fail the build instead of going stale (the fixture count was already
  pinned by tests, and it was the only one of the three that had stayed correct).

### Changed

- `patchrail ci explain`/`classify` now print a first-use hint when the log
  input is empty or whitespace-only. The common cause is the README one-liner
  `gh run view --log-failed | patchrail ci explain` pointed at a run whose logs
  GitHub already expired (or a run that has not failed), which pipes in nothing.
  The error keeps its exit code `2` and clean stdout; it just adds a line
  telling the user to point it at a *recent* failed run instead of leaving them
  guessing. Non-empty input is completely unaffected.

## 0.3.1 - 2026-07-11

### Added

- `patchrail ci explain`/`classify` now turn an `unknown` result into a
  contribution on-ramp: the text and markdown reports append one line pointing
  the maintainer at the `ci_failure_fixture` issue template
  (`.../issues/new?template=ci_failure_fixture.md`) so an unrecognized log
  becomes a fixture request instead of a dead-end. The classifier's behavior
  and JSON output are unchanged — the pointer is presentation-only and appears
  solely when `failure_class == "unknown"`.
- `patchrail -V` is now a short alias for `--version`. Both print
  `patchrail <version>` and exit `0`, matching the conventional single-letter
  flag most CLIs expose (handy in bug reports and CI logs).
- New `tests/test_schema_conformance.py` validates real CLI output against
  `src/patchrail/schemas/*.v1.schema.json` with `jsonschema` (dev-only
  dependency; the installed package still ships with zero runtime
  dependencies). Previously `_load_schema()` only read schema files as text
  to print them via `patchrail ci schema`; nothing checked that a payload
  builder's output still matched its schema. Covers `ci-result` (every
  fixture in `examples/ci-triage/`, 221 cases), `ci-benchmark`, and
  `ci-fixture-check`.
- `mypy --strict` now runs on `src/patchrail/ci/classify.py` (the classifier
  engine) as a dev dependency and a CI step, alongside `ruff check`/`ruff
  format --check`. The module already passed strict type checking with no
  changes required; this locks that in against regressions. See
  `[tool.mypy]` in `pyproject.toml`.
- New sanitized `github-actions-cmake-gcc-compile-error` fixture covers a real
  CMake + g++ undeclared-identifier link failure for `cpp_build_failure`, which
  previously had a classifier rule but no fixture in the benchmark zoo despite
  the README advertising C++ support. Bringing the benchmark zoo to 220 cases.
- `java_build_failure` now also recognises kotlinc's own diagnostic format
  (`e: File.kt: (line, col): ...`), `Unresolved reference:`, and Kotlin Gradle
  task failures (`:compileDebugKotlin FAILED`). A maintainer pasting only the
  kotlinc excerpt of a Kotlin/Android CI failure — without the Gradle
  `Execution failed for task` / `BUILD FAILED` banner further down the log —
  previously fell through to `unknown` at 0.15 confidence. New sanitized
  `github-actions-kotlin-compile-excerpt-no-banner` fixture guards this,
  bringing the benchmark zoo to 221 cases.

### Fixed

- `patchrail ci explain`/`classify` now normalize the GitHub Actions log line
  prefix before classifying, so the common one-liner
  `gh run view <run-id> --log-failed --repo <owner/repo> | patchrail ci explain`
  classifies identically to a saved raw log. `gh` prefixes every line with
  `<job>\t<step>\t<timestamp>` (and a UTF-8 BOM on the first line), which shifted
  real content off the start of the line and silently defeated the classifier's
  line-anchored (`^`) patterns — dropping confidence (e.g. `go_lint` and
  `node_test_failure` fell from `0.95` to `0.89` on sparse logs). The raw
  Actions log-download form (`<timestamp> <line>`) is normalized too. Regression
  cases in `tests/test_ci_classify_expansion.py` pin gh-prefixed == raw.

### Changed

- Extracted the entire `funded-issues` subcommand group (20 argparse handlers,
  ~50 markdown/text/CSV/JSONL renderers, and the argparse wiring for all 20
  sub-subcommands — 3853 of `cli.py`'s 10368 lines) into a new
  `src/patchrail/cli_funded.py` module, registered from `_build_parser()` via
  `cli_funded.register(subparsers)`. No behavior change: same commands, same
  flags, same output. `cli.py` drops from 10368 to ~5650 lines. If you import
  `patchrail.cli._normalize_recheck_observation` or similar funded-issues
  internals directly (rather than going through the public CLI), import from
  `patchrail.cli_funded` instead.

## 0.3.0 - 2026-07-09

### Fixed

- Deterministic Go test failures are no longer misread as
  `network_transient_failure` when their logs contain incidental
  network-shaped noise (`dial tcp`, `connection refused`, `context deadline
  exceeded`, `i/o timeout`). The classifier now defers a broad transient-network
  match built *entirely* from these ambiguous signals to the concrete failure
  when one also matched, so a real bug isn't mislabeled "just retry". Genuine
  outages still classify as transient because they trip a terminal signal (DNS
  resolution, rate limit, gateway error, TLS handshake, or a git remote hang-up)
  outside the ambiguous set. `go_test_failure` also now recognises the canonical
  `--- FAIL:` marker. New `go-integration-test-network-noise` fixture guards this,
  bringing the benchmark zoo to 208 cases.

### Added

- `patchrail --version` now prints the installed version (e.g. `patchrail 0.3.0`)
  and exits, so a maintainer can confirm which release they are running without
  invoking a subcommand.
- `java_build_failure` now also recognises **sbt** (Scala on the JVM). sbt prints
  none of the Maven/Gradle banners the rule keyed on, so a genuine
  `(project / Test / compileIncremental) Compilation failed` — or an
  `sbt.TestsFailedException` — previously fell through to `unknown`. New signals
  cover the sbt session banner, incremental-compile failure, Scala
  `not found: value`/`not found: type` errors, and the sbt test-failure
  exception; the reproduction command now suggests `sbt test`. New sanitized
  `github-actions-sbt-scala-compile` fixture (modelled on a real
  `scalatest/scalatest` GitHub Actions run) guards this, bringing the benchmark
  zoo to 209 cases.
- New sanitized `ruby-rspec-parallel-failure` fixture captures a real
  `rubocop/rubocop` RSpec failure tail (parallel/turbo_tests summary with
  `pending` before `failures`), bringing the benchmark zoo to 207 cases.
- New `xcode_build_failure` class classifies Apple-platform build and test
  failures from `xcodebuild`, `swift build`/`swift test`, and Swift Package
  Manager — Swift compile errors, missing modules (`error: no such module`),
  unresolved package dependencies, and XCTest failures (`** BUILD FAILED **`,
  `** TEST FAILED **`, `The following build commands failed:`). Backed by three
  sanitized fixtures in `examples/ci-triage/`, bringing the benchmark zoo to 169
  cases and the classifier to 40 failure classes.
- New `docs_build_failure` class classifies documentation-site build failures
  from Sphinx (`sphinx-build -W` warnings-as-errors, missing toctree entries),
  MkDocs (`mkdocs build --strict` broken links), and Docusaurus (`docusaurus
  build` broken links). Backed by three sanitized fixtures in
  `examples/ci-triage/`, bringing the benchmark zoo to 166 cases.
- `patchrail ci classes` lists every supported failure class with its likely
  subsystem and reproduction command (plus the `unknown` fallback), in stable
  order. Supports `--format text|json|markdown` and `--out`, so the set of
  classes the classifier can diagnose is discoverable from the CLI instead of
  only in the source. Closes #150.

### Fixed

- Real RSpec failures now classify as `ruby_bundle_failure` instead of
  `unknown`. RSpec prints its rerun list as `rspec ./path/to/thing_spec.rb[…]`
  and its summary as `N examples, [K pending, ]M failures` (rspec, parallel and
  turbo_tests) — neither of which the old `rspec .*failures?` pattern matched,
  so a pasted spec-failure tail without bundler setup lines fell through to
  `unknown`. Two shape-matching patterns were added to the rule. Surfaced by
  dogfooding a real `rubocop/rubocop` CI run.
- Python CI logs no longer misclassify as `python_dependency_resolution` just
  because they run `python -m pip install`. That bare command line was a
  detection pattern, but it appears in almost every Python CI job regardless of
  what actually failed, so any failing Python job with no stronger signal was
  reported as a dependency-resolution conflict with the misleading "pin or relax
  the conflicting dependency range" advice. Dogfooded against a real
  `pandas-dev/pandas` 32-bit CI run whose `pip install` failed at
  `metadata-generation-failed` (a package build error, `Rust not found`) — it was
  reported as `python_dependency_resolution` (0.53). The boilerplate pattern is
  dropped, so a build/metadata failure with no genuine resolution signal now
  stays honest (`unknown`) instead. To keep recall on real conflicts, two
  genuine pip signals were added: pip's actual Requires-Python wording
  (`requires a different Python:`) and its no-distribution `(from versions: …)`
  line; the three synthetic no-matching-distribution fixtures were updated to
  include the real `(from versions: …)` output pip prints. Benchmark stays at
  206/206 top-1 with all confidence floors met; the bundled dependency-failure
  demo now reports 0.89 (three genuine resolution signals) instead of 0.95.
  Regression covered in `tests/`.
- `patchrail ci explain`/`classify` no longer hangs on large CI logs. The
  `github_actions_workflow` rule paired two unanchored lookaheads
  (`(?=[\s\S]*.github/workflows/…)(?=[\s\S]*Invalid workflow file…)`); under
  `re.search` that compound is retried at every start position, so a log that
  mentions `.github/workflows/*.yml` (every `actions/checkout` step does) but not
  a workflow-error phrase drove the matcher into O(n²) backtracking and pegged a
  core at 100% for minutes. Dogfooded against a real `cli/cli` Go CI run
  (~200 KB) that never returned. The lookahead is now anchored with `\A` so it is
  evaluated once, in linear time; the "workflow path AND error phrase present"
  signal is unchanged. Regression covered in `tests/`.
- Rust CI failures no longer misclassify as `node_dependency_install`,
  `dotnet_build_failure`, or `java_build_failure` because of generic boilerplate.
  The `Swatinem/rust-cache` action prints `Lockfiles considered:` (which matched
  the old bare `lockfile` node signal) and cargo prints `build failed, waiting
  for other jobs to finish` (which matched the case-insensitive `Build FAILED` /
  `BUILD FAILED` banners). The node lockfile signal now requires a whole-word
  `lockfile`, and the .NET/Gradle banners are matched case-sensitively so they
  fire only on the tool's actual `Build FAILED` / `BUILD FAILED` output. A real
  `tokio-rs/tokio` rustdoc failure (`error[E0433]`) now classifies as
  `rust_test_failure`. Regression covered in `tests/`.
- Sharper reproduce commands for three failure classes surfaced by `patchrail ci
  classes` / `ci explain`. `node_script_missing` no longer suggests `npm run
  build` (which just re-triggers the "missing script" error) and instead runs
  `npm run` to list the scripts `package.json` actually defines, so you can
  compare against the one your workflow calls. `security_scan_failure` names the
  concrete scanners to rerun locally (`npm audit`, `pip-audit`, `cargo audit`,
  `trivy fs .`, `bandit -r .`, `semgrep --config auto`) instead of the generic
  "rerun the failing security scan locally". `github_actions_workflow` points at
  `actionlint .github/workflows/`, which validates workflow syntax and action
  refs locally, rather than only printing the YAML back with `gh workflow view`.
- Real GitHub Actions logs no longer misclassify as `git_checkout_failure` when
  checkout actually succeeded. The rule dropped three boilerplate signals that
  appear in almost every Actions log regardless of outcome — the `actions/checkout`
  setup step, the `git submodule foreach` post-job cleanup line, and a bare
  `git-lfs` mention — keeping only genuine checkout/clone/submodule/LFS *failure*
  markers (`fatal: ...`, `Failed to fetch submodule`, `smudge filter lfs failed`,
  `error downloading object`, …). Dogfooded against a real `pallets/flask` CI run
  whose pytest jobs failed on a conftest `SyntaxError` but were reported as a git
  checkout problem.
- `python_test_failure` now also recognizes pytest collection failures
  (`ImportError while loading conftest ...`, `N errors during collection`), so a
  broken `conftest.py` or import-time error surfaces as a test failure with the
  `python -m pytest -q` reproduce line instead of falling through to a weaker or
  wrong class.
- `patchrail ci explain` and `ci classify` now fail clearly on empty or
  whitespace-only input (from `--log` or stdin) instead of silently reporting
  `failure_class: unknown` with confidence `0.15` and exit code `0`. They print
  `log input is empty` to stderr, exit with code `2`, and write nothing to
  `--out`, so a bad shell redirect is no longer mistaken for an unclassifiable
  log. Closes #151.
- Added `node_script_missing` to the published `ci-result` schema enum; the
  classifier could already emit it, so a valid classification previously failed
  schema validation for downstream consumers. A new test guards that every rule
  class is declared in the schema enum.

## 0.2.0 - 2026-07-07

### Removed

- Removed the commercial `Guide:` link that `ci explain` appended to text and
  Markdown reports, and the matching guide URL outputs from the GitHub Action.
  Reports now end after the classification; per-class remediation write-ups
  live in-repo under `docs/fix/`.
- Removed commercial product links and campaign-tagged URLs from the README,
  docs, and the PyPI project URL list.
- Removed the distribution and web-metrics tooling (`ci share-links` and the
  web metrics commands and store). PatchRail no longer ships link-tracking or
  distribution helpers.

### Changed

- `funded-issues` is now explicitly labeled experimental. Discovery commands
  default to safe-only filtering, and risky entries require an explicit
  `--include-risky` flag.
- Rewrote the README around the open-source CI triage workflow: quickstart
  with real classifier output, honest feature table, local-first safety
  section, and the fixture contribution path.

### Added

- Added `node_script_missing` CI classification so npm/pnpm/yarn jobs that
  call a missing package script are separated from dependency-install failures
  and routed to a workflow/script repair path.
- Added a permanent source-level blocklist to the funded-issues tracker:
  owners manually verified as fake-bounty sources are dropped at the
  `merge_into_store` choke point (counted as `blocked` in the merge summary)
  and `purge_blocklisted_entries` removes any legacy entries; `track` runs the
  purge on every merge so existing stores self-heal.
- Added `funded-issues import-algora-board`, an offline parser for a locally
  saved Algora organization bounty-board page. It extracts the funder-stated
  USD amount, GitHub issue reference, posting age, and declared claim count
  per bounty, and can merge the scored records into a tracker store. No
  network access is performed.
- Added read-only competition and payout-vs-effort scoring signals plus the
  `funded-issues competition` and `funded-issues payout-effort` batch
  commands, all derived from public metadata observations with no claims,
  comments, or maintainer contact.
- Added an offline owner-level `source_noise` heuristic and
  `funded-issues apply-recheck`, a local-file-only command that transitions
  tracker entries to closed / stale / active from recheck observations.
- Added .NET/NuGet/C# and xUnit fixture coverage for `dotnet restore`,
  `dotnet build`, and `dotnet test` failure modes, growing the public CI
  fixture zoo to 153 cases.

## 0.1.1 - 2026-06-12

- `ci explain` now ends text and Markdown reports with a `Guide:` link to the
  matching getpatchrail.com `/fix` remediation page; unknown or unpublished
  failure classes fall back to the `/fix` index without a network call.
- Added `funded-issues fresh`, a local read-only radar over the tracker store
  that surfaces recently posted or recently labeled funded issues for fast
  solver-side triage.
- Added `pre_commit_hook_failure` CI classification so pre-commit hook output is
  recognized directly while the CLI still avoids linking to a missing `/fix`
  page until that guide exists.

## 0.1.0 - 2026-06-02

- Initial public CI Janitor snapshot.
- Added `patchrail ci explain` and `patchrail ci classify`.
- Added local Markdown, JSON, and text reports.
- Added Apache-2.0 license and safety/ethics documentation.
- Added fixture-backed tests, local benchmark command, and GitHub Actions CI.
- Expanded the initial CI fixture zoo to 101 sanitized synthetic examples across
  Python, Node, TypeScript, Go, Rust, and GitHub Actions failure modes.
- Added a read-only GitHub Actions triage artifact workflow.
- Added the experimental local Agent Control Plane queue with SQLite-backed
  work items, approval states, audit export, CI result import, and proposal
  records.
- Added the experimental read-only `funded-issues` CLI over local metadata,
  with safe-only filtering and explicit anti-abuse blocked actions.
- Added permission-only adopter reporting and a public metrics tracker for
  pilot outcomes, adoption signals, and open-source program evidence gaps.
- Added release-prep evidence docs, package smoke checks, and manual publish
  gates. Release tags, PyPI publishing, GitHub Releases, and public
  announcements remain maintainer actions.
