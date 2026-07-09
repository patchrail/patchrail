# Changelog

## Unreleased

### Added

- `patchrail -V` is now a short alias for `--version`. Both print
  `patchrail <version>` and exit `0`, matching the conventional single-letter
  flag most CLIs expose (handy in bug reports and CI logs).

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
