from __future__ import annotations

import re
from collections import Counter
from typing import Any


REDACTION_PATTERNS: list[tuple[str, str, str]] = [
    ("github_token", r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b", "<github-token>"),
    ("github_fine_grained_token", r"\bgithub_pat_[A-Za-z0-9_]{20,}\b", "<github-token>"),
    ("api_key", r"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b", "<api-key>"),
    ("aws_access_key", r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "<aws-access-key>"),
    ("stripe_secret_key", r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b", "<stripe-secret-key>"),
    ("bearer_token", r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}\b", "Bearer <token>"),
    (
        "env_secret_assignment",
        r"\b([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|KEY))=([^\s'\"]+)",
        r"\1=<redacted>",
    ),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "<email>"),
    ("unix_home_path", r"/home/[^/\s'\":]+", "/home/<user>"),
    ("mac_home_path", r"/Users/[^/\s'\":]+", "/Users/<user>"),
]


RULES: list[dict[str, Any]] = [
    {
        "failure_class": "python_dependency_resolution",
        "likely_subsystem": "Python dependency installation",
        "patterns": [
            r"Could not find a version that satisfies the requirement",
            r"No matching distribution found",
            r"Cannot install .*because these package versions have conflicting dependencies",
            r"ResolutionImpossible",
            r"pip._vendor.resolvelib",
            r"python -m pip install",
            r"The conflict is caused by:",
            r"Requires-Python",
            r"requires a different python version",
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
        "failure_class": "python_test_failure",
        "likely_subsystem": "Python tests",
        "patterns": [r"\bpytest\b", r"FAILED .*::", r"AssertionError", r"ModuleNotFoundError"],
        "reproduction_command": "python -m pytest -q",
        "minimal_repair_strategy": (
            "Reproduce the failing test, patch the narrow behavior drift, and rerun the "
            "focused pytest node before broad test runs."
        ),
    },
    {
        "failure_class": "node_dependency_install",
        "likely_subsystem": "Node package installation",
        "patterns": [r"npm ERR!", r"ERR_PNPM", r"YN\d{4}", r"lockfile", r"peer dep"],
        "reproduction_command": "corepack pnpm install --frozen-lockfile || npm ci",
        "minimal_repair_strategy": (
            "Reconcile lockfile and package metadata without upgrading unrelated dependencies."
        ),
    },
    {
        "failure_class": "typescript_typecheck",
        "likely_subsystem": "TypeScript type checking",
        "patterns": [
            r"\bTS\d{4}\b",
            r"\btsc\b",
            r"Type '.*' is not assignable",
            r"Cannot find name",
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
            r"\.github/workflows",
            r"Unable to resolve action",
            r"Resource not accessible by integration",
        ],
        "reproduction_command": "gh workflow view <workflow> --yaml",
        "minimal_repair_strategy": (
            "Inspect workflow syntax, action versions, and permissions, then adjust only the "
            "broken job or permission stanza."
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
            r"no such file or directory",
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
            r"thread '.*' panicked",
            r"test result: FAILED",
        ],
        "reproduction_command": "cargo test",
        "minimal_repair_strategy": (
            "Reproduce the failing crate or test target, patch the narrow Rust error, and "
            "rerun cargo test for that crate."
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
            "failure_class": "unknown",
            "likely_subsystem": "unknown",
            "reproduction_command": "inspect CI log and run the failing job locally",
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
