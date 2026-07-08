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
            r"\btimeout-minutes\b",
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
            r"\bpytest\b",
            r"FAILED .*::",
            r"AssertionError",
            r"ModuleNotFoundError",
            r"ImportError while loading conftest",
            r"\berrors? during collection\b",
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
            r"ERR_PNPM",
            r"ERR_PNPM_NO_MATCHING_VERSION",
            r"ERR_PNPM_MINIMUM_RELEASE_AGE",
            r"YN\d{4}",
            r"\blockfile\b",
            r"peer dep",
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
            r"info Visit https://yarnpkg\.com",
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
            r"\btsc\b",
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
            r"\b(?-i:[A-Z][A-Z0-9_]{2,})\s+is not set\b",
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
        "likely_subsystem": "Java build or test lifecycle",
        "patterns": [
            r"\bmvn\b",
            r"\bgradle\b",
            r"COMPILATION ERROR",
            r"Failed to execute goal",
            r"Execution failed for task",
            r"Could not resolve all files",
            r"Could not resolve dependencies",
            r"Could not determine java version",
            r"Unsupported class file major version",
            r"No tests found for given includes",
            # Case-sensitive banner: Gradle prints "BUILD FAILED"; do not match
            # cargo's lowercase "build failed" or Go's lowercase "build failed".
            r"(?-i:BUILD FAILED)",
            r"cannot find symbol",
            r"package .* does not exist",
        ],
        "reproduction_command": "./gradlew test || mvn test",
        "minimal_repair_strategy": (
            "Reproduce the failing Maven or Gradle task, then fix the narrow dependency, "
            "toolchain, compiler, or test-selection drift before rerunning the same task."
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
        "likely_subsystem": "PHP Composer dependency installation or PHPUnit lifecycle",
        "patterns": [
            r"\bcomposer install\b",
            r"\bcomposer update\b",
            r"Your requirements could not be resolved to an installable set of packages",
            r"requires php",
            r"Problem \d+",
            r"lock file is not up to date",
            r"not present in the lock file",
            r"\bvendor/bin/phpunit\b",
            r"\bphpunit\b",
            r"FAILURES!",
            r"Tests: .*Failures?:",
            r"Failed asserting",
            r"Class .* not found",
        ],
        "reproduction_command": "composer install && vendor/bin/phpunit",
        "minimal_repair_strategy": (
            "Reproduce the failing Composer or PHPUnit command, then fix the narrow "
            "composer.json, lockfile, PHP platform, autoload, or test drift before rerunning it."
        ),
    },
    {
        "failure_class": "go_test_failure",
        "likely_subsystem": "Go tests",
        "patterns": [r"\bgo test\b", r"FAIL\t", r"undefined:", r"panic: test timed out"],
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
            "defect, then resolve the reported revision/history conflict or checksum mismatch "
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


def _matching_signals(text: str, patterns: list[str]) -> list[str]:
    return [
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
    ]


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


def list_failure_classes() -> dict[str, Any]:
    """List every supported failure class in stable rule order.

    Emits ``failure_class``, ``likely_subsystem`` and ``reproduction_command``
    for each rule, plus the ``unknown`` fallback classifier returns when no
    rule matches. This is the machine-readable inventory of what PatchRail can
    diagnose locally, without having to read the source ``RULES`` table.
    """
    classes = [
        {
            "failure_class": rule["failure_class"],
            "likely_subsystem": rule["likely_subsystem"],
            "reproduction_command": rule["reproduction_command"],
        }
        for rule in RULES
    ]
    classes.append(
        {
            "failure_class": UNKNOWN_FAILURE_CLASS,
            "likely_subsystem": UNKNOWN_LIKELY_SUBSYSTEM,
            "reproduction_command": UNKNOWN_REPRODUCTION_COMMAND,
        }
    )
    return {
        "schema_version": "patchrail.ci_classes.v1",
        "count": len(classes),
        "classes": classes,
    }


def classify_ci_log(text: str) -> dict[str, Any]:
    best_rule: dict[str, Any] | None = None
    best_signals: list[str] = []
    for rule in RULES:
        signals = _matching_signals(text, list(rule["patterns"]))
        if len(signals) > len(best_signals):
            best_rule = rule
            best_signals = signals

    if best_rule is None or not best_signals:
        return {
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

    confidence = min(0.95, 0.35 + 0.18 * len(best_signals))
    return {
        "schema_version": "patchrail.ci_result.v1",
        "failure_class": best_rule["failure_class"],
        "likely_subsystem": best_rule["likely_subsystem"],
        "reproduction_command": best_rule["reproduction_command"],
        "minimal_repair_strategy": best_rule["minimal_repair_strategy"],
        "confidence": round(confidence, 2),
        "signals": best_signals,
        "requirements": _requirements(),
    }
