# Release Process

PatchRail uses semantic versioning while the public API stabilizes.

This process is a release-prep workflow. It collects evidence for a maintainer to
review before tagging or publishing. It does not publish to PyPI, create tags, or
announce a release.

The current v0.1.0 prep artifact is tracked in
[release-v0.1.0-evidence.md](release-v0.1.0-evidence.md). The current
v0.2.0 release-candidate evidence is tracked in
[release-v0.2.0-evidence.md](release-v0.2.0-evidence.md). Agent Control Plane
evidence is tracked in [release-v0.3.0-evidence.md](release-v0.3.0-evidence.md).
Funded issue read-only evidence is tracked in
[release-v0.4.0-evidence.md](release-v0.4.0-evidence.md).

## v0.1.0 Release-Prep Evidence Checklist

Use this checklist before preparing the first public package release.

### 1. Repository State

- [ ] Working tree is clean before release-prep starts:

```bash
git status --short
```

- [ ] Version in `pyproject.toml` matches the intended release version.
- [ ] `README.md`, `docs/quickstart.md`, and this release process describe the
  same install and smoke-test commands.
- [ ] `CHANGELOG.md` or release notes draft records user-visible changes.

### 2. Local Test Evidence

- [ ] Unit and CLI tests pass:

```bash
uv run --extra dev pytest -q
```

- [ ] Lint and format checks pass:

```bash
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
```

- [ ] CI fixture benchmark passes and records total fixtures:

```bash
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
```

- [ ] Safety doctor passes locally:

```bash
uv run --extra dev patchrail doctor --format json
```

- [ ] Quickstart fixture still renders a maintainer-readable report:

```bash
uv run --extra dev patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text
```

### 3. Package Artifact Evidence

The reusable local release-readiness command runs build, metadata validation,
fresh-wheel install, `patchrail doctor`, and a fixture smoke test without
publishing, tagging, announcing, or contacting third parties:

```bash
uv run --extra dev python scripts/release_readiness.py --clean-dist
```

To save a machine-readable evidence artifact for maintainer review:

```bash
uv run --extra dev python scripts/release_readiness.py --clean-dist --output release-readiness.json
```

- [ ] Build the source distribution and wheel:

```bash
uv run --extra dev python -m build
```

- [ ] Validate distribution metadata:

```bash
uv run --extra dev twine check dist/*
```

- [ ] Install the wheel into a fresh virtual environment and run a smoke test:

```bash
python3 -m venv .pkg-smoke
. .pkg-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install dist/*.whl
patchrail doctor --format json
patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text
deactivate
```

- [ ] Or run `scripts/release_readiness.py --clean-dist` and attach its JSON
  output to the release-prep evidence.
- [ ] Remove local transient build artifacts after capturing evidence, using the
  maintainer's normal cleanup tool.

### 4. Safety And Privacy Evidence

- [ ] No raw private logs, credentials, tokens, personal contact data, or local
  machine paths were added.
- [ ] Fixtures are sanitized and synthetic or intentionally redacted.
- [ ] No workflow introduces third-party repository write automation.
- [ ] No command claims funded issues, submits pull requests, posts comments, or
  sends outreach.
- [ ] Any new network access is documented, opt-in, and off by default.
- [ ] Safety docs still link from `README.md`: `ETHICS.md`, `SECURITY.md`, and
  `docs/threat-model.md`.

Suggested review commands:

```bash
git diff --check
git status --short
git grep -n -E 'BEGIN (RSA|OPENSSH|PRIVATE) KEY|ghp_|github_pat_|sk-[A-Za-z0-9]|AKIA[0-9A-Z]{16}|xox[baprs]-|Bearer [A-Za-z0-9._-]+' -- . ':!docs/release-process.md' || true
git grep -n -E '/Users/|/Volumes/|C:\\\\Users\\\\|@[^[:space:]]+\\.[^[:space:]]+' -- . ':!docs/release-process.md' || true
```

If a command reports a match, inspect it manually. Test fixtures and redaction
patterns may intentionally contain fake tokens or placeholder emails.

### 5. Public CI Evidence

- [ ] Push release-prep changes to the repo branch.
- [ ] Confirm the GitHub Actions `CI` workflow passed.
- [ ] Confirm the package smoke job passed.
- [ ] Record the CI run URL in `docs/openai-codex-for-oss-evidence.md`.

