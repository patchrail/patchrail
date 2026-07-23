from __future__ import annotations

import re
from collections import Counter
from typing import Any


REDACTION_PATTERNS: list[tuple[str, str, str]] = [
    ("github_token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b", "<github-token>"),
    ("github_fine_grained_token", r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "<github-token>"),
    ("gitlab_token", r"\bglpat-[A-Za-z0-9_-]{20,}\b", "<gitlab-token>"),
    ("api_key", r"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b", "<api-key>"),
    ("npm_token", r"\bnpm_[A-Za-z0-9]{20,}\b", "<npm-token>"),
    ("pypi_token", r"\bpypi-[A-Za-z0-9_.-]{20,}\b", "<pypi-token>"),
    ("aws_access_key", r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "<aws-access-key>"),
    ("stripe_secret_key", r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b", "<stripe-secret-key>"),
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b", "<slack-token>"),
    ("google_api_key", r"\bAIza[0-9A-Za-z_-]{35}\b", "<google-api-key>"),
    ("google_oauth_token", r"\bya29\.[A-Za-z0-9_-]{20,}", "<google-oauth-token>"),
    ("huggingface_token", r"\bhf_[A-Za-z0-9]{20,}\b", "<huggingface-token>"),
    (
        "private_key_block",
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
        r"[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----",
        "<private-key>",
    ),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b", "<jwt>"),
    ("bearer_token", r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", "Bearer <token>"),
    ("sendgrid_api_key", r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b", "<sendgrid-api-key>"),
    ("telegram_bot_token", r"\b\d{8,10}:AA[A-Za-z0-9_-]{30,}\b", "<telegram-bot-token>"),
    (
        "url_credentials",
        r"\b([a-z][a-z0-9+.-]*://)[^\s:/@]+:[^\s/@]+@",
        r"\1<credentials>@",
    ),
    (
        "env_secret_assignment",
        r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|KEY))=([^\s'\"]+)",
        r"\1=<redacted>",
    ),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<email>"),
    (
        # Must run before unix_home_path: GitHub-hosted runner workspace
        # paths follow /home/runner/work/<org>/<repo>/... . "runner" itself
        # isn't sensitive, but the org/repo segments after it can leak a
        # private repository's name; unix_home_path alone only scrubs
        # "runner" and leaves those segments exposed.
        "linux_ci_runner_home_path",
        r"/home/runner/work/[^/\s'\":]+/[^/\s'\":]+",
        "/home/runner/work/<org>/<repo>",
    ),
    ("unix_home_path", r"/home/[^/\s'\":]+", "/home/<user>"),
    ("mac_home_path", r"/Users/[^/\s'\":]+", "/Users/<user>"),
    (
        "windows_home_path",
        r"\b([A-Z]):[\\/]+Users[\\/]+[^\\/\s'\":]+",
        r"\1:/Users/<user>",
    ),
]


RULES: list[dict[str, Any]] = [
    {
        "failure_class": "runner_resource_exhaustion",
        "likely_subsystem": "CI runner memory or disk capacity",
        "patterns": [
            r"OOMKilled",
            r"Out of memory",
            r"Cannot allocate memory",
            r"JavaScript heap out of memory",
            r"runtime: out of memory",
            r"signal: killed",
            r"Process completed with exit code 137",
            r"\bexit code 137\b",
            r"No space left on device",
            r"\bENOSPC\b",
            r"disk quota exceeded",
            r"received a shutdown signal",
            r"exceeded memory limit",
        ],
        "reproduction_command": (
            "rerun the failing job while watching runner memory and disk "
            "(e.g. /usr/bin/time -v and df -h)"
        ),
        "minimal_repair_strategy": (
            "Confirm the runner hit a memory or disk limit rather than a code defect, then lower "
            "peak memory use, free disk space, or raise the runner resource class before rerunning."
        ),
    },
    {
        "failure_class": "network_transient_failure",
        "likely_subsystem": "Network connectivity or upstream service availability",
        "patterns": [
            r"Could not resolve host",
            r"Temporary failure in name resolution",
            r"Name or service not known",
            r"getaddrinfo ENOTFOUND",
            r"getaddrinfo EAI_AGAIN",
            r"\bno such host\b",
            r"Connection timed out",
            r"\bETIMEDOUT\b",
            r"\bECONNREFUSED\b",
            r"Connection refused",
            r"\bECONNRESET\b",
            r"Connection reset by peer",
            r"Network is unreachable",
            r"\bENETUNREACH\b",
            r"TLS handshake timeout",
            r"\bESOCKETTIMEDOUT\b",
            r"\bi/o timeout\b",
            r"context deadline exceeded",
            r"\bdial tcp\b",
            r"429 Too Many Requests",
            r"API rate limit exceeded",
            r"503 Service Unavailable",
            r"502 Bad Gateway",
            r"504 Gateway Time-?out",
            # HTTP clients that print the reason phrase with the code trailing in
            # parentheses -- `Error: Gateway Timeout (504)` from the coveralls
            # reporter (expressjs/express run 29218121905) -- never matched the
            # status-line ordering above, so a textbook upstream 504 fell through
            # to `unknown`. The reverse-order form is just as terminal.
            r"Gateway Time-?out \(504\)",
            r"Bad Gateway \(502\)",
            r"Service Unavailable \(503\)",
            r"The remote end hung up unexpectedly",
            r"RPC failed",
            r"fetch-pack: unexpected disconnect",
            r"early EOF",
            r"fatal: unable to access",
            r"Failed to connect to .* port",
        ],
        "reproduction_command": (
            "re-run the failing job; if it fails again, probe the endpoint "
            "(e.g. curl -sSf <url> or nslookup <host>) from the runner"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a transient network or upstream-service outage rather than a "
            "code defect, then retry the job; if it persists, pin a reachable mirror, add a "
            "bounded retry, or wait for the upstream service to recover before changing code."
        ),
    },
    {
        "failure_class": "ci_job_timeout",
        "likely_subsystem": "CI job execution time limit or cancellation",
        "patterns": [
            r"has exceeded the maximum execution time of \d+ minutes",
            r"The job running on runner .+ has exceeded",
            r"##\[error\]The operation was canceled",
            r"The operation was canceled",
            r"ERROR: Job failed: execution took longer than",
            r"execution took longer than \S+ seconds",
            r"Too long with no output",
            r"\(exceeded \d+m\d*s?\)",
            r"exceeded the maximum time limit for jobs",
            r"ran longer than the maximum time of \d+ minutes",
            # Every pattern above is a timeout that HAPPENED. `timeout-minutes: 180` is a limit a
            # job DECLARES -- Actions echoes it from the workflow when it prints the step config,
            # on the happy path too. It is the knob you raise afterwards (docs/fix/ci-job-timeout.md),
            # never evidence that anything ran long.
            #
            # envoyproxy/envoy's coverage run 29363920524 failed a coverage gate:
            #
            #     FAILED: Directories not meeting coverage thresholds:
            #
            # Its one and only witness for a TIMEOUT, at 0.53, was the config line the runner
            # echoed 16 minutes before the job died -- so we told a maintainer whose coverage had
            # slipped to go raise a limit their job never came near. A mention in prose still
            # counts; the `key:` form does not.
            r"\btimeout-minutes\b(?!\s*:)",
        ],
        "reproduction_command": (
            "re-run the job and compare step durations against the configured job/step "
            "time limit (e.g. timeout-minutes)"
        ),
        "minimal_repair_strategy": (
            "Confirm the job hit a time limit or was canceled (manual or matrix fail-fast) "
            "rather than a code defect, then cache dependencies, split or parallelize the "
            "slowest steps, or raise the limit deliberately before rerunning."
        ),
    },
    {
        "failure_class": "python_dependency_resolution",
        "likely_subsystem": "Python dependency installation",
        "patterns": [
            r"Could not find a version that satisfies the requirement",
            r"No matching distribution found",
            r"\(from versions:",
            r"Cannot install .*because these package versions have conflicting dependencies",
            r"ResolutionImpossible",
            r"pip._vendor.resolvelib",
            r"The conflict is caused by:",
            r"Requires-Python",
            r"requires a different python version",
            r"requires a different Python:",
            r"version solving failed",
            r"SolverProblemError",
            r"Could not find a version that matches",
            r"incompatible versions in the resolved dependencies",
            r"uv pip compile",
            r"No solution found",
            r"requirements are unsatisfiable",
            r"pip-compile",
            r"yanked",
        ],
        "reproduction_command": "python -m pip install -r requirements.txt",
        "minimal_repair_strategy": (
            "Pin or relax the conflicting dependency range, then rerun the same install "
            "command and the affected tests."
        ),
    },
    {
        "failure_class": "code_coverage_threshold",
        "likely_subsystem": "Test coverage gate",
        "patterns": [
            r"Required test coverage of \d",
            r"Coverage failure: total of",
            r"\bfail[_-]under\b",
            r"coverage threshold",
            r"does not meet (?:the )?(?:global )?threshold",
            r"is below the (?:expected )?minimum coverage",
            r"below the (?:minimum )?coverage threshold",
            r"Coverage for \w+ \(\d+(?:\.\d+)?%\) does not meet",
            r"SimpleCov failed",
            r"project coverage.*(?:target|failed)",
            r"total coverage.*(?:decreased|below)",
            r"\bTotal coverage:",
            r"coverage .*(?:is )?less than",
        ],
        "reproduction_command": (
            "re-run the suite with coverage locally "
            "(e.g. pytest --cov, npm test -- --coverage, or go test -cover)"
        ),
        "minimal_repair_strategy": (
            "Confirm the tests passed but coverage fell under the configured threshold, then add "
            "focused tests for the uncovered lines named in the coverage summary; only lower the "
            "threshold deliberately when the uncovered code is intentionally excluded."
        ),
    },
    {
        "failure_class": "python_type_check",
        "likely_subsystem": "Python static type checking",
        "patterns": [
            r"\bmypy\b",
            r"\bpyright\b",
            r"Found \d+ errors? in \d+ files?",
            r"error: Incompatible (?:types|return value type|default for argument)",
            r"has incompatible type",
            r"Argument \d+ to .* has incompatible type",
            r"error: .*\[(?:assignment|arg-type|return-value|attr-defined|call-arg|union-attr"
            r"|index|operator|var-annotated|name-defined|misc|override|valid-type|no-any-return"
            r"|type-var|dict-item|list-item|import-untyped|func-returns-value)\]",
            r"error: Need type annotation for",
            r"error: Function is missing a (?:return )?type annotation",
            r"error: Missing (?:return statement|type parameters)",
            r"report(?:GeneralTypeIssues|ArgumentType|AttributeAccessIssue|ReturnType"
            r"|OptionalMemberAccess|CallIssue|AssignmentType|IndexIssue|Redeclaration"
            r"|UndefinedVariable)",
            r"\d+ errors?, \d+ warnings?, \d+ informations?",
            r"is not assignable to (?:parameter|return type|declared type)",
        ],
        "reproduction_command": "mypy . || pyright",
        "minimal_repair_strategy": (
            "Confirm the static type checker (mypy or pyright) failed rather than the tests, then "
            "fix the narrowest reported type mismatch, missing annotation, or import drift and "
            "rerun the same type checker before broad CI."
        ),
    },
    {
        "failure_class": "python_lint",
        "likely_subsystem": "Python linting or formatting",
        # Match evidence of a lint/format *failure*, never a bare tool mention.
        # A repo that *is* a linter (e.g. astral-sh/ruff) or a type checker that
        # models these tools prints "ruff"/"pylint"/"isort" thousands of times in
        # passing output; the bare tool names used to accumulate enough signals to
        # hijack real Rust/test failures. Require an invocation or diagnostic instead.
        "patterns": [
            r"ruff check",
            r"flake8 \S",
            r"pylint \S",
            r"imported but unused",
            r"\bF401\b",
            r"\bE501\b",
            r"\.py:\d+:\d+: [EWFCBN]\d{2,4}\b",
            r"line too long \(\d+ > \d+",
            r"Your code has been rated at",
            r"\((?:unused-import|line-too-long|missing-(?:module|function|class)-docstring"
            r"|undefined-variable|unused-variable)\)",
            r"\d+ files? would be reformatted",
            r"would reformat \S+\.py",
            r"Imports are incorrectly sorted",
        ],
        "reproduction_command": "ruff check . || flake8 .",
        "minimal_repair_strategy": (
            "Confirm a linter or formatter (ruff, flake8, pylint, black, or isort) failed rather "
            "than the tests, then apply the reported fix only in the touched files and rerun the "
            "same linter."
        ),
    },
    {
        "failure_class": "pre_commit_hook_failure",
        "likely_subsystem": "pre-commit hook framework",
        "patterns": [
            r"\bpre-commit\b",
            r"files were modified by this hook",
            r"- hook id:",
            r"\.pre-commit-config\.yaml",
            r"InvalidManifestError",
            r"InvalidConfigError",
            r"\[INFO\] Initializing environment for",
            r"pre-commit run --all-files",
            r"\bFailed\b\s*\n\s*- hook id",
        ],
        "reproduction_command": "pre-commit run --all-files",
        "minimal_repair_strategy": (
            "Confirm a pre-commit hook failed (commonly a formatter that rewrote files, or a hook "
            "config or pinned-revision error), run pre-commit run --all-files locally, commit the "
            "resulting changes or fix the reported hook, and rerun the same hook before broad CI."
        ),
    },
    {
        "failure_class": "python_test_failure",
        "likely_subsystem": "Python tests",
        "patterns": [
            # A bare `pytest` is a defensible last-resort invocation (see below), but only
            # when the word is the tool being RUN. `\b` also treats `-`, `<`, `>`, `=`, `~`
            # as boundaries, so it read `pytest` off every dependency SPEC a Python job
            # installs -- the plugin package `pytest-cov`/`pytest-xdist` and the version
            # constraint `pytest<9.1`/`pytest>=8.3.4`. pandas-dev/pandas's Doc Build job
            # (issue #347) never runs pytest at all; it installs it via micromamba, and its
            # env dump (`create-args: pytest<9.1`, `- pytest-cov`, `+ pytest 9.0.3 ...`) was
            # the rule's entire case -- `python_test_failure` at 0.53, sending the maintainer
            # to debug tests that never ran. A run that actually invokes pytest writes
            # `pytest`, `pytest -q`, `python -m pytest`; none of those is followed by a
            # version operator or a `-plugin` suffix, so the guard costs a real invocation
            # nothing and drops the package-spec mentions the install phase throws off.
            r"\bpytest\b(?![-<>=~])",
            r"FAILED .*::",
            # `AssertionError` is Python's, but it is also the class Node's built-in `assert`
            # throws -- and Node stamps its own with an error code Python never emits:
            # `AssertionError [ERR_ASSERTION]: ...` (nodejs/node run 29943544407, the
            # `parallel/test-repl-user-error-handler` test under `node:internal/test_runner`).
            # That one line was the rule's entire case -- `python_test_failure` at 0.53 on a
            # log with zero pytest and zero Python, naming the wrong ecosystem with confidence.
            # A real Python `AssertionError` is bare or `AssertionError:`, never `[ERR_ASSERTION]`,
            # so the guard costs a genuine pytest failure nothing and drops Node's assert dumps.
            r"AssertionError(?!\s*\[ERR_ASSERTION\])",
            r"ModuleNotFoundError",
            r"ImportError while loading conftest",
            r"\berrors? during collection\b",
            # pytest's own verdict. Without these the rule could only match a *named*
            # failing test (`FAILED x::y`) or a bare `pytest` invocation, so a run that
            # reports the count and not the names -- `-q`, `-p no:randomly`, a plugin
            # that rewrites the summary -- was carried by its invocation alone and lost
            # to whatever tool the job had merely *mentioned*. encode/httpx
            # (`1 failed, 1416 passed`) scored `python_lint`. The `=` run and the `in
            # 12.3s` tail are pytest's summary line, not jest's (`Tests: 1 failed, 5
            # passed` on its own line, timing separately), so node stays out of it.
            r"^=+ .*\b\d+ failed\b",
            r"\b\d+ failed\b.*\bin \d+(?:\.\d+)?s\b",
            r"short test summary info",
            # A collection error names the file, never a test: `ERROR tests/x.py - ValueError`.
            r"^ERROR \S+\.py\b",
        ],
        "reproduction_command": "python -m pytest -q",
        "minimal_repair_strategy": (
            "Reproduce the failing test, patch the narrow behavior drift, and rerun the "
            "focused pytest node before broad test runs."
        ),
    },
    {
        "failure_class": "node_script_missing",
        "likely_subsystem": "Node package scripts",
        "patterns": [
            r"Missing script: [\"']?(?:build|test|lint|typecheck|ci)[\"']?",
            r"npm ERR! missing script",
            r"npm error Missing script",
            r"Command [\"'](?:build|test|lint|typecheck|ci)[\"'] not found",
            r"ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL.*Command .* not found",
            r"Usage Error: Couldn't find a script named",
            r"error Command [\"'](?:build|test|lint|typecheck|ci)[\"'] not found",
        ],
        "reproduction_command": (
            "npm run  # lists the scripts package.json actually defines; compare against the "
            "one your workflow calls (also: pnpm run, yarn run)"
        ),
        "minimal_repair_strategy": (
            "Confirm the CI job is calling a package script that does not exist in the target "
            "workspace, then add the narrow missing script or point the workflow at the existing "
            "package command before rerunning that job."
        ),
    },
    {
        "failure_class": "node_dependency_install",
        "likely_subsystem": "Node package installation",
        "patterns": [
            r"npm ERR!",
            r"npm error\b",
            # Every pnpm error code EXCEPT the audit family: `ERR_PNPM_AUDIT_*` is a scan
            # that failed, not an install that failed, and this prefix was claiming it.
            # The install codes (OUTDATED_LOCKFILE, PEER_DEP_ISSUES, NO_MATCHING_VERSION,
            # WORKSPACE_PKG_NOT_FOUND, ...) are untouched.
            r"ERR_PNPM(?!_AUDIT)",
            r"ERR_PNPM_NO_MATCHING_VERSION",
            r"ERR_PNPM_MINIMUM_RELEASE_AGE",
            r"YN\d{4}",
            r"\blockfile\b",
            r"peer dep",
            # The lockfile messages that are a FAILURE and not a filename. npm's and pnpm's
            # already arrive under `npm ERR!` / `ERR_PNPM`; yarn's and bun's do not, and
            # without them a frozen-lockfile break would rest on the bare noun above.
            r"[Yy]our lockfile needs to be updated",
            r"lockfile would have been modified by this install",
            r"lockfile had changes, but lockfile is frozen",
            r"\bERESOLVE\b",
            r"unable to resolve dependency tree",
            r"could not resolve dependency",
            r"Conflicting peer dependency",
            r"Fix the upstream dependency conflict",
            r"npm ci can only install packages when your package\.json and package-lock\.json",
            r"404 Not Found - GET https?://registry\.npmjs\.org",
            r"is not in this registry",
            r"yarn install v\d",
            r"error An unexpected error occurred",
            # yarn classic closes EVERY failed command with `info Visit
            # https://yarnpkg.com/en/docs/cli/<cmd>`, so the bare host scored a failed
            # `yarn run prettier` / `yarn lint` / `yarn test` as a dependency install.
            # Pin the footer to the two subcommands that ARE a dependency operation
            # (`install`, `add`); a formatting or test failure now falls to its own class.
            r"info Visit https://yarnpkg\.com/[\w/]*docs/cli/(?:install|add)\b",
        ],
        "reproduction_command": "corepack pnpm install --frozen-lockfile || npm ci",
        "minimal_repair_strategy": (
            "Reconcile lockfile and package metadata without upgrading unrelated dependencies; "
            "if a supply-chain policy rejected a too-new entry (for example pnpm's "
            "minimumReleaseAge / ERR_PNPM_MINIMUM_RELEASE_AGE), pin an already-aged version or "
            "widen the policy window rather than force-reinstalling."
        ),
    },
    {
        "failure_class": "typescript_typecheck",
        "likely_subsystem": "TypeScript type checking",
        "patterns": [
            r"\bTS\d{4}\b",
            # `tsc` only counts in command position (line start, a shell/npm echo
            # marker, or a package-manager invocation) or when a flag/verb follows
            # it. A bare \btsc\b also matches the x86 *time stamp counter* CPU
            # feature in the `flags :` line of /proc/cpuinfo, which jobs on
            # perf-sensitive projects dump into the log preamble -- enough on its
            # own to score a Rust or C++ build failure as a TypeScript typecheck.
            r"(?:^\s*|[>$+]\s+|\b(?:npx|pnpm|yarn|bunx|npm run)\s+)(?:vue-)?tsc\b"
            r"|\b(?:vue-)?tsc\b(?=\s+(?:-{1,2}\w|failed\b|exited\b))",
            r"tsc --noEmit",
            r"vue-tsc --noEmit",
            r"TSError: .* Unable to compile TypeScript",
            r"Type '.*' is not assignable",
            r"Cannot find name",
            r"Property '.*' does not exist on type",
            r"No overload matches this call",
            r"Argument of type '.*' is not assignable to parameter of type",
            r"Object is possibly '(?:null|undefined)'",
            r"is declared but its value is never read",
            r"tsc exited with code [1-9]",
            r"Type checking failed",
        ],
        "reproduction_command": "pnpm typecheck || npm run typecheck",
        "minimal_repair_strategy": (
            "Fix the smallest reported type mismatch, import drift, or schema mismatch and "
            "rerun the targeted typecheck."
        ),
    },
    {
        "failure_class": "javascript_lint",
        "likely_subsystem": "JavaScript or TypeScript linting",
        "patterns": [r"\beslint\b", r"\bbiome\b", r"lint failed", r"no-unused-vars", r"prettier"],
        "reproduction_command": "pnpm lint || npm run lint",
        "minimal_repair_strategy": "Apply the reported lint correction only in touched files.",
    },
    {
        "failure_class": "github_actions_workflow",
        "likely_subsystem": "GitHub Actions workflow wiring",
        "patterns": [
            r"Invalid workflow file",
            (
                # Anchored with \A so re.search evaluates the compound lookahead
                # once instead of retrying it at every start position. Without the
                # anchor this is O(n^2) on large logs (catastrophic backtracking)
                # and hangs on real CI output; \A keeps the "both present anywhere"
                # semantics while running in linear time.
                r"\A(?=[\s\S]*\.github/workflows/\S+\.ya?ml)"
                r"(?=[\s\S]*(?:Invalid workflow file|Unable to resolve action"
                r"|Resource not accessible by integration))"
            ),
            r"Unable to resolve action",
            r"Resource not accessible by integration",
        ],
        "reproduction_command": (
            "actionlint .github/workflows/  # validates workflow syntax and action refs "
            'locally; for "Resource not accessible" errors check the permissions: block and '
            "gh secret list"
        ),
        "minimal_repair_strategy": (
            "Inspect workflow syntax, action versions, and permissions, then adjust only the "
            "broken job or permission stanza."
        ),
    },
    {
        "failure_class": "artifact_or_cache_failure",
        "likely_subsystem": "GitHub Actions artifact or cache storage",
        "patterns": [
            r"Failed to CreateArtifact",
            r"Artifact upload failed",
            r"an artifact with this name already exists",
            r"Unable to download artifact",
            r"error occurred while (?:trying to )?download(?:ing)? (?:the )?artifact",
            r"No files were found with the provided path",
            r"Provided artifact name input during validation",
            r"actions/(?:upload|download)-artifact",
            r"Cache service responded with \d+",
            r"Failed to restore:? .*[Cc]ache",
            r"Failed to save:? .*[Cc]ache",
            r"reserveCache failed",
            r"Unable to reserve cache",
            r"getCacheEntry failed",
            r"Cache upload failed",
        ],
        "reproduction_command": (
            "re-run the job and inspect the failing actions/upload-artifact, "
            "actions/download-artifact, or actions/cache step (paths, name, key, action version)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is artifact or cache storage (wrong path, name collision, stale "
            "action version, or a transient storage-service outage) rather than a code defect, "
            "then fix the step's path/name/key inputs or bump the action version and retry — "
            "do not change application code."
        ),
    },
    {
        "failure_class": "release_publish_failure",
        "likely_subsystem": "Package or release publishing",
        "patterns": [
            r"npm publish",
            r"You cannot publish over the previously published versions?",
            r"\bEPUBLISHCONFLICT\b",
            r"\bENEEDAUTH\b",
            r"npm error code E403",
            r"403 Forbidden.*(?:upload|pypi|package)",
            r"(?:upload|pypi|package).*403 Forbidden",
            r"\btwine upload\b",
            r"HTTPError: 400.*File already exists",
            r"File already exists",
            r"This filename has already been used",
            r"cargo publish",
            r"crate version .* is already uploaded",
            r"is already uploaded",
            r"the remote server responded with an error.*already exists",
            r"gh release create",
            r"a release with the same tag .* already exists",
            r"Validation Failed.*already_exists",
        ],
        "reproduction_command": (
            "rerun the publish step locally with the same registry credentials "
            "(e.g. npm publish --dry-run, twine upload, cargo publish --dry-run, "
            "or gh release create)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a release or package publish conflict (a version/tag already "
            "exists or the publish step lacked auth) rather than a build or test defect, then bump "
            "the version, restore the missing publish credential, or skip the already-published "
            "artifact before rerunning only the publish step."
        ),
    },
    {
        "failure_class": "git_checkout_failure",
        "likely_subsystem": "Git checkout, clone, or submodule fetch",
        "patterns": [
            r"fatal: could not read Username",
            r"fatal: Authentication failed",
            r"Repository not found",
            r"fatal: repository '.*' not found",
            r"fatal: clone of '.*' (?:into submodule path|failed)",
            r"Fetched in submodule path",
            r"Failed to (?:clone|fetch|recurse into) submodule",
            r"smudge filter lfs failed",
            r"error downloading object",
            r"reference is not a tree",
            r"fatal: reference is not a tree",
            r"error: pathspec '.*' did not match",
            r"fatal: not a git repository",
        ],
        "reproduction_command": (
            "reproduce the checkout locally with the same ref and credentials "
            "(e.g. git clone --recurse-submodules <repo> && git checkout <ref>)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a git checkout, clone, submodule, or LFS fetch problem rather "
            "than a build or test defect, then fix the narrow ref, submodule URL, LFS pointer, or "
            "checkout credential before rerunning only the checkout step."
        ),
    },
    {
        "failure_class": "git_merge_conflict",
        "likely_subsystem": "Git merge or rebase against the base branch",
        "patterns": [
            r"Automatic merge failed; fix conflicts and then commit",
            r"CONFLICT \((?:content|add/add|rename|modify/delete|delete/modify|"
            r"submodule)",
            r"Merge conflict in ",
            r"fix conflicts and then commit the result",
            r"error: Merging is not possible because you have unmerged files",
            r"fatal: You have not concluded your merge \(MERGE_HEAD exists\)",
            r"\byou have unmerged paths\b",
            r"\bUnmerged paths:",
            r"\bneeds merge\b",
            r"Resolve all conflicts manually",
            r"error: could not apply [0-9a-f]+",
            r"Resolve the conflicts before",
            r"hint: after resolving the conflicts",
        ],
        "reproduction_command": (
            "merge or rebase the base branch locally to surface the conflict "
            "(e.g. git fetch origin && git merge origin/<base>)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a merge or rebase conflict against the base branch rather than "
            "a build or test defect, then resolve the conflicting files, commit the resolution, and "
            "rerun the job on the updated branch."
        ),
    },
    {
        "failure_class": "secrets_or_permissions_failure",
        "likely_subsystem": "CI secrets, tokens, or workflow permissions",
        "patterns": [
            r"Resource not accessible by integration",
            r"Error: Input required and not supplied",
            r"Input required and not supplied",
            # `SCREAMING_CASE is not set` is how a job reports a missing secret -- and how CMake
            # reports a POLICY it wants acknowledged. `CMP0148` is shaped exactly like an env var,
            # so the bare rule read one as the other.
            #
            # pytorch/pytorch's lint run 29361968044 failed on `jq: error: Could not open file
            # lint.json` -- lintrunner never wrote its report. Its one witness for a SECRETS
            # failure, at 0.53, was a line CMake prints for developers to ignore:
            #
            #     CMake Warning (dev) at third_party/NNPACK/CMakeLists.txt:110 (FIND_PACKAGE):
            #       Policy CMP0148 is not set: The FindPythonInterp and FindPythonLibs modules
            #       are removed.  Run "cmake --help-policy CMP0148" for policy details.
            #     This warning is for project developers.  Use -Wno-dev to suppress it.
            #
            # We would have sent a maintainer to audit their repository secrets over a
            # suppressible warning in a vendored third-party CMakeLists. A policy CMake names is
            # never a credential, so the subject may not be one CMake introduced; a token that
            # really is unset (`GITHUB_TOKEN is not set`) is untouched, because nothing precedes
            # it. Left with no witness, the log answers `unknown` and hands the failure back.
            #
            # Standard terminal/locale environment variables report themselves the same way, and
            # headless runners leave them unset by design -- they are never repository secrets.
            # rails/rails run 29648807728 printed `debconf: (TERM is not set, so the dialog
            # frontend is not usable.)` while apt provisioned the build image; on that lone
            # witness we answered `secrets_or_permissions_failure` at 0.53 and would have sent a
            # maintainer hunting for a missing credential over a cosmetic apt/debconf notice.
            # `TERM`, `DEBIAN_FRONTEND`, and their siblings are excluded by name so the benign
            # tooling chatter carries no witness, while a real secret in SCREAMING_CASE
            # (`GITHUB_TOKEN is not set`, `STRIPE_SECRET_KEY is not set`) still matches.
            r"\b(?<!Policy )"
            r"(?!(?-i:(?:TERM|DEBIAN_FRONTEND|DISPLAY|COLORTERM|LANG|LANGUAGE|LC_[A-Z]+|TZ|"
            r"PAGER|GIT_PAGER|EDITOR|VISUAL|SHELL|TMPDIR|NO_COLOR)\b))"
            r"(?-i:[A-Z][A-Z0-9_]{2,})\s+is not set\b",
            r"secret .* (?:is )?(?:not set|missing|empty|required)",
            r"\$\{\{\s*secrets\.[A-Z0-9_]+\s*\}\}",
            r"context access might be invalid",
            r"Permission to .* denied to github-actions",
            r"remote: Permission to .* denied",
            r"refusing to allow a(?:n)? (?:GitHub App|OAuth App|integration) to create or "
            r"update workflow",
            r"without (?:the )?workflows? permission",
            r"403.*write_packages",
            r"insufficient (?:permission|scope|privileges)",
            r"missing or insufficient permissions",
            r"(?:token|app|integration) lacks the .*(?:permission|scope)",
            r"lacks the .*(?:permission|scope)",
            r"requires the .* permission",
            r"\bpermissions:\b.*\bwrite\b",
        ],
        "reproduction_command": (
            "inspect the workflow permissions and required secrets "
            "(e.g. gh secret list and the permissions: block in the workflow)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a missing secret, unset input, or insufficient workflow "
            "permission rather than a code defect, then provision the missing secret or widen the "
            "narrow permissions/token scope the failing step needs before rerunning it."
        ),
    },
    {
        "failure_class": "security_scan_failure",
        "likely_subsystem": "Security scanner or dependency audit",
        "patterns": [
            r"\bnpm audit\b",
            # npm and pnpm report a scan that RAN and FAILED through their own audit error
            # channel, and never through the words `npm audit`. npm's own audit-error path
            # (`lib/utils/audit-error.js`) logs the registry's reply and then dies with
            # `audit endpoint returned an error`; the code arrives as an `EAUDIT*` and the
            # detail line as `npm ERR! audit ...` (npm <=9) or `npm error audit ...` (>=10).
            # None of that says `npm audit`, so the only thing left to match was the bare
            # `npm ERR!` of `node_dependency_install` -- and a private registry that cannot
            # audit was handed back as a broken install. Matched on the ERROR channel only:
            # `npm warn audit ...` is npm reporting a scan it SKIPPED, which is not a failure.
            r"audit endpoint returned an error",
            r"\bEAUDIT[A-Z]*\b",
            r"npm (?:ERR!|error) audit\b",
            r"\bERR_PNPM_AUDIT[A-Z_]*\b",
            r"\bpip-audit\b",
            r"\bcargo audit\b",
            r"\btrivy\b",
            r"\bgosec\b",
            r"\bsnyk\b",
            r"\bsemgrep\b",
            r"\bbandit\b",
            r"CRITICAL: Vulnerability",
            r"Found known vulnerabilities",
            r"Vulnerabilities found",
            r"High severity vulnerability",
            r"\bCVE-\d{4}-\d{4,}\b",
            r"\bGHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}\b",
            r"\bRUSTSEC-\d{4}-\d{4}\b",
            r"Severity:\s+(?:HIGH|CRITICAL)",
            r"Scan failed",
            r"gosec found issues",
        ],
        "reproduction_command": (
            "rerun the same scanner locally (e.g. npm audit, pip-audit, cargo audit, "
            "trivy fs ., bandit -r ., or semgrep --config auto)"
        ),
        "minimal_repair_strategy": (
            "Confirm the vulnerable package or finding, upgrade or patch the narrow affected "
            "dependency/configuration, and rerun the same scanner before broad CI."
        ),
    },
    {
        "failure_class": "dotnet_build_failure",
        "likely_subsystem": ".NET restore, build, or test lifecycle",
        "patterns": [
            r"\bdotnet restore\b",
            r"\bdotnet build\b",
            r"\bdotnet test\b",
            r"\bNU\d{4}\b",
            r"\bCS\d{4}\b",
            r"error NETSDK\d+",
            r"package downgrade",
            r"Version conflict detected",
            r"Unable to resolve",
            r"Xunit\.Sdk",
            r"Failed!  - Failed:",
            # Case-sensitive banner: msbuild prints "Build FAILED"; do not match
            # cargo's lowercase "build failed, waiting for other jobs to finish".
            r"(?-i:Build FAILED)",
        ],
        "reproduction_command": "dotnet restore && dotnet test",
        "minimal_repair_strategy": (
            "Reproduce the failing dotnet restore, build, or test command, then fix the narrow "
            "NuGet graph, target framework, compiler, or test assertion drift before rerunning it."
        ),
    },
    {
        "failure_class": "java_build_failure",
        "likely_subsystem": "JVM build or test lifecycle (Maven, Gradle, sbt, or Kotlin/Android)",
        "patterns": [
            r"\bmvn\b",
            r"\bgradle\b",
            r"COMPILATION ERROR",
            r"Failed to execute goal",
            r"Execution failed for task",
            r"Could not resolve all files",
            # Maven's own phrasing is "Could not resolve dependencies for project
            # <group>:<artifact>:jar:<version>". The bare "Could not resolve
            # dependencies:" (trailing colon, no "for project") is Cabal's -- and
            # pip's, and npm's -- so keep the Maven-specific suffix or a Haskell
            # `cabal build` failure reads as a JVM build. haskell/cabal's Validate
            # job (run 29562439929, GHC compile errors + a cabal-testsuite that
            # UNEXPECTED FAIL'd, no mvn/gradle/jvm token anywhere) came out
            # java_build_failure at 0.53 on this one line before the suffix.
            r"Could not resolve dependencies for project\b",
            r"Could not determine java version",
            r"Unsupported class file major version",
            r"No tests found for given includes",
            # Case-sensitive banner: Gradle prints "BUILD FAILED"; do not match
            # cargo's lowercase "build failed" or Go's lowercase "build failed".
            r"(?-i:BUILD FAILED)",
            r"cannot find symbol",
            r"package .* does not exist",
            # sbt (Scala on the JVM): sbt prints none of the Maven/Gradle banners
            # above, so a real sbt compile/test failure fell through to `unknown`.
            # Key on sbt's own markers instead.
            r"welcome to sbt",
            r"compileIncremental\) Compilation failed",
            r"not found: value ",
            r"not found: type ",
            r"sbt\.TestsFailedException",
            # Kotlin/Android: kotlinc's own diagnostic format and Gradle Kotlin
            # plugin task names. A trimmed CI paste that keeps only the compiler
            # diagnostics (no "Execution failed for task" / "BUILD FAILED"
            # banner further down the log) would otherwise fall through to
            # `unknown`, so key on kotlinc's own markers too.
            r"e: .*\.kt: \(\d+, \d+\): ",
            r"Unresolved reference: \S+",
            r":compile(?:Debug|Release)?Kotlin\b.*FAILED",
        ],
        "reproduction_command": "./gradlew test || mvn test || sbt test",
        "minimal_repair_strategy": (
            "Reproduce the failing Maven, Gradle, sbt, or Kotlin compile task, then "
            "fix the narrow dependency, toolchain, compiler, or test-selection drift "
            "before rerunning the same task."
        ),
    },
    {
        "failure_class": "docker_build_failure",
        "likely_subsystem": "Container image build",
        "patterns": [
            r"\bdocker build\b",
            r"\bdocker buildx build\b",
            r"\bdocker compose\b",
            r"failed to solve",
            r"failed to compute cache key",
            r"target stage .* could not be found",
            r"service .* is unhealthy",
            r"manifest .* not found",
        ],
        "reproduction_command": "docker build .",
        "minimal_repair_strategy": (
            "Reproduce the failing image build locally, then fix the narrow Dockerfile, "
            "build context, compose healthcheck, or base-image reference drift."
        ),
    },
    {
        "failure_class": "cpp_build_failure",
        "likely_subsystem": "C/C++ native build toolchain",
        "patterns": [
            r"CMake Error",
            r"ninja: build stopped",
            r"g?make(?:\[\d+\])?: \*\*\* \[[^\]]*\] Error \d+",
            r"undefined reference to",
            r"collect2: error: ld returned",
            r"error: ld returned \d+ exit status",
            r"fatal error: [^\s:]+\.(?:h|hpp|hxx): No such file or directory",
            r"was not declared in this scope",
            r"use of undeclared identifier",
            r"clang(?:\+\+)?: error:",
            r"\bcc1plus\b",
            r"undefined symbols for architecture",
        ],
        "reproduction_command": "cmake --build build || make",
        "minimal_repair_strategy": (
            "Reproduce the failing compile or link target, then fix the narrow drift "
            "(missing header or include path, undeclared symbol, or linker reference) "
            "before rerunning the same target."
        ),
    },
    {
        "failure_class": "browser_test_failure",
        "likely_subsystem": "Browser end-to-end tests",
        "patterns": [
            r"\bplaywright test\b",
            r"\bcypress run\b",
            r"browserType\.launch",
            r"Executable doesn't exist",
            r"Timeout \d+ms exceeded",
            r"locator\(",
            r"CypressError",
            r"browser exited unexpectedly",
        ],
        "reproduction_command": "npx playwright test || npx cypress run",
        "minimal_repair_strategy": (
            "Reproduce the browser test locally, install missing browsers if needed, "
            "then patch the selector, fixture, or launch configuration causing the failure."
        ),
    },
    {
        "failure_class": "rust_test_failure",
        "likely_subsystem": "Rust tests",
        "patterns": [
            r"\bcargo test\b",
            r"error\[E\d{4}\]",
            # Modern Rust prints an optional thread id between the name and
            # "panicked" for unnamed threads: `thread '<unnamed>' (4467) panicked`.
            r"thread '[^']*'(?: \(\d+\))? panicked",
            r"test result: FAILED",
        ],
        "reproduction_command": "cargo test",
        "minimal_repair_strategy": (
            "Reproduce the failing crate or test target, patch the narrow Rust error, and "
            "rerun cargo test for that crate."
        ),
    },
    {
        "failure_class": "ruby_bundle_failure",
        "likely_subsystem": "Ruby dependency installation or test lifecycle",
        "patterns": [
            r"\bbundle install\b",
            r"\bbundle exec\b",
            r"\bbundler\b",
            r"Bundler could not find compatible versions",
            r"Could not find gem",
            r"Gem::Ext::BuildError",
            r"An error occurred while installing",
            r"Your bundle is locked to",
            r"rake aborted!",
            r"rspec .*failures?",
            # Real RSpec output rarely puts "rspec" and "failures" on one line.
            # Its rerun list is `rspec ./path/to/thing_spec.rb[1:2]` and its
            # summary is `N examples, [K pending, ]M failures` (rspec, parallel
            # and turbo_tests all emit this), so match those shapes directly.
            r"rspec \./\S+_spec\.rb",
            r"\b\d+ examples?, (?:\d+ \w+, )*\d+ failures?\b",
        ],
        "reproduction_command": "bundle install && bundle exec rake test",
        "minimal_repair_strategy": (
            "Reproduce the failing Bundler, Rake, or RSpec command, then fix the narrow "
            "Gemfile, lockfile, native extension, or test drift before rerunning it."
        ),
    },
    {
        "failure_class": "php_composer_failure",
        "likely_subsystem": "PHP Composer dependency resolution or autoload",
        # PHPUnit running and reporting a failed assertion is not a Composer failure.
        # `FAILURES!`, `Failed asserting` and the `Tests: ... Failures:` summary are the
        # verdict of tests that ran; folding them in here labelled a symfony/symfony run
        # whose `composer update` step SUCCEEDED as `php_composer_failure` at 0.95 --
        # sending the maintainer to debug dependency installation for a failed assertion in
        # src/Symfony/Component/ErrorHandler. The bare `composer install`/`composer update`
        # commands run green in nearly every PHP job (symfony echoes both as setup), so
        # their presence is not a failure either. This rule now witnesses only genuine
        # resolution/lock/platform errors and the autoload `Class ... not found`; a plain
        # PHPUnit test failure carries no signal here and lands on `unknown`, the honest
        # ceiling until PatchRail has a PHP test-failure class.
        "patterns": [
            r"Your requirements could not be resolved to an installable set of packages",
            r"requires php",
            r"Problem \d+",
            r"lock file is not up to date",
            r"not present in the lock file",
            r"Class .* not found",
        ],
        "reproduction_command": "composer install && vendor/bin/phpunit",
        "minimal_repair_strategy": (
            "Reproduce the failing Composer command, then fix the narrow composer.json, "
            "lockfile, PHP platform, or autoload map before rerunning it."
        ),
    },
    {
        "failure_class": "go_test_failure",
        "likely_subsystem": "Go tests",
        "patterns": [
            r"\bgo test\b",
            r"FAIL\t",
            r"--- FAIL:",
            r"undefined:",
            r"not enough arguments in call to",
            r"too many arguments in call to",
            r"panic: test timed out",
        ],
        "reproduction_command": "go test ./...",
        "minimal_repair_strategy": (
            "Run the failing package test and make the smallest compile or runtime fix in "
            "that package."
        ),
    },
    {
        "failure_class": "node_test_failure",
        "likely_subsystem": "Node test runner (jest, vitest, or mocha)",
        "patterns": [
            r"\bjest\b",
            r"\bvitest\b",
            r"\bmocha\b",
            r"\bjasmine\b",
            r"jest --",
            r"vitest run",
            r"npx (?:jest|vitest|mocha)",
            r"npm (?:run )?test",
            r"Tests:\s+\d+ failed",
            r"Test Suites:\s+\d+ failed",
            r"\d+ failing",
            r"\d+ passing",
            r"^\s*FAIL\s+(?:src|test|tests|spec|__tests__)/",
            r"\bFAIL\b .*\.(?:test|spec)\.(?:[jt]sx?)\b",
            r"× .*\.(?:test|spec)\.(?:[jt]sx?)\b",
            r"Expected:.*Received:",
            r"expect\(.*\)\.to(?:Equal|Be|Match|Have)",
            r"AssertionError \[ERR_ASSERTION\]",
            r"toMatchSnapshot",
            r"● .* > ",
        ],
        "reproduction_command": "npx jest || npx vitest run || npx mocha",
        "minimal_repair_strategy": (
            "Confirm a Node unit-test runner (jest, vitest, or mocha) failed rather than a "
            "browser end-to-end suite, then reproduce the failing spec, patch the narrow "
            "assertion or behavior drift, and rerun that spec before the full suite."
        ),
    },
    {
        "failure_class": "rust_lint",
        "likely_subsystem": "Rust linting (clippy)",
        "patterns": [
            r"\bclippy\b",
            r"cargo clippy",
            r"error\[clippy::",
            r"warning: clippy::",
            r"could not compile due to clippy",
            r"-D warnings",
            r"unneeded `return` statement",
        ],
        "reproduction_command": "cargo clippy --all-targets -- -D warnings",
        "minimal_repair_strategy": (
            "Confirm clippy failed rather than the tests, then apply the reported fix only in "
            "the touched files and rerun cargo clippy."
        ),
    },
    {
        "failure_class": "go_lint",
        "likely_subsystem": "Go linting (golangci-lint)",
        "patterns": [
            r"\bgolangci-lint\b",
            r"golangci-lint run",
            r"\(gofmt\)",
            r"\(govet\)",
            r"\(staticcheck\)",
            r"\(errcheck\)",
            r"\(ineffassign\)",
            r"\(gosimple\)",
            r"\(revive\)",
            r"\(unused\)\s*$",
            r"^\s*\S+\.go:\d+:\d+: .* \(\w+\)\s*$",
        ],
        "reproduction_command": "golangci-lint run ./...",
        "minimal_repair_strategy": (
            "Confirm golangci-lint failed rather than the tests, then apply the reported fix "
            "only in the touched files and rerun golangci-lint."
        ),
    },
    {
        "failure_class": "terraform_iac_failure",
        "likely_subsystem": "Terraform/OpenTofu infrastructure-as-code plan, apply, or init",
        "patterns": [
            r"Error acquiring the state lock",
            r"Error: Inconsistent dependency lock file",
            r"Error: Failed to query available provider packages",
            r"Error: Failed to install provider",
            r"Error: Reference to undeclared (?:resource|input variable|local value|module)",
            r"Error: Unsupported (?:argument|block type)",
            r"Error: Invalid (?:value for|reference|resource type)",
            r"Error: Module not installed",
            r"Error: Provider configuration not present",
            r"╷\s*\n\s*│\s*Error:",
            r"\bterraform (?:init|plan|apply|validate|fmt)\b",
            r"\bopentofu\b|\btofu (?:init|plan|apply)\b",
            r"\bterragrunt\b",
            r"Terraform planned the following actions, but then encountered a problem",
        ],
        "reproduction_command": (
            "run the failing stage locally against the same workspace "
            "(e.g. terraform init && terraform validate && terraform plan)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a Terraform/IaC configuration or state issue rather than a "
            "downstream provider outage, then fix the reported HCL argument, lock file, or provider "
            "constraint (or release a stale state lock) and rerun plan before apply."
        ),
    },
    {
        "failure_class": "shell_lint",
        "likely_subsystem": "Shell script linting/formatting (ShellCheck, shfmt)",
        "patterns": [
            r"\bshellcheck\b",
            r"\bSC\d{4}\b",
            r"\^-{2,}\^ SC\d{4}",
            r"In .* line \d+:",
            r"\bshfmt\b",
            r"\bcheckbashisms\b",
        ],
        "reproduction_command": "shellcheck $(git ls-files '*.sh')",
        "minimal_repair_strategy": (
            "Confirm the failure is ShellCheck/shfmt rather than the tests, then apply the "
            "reported fix only in the touched files and rerun the same linter."
        ),
    },
    {
        "failure_class": "elixir_mix_failure",
        "likely_subsystem": "Elixir Mix build, Hex dependency resolution, or ExUnit tests",
        "patterns": [
            r"\bmix (?:deps\.get|deps\.compile|compile|test|format)\b",
            r"\*\* \(Mix\) ",
            r"\*\* \(CompileError\) ",
            r"\*\* \(UndefinedFunctionError\) ",
            r"Because .* depends on .* version solving failed",
            r"\d+ tests?, \d+ failures?",
            r"Assertion with == failed",
            r"mix format --check-formatted|mix format failed",
        ],
        "reproduction_command": "mix deps.get && mix compile --warnings-as-errors && mix test",
        "minimal_repair_strategy": (
            "Confirm the failure is a Mix compile, Hex resolution, or ExUnit issue rather than a "
            "downstream flake, then fix the reported module/dependency/assertion and rerun the "
            "same mix task."
        ),
    },
    {
        "failure_class": "database_migration_failure",
        "likely_subsystem": "Database schema migration (Alembic, Django, Rails, Flyway, Prisma)",
        "patterns": [
            r"alembic\.util\.exc\.CommandError",
            r"Target database is not up to date",
            r"Can't locate revision identified by",
            r"django\.db\.migrations\.exceptions\.(?:InconsistentMigrationHistory|NodeNotFoundError)",
            r"Conflicting migrations detected",
            r"\brails db:migrate\b|\brake db:migrate\b",
            r"ActiveRecord::(?:PendingMigrationError|IrreversibleMigration|StatementInvalid)",
            r"FlywayException|Migration checksum mismatch|Detected failed migration",
            r"Migration\s+V\d+__[A-Za-z0-9_.-]+\.sql\s+failed",
            r"^\s*SQL State\s*:\s*(?!00000\b)[0-9A-Z]{5}\s*$",
            r"\bprisma migrate (?:deploy|dev)\b",
            r"\bP3005\b|\bP3006\b|\bP3009\b",
            r"Drift detected",
        ],
        "reproduction_command": (
            "run the failing migration command locally against a disposable copy of the "
            "database (e.g. alembic upgrade head, rails db:migrate, or prisma migrate deploy)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a schema migration issue rather than an application code "
            "defect, then resolve the reported revision/history conflict, checksum mismatch, "
            "or SQL error "
            "and rerun the same migration command against a disposable database copy."
        ),
    },
    {
        "failure_class": "kubernetes_deploy_failure",
        "likely_subsystem": "Kubernetes deployment (kubectl apply/rollout, kustomize)",
        "patterns": [
            r"\bkubectl (?:apply|rollout|wait|create|diff)\b",
            r"error: unable to recognize",
            r"Error from server \(",
            r"error validating (?:data|\".*\")",
            r"error: deployment \".*\" exceeded its progress deadline",
            r"Waiting for deployment .* rollout to finish",
            r"field is immutable",
            r"admission webhook .* denied the request",
            r"\bkustomize build\b",
        ],
        "reproduction_command": (
            "rerun the failing step locally against the same manifests "
            "(e.g. kubectl apply --dry-run=server -f . or kustomize build .)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a Kubernetes manifest, admission-webhook, or rollout issue "
            "rather than an upstream API-server outage, then fix the reported field/resource and "
            "rerun the same kubectl or kustomize command."
        ),
    },
    {
        "failure_class": "helm_chart_failure",
        "likely_subsystem": "Helm chart lint, template rendering, or release install/upgrade",
        "patterns": [
            r"\bhelm (?:lint|template|install|upgrade|dependency)\b",
            r"Error: chart requires kubeVersion",
            r"Error: found in Chart\.yaml, but missing in charts/ directory",
            r"Error: YAML parse error on",
            r"Error: values don't meet the specifications of the schema",
            r"Error: template: [^<\n]*? executing \"[^\"\n]*\" at <[^>\n]*>:",
            r"Error: INSTALLATION FAILED",
            r"Error: UPGRADE FAILED",
        ],
        "reproduction_command": (
            "run the failing stage locally against the same chart/values "
            "(e.g. helm lint . && helm template . -f values.yaml)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is a Helm chart, values-schema, or template rendering issue "
            "rather than a downstream cluster outage, then fix the reported chart/values error "
            "and rerun the same helm command."
        ),
    },
    {
        "failure_class": "docs_build_failure",
        "likely_subsystem": "Documentation site build (Sphinx, MkDocs, Docusaurus)",
        "patterns": [
            r"\bsphinx-build\b",
            r"Warning, treated as error",
            r"WARNING: document isn't included in any toctree",
            r"toctree contains reference to nonexisting document",
            r"WARNING: undefined label:",
            r"WARNING: unknown document:",
            r"\bmkdocs build\b",
            r"Aborted with \d+ warnings in strict mode",
            r"is not found among documentation files",
            r"mkdocs\.exceptions\.",
            r"\bdocusaurus build\b",
            r"Docusaurus found broken links",
            r"Broken link on source page path",
            r"Docs markdown link couldn't be resolved",
            r"Error: Unable to build website for locale",
        ],
        "reproduction_command": (
            "build the docs locally with the same strict flags "
            "(e.g. sphinx-build -W -b html docs docs/_build, mkdocs build --strict, "
            "or npm run docusaurus build) and fix the first reported warning"
        ),
        "minimal_repair_strategy": (
            "Confirm the docs build failed on a warning-as-error (broken cross-reference, "
            "missing toctree entry, or unresolved link) rather than a code defect, then fix the "
            "offending reference or add the page to the site navigation before rerunning the "
            "strict build."
        ),
    },
    {
        "failure_class": "xcode_build_failure",
        "likely_subsystem": "Apple platform build/test (xcodebuild, swift build, Swift Package Manager)",
        "patterns": [
            r"\bxcodebuild\b",
            r"\bswift build\b",
            r"\bswift test\b",
            r"The following build commands failed:",
            r"\*\* BUILD FAILED \*\*",
            r"\*\* TEST FAILED \*\*",
            r"xcodebuild: error:",
            r"error: no such module ",
            r"error: Dependencies could not be resolved",
            r"error: could not find target",
            r"Testing failed:",
            r"\bCompileSwift(?:Sources)?\b",
        ],
        "reproduction_command": (
            "reproduce the failing Apple build/test locally against the same scheme "
            "(e.g. swift build && swift test, or "
            "xcodebuild -scheme <Scheme> build test)"
        ),
        "minimal_repair_strategy": (
            "Confirm the failure is an Xcode/SwiftPM build, module-resolution, or XCTest "
            "issue rather than a code-signing or provisioning problem, then fix the reported "
            "Swift compile error, missing module, or unresolved package dependency and rerun "
            "the same swift or xcodebuild command."
        ),
    },
]


# GitHub Actions encodes every log line with a leading prefix. ``gh run view
# --log``/``--log-failed`` emits ``<job>\t<step>\t<timestamp> <line>`` (plus a UTF-8
# BOM on the very first line); a raw log download from the Actions UI emits
# ``<timestamp> <line>``. Both push the real content off the start of the line, which
# silently defeats patterns anchored to the line start (``^``) and lowers — or drops —
# the classification. Strip the prefix up front so the common one-liner
# ``gh run view <id> --log-failed | patchrail ci explain`` classifies identically to a
# saved raw log.
_CI_LOG_LINE_PREFIX = re.compile(
    r"\ufeff?"  # optional UTF-8 BOM (gh emits it once, on the first line)
    r"(?:[^\t\n]*\t[^\t\n]*\t)?"  # optional `gh` job/step columns
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z "  # ISO-8601 timestamp + one space
)


def _strip_ci_log_line_prefixes(text: str) -> str:
    stripped = []
    for line in text.splitlines():
        match = _CI_LOG_LINE_PREFIX.match(line)
        stripped.append(line[match.end() :] if match else line)
    return "\n".join(stripped)


# CI tools colour their output and CI keeps the colour on: Airflow runs pytest with
# ``--color=yes``, cargo honours ``CARGO_TERM_COLOR=always``, jest and eslint colour
# unless told not to. The GitHub log API then serves those escapes back with the ESC
# byte written out as the two literal characters ``^`` ``[``, so stripping only
# ``\x1b``-introduced codes never fires on a downloaded log. The colour reset lands
# *inside* the failure line, between the token and the space that follows it:
#
#     ^[[31mFAILED^[[0m providers/edge3/.../test_worker.py::TestEdgeWorker::test_...
#     ^[[31m===== ^[[1m1 failed^[[0m, ^[[32m322 passed^[[0m in 15.81s =====
#
# which defeats ``FAILED .*::`` and every other pattern spanning a coloured token. A real
# apache/airflow test failure scored 1 -- on the bare ``pytest`` invocation, the only
# uncoloured token left -- and lost to post-failure artifact noise. Strip both encodings
# before matching. Anchoring to the ESC/``^[`` introducer keeps ordinary bracketed text
# (``error[E0277]``, ``[ERROR]``) untouched.
_ANSI_ESCAPE = re.compile(r"(?:\x1b|\^\[)\[[0-9;?]*[A-Za-z]")


def _strip_ansi_escapes(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


# Lines that only ever ECHO a command or INSTALL a tool. `set -x` (which every
# `scripts/check`-style CI shell turns on) echoes `+ ruff check httpx tests`; the Actions
# step header echoes the whole command back as `Run mypy .`; pip's resolver announces
# `Collecting mypy==1.17.1` and `Downloading ruff-0.12.11-...whl` for every dev
# dependency in the project. Every one of those names a tool in a job that may well have
# passed -- they are the job's cast list, not its cause of death.
#
# INVOCATION_ONLY_PATTERNS below says the same thing one pattern at a time, and cannot
# keep up: it needs `ruff check`, `pytest`, `mypy`, `eslint` and every other tool a rule
# ever names, and it only defends a rule whose signals are *entirely* in the list -- so a
# single contaminated signal switches the whole defence off. encode/httpx (a plain
# `1 failed, 1416 passed` pytest failure) came out as `python_lint` on exactly that: one
# `set -x` echo of `ruff check` -- a run that passed -- plus `F401` quoted inside a
# non-fatal `warning:` about an invalid noqa directive, which is not in the list. Judge
# the LINE a signal lands on instead: found nowhere but here, it never witnessed a failure.
#
# conda says all of this too, and louder. pandas-dev/pandas builds its docs in a conda env
# whose `environment.yml` pins the whole dev toolchain, so a job that runs nothing but Sphinx
# still prints `mypy` six times -- once as the spec (`- mypy=1.17.1`), then in the solver's
# transaction table, then `Linking mypy-1.17.1-py311h49ec1c0_1`, then twice more in the
# package tables, then in `conda list`. Not one of them RUNS it. pip's half of this is already
# handled above (`Collecting`, `Downloading`); the conda half was not, so `\bmypy\b` witnessed
# a "failure" on a line that was installing a package, and pandas's Sphinx crash came out
# `python_type_check` at 0.53. A conda listing is a bill of materials, not an event.
#
# The table row is matched structurally rather than by name -- `<pkg> <version> [<build>
# <channel>]`, columns to the end of the line, no severity word in front (the same guard the
# env dump uses, and for the same reason). A real failure never has that shape: it carries
# prose, a path, a code, a message. `FAILED tests/test_x.py::test_y - assert 1 == 2` is a
# severity plus a path, `error: cannot find crate` is prose, and `1 failed, 322 passed`
# begins with a bare number rather than a package name -- none of them are a two-column
# listing that stops at the version.
#
# A runner's env dump and a CMake probe name tools the same way. The hosted images ship a
# whole toolchain, so every Windows job that prints its environment advertises Gradle and
# Maven it will never run: moby/moby (Go, `build-windows`) and apache/kafka (whose failing
# job was `check-pr-labels`) both came out `java_build_failure` on `GRADLE_HOME=/usr/share/
# gradle-9.6.1` and `MAVEN_OPTS   -Xms256m` -- the ONLY lines in either log to say gradle or
# maven. CMake announces optional tools it merely found (`-- Found Pylint: /usr/bin/pylint`,
# `-- Registered 'check_pylint' target`) and prints `- Failed` for capability probes that are
# SUPPOSED to fail (`-- Performing Test HAVE_C_WSIGN_PROMO - Failed`); that made opencv/opencv
# -- C++, and killed by a CodeQL `commit not found` -- a 0.71-confidence `python_lint`.
# A real gradle or pylint failure still wins: it also fails somewhere off these lines.
# A tool that was INVOKED here. The job ran it and the job died, so as a last resort -- when
# the log offers nothing else at all -- naming it is a defensible guess.
_INVOCATION_LINE = re.compile(
    r"""^(?:
          \++\ +                       # bash `set -x` command echo: `+ ruff check .`
        | \[command\]                  # Actions command echo: `[command]/usr/bin/git ...`
        | \#\#\[(?:group|command)\]    # Actions group header, which echoes the command
        | Run\ +\S                     # Actions step header: `Run mypy .`
        | Running\ \[                  # bracketed echo: `Running [/path/golangci-lint run] in [/src]`
        | \$\ +\S                      # pnpm/turbo script echo: `$ tsc -b`
    )""",
    re.VERBOSE | re.IGNORECASE,
)


# npm and pnpm close a SUCCESSFUL install with an audit summary: a count of advisories in
# the dependency tree, and the command that would fix them. No scanner ran, nothing failed
# -- `npm audit` is only ever *suggested* here. withastro/astro's Windows smoke job died in
# a build script (`##[error]Process completed with exit code 127`) and we called it a failed
# security scan at 0.71, on this block and nothing else:
#     1 high severity vulnerability
#     To address all issues, run:
#       npm audit fix --force
# A scan that really ran and really failed says so away from this block -- `npm ERR! code
# EAUDIT`, `Found known vulnerabilities`, trivy's `Severity: HIGH`, a bare `CVE-2026-1234`
# in a report -- and still wins at full confidence. The count line is matched only when the
# count is the WHOLE line, so a scanner's own finding (`High severity vulnerability found in
# openssl (CVE-...)`) is never mistaken for npm's tally.
_AUDIT_SUMMARY_LINE = re.compile(
    r"""^\s*(?:
          \d+\ (?:low|moderate|high|critical)\ severity\ vulnerabilit(?:y|ies)\s*$
        | found\ \d+\ vulnerabilit(?:y|ies)\b
        | to\ address\ (?:all\ )?(?:these\ )?issues\b
        | (?:npm|pnpm|yarn)\ audit\ fix\b
        | run\ `?(?:npm|pnpm|yarn)\ audit`?\ for\ details
    )""",
    re.VERBOSE | re.IGNORECASE,
)

# A tool that was never even RUN here -- only installed, exported, probed for, or quoted in a
# config blob. It cannot be the cause of anything, so it must never be the answer (see
# `never_invoked` in classify_ci_log).
_MERE_MENTION_LINE = re.compile(
    r"""^(?:
          (?:Collecting|Downloading|Using\ cached|Requirement\ already\ satisfied
           |Installing\ collected\ packages|Successfully\ installed)\b  # pip resolver
        | Download\ action\ repository\b   # runner pre-loading every action the job declares
        | (?:                              # an action SHIPPING its tool: fetch, cache, probe,
                                           # install, time it. golangci-lint-action prints all
                                           # five before the linter inspects a single file, and
                                           # each one names the tool.
            Finding\ needed\ [\w.\-]+\ version
          | Install(?:ing|ed)\ [\w.\-]+\ (?:binary|into)\b
          | (?:Cache\ hit\ (?:for|occurred)|Restored\ cache\ for)\b
          | Ran\ [\w.\-]+\ in\ \d+\s*m?s\b
          )
        | level=info\b                     # a structured log line that grades itself: not a failure
        | (?-i:                            # env dump -- case-sensitive, and never a severity
            (?!(?:ERROR|ERR|FAIL|FAILED|FAILURE|FATAL|PANIC|WARN|WARNING|CRITICAL)\b)
            [A-Z][A-Z0-9_]+ (?: = | \ {2,} ) \S      # `GRADLE_HOME=/usr/...`, `M2   C:\...`
          )
        | --\ +\S                          # CMake status line / capability probe
        | \s* " [^"]+ " \s* :              # a key in a pretty-printed JSON config blob
        | \s* (?:Linking|Unlinking|Extracting|Downloading\ and\ Extracting)\ +\S  # conda link phase
        | \s* -\ +[\w.\-]+ \s* [=<>!~]=? \s* [\d*]   # env.yml spec echo: `- mypy=1.17.1`
        | \s* (?:\w+\ )? Dependencies \s* :   # pixi/rattler env resolve prints one bill-of-materials
            \s* [\w.\-]+ (?: \s*,\s* [\w.\-]+ )* \s* $  # line per environment: `Dependencies: python,
                                           # numpy, ..., mypy, ...` (and `PyPI Dependencies: ...`).
                                           # pandas-dev/pandas resolves ~20 of these before any job runs;
                                           # its `Pyarrow Nightly` env update (run 29719453153) died in
                                           # `pixi` (`Failed to update PyPI packages`), and `mypy` is one
                                           # declared dev dependency in the list -- never invoked. That
                                           # ONE line was `\bmypy\b`'s only witness, so the pixi failure
                                           # came out python_type_check at 0.53. Matched only when the
                                           # whole tail is a comma-list of package tokens: a real resolver
                                           # error carries prose (`could not resolve x because ...`), a
                                           # path, or a code -- never a bare manifest.
        | (?-i:                            # conda/mamba package table -- see below
            (?!(?:ERROR|ERR|FAIL|FAILED|FAILURE|FATAL|PANIC|WARN|WARNING|CRITICAL)\b)
            \s* [+-]?\ * [\w.\-]+ (?: \s{2,} | \s*[=<>!~]=?\s* ) v?\d[\w.+!]*
            (?: \s+\S+ )*? \s* $          # nothing but more columns to the end of the line
          )
        | [\ \t│├└─]* \[\d+/\d+\]\s        # the Flutter tool's `precache` artifact listing, one
            [^\n]*? \d+(?:\.\d+)?\s*m?s \s* $  # timed line per bundled artifact it CACHED: `[2/10]
                                           # Gradle Wrapper   7ms`. rrousselGit/riverpod (a Dart
                                           # monorepo whose `flutter analyze` reported 4 lints,
                                           # run 29573819047) said java_build_failure at 0.53 on
                                           # that ONE line -- the only line in 972 to say gradle --
                                           # the way apache/kafka's GRADLE_HOME env dump did. A
                                           # cached artifact is not a build tool that ran.
    )""",
    re.VERBOSE | re.IGNORECASE,
)


# GitHub Actions echoes the SOURCE of a `run:` step -- every line of it -- before running
# it, wrapped in cyan-bold. Those lines are the step's PROGRAM TEXT, not its output, and a
# program's text says what it WOULD print, not what happened. astral-sh/ruff's benchmark job
# (killed by a Rust panic, `exit code: 101`) listed an error-handling branch it never took:
#
#     ^[[36;1m    echo "::error title=Failed to install CodSpeed CLI::Installation of ..."^[[0m
#
# and `FAILED .*::` -- pytest's short-summary line, matched case-insensitively -- read
# `Failed to install CodSpeed CLI::` off it and called that Rust panic a `python_test_failure`.
# No rule is safe from this: seven of ten real failing logs sampled (ruff, airflow, pydantic,
# tokio, vite, prometheus, httpx) echo a step body, and those bodies say `pnpm run lint`,
# `bail() {`, `exit 1`. A branch that never executed is not evidence that anything failed.
#
# Colour is the only thing marking these lines, and `_strip_ansi_escapes` erases it -- so they
# have to be found BEFORE the strip. Both normalizations are line-preserving, so a line number
# taken here still addresses the same content afterwards. What they are, once found, is a
# command echo like `Run mypy .` or `+ ruff check .`: it corroborates, it cannot carry. A tool
# that really failed also fails somewhere off the script listing.
_RUNNER_SCRIPT_ECHO_LINE = re.compile(r"^(?:\x1b|\^\[)\[36;1m")


def _runner_script_echo_bounds(raw: str, text: str) -> list[tuple[int, int]]:
    """Character spans, in the normalized ``text``, of the runner's echo of a step's source."""
    echoed = {
        index
        for index, line in enumerate(_strip_ci_log_line_prefixes(raw).splitlines())
        if _RUNNER_SCRIPT_ECHO_LINE.match(line)
    }
    if not echoed:
        return []
    bounds = []
    offset = 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        if index in echoed:
            bounds.append((offset, offset + len(line)))
        offset += len(line)
    return bounds


# `git checkout <ref>` prints `error: pathspec '<ref>' did not match any file(s) known to git`
# when the ref is not present -- and CI scripts trip that benignly all the time, then recover.
# A fork/enterprise dual-checkout tries the PR branch in the counterpart repo, misses, and falls
# back: grafana/grafana's lint-knip job (run 29806261731) logs
#
#     error: pathspec 'hugoh/add-enable-disable-app-plugin-e2e-tests' did not match ...
#     Already on 'main'
#     checked out main
#     Checkout succeeded, breaking retry loop
#
# and the job then ran on and died 1200 lines later on `knip`. A pathspec miss the log goes on
# to RECOVER from -- git confirms the checkout right after (`Already on`, `Switched to`, `HEAD is
# now at`) or a retry wrapper announces it (`Checkout succeeded`, `checked out`) -- is not why
# the job failed, so it should not carry `git_checkout_failure` on its own. Only this one
# non-fatal `error:` recovers; the terminal git failures (`fatal: reference is not a tree`,
# `fatal: repository ... not found`, a `smudge filter lfs failed`) do not print a recovery line
# after them, so a genuine checkout failure still witnesses. Scoring is untouched -- the pathspec
# still corroborates a real checkout failure that also tripped a fatal signal.
_PATHSPEC_MISS_LINE = re.compile(r"error: pathspec '.*' did not match", re.IGNORECASE)
_CHECKOUT_RECOVERED_LINE = re.compile(
    r"Checkout succeeded|checked out\b|Already on |Switched to |HEAD is now at ",
    re.IGNORECASE,
)
_CHECKOUT_RECOVERY_WINDOW = 8


def _recovered_checkout_bounds(text: str) -> list[tuple[int, int]]:
    """Spans of `pathspec did not match` lines the log then recovers the checkout from."""
    lines = text.splitlines(keepends=True)
    starts = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)
    bounds = []
    for index, line in enumerate(lines):
        if not _PATHSPEC_MISS_LINE.search(line):
            continue
        window = lines[index + 1 : index + 1 + _CHECKOUT_RECOVERY_WINDOW]
        if any(_CHECKOUT_RECOVERED_LINE.search(following) for following in window):
            bounds.append((starts[index], starts[index] + len(line)))
    return bounds


def _line_bounds(text: str, pattern: re.Pattern[str]) -> list[tuple[int, int]]:
    """Character spans of the lines in ``text`` that ``pattern`` matches."""
    bounds = []
    offset = 0
    for line in text.splitlines(keepends=True):
        if pattern.match(line):
            bounds.append((offset, offset + len(line)))
        offset += len(line)
    return bounds


# A tool's name inside a filesystem path is a filename, not a failure -- and a monorepo's CI
# log is mostly filenames. Every rule below was carried, on a real log, by a word that only
# ever appeared inside a path: oven-sh/bun's formatter listed `.../features/lockfile/index.ts`
# and `test/cli/install/GHSA-pfwx-36v6-832x.test.ts` -- a regression test named after an
# advisory -- as *unchanged*, and that was enough to diagnose the run as an outdated lockfile
# and then as a failed security scan. The file was passing. It was never even opened.
#
# Errors that happen to cite a path are untouched, because a match is only discounted when it
# STARTS inside the path token: `src/main.rs:12:5: error[E0277]` still witnesses on
# `error[E0277]`, and `FAIL tests/foo.test.ts` still witnesses on `FAIL`. What dies is the
# bare noun with nothing but a directory around it.
_PATH_TOKEN = re.compile(r"[\w.\-@+~]*(?:/[\w.\-@+]+)+")


def _path_token_bounds(text: str) -> list[tuple[int, int]]:
    """Character spans of the path-shaped tokens in ``text``."""
    return [match.span() for match in _PATH_TOKEN.finditer(text)]


# When a test suite asserts on the output of a tool, that tool's diagnostics become the test's
# DATA. A harness that reports a failing assertion prints them back -- the output it got, the
# output it expected -- and every one of those lines reads exactly like a compiler talking,
# because a compiler is what produced them. They are quotations, not diagnostics.
#
# denoland/deno's spec suite (`test specs`, run 29349357779) is 30MB of this: 1553 failing
# specs, each dumped as an actual/expected/debug triplet, carrying 4899 TypeScript diagnostics
# between them -- `TS2304 [ERROR]: Cannot find name 'Deno'`, `error: Type checking failed.` --
# nearly all of which are the CONTENTS OF A FIXTURE FILE the spec asserts against, named on the
# preceding `output path .../main.out` line. Deno's own tests deliberately typecheck broken
# programs. PatchRail read the fixtures and told the maintainer their types were broken, at 0.95
# confidence, when what had actually happened was that the spec suite panicked
# (`panicked at tests/specs/mod.rs:669`, exit code 101 -- Rust's).
#
# Two renderings, both machine-emitted and both delimited, so both can be excised exactly:
#
#   * deno's spec harness frames each side in `-- OUTPUT START --` / `-- EXPECTED START --` /
#     `-- DEBUG START --` blocks (the last block may be cut off when the log is truncated);
#   * `pretty_assertions`, which the harness uses for `assertion failed: `(left == right)``,
#     prints `Diff < left / right > :` and then the compared text itself, one line per line,
#     prefixed `<` (left), `>` (right) or a space (common). A blank line ends it.
#
# Errors the job itself emitted are untouched: they are outside these blocks by construction.
# A real `tsc` failure in a job that also runs deno's specs still witnesses on its own line, and
# a suite whose ONLY evidence is quoted output still stands as a last resort -- it defers to a
# rule that saw a real error, and here one did: the Rust tests that actually failed.
_ASSERTION_REPORT_BLOCK = re.compile(
    r"^[ \t]*--[ \t]*(OUTPUT|EXPECTED|DEBUG)[ \t]+START[ \t]*--[ \t]*$"
    r".*?"
    r"(?=^[ \t]*--[ \t]*\1[ \t]+END[ \t]*--[ \t]*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
_ASSERTION_DIFF_BODY = re.compile(
    r"^[ \t]*Diff[ \t]*<[ \t]*left[ \t]*/[ \t]*right[ \t]*>[ \t]*:[ \t]*$"
    r"(?:\n(?:[<>].*| .*))*",
    re.MULTILINE,
)


def _assertion_report_bounds(text: str) -> list[tuple[int, int]]:
    """Character spans of the output a test harness quotes back when an assertion fails."""
    return [match.span() for match in _ASSERTION_REPORT_BLOCK.finditer(text)] + [
        match.span() for match in _ASSERTION_DIFF_BODY.finditer(text)
    ]


# Dependabot runs its updater as a container and streams it back into the job log, docker-compose
# style: `updater | `, then a record from its own logger. Those records are Dependabot's
# bookkeeping, not the repository's job -- and the updater opens by echoing its JOB DEFINITION,
# one line of JSON naming every dependency it may touch and every PR already open. It names half
# the dependency tree without running any of it.
#
# sveltejs/svelte's security update (run 29330826741) died inside the updater, and the runner said
# so: `##[error]Dependabot encountered an error performing the update`. We told the Svelte
# maintainers their linter had failed, at 0.71 -- on ONE line, the job definition:
#
#     updater | 2026/07/14 11:59:49 INFO <job_1460286594> Job definition: {"job":{...
#       "existing-pull-requests":[...,{"pr-number":17594,"dependencies":[{"dependency-name":
#       "eslint","dependency-version":"9.26.0"}]},...
#
# No linter ran. 58 of that log's 59 `eslint` hits were already discounted as registry URLs the
# proxy fetched; this was the 59th, and one witness is all it takes to carry a verdict. It is the
# same blob #333 found `lockfile` inside (the config key `"gradle-lockfile-updater"`) and treated
# one failure class at a time -- so the cure belongs here instead, where the evidence is read.
# `never_invoked` then answers `unknown`, which hands the annotation back.
#
# What marks a record as the updater's OWN is the job id it files under, `<job_1460286594>` --
# Dependabot's, not the repository's. Output the updater forwards from a subprocess arrives on the
# same stream without one (`updater | rehash: warning: ...`), so a package manager that really
# failed under Dependabot -- `npm ERR! ERESOLVE` -- still witnesses on its own line. So does a
# record the updater files at an error level. The clock is optional because both renderings are
# in the wild: istio's updater logs `updater | INFO <job_1458843111>`, svelte's stamps the time.
_DEPENDABOT_UPDATER_RECORD = re.compile(
    r"""^[ \t]*updater[ \t]\|[ \t]+              # the updater container's stream prefix
        (?:\d{4}/\d{2}/\d{2}[ \t]+[\d:]+[ \t]+)?  # its clock, in the rendering that carries one
        (?!(?:ERROR|FATAL|PANIC)\b)             # an error it FILES is still an error
        [A-Z]+[ \t]+<job_\d+>                   # ... its level, and its own job id
    """,
    re.VERBOSE,
)


# A TAP report prints one `ok N` line per assertion that PASSED, and the assertion's
# description is whatever the test named itself -- application vocabulary, not a runner
# diagnostic. discourse/discourse's `Plugins QUnit` suite (run 29572043439) failed on six
# `not ok` chat-component timeouts, but its ONE witness for a secrets failure, at 0.53, was a
# test that GREEN-passed:
#
#     ok 1523 [564 ms] - poll - Acceptance: Poll Builder - polls are disabled:
#       regular user - insufficient permissions
#
# `insufficient permissions` is the scenario that test asserts the UI handles gracefully, not a
# credential the job lacked -- and it lands on a line that begins `ok `, TAP for "this passed".
# Read verbatim it sent a maintainer to `gh secret list` over the title of a passing test. A
# real permissions failure is untouched: it does not announce itself on a green TAP line, and
# the run's actual failures start `not ok` (so `.match` at line-start skips them) and carry
# nothing this rule keys on -- with no browser-QUnit class, `unknown` is the honest ceiling.
_TAP_PASSING_LINE = re.compile(r"ok \d+\b")


def _mention_only_bounds(text: str) -> list[tuple[int, int]]:
    """Character spans of the lines where a tool is named but never actually run."""
    return (
        _line_bounds(text, _MERE_MENTION_LINE)
        + _line_bounds(text, _AUDIT_SUMMARY_LINE)
        + _line_bounds(text, _DEPENDABOT_UPDATER_RECORD)
        + _line_bounds(text, _TAP_PASSING_LINE)
        + _path_token_bounds(text)
    )


def _non_failure_line_bounds(text: str) -> list[tuple[int, int]]:
    """Character spans of the lines that only name a command, rather than watch it fail."""
    return sorted(_line_bounds(text, _INVOCATION_LINE) + _mention_only_bounds(text))


def _matching_signals(text: str, patterns: list[str]) -> list[str]:
    return [
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    ]


def _signals_witnessing_failure(
    text: str, patterns: list[str], noise: list[tuple[int, int]]
) -> list[str]:
    """The signals in ``patterns`` that matched somewhere other than an echo/install line.

    Deliberately *not* used for scoring. An invocation next to a real error is honest
    corroboration -- it is what keeps a genuine dotnet or helm failure at full confidence
    -- so every matched signal still counts. What it must not do is carry a rule on its
    own: a rule with none of these has watched a tool get named, never fail.
    """
    witnessing = []
    for pattern in patterns:
        # Match against the whole text, not line by line: three patterns deliberately
        # span a newline (`Failed\n - hook id`, terraform's `╷\n │ Error:`). A match is
        # noise when it STARTS on an echo/install line.
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            if not any(start <= match.start() < end for start, end in noise):
                witnessing.append(pattern)
                break
    return witnessing


def _requirements() -> dict[str, Any]:
    return {
        "billing_required": False,
        "webhook_required_for_local_classification": False,
        "github_app_required_for_local_classification": False,
        "pr_creation_required": "no; write actions remain separate human-approved gates",
        "external_model_required": False,
    }


def redact_ci_log(text: str) -> dict[str, Any]:
    redacted = text
    counts: Counter[str] = Counter()
    for name, pattern, replacement in REDACTION_PATTERNS:
        redacted, count = re.subn(pattern, replacement, redacted, flags=re.IGNORECASE)
        if count:
            counts[name] += count
    return {
        "schema_version": "patchrail.redaction.v1",
        "text": redacted,
        "redactions": dict(sorted(counts.items())),
        "local_only": True,
    }


UNKNOWN_FAILURE_CLASS = "unknown"
UNKNOWN_LIKELY_SUBSYSTEM = "unknown"
UNKNOWN_REPRODUCTION_COMMAND = "inspect CI log and run the failing job locally"


# A log no rule matches usually still names its own failure: the Actions runner annotates
# the failing line for the web UI (``##[error]…``), and a step can emit the ``::error::``
# workflow command itself. That annotation is the runner's verdict, not a guess of ours, so
# an `unknown` answer can hand back the line the maintainer would have scrolled to instead
# of a shrug. It stays evidence and nothing more -- an annotation says where the job died,
# not why -- so the class stays `unknown` and the confidence stays put.
_RUNNER_ERROR_ANNOTATION = re.compile(
    r"^(?:##\[error\]|::error(?:\s.*?)?::)\s*(.+?)\s*$",
    re.MULTILINE,
)

_MAX_RUNNER_ERRORS = 5
_MAX_RUNNER_ERROR_CHARS = 300

# Not every annotation is evidence. The runner marks up each failing step the same way
# whatever went wrong -- "Process completed with exit code 1." appears in every failing log
# there is, and the workflow-level "Workflow failed because one or more jobs failed" only
# restates that something, somewhere, failed. Handing those back under "Errors the runner
# reported" dresses an empty answer up as a finding, which is the one thing an `unknown`
# verdict must never do. They also crowd out real evidence: each exit code is a distinct
# string, so a matrix build's worth of them survives de-duplication and fills the cap ahead
# of the annotation that names the failure. Dropped, an `unknown` log either carries a line
# worth reading or says nothing at all.
_RUNNER_ERROR_BOILERPLATE = (
    re.compile(r"process completed with exit code \d+\.?", re.IGNORECASE),
    re.compile(r"workflow failed because one or more jobs failed\.?", re.IGNORECASE),
)

# The error channel carries whatever a step writes to it, and some steps write a *success*
# through it: `oven-sh/bun` annotates its run with `##[error]✅ Autofix task started.`, the
# only annotation in 4,700 lines. Handed back under "start there", a line reporting that a
# task started fine is the same dead end the boilerplate above exists to prevent -- arriving
# through content rather than through the runner's own template.
#
# Reading content is a heuristic, so this one is deliberately lopsided towards keeping: an
# annotation is dropped only when it *opens* with a success mark AND names no failure
# anywhere in the line. `✅ Autofix task started.` goes; `✅ 2 passed, ❌ 1 failed` and
# `✔ image built, but the upload failed` both stay, because the failure is right there in
# them, and a tick further along the line never counts. A puzzling line a maintainer
# dismisses in a second costs far less than a real error we swallowed on their behalf.
_RUNNER_ERROR_SUCCESS_MARK = re.compile(r"^[✅✔✓☑🎉🟢]")
_RUNNER_ERROR_FAILURE_HINT = re.compile(
    r"error|fail|abort|fatal|panic|cannot|can not|can't|unable|denied|refus|reject"
    r"|invalid|missing|not found|timed out|timeout|exit code|❌|✗|✖|🔴",
    re.IGNORECASE,
)


def _announces_success(message: str) -> bool:
    """True for an annotation that opens with a success mark and reports no failure."""
    return bool(
        _RUNNER_ERROR_SUCCESS_MARK.match(message) and not _RUNNER_ERROR_FAILURE_HINT.search(message)
    )


def _runner_annotated_a_failure(text: str) -> bool:
    """True if the runner marked ANY genuine error -- boilerplate included.

    Deliberately NOT ``bool(_runner_error_annotations(text))``. That function drops
    ``Process completed with exit code 2`` because it is useless to *show* a maintainer, and
    that is the right call for evidence. It is the wrong call for this question: unreadable
    as it is, the line still proves that a step exited non-zero. A success announced through
    the error channel proves nothing, so it is excluded here for the same reason it is there.
    """
    return any(
        not _announces_success(message.strip())
        for message in _RUNNER_ERROR_ANNOTATION.findall(text)
    )


def _runner_error_annotations(text: str) -> list[str]:
    """Error lines the CI runner annotated itself, redacted and de-duplicated."""
    found: list[str] = []
    for message in _RUNNER_ERROR_ANNOTATION.findall(text):
        # This gets echoed back to the user, so it goes through the same redaction the
        # `redact` command applies: a log saved to disk can still carry the token that
        # Actions would have masked on the way out.
        message = redact_ci_log(message)["text"].strip()
        if any(pattern.fullmatch(message) for pattern in _RUNNER_ERROR_BOILERPLATE):
            continue
        if _announces_success(message):
            continue
        if len(message) > _MAX_RUNNER_ERROR_CHARS:
            message = message[: _MAX_RUNNER_ERROR_CHARS - 1].rstrip() + "…"
        if message and message not in found:
            found.append(message)
        if len(found) == _MAX_RUNNER_ERRORS:
            break
    return found


# An `unknown` with no runner annotation is the emptiest answer PatchRail can give: no class, no
# subsystem, no evidence -- `No high-confidence local signal found.` and nothing else. Declining is
# the honest call, but a maintainer who pipes 1,164 lines in and gets a shrug back is worse off than
# if they had scrolled to the bottom themselves, which is exactly what they do next. apache/kafka
# run 29805964231 is the case: the job dies one line above the boilerplate exit-code annotation, on
# `Could not find the PR that triggered this workflow request` -- three seconds of human scrolling,
# and PatchRail printed none of it.
#
# So when we cannot name the cause, we hand back the place we could not name it from. This is
# EXTRACTION, not classification: the class stays `unknown`, the confidence stays 0.15, and nothing
# below is ever read for meaning. The heuristic is POSITIONAL -- the last few lines that carried
# output -- and deliberately so. A lexical version ("look for `Could not find the PR`") would fix
# apache/kafka and no other log in the world; where the log stops is the same question in every
# ecosystem, including the ones no rule will ever cover.
#
# `unknown` is not the only answer that leaves a maintainer with nothing to read. A verdict under
# LOW_CONFIDENCE_THRESHOLD names a class it cannot prove -- rails/rails run 29648807728 comes back
# `ruby_bundle_failure` at 0.3 off three `bundle` invocations, and the report says out loud that
# this is a hint and the raw log is the thing to read. Saying "go read the log" while showing none
# of it is the same dead end as `unknown`, so the tail covers both. Same extraction, same cap, same
# redaction: only the condition that turns it on is wider.
_MAX_LOG_TAIL_LINES = 5
_MAX_LOG_TAIL_CHARS = 300

# Where the step's output stops and the runner's epilogue begins. `Process completed with exit code
# 1.` is the runner's own template -- the same string in every failing log there is, which is why
# `_RUNNER_ERROR_BOILERPLATE` already refuses to show it -- and everything the runner prints after
# it belongs to post-job cleanup, not to the job: caches saved, git config unwound, orphan processes
# reaped. Reading the tail from the end of the FILE would return that plumbing in every GitHub
# Actions log; reading it from here returns the last thing the step actually said.
_LOG_TAIL_EPILOGUE = re.compile(
    r"^##\[error\]\s*(?:process completed with exit code \d+\.?"
    r"|workflow failed because one or more jobs failed\.?)$",
    re.IGNORECASE,
)

# Lines that are structure, not output. The runner's fold markers (`##[group]`, `##[endgroup]`),
# its debug channel, and the cleanup headings say only that a section began or ended. Printed under
# "the log ends here" they push out lines a maintainer could have used.
_LOG_TAIL_NOISE = re.compile(
    r"^##\[(?:group|endgroup|section|debug)\]"
    r"|^post job cleanup\.?$"
    r"|^cleaning up orphan processes\.?$",
    re.IGNORECASE,
)


def _log_tail(raw: str, text: str) -> list[str]:
    """The last lines that carried output, redacted -- evidence of WHERE the log stopped.

    ``text`` must already be prefix- and colour-normalized (as it is inside
    :func:`classify_ci_log`); ``raw`` is needed only to find the colour-marked script echo, which
    the normalization erases.
    """
    lines = text.splitlines()
    # The runner echoes the step's own source before running it. Those lines are a listing of
    # branches that may never have executed -- `exit 1;` inside an `if` that was not taken reads
    # like a cause and is not one -- so they are as unwelcome here as they are in scoring.
    echoed = {
        index
        for index, line in enumerate(_strip_ci_log_line_prefixes(raw).splitlines())
        if _RUNNER_SCRIPT_ECHO_LINE.match(line)
    }
    end = len(lines)
    for index in range(len(lines) - 1, -1, -1):
        if _LOG_TAIL_EPILOGUE.match(lines[index].strip()):
            end = index
            break
    collected: list[str] = []
    for index in range(end - 1, -1, -1):
        if index in echoed:
            continue
        # Raw log goes out for the first time here, so it goes through the same redaction the
        # `redact` command applies. A log saved to disk still carries the token Actions would
        # have masked on the way out, and a leaked secret would break the one promise -- local,
        # nothing leaves the machine -- this product is built on.
        line = redact_ci_log(lines[index])["text"].strip()
        if not line or _LOG_TAIL_NOISE.match(line):
            continue
        if len(line) > _MAX_LOG_TAIL_CHARS:
            line = line[: _MAX_LOG_TAIL_CHARS - 1].rstrip() + "…"
        if line not in collected:
            collected.append(line)
        if len(collected) == _MAX_LOG_TAIL_LINES:
            break
    return list(reversed(collected))


# A verdict under this confidence was carried by evidence too thin to name a cause. The
# invocation-only guard lands such verdicts at 0.3, while any rule that actually watched something
# fail starts at 0.53 -- so the threshold separates "we recognized the tool" from "we recognized
# the failure" without naming a single class or ecosystem. It lives here, next to the confidence
# scale it reads, and the renderers import it: one number, one meaning.
LOW_CONFIDENCE_THRESHOLD = 0.35


def is_low_confidence(result: dict[str, Any]) -> bool:
    """Report whether a verdict is too weakly evidenced to be read as a diagnosis.

    `unknown` declines outright at 0.15 and a green log never diagnosed anything, so neither is
    "low confidence" in this sense -- both have their own answer to give.
    """
    if result.get("likely_successful_run"):
        return False
    if result.get("failure_class") == UNKNOWN_FAILURE_CLASS:
        return False
    try:
        confidence = float(result["confidence"])
    except (KeyError, TypeError, ValueError):
        return False
    return confidence < LOW_CONFIDENCE_THRESHOLD


def _attach_log_tail(result: dict[str, Any], raw: str, text: str) -> None:
    """Give the report the end of the log whenever the verdict cannot stand on its own.

    Two verdicts qualify and they fail the reader the same way: `unknown`, which names nothing,
    and a sub-threshold class, which names something it cannot prove. Neither leaves anything to
    read. A runner annotation outranks the tail -- the runner naming the error beats us pointing
    at where output stopped -- and a successful run has no failure to point at.
    """
    if result.get("runner_errors") or result.get("likely_successful_run"):
        return
    if result.get("failure_class") != UNKNOWN_FAILURE_CLASS and not is_low_confidence(result):
        return
    tail = _log_tail(raw, text)
    if tail:
        result["log_tail"] = tail


# A maintainer's first run is often a GREEN one: they pipe in whatever `gh run view` hands
# back, or point PatchRail at a build that passed, before they have a failure to triage. That
# log matches no failure rule, so it lands on `unknown` at 0.15 -- the very same answer a
# genuinely unrecognized *failure* gets, down to the invitation to open a CI failure fixture
# issue. Nudging someone to file a fixture for a build that never failed is worse than
# unhelpful: it pollutes the tracker with non-failures. When the log plainly announces success
# and betrays no failure, say that instead.
_SUCCESS_ANNOUNCEMENT = re.compile(
    r"\bbuild succeeded\b"
    r"|\bbuild successful\b"
    r"|\bBUILD SUCCESS\b"
    r"|\ball checks (?:have )?passed\b"
    r"|\ball (?:\d+ )?tests? passed\b"
    r"|\b[1-9]\d* passed\b"
    r"|\b(?:job|run|pipeline|workflow|stage|suite) (?:succeeded|passed)\b"
    r"|\b(?:completed|finished) successfully\b"
    r"|\bsuccessfully (?:built|compiled|completed|finished|installed|published)\b"
    r"|\bprocess completed with exit code 0\b"
    r"|\bexit code:? 0\b",
    re.IGNORECASE,
)

# Any of these vetoes the success reading. Counts are read numerically so `0 failed` and
# `no errors` stay green while `3 failed` and `1 error` do not; the bare words `failed`/`error`
# are far too common in benign lines (`0 failed`, `error-handling.ts`, `on error resume`) to
# veto on their own.
_FAILURE_TELL = re.compile(
    r"\bprocess completed with exit code [1-9]"
    r"|\bexit(?:ed)? (?:with )?code:? [1-9]"
    r"|\bbuild (?:failed|failure)\b"
    r"|\bBUILD FAILED\b"
    r"|\b[1-9]\d* (?:tests? )?(?:failed|failing|failures?|errors?)\b"
    r"|\btraceback \(most recent call last\)"
    r"|\bpanic(?:ked)?\b"
    r"|^\s*(?:fatal|error)[: ]",
    re.IGNORECASE | re.MULTILINE,
)


def _looks_like_successful_run(text: str) -> bool:
    """True when the log plainly reports success and betrays no failure.

    Conservative on purpose: it is consulted only from the `unknown` path, where no rule
    witnessed a failure, and it still demands an explicit success announcement AND the absence
    of any failure tell (a runner-annotated error, a non-zero exit, a real failure count). A
    failure that slips past every rule keeps its plain `unknown` verdict -- the invitation to
    file a fixture is the right answer there.
    """
    if _runner_annotated_a_failure(text):
        return False
    if _FAILURE_TELL.search(text):
        return False
    return bool(_SUCCESS_ANNOUNCEMENT.search(text))


def list_failure_classes() -> dict[str, Any]:
    """List every supported failure class in stable rule order.

    Emits ``failure_class``, ``likely_subsystem`` and ``reproduction_command``
    for each rule. This is the machine-readable inventory of what PatchRail can
    diagnose locally, without having to read the source ``RULES`` table.

    ``unknown`` is reported separately under ``fallback``: it is the result
    ``ci explain`` returns when no rule matches, not something the classifier
    can diagnose. Keeping it out of ``classes``/``count`` means the README
    documented use — ``ci classes --format json`` to check coverage from a
    script — measures against a denominator every entry of which is reachable.
    """
    classes = [
        {
            "failure_class": rule["failure_class"],
            "likely_subsystem": rule["likely_subsystem"],
            "reproduction_command": rule["reproduction_command"],
        }
        for rule in RULES
    ]
    return {
        "schema_version": "patchrail.ci_classes.v2",
        "count": len(classes),
        "classes": classes,
        "fallback": {
            "failure_class": UNKNOWN_FAILURE_CLASS,
            "likely_subsystem": UNKNOWN_LIKELY_SUBSYSTEM,
            "reproduction_command": UNKNOWN_REPRODUCTION_COMMAND,
        },
    }


# Patterns in ``network_transient_failure`` that, on their own, do NOT prove a
# transient outage: they routinely appear *inside* a deterministic test or build
# failure (a Go test dialing a service that never started, a gRPC deadline in a
# broken test, a socket reset in a failing integration case). A genuine outage
# also trips a terminal signal (DNS resolution, rate limit, gateway error, TLS
# handshake, or a git remote hang-up), none of which are in this set.
AMBIGUOUS_NETWORK_PATTERNS = frozenset(
    {
        r"\bECONNREFUSED\b",
        r"Connection refused",
        r"\bECONNRESET\b",
        r"Connection reset by peer",
        r"\bi/o timeout\b",
        r"context deadline exceeded",
        r"\bdial tcp\b",
    }
)


# Patterns in ``runner_resource_exhaustion`` that describe a process killed for
# memory but never say WHOSE: a container under test hitting its own cgroup limit,
# a Go test's exec being reaped, an `OOMKilled` status line an integration suite
# prints because it provokes the kill on purpose. A container runtime's tests
# (containerd, runc, k8s) trip every one of these by design while a Go test two
# lines up is the thing that actually failed. A genuine runner exhaustion also
# trips a terminal signal -- the runner's OWN `Process completed with exit code
# 137`, a disk `No space left on device`/`ENOSPC`, a build `JavaScript heap out of
# memory`/`runtime: out of memory` -- none of which are in this set, so it keeps
# winning.
AMBIGUOUS_RESOURCE_PATTERNS = frozenset(
    {
        r"OOMKilled",
        r"Out of memory",
        r"signal: killed",
        r"\bexit code 137\b",
    }
)


# The generic GNU make recipe-failure line -- `make: *** [Makefile:140: std_spec] Error 1`
# -- in ``cpp_build_failure``. It says a make TARGET failed, and nothing about what the
# target does: make drives test suites, doc builds, linters and packaging in every language.
# The zoo alone has it firing under Sphinx docs, a Go integration test and a shellcheck lint;
# crystal-lang/crystal's stdlib specs fail through `make std_spec` on a `Socket::BindError`,
# and that recipe line was the ENTIRE case for a `cpp_build_failure` 0.53 -- handing a Crystal
# maintainer `cmake --build build` for a socket bind in a spec. A genuine C/C++ build also
# trips a real toolchain signal (`CMake Error`, `undefined reference`, `clang: error`,
# `cc1plus`, a missing `.h`), none of which are in this set, so it keeps winning -- the recipe
# line rides along as corroboration but never carries the verdict alone.
AMBIGUOUS_MAKE_PATTERNS = frozenset(
    {
        r"g?make(?:\[\d+\])?: \*\*\* \[[^\]]*\] Error \d+",
    }
)


# The RSpec-style summary line -- `18017 examples, 0 failures, 1 errors, 30 pending` -- in
# ``ruby_bundle_failure``. RSpec is not the only framework that prints it: Crystal's built-in
# Spec copies RSpec's output verbatim, so crystal-lang/crystal's `make std_spec` run emitted
# exactly this line off a `Socket::BindError` and scored `ruby_bundle_failure` 0.53 once the
# make line above deferred -- handing a Crystal maintainer `bundle exec rake test`. The line
# witnesses that a spec suite reported failures; it does not pin the ecosystem to Ruby. Every
# genuine RSpec fixture and the mastodon real-world log ALSO trip a Ruby-exclusive signal
# (`bundle exec`, `rake aborted!`, the `rspec ./<path>_spec.rb` rerun line whose `.rb` Crystal's
# `crystal spec spec/...cr` never matches), so a real Ruby failure keeps winning; the summary
# line rides along as corroboration but never carries the Ruby verdict alone.
AMBIGUOUS_SPEC_SUMMARY_PATTERNS = frozenset(
    {
        r"\b\d+ examples?, (?:\d+ \w+, )*\d+ failures?\b",
    }
)


# Patterns that prove a tool RAN, not that it failed. `docker build` shows up in
# every job that builds a container as a setup step; `cargo test` and `clippy` show
# up in the command line of every Rust CI job, passing or not. They are useful
# corroboration next to a real error -- they keep a genuine docker or clippy failure
# at full confidence -- but a rule carried by nothing else has only established that
# a command was executed. Scoring is by matched-pattern count, so such a rule can tie
# and, on declaration order alone, outrank the rule that matched the actual error:
# a real rust-lang/rust build failure (`error[E0277]`) scored as docker_build_failure
# purely because the job happened to run `docker buildx build` first.
INVOCATION_ONLY_PATTERNS = frozenset(
    {
        r"\bdocker build\b",
        r"\bdocker buildx build\b",
        r"\bdocker compose\b",
        r"\bcargo test\b",
        r"\bclippy\b",
        # "Run actions/upload-artifact@v4" is in the log of every job that uploads
        # anything, passing or failing.
        r"actions/(?:upload|download)-artifact",
        # The same argument, and the same bug, for every other tool we recognise by name.
        # A monorepo says these words constantly without any of them failing: oven-sh/bun's
        # formatter listed `packages/bun-vscode/.../lockfile/index.ts` and
        # `test/cli/install/*.test.ts` as *unchanged* and passing, and that alone -- the bare
        # words `prettier`, `jest`, `bundler` -- was four different rules' entire case.
        # istio/istio, a Go repo, matched `gradle` inside the key `"gradle-lockfile-updater"`
        # of the JSON config Dependabot echoes. Each of these rules keeps a real error
        # pattern of its own to stand on (`lint failed`, `Tests: 3 failed`, `Bundler could
        # not find compatible versions`, `COMPILATION ERROR`, `CVE-2024-...`); the name is
        # corroboration next to one, never a verdict without one.
        r"\beslint\b",
        r"\bbiome\b",
        r"prettier",
        r"\bjest\b",
        r"\bvitest\b",
        r"\bmocha\b",
        r"\bjasmine\b",
        r"jest --",
        r"vitest run",
        r"npx (?:jest|vitest|mocha)",
        r"npm (?:run )?test",
        r"\bbundler\b",
        r"\bbundle install\b",
        r"\bbundle exec\b",
        r"\bmvn\b",
        r"\bgradle\b",
        r"\bnpm audit\b",
        r"\bpip-audit\b",
        r"\bcargo audit\b",
        r"\btrivy\b",
        r"\bgosec\b",
        r"\bsnyk\b",
        r"\bsemgrep\b",
        r"\bbandit\b",
    }
)


# Patterns that are an explicit *warning*, not a failure. upload-artifact emits "No files
# were found with the provided path" when its glob matches nothing -- it says as much
# itself ("No artifacts will be uploaded") and, under the default
# ``if-no-files-found: warn``, does not fail the step.
#
# Together with the invocation above, this is the single most common shape in CI: a test
# fails, and the ``if: failure()`` step that uploads logs/screenshots/coverage for
# diagnosis finds nothing to upload and warns. That is noise from the cleanup that runs
# *after* the failure, not the cause of it -- yet the two signals tie and then win on
# declaration order. apache/airflow's pytest failure was classified
# ``artifact_or_cache_failure`` on exactly this pair. A genuine artifact or cache failure
# is unaffected: it trips a terminal signal ("Failed to CreateArtifact", "Artifact upload
# failed", "Cache service responded with 500"), none of which are in these sets.
#
# A cache SAVE failure is the same shape, and the action says so in its own source:
# `actions/cache`'s `saveImpl` wraps the whole save in `try { ... } catch { logWarning(...) }`
# -- every save error is reported through `core.warning`, never `core.setFailed`, so it
# cannot be why a job failed. The runner agrees on the wire: pandas-dev/pandas emitted
#
#     ##[warning]Failed to save: Unable to reserve cache with key micromamba-downloads
#     --linux-64, another job may be creating this cache.
#
# on the WARNING channel, and the job then ran on and died 2000 lines later on
# `##[error]Process completed with exit code 2`. Two matrix jobs racing for one cache key is
# the most ordinary event in a big CI matrix, and it is not a failure -- the message says as
# much ("another job may be creating this cache").
#
# A genuine cache failure is untouched, and the toolkit draws the line in the same place:
# "warning for most failures, info for benign concurrency races, ERROR for 5xx". The 5xx is
# `Cache service responded with \d+`, which stays terminal, along with `getCacheEntry
# failed`, `reserveCache failed` and `Cache upload failed`. None are in this set.
BENIGN_WARNING_PATTERNS = frozenset(
    {
        r"No files were found with the provided path",
        r"Failed to save:? .*[Cc]ache",
        r"Unable to reserve cache",
        # Yarn Berry tags EVERY line it prints -- success, info, warning, error -- with a
        # `YNxxxx` code, so the bare code witnesses that yarn spoke, not that the install broke.
        # `YN0000` is literally "Done"/"Completed"; the peer-dependency family (`YN0002` missing
        # peer dep, `YN0060` incompatible dependency, `YN0086` peer deps incorrectly met) are
        # warnings it prints while installing perfectly well. grafana/grafana's lint-knip job
        # (run 29806261731) installed cleanly (`YN0000: Done with warnings`) and then failed on
        # `knip` (unused dependencies) and a `yarn constraints` check -- yet `YN\d{4}`, read off
        # those peer warnings and joined by `peer dep`, scored it `node_dependency_install` at
        # 0.71 and handed the maintainer `corepack pnpm install` (the wrong package manager too)
        # as the way to reproduce a working install. A genuine install failure is untouched: it
        # trips a terminal signal (`YN0028`'s "lockfile would have been modified by this
        # install", `ERESOLVE`, "error An unexpected error occurred") that stays a verdict on its
        # own, so the code rides along only as corroboration -- like `peer dep` beside it.
        r"YN\d{4}",
    }
)


# Patterns that NAME a thing without asserting anything about it. A bare noun is not an
# error, and in a monorepo it is everywhere: `\blockfile\b` matched a path in prettier's
# list of files it left *unchanged* (`packages/bun-vscode/src/features/lockfile/index.ts`
# -- oven-sh/bun), a key inside the JSON config Dependabot echoes on one 2929-char line
# (`"lockfile-only":false` -- istio/istio, a Go repo), and `--no-frozen-lockfile`, the flag
# that explicitly *permits* the lockfile to change. `peer dep` matched pnpm's "Issues with
# peer dependencies found", a warning it prints while installing perfectly well; the forms
# that mean a peer conflict actually failed the install (`ERESOLVE`, `Conflicting peer
# dependency`) are separate patterns and are unaffected.
#
# All three real logs above were `node_dependency_install` at 0.53-0.71 -- two of them in
# repos with no Node dependency install anywhere in the job -- and each handed its
# maintainer `corepack pnpm install --frozen-lockfile || npm ci` as the way to reproduce a
# Go or Zig failure. A wrong ecosystem with a confident number on it costs more than
# `unknown`, which at least prints the line the runner reported.
#
# These still earn their keep as corroboration: every one of the 21 genuine
# node_dependency_install fixtures also trips a real error signal, so the noun rides along
# and keeps the confidence up. It just may no longer carry a verdict on its own.
MENTION_ONLY_PATTERNS = frozenset(
    {
        r"\blockfile\b",
        r"peer dep",
    }
)


# A rule carried by nothing but these has established that a step ran, or warned -- never
# that it failed.
NON_FAILURE_PATTERNS = INVOCATION_ONLY_PATTERNS | BENIGN_WARNING_PATTERNS | MENTION_ONLY_PATTERNS

# What a verdict is worth when invocations are the only thing holding it up: a lead, printed
# below every fixture floor in the zoo (0.7), and plainly above the 0.15 of a decline. See the
# guard next to the confidence computation in `classify_ci_log`.
_INVOCATION_ONLY_CONFIDENCE = 0.3


def _is_non_failure_only(signals: list[str]) -> bool:
    return bool(signals) and set(signals) <= NON_FAILURE_PATTERNS


def _is_mention_only(signals: list[str]) -> bool:
    return bool(signals) and set(signals) <= MENTION_ONLY_PATTERNS


def _is_ambiguous_noise_match(rule: dict[str, Any], signals: list[str]) -> bool:
    """A broad rule carried only by signals that name a *symptom*, not a culprit.

    ``network_transient_failure`` off nothing but `connection refused`/`context
    deadline exceeded`, or ``runner_resource_exhaustion`` off nothing but
    `OOMKilled`/`Out of memory`, is the kind of network- or memory-shaped noise a
    deterministic failure throws off. When one such rule defers, the concrete cause
    it hands to must not be the *other* one -- a container runtime's suite trips both
    at once -- so both are excluded from the handoff together.
    """
    failure_class = rule["failure_class"]
    if failure_class == "network_transient_failure":
        return bool(signals) and set(signals) <= AMBIGUOUS_NETWORK_PATTERNS
    if failure_class == "runner_resource_exhaustion":
        return bool(signals) and set(signals) <= AMBIGUOUS_RESOURCE_PATTERNS
    if failure_class == "cpp_build_failure":
        return bool(signals) and set(signals) <= AMBIGUOUS_MAKE_PATTERNS
    if failure_class == "ruby_bundle_failure":
        return bool(signals) and set(signals) <= AMBIGUOUS_SPEC_SUMMARY_PATTERNS
    return False


def _highest_scoring_rule(
    scored: list[tuple[dict[str, Any], list[str]]],
    carrying: dict[str, list[str]] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """The rule matching the most signals. A TIE goes to the one that saw the most fail.

    Scoring stays most-matching-patterns-wins. The tie is what changes. A tie used to be
    settled by declaration order in ``RULES`` -- a coin flip, and one the comment above
    ``BENIGN_WARNING_PATTERNS`` already names as the mechanism behind a misdiagnosis.
    prometheus/prometheus -- a Go repo, whose Go tests failed -- lost that flip:
    `javascript_lint` matched three signals, `go_test_failure` matched three, and
    `javascript_lint` is declared first. A Go maintainer was handed `pnpm lint` as the way to
    reproduce a Go test failure.

    Not all three signals are equal, though, and the log says so. `javascript_lint`'s three
    were `eslint` and `prettier`, read off pnpm's listing of the web UI's *installed
    packages*, and `no-unused-vars`, read off an eslint WARNING from a build that exited 0.
    `go_test_failure`'s three were `--- FAIL:`, `FAIL\\t` and `go test`, off the Go test that
    actually died.

    So a tie is broken by the signals that CARRY: matched away from an echo/install line
    (they witnessed something) and not one of the bare tool names in
    ``NON_FAILURE_PATTERNS`` (a name is corroboration, never a verdict on its own -- the same
    rule the deferrals below already enforce). Both facts are already computed; only the
    tiebreak reads them. Counting a bare name here would resurrect exactly what those
    deferrals exist to bury: oven-sh/bun's formatter listing files it left `(unchanged)`
    witnesses `prettier` off `[prettier]`, and would take the tie on nothing at all.

    A rule that wins on signal count outright is untouched, so no genuine verdict moves, and
    a tie that carrying signals cannot separate still falls back to declaration order.
    """
    best_rule: dict[str, Any] | None = None
    best_signals: list[str] = []
    best_rank = (0, 0)
    for rule, signals in scored:
        carried = len(carrying.get(rule["failure_class"], ())) if carrying else 0
        rank = (len(signals), carried)
        if rank > best_rank:
            best_rule = rule
            best_signals = signals
            best_rank = rank
    return best_rule, best_signals


def classify_ci_log(text: str) -> dict[str, Any]:
    raw = text
    # Colour first: an escape sequence sitting between the job columns and the timestamp
    # would otherwise defeat the line-prefix match too.
    text = _strip_ci_log_line_prefixes(_strip_ansi_escapes(text))
    scored = [(rule, _matching_signals(text, list(rule["patterns"]))) for rule in RULES]
    scored = [(rule, signals) for rule, signals in scored if signals]

    # Which rules actually saw a failure, as opposed to seeing a tool named on a `set -x`
    # echo, an Actions step header, a pip install line, the runner's echo of the step's
    # own source, or a test harness quoting back the output it compared. Scoring is untouched
    # by this; winning is not.
    noise = (
        _non_failure_line_bounds(text)
        + _runner_script_echo_bounds(raw, text)
        + _assertion_report_bounds(text)
        + _recovered_checkout_bounds(text)
    )
    witnessing = {
        rule["failure_class"]: _signals_witnessing_failure(text, signals, noise)
        for rule, signals in scored
    }
    unwitnessed = {failure_class for failure_class, seen in witnessing.items() if not seen}

    # Of those, the signals that could carry a verdict alone: a bare tool name witnesses
    # nothing even when it lands off an echo line -- `[prettier]`, printed beside a file the
    # formatter left unchanged, is not evidence that anything failed. Used only to break ties.
    carrying = {
        failure_class: [pattern for pattern in seen if pattern not in NON_FAILURE_PATTERNS]
        for failure_class, seen in witnessing.items()
    }

    # Stricter than unwitnessed: a rule every one of whose signals landed on a line that only
    # ever MENTIONS a tool -- an env export, a CMake probe, a JSON config key, an installer's
    # advice to go run something -- has not just missed the failure, it has watched a tool
    # that never ran. It cannot stand even as a last resort, the way an invocation can.
    mentions = _mention_only_bounds(text)
    never_invoked = {
        rule["failure_class"]
        for rule, signals in scored
        if not _signals_witnessing_failure(text, signals, mentions)
    }

    def carried_by_noise_alone(rule: dict[str, Any], signals: list[str]) -> bool:
        return _is_non_failure_only(signals) or rule["failure_class"] in unwitnessed

    best_rule, best_signals = _highest_scoring_rule(scored, carrying)

    # A broad "transient network" match built ENTIRELY from ambiguous signals
    # (dial tcp / connection refused / context deadline exceeded / i/o timeout …)
    # usually means a deterministic test or build failure produced network-shaped
    # noise, not that the network is at fault. Don't let it mask a concrete cause
    # the maintainer must actually fix: defer to the best non-transient rule when
    # one also matched. A real outage keeps winning because it also trips a
    # terminal network signal outside the ambiguous set.
    if (
        best_rule is not None
        and best_rule["failure_class"] == "network_transient_failure"
        and set(best_signals) <= AMBIGUOUS_NETWORK_PATTERNS
    ):
        alternative_rule, alternative_signals = _highest_scoring_rule(
            [
                (rule, signals)
                for rule, signals in scored
                if rule["failure_class"] != "network_transient_failure"
            ],
            carrying,
        )
        if alternative_rule is not None:
            best_rule = alternative_rule
            best_signals = alternative_signals

    # A broad "the runner ran out of memory/disk" match built ENTIRELY from ambiguous
    # kill signals (OOMKilled / Out of memory / signal: killed / exit code 137) usually
    # means a container or process UNDER the job was killed -- a container runtime's
    # integration suite provokes exactly these -- not that the CI runner hit a host
    # limit. Don't let it mask the concrete cause the maintainer must fix: defer to the
    # best rule that is NOT itself an ambiguous-noise match. The same container-runtime
    # suite also logs `connection refused` from an upgrade test, so a plain
    # non-resource handoff would just trade one ambiguous verdict for another; the
    # concrete cause (the Go test that actually failed) is the honest answer. A real
    # runner exhaustion keeps winning because it also trips a terminal signal (the
    # runner's own exit-137 annotation, No space left on device, a build heap OOM)
    # outside the ambiguous set.
    if (
        best_rule is not None
        and best_rule["failure_class"] == "runner_resource_exhaustion"
        and set(best_signals) <= AMBIGUOUS_RESOURCE_PATTERNS
    ):
        alternative_rule, alternative_signals = _highest_scoring_rule(
            [
                (rule, signals)
                for rule, signals in scored
                if not _is_ambiguous_noise_match(rule, signals)
            ],
            carrying,
        )
        if alternative_rule is not None:
            best_rule = alternative_rule
            best_signals = alternative_signals

    # A "C/C++ build failed" match built ENTIRELY from the generic GNU make recipe line
    # (`make: *** [target] Error N`) has established only that SOME make target failed. Defer
    # to the best rule that saw a real error. Unlike the network/resource symptoms above,
    # which at least name their own category, the bare recipe line names no ecosystem -- make
    # drives specs, docs and linters in every language -- so when nothing else matched the
    # honest answer is `unknown`, not a C/C++ verdict on a project (crystal-lang/crystal's
    # `make std_spec`) that never compiled one. A genuine C/C++ build keeps winning: it also
    # trips a toolchain signal outside this set, so its match is never ambiguous-only.
    if (
        best_rule is not None
        and best_rule["failure_class"] == "cpp_build_failure"
        and set(best_signals) <= AMBIGUOUS_MAKE_PATTERNS
    ):
        best_rule, best_signals = _highest_scoring_rule(
            [
                (rule, signals)
                for rule, signals in scored
                if not _is_ambiguous_noise_match(rule, signals)
            ],
            carrying,
        )

    # A "Ruby suite failed" match built ENTIRELY from the RSpec-style summary line has
    # established only that SOME spec framework reported failures -- Crystal's Spec prints the
    # identical line. Defer to the best rule that saw a Ruby-specific error; when nothing else
    # matched, the honest answer is `unknown`, not `bundle exec rake test` for a language whose
    # specs live in `.cr` files. A genuine RSpec failure keeps winning: it also trips a
    # Ruby-exclusive signal outside this set, so its match is never summary-only.
    if (
        best_rule is not None
        and best_rule["failure_class"] == "ruby_bundle_failure"
        and set(best_signals) <= AMBIGUOUS_SPEC_SUMMARY_PATTERNS
    ):
        best_rule, best_signals = _highest_scoring_rule(
            [
                (rule, signals)
                for rule, signals in scored
                if not _is_ambiguous_noise_match(rule, signals)
            ],
            carrying,
        )

    # Same rule, different noise: a match built ENTIRELY from invocation or benign-warning
    # signals says a step ran or warned, not that it failed. Defer to the best rule that
    # matched a real error. If nothing else matched, it stands -- it is the only thing the
    # log gave us.
    #
    # The handoff must not resurrect a rule the make/summary deferrals above already ruled
    # unable to carry a verdict alone. Those deferrals only run while such a rule is best, so a
    # benign-warning rule that outscored one slips past them: ocaml/dune's `make: *** [test]
    # Error 1` (its cram suite, not a C/C++ compile) matches `cpp_build_failure` once, while a
    # two-line `Unable to reserve cache` save-warning gives `artifact_or_cache_failure` the
    # higher count -- so the make-defer never sees cpp as best, then this handoff would hand
    # the verdict straight back to that same make-only rule. Re-excluding it here keeps the
    # deferral honest whatever the route: the save-warning stays best and the benign-warning
    # guard below settles it to `unknown`. Only the ecosystem-blind lines qualify (the bare
    # make recipe, the RSpec-style summary); the resource/network symptoms name their own
    # category and can still stand as a last resort, so they remain eligible here -- a
    # buildkite job OOM-killed at `exit code 137` keeps `runner_resource_exhaustion`. A genuine
    # C/C++ build is untouched: it trips a real toolchain signal, so it is never make-only.
    if best_rule is not None and carried_by_noise_alone(best_rule, best_signals):
        alternative_rule, alternative_signals = _highest_scoring_rule(
            [
                (rule, signals)
                for rule, signals in scored
                if not carried_by_noise_alone(rule, signals)
                and not (
                    rule["failure_class"] in ("cpp_build_failure", "ruby_bundle_failure")
                    and _is_ambiguous_noise_match(rule, signals)
                )
            ],
            carrying,
        )
        if alternative_rule is not None:
            best_rule = alternative_rule
            best_signals = alternative_signals

    # Nothing else matched, and the one rule that did never saw its tool run. `unknown` is not
    # a failure to answer here, it is the answer: apache/kafka's `check-pr-labels` job is not a
    # Gradle build because the runner image exports GRADLE_HOME.
    if best_rule is not None and best_rule["failure_class"] in never_invoked:
        best_rule, best_signals = None, []

    # And a rule left holding nothing but a noun it read off a filename or a config key has
    # not watched anything fail either -- so, like the above, it cannot stand as a last
    # resort. An invocation at least proves the tool ran; a mention does not even prove that.
    if best_rule is not None and _is_mention_only(best_signals):
        best_rule, best_signals = None, []

    # Nor can a rule that only ever WARNED -- once we can see the warning was not the cause.
    # The deferral above hands off to the best rule that saw a real error, but when nothing
    # else matched it lets the noise-carried rule stand, on the grounds that it is "the only
    # thing the log gave us". That holds for a warning in an otherwise quiet log whose outcome
    # we cannot read: there may be a failure to explain, and one lead beats none.
    #
    # It inverts the moment the log settles that outcome, in either direction. A benign
    # warning provably did not cause the job to fail, so once we know a failure happened
    # ELSEWHERE -- or that none happened at all -- the warning is not a lead worth handing back.
    #
    #   * The runner annotates an error: a step provably exited non-zero, and it was not this
    #     save. `actions/cache` settles that in its own source: `saveImpl` wraps the save in
    #     `try { ... } catch { logWarning(...) }`, so a save error goes out through
    #     `core.warning`, never `core.setFailed`. Whatever failed is elsewhere; we did not find it.
    #   * The log plainly announces success and betrays no failure (`_looks_like_successful_run`
    #     -- an explicit success line, no runner error, no failure tell): there is no failure at
    #     all for the warning to be. pandas-dev/pandas's Doc Build (issue #347) is this case in a
    #     log truncated before the crash -- all we captured is a micromamba env build that ends
    #     `Successfully built`, then `Post job cleanup` racing two matrix jobs for one cache key
    #     (`##[warning]Failed to save: Unable to reserve cache ... another job may be creating
    #     this cache`). Handed back verbatim that was `artifact_or_cache_failure` at 0.89 --
    #     sending the maintainer to debug a cache that was working. `unknown` at 0.15 (with
    #     `likely_successful_run`) says the true thing: this log shows no failure.
    #
    # A genuine artifact or cache failure is untouched: it trips a terminal signal (`Failed to
    # CreateArtifact`, `Cache service responded with 500`, `an artifact with this name already
    # exists`) outside these sets, so it never reaches here. A pure invocation-only match still
    # stands; so does a benign warning in a log that neither announces success nor shows a
    # runner error -- an unrecognized failure keeps its one lead.
    if (
        best_rule is not None
        and _is_non_failure_only(best_signals)
        and any(signal in BENIGN_WARNING_PATTERNS for signal in best_signals)
        and (_runner_annotated_a_failure(text) or _looks_like_successful_run(text))
    ):
        best_rule, best_signals = None, []

    # Last word on a transient-network verdict that only ambiguous signals ever carried: if
    # the runner itself annotated the error, that annotation beats our guess. istio/istio's
    # Dependabot job dies with `##[error]Dependabot encountered an error performing the
    # update`; the sole network evidence is Dependabot's own MITM proxy logging `connection
    # reset by peer` at its client, by design, dozens of times. The deferral above cannot
    # catch this on its own -- it hands off to `node_dependency_install`, matched by the bare
    # word `lockfile` inside the JSON config key `"gradle-lockfile-updater"`, and the noise
    # guard then bounces that mention-only rule straight back here. So this runs last, once
    # the verdict has settled, whatever route it took to get here. A genuine outage is
    # untouched: it trips a terminal signal (DNS, TLS, rate limit, gateway) outside the
    # ambiguous set and so never qualifies. Boilerplate annotations ("Process completed with
    # exit code 1") are already filtered, so a surviving one is a message worth reading --
    # and `unknown` hands it back under `runner_errors`.
    if (
        best_rule is not None
        and best_rule["failure_class"] == "network_transient_failure"
        and set(best_signals) <= AMBIGUOUS_NETWORK_PATTERNS
        and _runner_error_annotations(text)
    ):
        best_rule, best_signals = None, []

    # The same last word, for the same reason, on any verdict left standing as a LAST RESORT:
    # a rule none of whose signals ever witnessed a failure won only because its tool got
    # named -- on a step header, a `set -x` echo, a package script. Naming is a defensible
    # guess when the log offers nothing else. It is not a guess worth making when the runner
    # has already said what broke. withastro/astro's Windows smoke job dies in a build script
    # (`##[error]@benchmark/timer#build: command ... exited (-1073741502)`); the only lint
    # evidence is `eslint`, `biome` and `prettier` echoed in turbo's `##[group]` headers as
    # the build walks the monorepo, and that alone was enough to call it `javascript_lint` at
    # 0.89. A rule that actually watched something fail is untouched -- it witnesses off these
    # lines and never reaches here -- so every genuine verdict keeps its confidence.
    if (
        best_rule is not None
        and best_rule["failure_class"] in unwitnessed
        and _runner_error_annotations(text)
    ):
        best_rule, best_signals = None, []

    if best_rule is None or not best_signals:
        result = {
            "schema_version": "patchrail.ci_result.v1",
            "failure_class": UNKNOWN_FAILURE_CLASS,
            "likely_subsystem": UNKNOWN_LIKELY_SUBSYSTEM,
            "reproduction_command": UNKNOWN_REPRODUCTION_COMMAND,
            "minimal_repair_strategy": (
                "Do not auto-repair until the failing subsystem is identified."
            ),
            "confidence": 0.15,
            "signals": [],
            "requirements": _requirements(),
        }
        runner_errors = _runner_error_annotations(text)
        if runner_errors:
            result["runner_errors"] = runner_errors
        elif _looks_like_successful_run(text):
            result["likely_successful_run"] = True
        # Last resort: no rule matched, the runner annotated nothing worth showing, and the log
        # does not announce success. Without this the answer is a shrug.
        _attach_log_tail(result, raw, text)
        return result

    # An invocation proves a tool RAN. It never proves the tool FAILED. A verdict every one of
    # whose signals is an invocation therefore survived only as a LAST RESORT: the deferral
    # above already looked for a rule that witnessed a real error and found none, so what we
    # are handing back is the name of the tool that happened to be running when the job died.
    # That is a lead worth printing -- it is the only thing the log gave us -- but it is not a
    # diagnosis, and seeing the same command echoed three times does not make it one. The
    # count-based score says otherwise: rails/rails run 29648807728 dies on a Ruby
    # `SyntaxError` (`bin/rails aborted!`) that no class covers, and the only matches are
    # `bundle install` (which succeeded), `bundle exec` and `bundler` -- three invocations,
    # `ruby_bundle_failure` at 0.89, sending the maintainer to debug a Gemfile that is fine.
    #
    # So the class stands and the confidence tells the truth about what carried it. The guard
    # is on the MECHANISM, not on any log: nothing here mentions Ruby, and every legitimate
    # last resort keeps its verdict -- apache/airflow's bare `pytest` still answers
    # `python_test_failure`, just at the confidence a naming-only match earns. Any rule that
    # actually watched something fail trips a signal outside INVOCATION_ONLY_PATTERNS and never
    # reaches here, so no genuine verdict loses confidence.
    confidence = min(0.95, 0.35 + 0.18 * len(best_signals))
    if all(signal in INVOCATION_ONLY_PATTERNS for signal in best_signals):
        confidence = min(confidence, _INVOCATION_ONLY_CONFIDENCE)
    result = {
        "schema_version": "patchrail.ci_result.v1",
        "failure_class": best_rule["failure_class"],
        "likely_subsystem": best_rule["likely_subsystem"],
        "reproduction_command": best_rule["reproduction_command"],
        "minimal_repair_strategy": best_rule["minimal_repair_strategy"],
        "confidence": round(confidence, 2),
        "signals": best_signals,
        "requirements": _requirements(),
    }
    # Only a verdict that admits it is a hint reaches past this guard; a confident class is
    # returned exactly as it was.
    _attach_log_tail(result, raw, text)
    return result