### 6. Manual Publish Gate

These actions are manual maintainer gates and are not part of automated
release-prep:

- [ ] Create or push a release tag.
- [ ] Publish to PyPI.
- [ ] Create a GitHub release.
- [ ] Announce the release publicly.
- [ ] Apply to external programs with placeholder metrics.

Record completed prep evidence in `docs/release-v0.1.0-evidence.md` before any
manual publish step.

## v0.2.0 Release-Candidate Evidence Checklist

Use [docs/release-v0.2.0-evidence.md](release-v0.2.0-evidence.md) to track the
CI Janitor v0.2 milestone before any version bump, tag, PyPI publish, public
announcement, or external application.

- [ ] `patchrail ci fixture-check examples/ci-triage --format json` reports
  `135 / 135` fixtures passing.
- [ ] `patchrail ci benchmark examples/ci-triage --format json` reports
  `135` total and `0` failed.
- [ ] GitHub Actions triage remains read-only with `contents: read` and
  `actions: read`.
- [ ] The example `patchrail-ci-triage` artifact includes Markdown, JSON,
  fixture benchmark, and doctor outputs.
- [ ] The pilot guide stays consent-only and does not require repository write
  access.
- [ ] `docs/metrics.md` does not promote placeholder adoption, PyPI, or Codex
  evidence.
- [ ] `ADOPTERS.md` lists only permissioned adopters.
- [ ] Manual gates are clear for version bump, tag, PyPI publish, announcements,
  and external program applications.

## v0.3.0 Release-Candidate Evidence Checklist

Use [docs/release-v0.3.0-evidence.md](release-v0.3.0-evidence.md) to track the
Agent Control Plane milestone before any version bump, tag, PyPI publish, public
announcement, or external application.

- [ ] `examples/local-agent-queue/run_demo.py` produces the expected stable
  summary.
- [ ] Queue item import from CI result keeps `write_actions_allowed=false`.
- [ ] Queue audit export records local decisions as JSONL.
- [ ] Proposal approval/rejection records human decisions only and does not
  execute patches.
- [ ] `patchrail serve --host 127.0.0.1 --port 8765` remains local-only.
- [ ] Queue schemas are emitted by `patchrail schema` and bundled in the wheel.
- [ ] Manual gates are clear for version bump, tag, PyPI publish, announcements,
  and external program applications.

## v0.4.0 Release-Candidate Evidence Checklist

Use [docs/release-v0.4.0-evidence.md](release-v0.4.0-evidence.md) to track the
Funded Issue Scout read-only milestone before any version bump, tag, PyPI
publish, public announcement, or external application.

- [ ] `examples/funded-issues-readonly/run_demo.py` produces the expected stable
  summary.
- [ ] `patchrail funded-issues list` filters risky records by default.
- [ ] `patchrail funded-issues explain` reports blocked actions and contribution
  etiquette.
- [ ] `patchrail funded-issues import` reads local provider exports only.
- [ ] No funded issue command fetches provider APIs, scrapes websites, claims
  rewards, posts comments, opens pull requests, or contacts maintainers.
- [ ] Manual gates are clear for version bump, tag, PyPI publish, announcements,
  and external program applications.

## Minimum Local Checks

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev patchrail ci benchmark examples/ci-triage --format json
uv run --extra dev python scripts/release_readiness.py --clean-dist
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
python3 -m venv .pkg-smoke
. .pkg-smoke/bin/activate
python -m pip install --upgrade pip
python -m pip install dist/*.whl
patchrail doctor --format json
patchrail ci explain --log examples/ci-triage/dependency-failure.log --format text
deactivate
```

## Release-Prep Prompt

Use this prompt when preparing a release-prep PR:

```text
Prepare PatchRail release evidence for vX.Y.Z. Check the changelog, version,
README quickstart, docs links, CI fixture benchmark, package build, wheel smoke
test, and safety/privacy checklist. Do not publish, tag, announce, or submit any
external application. Return a checklist with commands run, results, artifact
names, CI URLs, and remaining manual gates.
```

## After Release

- Verify install from the released artifact.
- Create release notes from `CHANGELOG.md`.
- Link any classifier, redaction or docs changes.
- Update docs if the quickstart changed.
