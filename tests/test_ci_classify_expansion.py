from __future__ import annotations

import json
import subprocess
import sys
import unittest

from patchrail.ci.classify import classify_ci_log, redact_ci_log


class NodeTestFailureClassification(unittest.TestCase):
    def test_jest_run_classifies_as_node_test_failure(self) -> None:
        log = (
            "Run npm test\n"
            "> demo@1.0.0 test\n"
            "> jest --ci --coverage=false\n"
            " FAIL  src/utils/math.test.ts\n"
            "  math > adds numbers\n"
            "    Expected: 4\n"
            "    Received: 5\n"
            "      expect(received).toEqual(expected)\n"
            "Tests:       1 failed, 12 passed, 13 total\n"
            "Test Suites: 1 failed, 4 passed, 5 total\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "node_test_failure")
        self.assertEqual(result["requirements"]["external_model_required"], False)
        self.assertIn("jest", result["reproduction_command"])

    def test_vitest_run_classifies_as_node_test_failure(self) -> None:
        log = (
            "Run npx vitest run\n"
            " FAIL  test/parser.spec.ts > parser > handles empty input\n"
            "AssertionError: expected undefined to equal []\n"
            " ❯ test/parser.spec.ts:14:22\n"
            "Tests:  2 failed, 40 passed\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "node_test_failure")

    def test_pure_jest_log_wins_over_browser_test_failure(self) -> None:
        log = (
            "Run npx jest\n"
            " FAIL  src/checkout/cart.test.tsx\n"
            "  ● cart > totals items > sums prices\n"
            "    Expected: 30\n"
            "    Received: 25\n"
            "Tests:       2 failed, 18 passed, 20 total\n"
            "Test Suites: 1 failed, 6 passed, 7 total\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "node_test_failure")

    def test_playwright_log_stays_browser_test_failure_not_node_test(self) -> None:
        log = (
            "Run npx playwright test\n"
            "Running 12 tests using 4 workers\n"
            "  1) [chromium] login.spec.ts:8:5 › login flow\n"
            "    Error: Timeout 30000ms exceeded.\n"
            "    locator('#submit')\n"
            "    browserType.launch: Executable doesn't exist\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "browser_test_failure")


class NodeDependencyInstallClassification(unittest.TestCase):
    def test_npm_missing_script_classifies_as_node_script_missing(self) -> None:
        log = (
            "Run npm run build\n"
            'npm ERR! Missing script: "build"\n'
            "npm ERR! To see a list of scripts, run:\n"
            "npm ERR!   npm run\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "node_script_missing")
        self.assertIn("package script", result["minimal_repair_strategy"])

    def test_pnpm_missing_script_wins_over_node_dependency_install(self) -> None:
        log = (
            "Run pnpm --filter web lint\n"
            'ERR_PNPM_RECURSIVE_EXEC_FIRST_FAIL Command "lint" not found\n'
            "Lockfile is up to date, resolution step is skipped\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "node_script_missing")

    def test_npm_eresolve_classifies_as_node_dependency_install(self) -> None:
        log = (
            "Run npm ci\n"
            "npm error code ERESOLVE\n"
            "npm error ERESOLVE unable to resolve dependency tree\n"
            "npm error While resolving: demo@1.0.0\n"
            "npm error Could not resolve dependency:\n"
            "npm error Fix the upstream dependency conflict, or retry this command with --force\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "node_dependency_install")
        self.assertIn("lockfile", result["minimal_repair_strategy"])

    def test_registry_404_classifies_as_node_dependency_install(self) -> None:
        log = (
            "Run npm install\n"
            "npm error code E404\n"
            "npm error 404 Not Found - GET https://registry.npmjs.org/@acme%2fnope\n"
            "npm error 404  '@acme/nope@1.0.0' is not in this registry.\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "node_dependency_install")

    def test_yarn_classic_unexpected_error_is_node_dependency_install(self) -> None:
        log = (
            "Run yarn install --frozen-lockfile\n"
            "yarn install v1.22.19\n"
            'error An unexpected error occurred: couldn\'t find package "left-pad@^2.0.0".\n'
            "info Visit https://yarnpkg.com/en/docs/cli/install for documentation.\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "node_dependency_install")

    def test_npm_eresolve_wins_over_node_test_failure_signal(self) -> None:
        log = (
            "Run npm ci && npm test\n"
            "npm error code ERESOLVE\n"
            "npm error ERESOLVE unable to resolve dependency tree\n"
            "npm error Could not resolve dependency:\n"
            "npm error Conflicting peer dependency: react@18.2.0\n"
            "npm error Fix the upstream dependency conflict, or retry with --force\n"
            "(the jest test step never ran)\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "node_dependency_install")


class RustLintClassification(unittest.TestCase):
    def test_clippy_run_classifies_as_rust_lint(self) -> None:
        log = (
            "Run cargo clippy --all-targets --all-features -- -D warnings\n"
            "warning: clippy::needless_return\n"
            "error[clippy::needless_return]: unneeded `return` statement\n"
            "  --> src/lib.rs:12:5\n"
            "help: remove `return`\n"
            "error: could not compile due to clippy warnings\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "rust_lint")
        self.assertIn("clippy", result["reproduction_command"])

    def test_clippy_log_wins_over_rust_test_failure(self) -> None:
        log = (
            "Run cargo clippy --workspace -- -D warnings\n"
            "warning: clippy::redundant_clone\n"
            "error[clippy::redundant_clone]: redundant clone\n"
            "  --> src/handler.rs:30:9\n"
            "error: could not compile due to clippy warnings\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "rust_lint")


class GoLintClassification(unittest.TestCase):
    def test_golangci_lint_run_classifies_as_go_lint(self) -> None:
        log = (
            "Run golangci-lint run ./...\n"
            "internal/server/handler.go:42:6: func unusedHelper is unused (unused)\n"
            "internal/server/handler.go:51:2: ineffectual assignment to err (ineffassign)\n"
            "internal/server/handler.go:60:9: error return value not checked (errcheck)\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "go_lint")
        self.assertIn("golangci-lint", result["reproduction_command"])

    def test_golangci_lint_log_wins_over_go_test_failure(self) -> None:
        log = (
            "Run golangci-lint run ./...\n"
            "internal/api/router.go:18:2: ineffectual assignment to ctx (ineffassign)\n"
            "internal/api/router.go:25:6: func mountRoutes is unused (unused)\n"
            "internal/api/router.go:31:9: error return value not checked (errcheck)\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "go_lint")

    def test_pytest_log_mentioning_ruff_stays_python_test_failure(self) -> None:
        log = (
            "Run python -m pytest -q\n"
            "============================= test session starts =============================\n"
            "(we also run ruff check in a separate lint job)\n"
            "FAILED tests/test_app.py::test_ok - AssertionError: 1 != 2\n"
            "=========================== 1 failed, 30 passed ===========================\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "python_test_failure")


class TypescriptTypecheckClassification(unittest.TestCase):
    def test_tsc_run_classifies_as_typescript_typecheck(self) -> None:
        log = (
            "Run npm run typecheck\n"
            "> tsc --noEmit\n"
            "src/api.ts:14:7 - error TS2339: Property 'user' does not exist on type 'Session'.\n"
            "src/api.ts:22:3 - error TS2769: No overload matches this call.\n"
            "src/api.ts:30:5 - error TS2531: Object is possibly 'null'.\n"
            "src/api.ts:40:9 - error TS2345: Argument of type 'number' "
            "is not assignable to parameter of type 'string'.\n"
            "tsc exited with code 2\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "typescript_typecheck")
        self.assertIn("typecheck", result["minimal_repair_strategy"])

    def test_ts_node_compile_error_classifies_as_typescript_typecheck(self) -> None:
        log = (
            "Run npm start\n"
            "TSError: ⨯ Unable to compile TypeScript:\n"
            "src/index.ts:5:18 - error TS2304: Cannot find name 'process'.\n"
            "Property 'env' does not exist on type 'unknown'.\n"
            "Type checking failed\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "typescript_typecheck")

    def test_tsc_log_wins_over_javascript_lint(self) -> None:
        log = (
            "Run npm run typecheck\n"
            "> tsc --noEmit\n"
            "src/store.ts:12:5 - error TS2322: Type 'string' is not assignable to type 'number'.\n"
            "src/store.ts:18:9 - error TS2339: Property 'id' does not exist on type 'State'.\n"
            "src/store.ts:24:3 - error TS2769: No overload matches this call.\n"
            "(a separate eslint job runs prettier and no-unused-vars checks)\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "typescript_typecheck")

    def test_pure_mypy_log_does_not_fall_into_python_test_failure(self) -> None:
        log = (
            "Run mypy .\n"
            'src/app.py:14: error: Incompatible return value type (got "str", '
            'expected "int")  [return-value]\n'
            'src/app.py:20: error: Argument 1 to "f" has incompatible type "int"; '
            'expected "str"  [arg-type]\n'
            "Found 2 errors in 1 file (checked 30 source files)\n"
        )
        result = classify_ci_log(log)
        self.assertNotEqual(result["failure_class"], "python_test_failure")
        self.assertEqual(result["failure_class"], "python_type_check")


class ReleasePublishFailureClassification(unittest.TestCase):
    def test_npm_publish_e403_classifies_as_release_publish_failure(self) -> None:
        log = (
            "Run npm publish --access public\n"
            "npm notice Publishing to https://registry.npmjs.org with tag latest\n"
            "npm error code E403\n"
            "npm error 403 403 Forbidden - PUT https://registry.npmjs.org/demo\n"
            "npm error 403 You cannot publish over the previously published versions: 1.2.3.\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "release_publish_failure")
        self.assertIn("publish", result["reproduction_command"])

    def test_twine_file_already_exists_classifies_as_release_publish_failure(self) -> None:
        log = (
            "Run twine upload dist/*\n"
            "Uploading distributions to https://upload.pypi.org/legacy/\n"
            "Uploading demo-1.2.3-py3-none-any.whl\n"
            "HTTPError: 400 Bad Request from https://upload.pypi.org/legacy/\n"
            "File already exists. See https://pypi.org/help/#file-name-reuse for more.\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "release_publish_failure")

    def test_cargo_publish_already_uploaded_classifies_as_release_publish_failure(self) -> None:
        log = (
            "Run cargo publish\n"
            "Packaging demo v0.3.1\n"
            "Uploading demo v0.3.1 to registry https://crates.io\n"
            "error: failed to publish to registry at https://crates.io\n"
            "crate version 0.3.1 is already uploaded\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "release_publish_failure")

    def test_npm_publish_e403_wins_over_node_dependency_install(self) -> None:
        log = (
            "Run npm publish\n"
            "npm error code E403\n"
            "npm error 403 You cannot publish over the previously published versions: 2.0.0.\n"
            "npm ERR! A complete log of this run can be found in npm-debug.log\n"
            "npm error EPUBLISHCONFLICT cannot modify pre-existing version: 2.0.0\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "release_publish_failure")

    def test_publish_log_with_npm_token_redacts_and_still_classifies(self) -> None:
        token = "npm_" + "abcdefghijklmnopqrstuvwxyz1234"
        log = (
            "Run npm publish\n"
            f"//registry.npmjs.org/:_authToken={token}\n"
            "npm error code ENEEDAUTH\n"
            "npm error need auth This command requires you to be logged in.\n"
            "File already exists\n"
        )
        redacted = redact_ci_log(log)
        self.assertNotIn(token, redacted["text"])
        self.assertEqual(redacted["redactions"].get("npm_token"), 1)
        self.assertEqual(
            classify_ci_log(redacted["text"])["failure_class"], "release_publish_failure"
        )


class GitCheckoutFailureClassification(unittest.TestCase):
    def test_checkout_auth_failure_classifies_as_git_checkout_failure(self) -> None:
        log = (
            "Run actions/checkout@v4\n"
            "Syncing repository: acme/private\n"
            "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n"
            "Repository not found\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "git_checkout_failure")
        self.assertIn("checkout", result["reproduction_command"])

    def test_submodule_clone_failure_classifies_as_git_checkout_failure(self) -> None:
        log = (
            "Run actions/checkout@v4 with submodules: recursive\n"
            "fatal: clone of 'git@github.com:acme/private.git' into submodule path failed\n"
            "Failed to recurse into submodule path vendor/lib\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_checkout_failure")

    def test_git_lfs_smudge_failure_classifies_as_git_checkout_failure(self) -> None:
        log = (
            "Run actions/checkout@v4 with lfs: true\n"
            "Downloading lfs objects for repository\n"
            "smudge filter lfs failed\n"
            "error downloading object: assets/model.bin (a1b2c3)\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_checkout_failure")

    def test_checkout_failure_wins_over_github_actions_workflow(self) -> None:
        log = (
            "Run actions/checkout@v4\n"
            "Job defined in .github/workflows/ci.yml started the checkout step\n"
            "fatal: could not read Username for 'https://github.com'\n"
            "error: pathspec 'release-ref' did not match any file(s) known to git\n"
            "reference is not a tree: 0123456789abcdef\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_checkout_failure")

    def test_checkout_log_with_token_url_redacts_and_still_classifies(self) -> None:
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
        log = (
            "Run actions/checkout@v4\n"
            "fatal: unable to access "
            f"'https://x-access-token:{token}@github.com/acme/repo.git/'\n"
            "fatal: could not read Username for 'https://github.com'\n"
            "Repository not found\n"
        )
        redacted = redact_ci_log(log)
        self.assertNotIn(token, redacted["text"])
        self.assertEqual(redacted["redactions"].get("url_credentials"), 1)
        self.assertEqual(classify_ci_log(redacted["text"])["failure_class"], "git_checkout_failure")


class GitMergeConflictClassification(unittest.TestCase):
    def test_automatic_merge_failed_classifies_as_git_merge_conflict(self) -> None:
        log = (
            "Run git merge origin/main\n"
            "Auto-merging src/app.py\n"
            "CONFLICT (content): Merge conflict in src/app.py\n"
            "Automatic merge failed; fix conflicts and then commit the result\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "git_merge_conflict")
        self.assertIn("conflict", result["minimal_repair_strategy"])

    def test_rebase_conflict_classifies_as_git_merge_conflict(self) -> None:
        log = (
            "Run git rebase origin/main\n"
            "error: could not apply 0a1b2c3 feat: add widget\n"
            "hint: after resolving the conflicts, mark the corrected paths\n"
            "CONFLICT (content): Merge conflict in lib/widget.ts\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_merge_conflict")

    def test_unmerged_paths_classifies_as_git_merge_conflict(self) -> None:
        log = (
            "error: Merging is not possible because you have unmerged files\n"
            "Unmerged paths:\n"
            "  both modified:   README.md\n"
            "Resolve all conflicts manually, mark them as resolved\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_merge_conflict")

    def test_merge_conflict_wins_over_git_checkout_failure(self) -> None:
        log = (
            "Run actions/checkout@v4\n"
            "Merging the base branch into the PR head\n"
            "Auto-merging src/main.py\n"
            "CONFLICT (content): Merge conflict in src/main.py\n"
            "Automatic merge failed; fix conflicts and then commit the result\n"
            "error: Merging is not possible because you have unmerged files\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "git_merge_conflict")


class SecretsOrPermissionsFailureClassification(unittest.TestCase):
    def test_resource_not_accessible_token_scope_classifies_as_secrets(self) -> None:
        log = (
            "Run gh pr comment 5 --body-file out.md\n"
            "Resource not accessible by integration\n"
            "gh: this token lacks the pull-requests: write permission\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "secrets_or_permissions_failure")
        self.assertIn("permission", result["minimal_repair_strategy"])

    def test_missing_input_classifies_as_secrets_or_permissions_failure(self) -> None:
        log = (
            "Run acme/deploy-action@v1\n"
            "Error: Input required and not supplied: token\n"
            "the DEPLOY_KEY secret is not set for this environment\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "secrets_or_permissions_failure")

    def test_push_permission_denied_classifies_as_secrets_or_permissions_failure(self) -> None:
        log = (
            "Run git push origin HEAD:main\n"
            "remote: Permission to acme/repo.git denied to github-actions[bot].\n"
            "refusing to allow a GitHub App to create or update workflow "
            ".github/workflows/release.yml without workflows permission\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "secrets_or_permissions_failure")

    def test_permissions_failure_wins_over_github_actions_workflow(self) -> None:
        log = (
            "Run git push\n"
            "Job from .github/workflows/release.yml attempted to push tags\n"
            "Resource not accessible by integration\n"
            "remote: Permission to acme/repo.git denied to github-actions[bot].\n"
            "refusing to allow a GitHub App to create or update workflow "
            "without workflows permission\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "secrets_or_permissions_failure")

    def test_secret_value_in_log_redacts_and_still_classifies(self) -> None:
        secret = "ghp_" + "ZYXWVUTSRQPONMLKJIHGFEDCBA987654"
        log = (
            "Run acme/deploy-action@v1\n"
            f"DEPLOY_TOKEN={secret}\n"
            "Error: Input required and not supplied: api-key\n"
            "the API_KEY secret is not set for this environment\n"
        )
        redacted = redact_ci_log(log)
        self.assertNotIn(secret, redacted["text"])
        self.assertIn("DEPLOY_TOKEN=<redacted>", redacted["text"])
        self.assertEqual(
            classify_ci_log(redacted["text"])["failure_class"],
            "secrets_or_permissions_failure",
        )


class RedactionExpansion(unittest.TestCase):
    def test_url_credentials_redacted_in_git_clone_with_token(self) -> None:
        token = "ghp_" + "abcdefghijklmnopqrstuvwxyz123456"
        log = (
            "fatal: unable to access "
            f"https://x-access-token:{token}@github.com/acme/repo.git/: "
            "The requested URL returned error: 403\n"
        )
        result = redact_ci_log(log)
        self.assertIn("https://<credentials>@github.com/acme/repo.git/", result["text"])
        self.assertNotIn("x-access-token:", result["text"])
        self.assertNotIn(token, result["text"])
        self.assertEqual(result["redactions"].get("url_credentials"), 1)

    def test_url_credentials_redacted_in_postgres_dsn(self) -> None:
        log = (
            "sqlalchemy.exc.OperationalError: could not connect to "
            "postgres://dbuser:s3cr3tPass@db.internal:5432/appdb\n"
        )
        result = redact_ci_log(log)
        self.assertIn("postgres://<credentials>@db.internal:5432/appdb", result["text"])
        self.assertNotIn("dbuser:s3cr3tPass", result["text"])
        self.assertEqual(result["redactions"].get("url_credentials"), 1)

    def test_sendgrid_api_key_redacted_and_counted(self) -> None:
        key = "SG.aBcDeFgHiJkLmNoPqRsT12.uVwXyZ0123456789AbCdEfGhIjKlMnOpQrStUvWx"
        log = f"Error sending mail: rejected {key} not authorized\n"
        result = redact_ci_log(log)
        self.assertIn("<sendgrid-api-key>", result["text"])
        self.assertNotIn(key, result["text"])
        self.assertEqual(result["redactions"].get("sendgrid_api_key"), 1)

    def test_telegram_bot_token_redacted_and_counted(self) -> None:
        token = "123456789:AAH9xZ_qWeRtYuIoPaSdFgHjKlZxCvBnMqp"
        log = f"requests.exceptions.HTTPError: bot {token} failed with 401\n"
        result = redact_ci_log(log)
        self.assertIn("<telegram-bot-token>", result["text"])
        self.assertNotIn(token, result["text"])
        self.assertEqual(result["redactions"].get("telegram_bot_token"), 1)


class ArtifactOrCacheFailureClassification(unittest.TestCase):
    def test_artifact_no_files_classifies_as_artifact_or_cache_failure(self) -> None:
        log = (
            "Run actions/upload-artifact@v4\n"
            "With the provided path, there will be 0 files uploaded\n"
            "Error: No files were found with the provided path: dist/. "
            "No artifacts will be uploaded.\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")
        self.assertEqual(result["requirements"]["external_model_required"], False)
        self.assertIn("artifact", result["reproduction_command"])

    def test_artifact_name_collision_classifies_as_artifact_or_cache_failure(self) -> None:
        log = (
            "Run actions/upload-artifact@v4\n"
            "Error: Failed to CreateArtifact: Received non-retryable error: "
            "Failed request: (409) Conflict: an artifact with this name already exists "
            "on the workflow run\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "artifact_or_cache_failure")

    def test_cache_service_error_classifies_as_artifact_or_cache_failure(self) -> None:
        log = (
            "Run actions/cache@v4\n"
            "Received 503 from cache service\n"
            "Failed to restore: Cache service responded with 503 during download cache\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")
        self.assertGreaterEqual(len(result["signals"]), 2)

    def test_cache_failure_does_not_match_github_actions_workflow(self) -> None:
        log = (
            "Run actions/download-artifact@v4\n"
            "Error: Unable to download artifact(s): Artifact not found for name: build-output\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "artifact_or_cache_failure")


class TerraformIacFailureClassification(unittest.TestCase):
    def test_terraform_plan_config_error_classifies_as_terraform_iac_failure(self) -> None:
        log = (
            "Run terraform plan -no-color\n"
            "Initializing the backend...\n"
            "╷\n"
            "│ Error: Reference to undeclared resource\n"
            "│\n"
            '│   on main.tf line 22, in resource "aws_instance" "web":\n'
            "│   22:   subnet_id = aws_subnet.private.id\n"
            "│\n"
            '│ A managed resource "aws_subnet" "private" has not been declared.\n'
            "╵\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "terraform_iac_failure")
        self.assertIn("terraform", result["reproduction_command"])
        self.assertEqual(result["requirements"]["external_model_required"], False)

    def test_terraform_state_lock_classifies_as_terraform_iac_failure(self) -> None:
        log = (
            "Run terraform apply -auto-approve\n"
            "Acquiring state lock. This may take a few moments...\n"
            "│ Error: Error acquiring the state lock\n"
            "│ Lock Info:\n"
            "│   ID:        9f3c-...\n"
            "│   Operation: OperationTypeApply\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "terraform_iac_failure")


class PreCommitHookClassification(unittest.TestCase):
    def test_files_modified_by_hook_classifies_as_pre_commit(self) -> None:
        log = (
            "Run pre-commit run --all-files\n"
            "trim trailing whitespace.................................................Failed\n"
            "- hook id: trailing-whitespace\n"
            "- exit code: 1\n"
            "- files were modified by this hook\n"
            "\n"
            "Fixing src/app/main.py\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "pre_commit_hook_failure")
        self.assertIn("pre-commit run --all-files", result["reproduction_command"])
        self.assertEqual(result["requirements"]["external_model_required"], False)

    def test_pre_commit_config_error_classifies_as_pre_commit(self) -> None:
        log = (
            "Run pre-commit run --all-files\n"
            "An error has occurred: InvalidConfigError:\n"
            "==> File .pre-commit-config.yaml\n"
            "==> At Config()\n"
            "=====> Additional properties are not allowed\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "pre_commit_hook_failure")


class ShellLintClassification(unittest.TestCase):
    def test_shellcheck_findings_classify_as_shell_lint(self) -> None:
        log = (
            "Run make lint-shell\n"
            "+ shellcheck scripts/*.sh\n"
            "\n"
            "In scripts/entrypoint.sh line 4:\n"
            'source "$(dirname "$0")/../lib/common.sh"\n'
            "^-- SC1091 (info): Not following: ../lib/common.sh was not specified as input.\n"
            "\n"
            "For more information:\n"
            "  https://www.shellcheck.net/wiki/SC1091 -- Not following: ../lib/common.sh...\n"
            "make: *** [lint-shell] Error 1\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "shell_lint")
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertIn("shellcheck", result["reproduction_command"])

    def test_shfmt_diff_classifies_as_shell_lint(self) -> None:
        log = (
            "Run shfmt -d .\n"
            "diff scripts/build.sh.orig scripts/build.sh\n"
            "--- scripts/build.sh.orig\n"
            "+++ scripts/build.sh\n"
            "@@ -1,4 +1,4 @@\n"
            '-if [ "$1" == "prod" ]; then\n'
            '+if [ "$1" == "prod" ]; then\n'
            "shfmt: 1 file(s) not formatted, run 'shfmt -w .' to fix\n"
            "shellcheck scripts/build.sh\n"
            "In scripts/build.sh line 2:\n"
            "cd $DIR\n"
            "^-- SC2164 (warning): Use 'cd ... || exit' or 'cd ... || return' in case cd fails.\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "shell_lint")
        self.assertGreaterEqual(result["confidence"], 0.7)


class ElixirMixFailureClassification(unittest.TestCase):
    def test_mix_compile_error_classifies_as_elixir_mix_failure(self) -> None:
        log = (
            "Run mix compile --warnings-as-errors\n"
            "==> demo\n"
            "Compiling 14 files (.ex)\n"
            "\n"
            "== Compilation error in file lib/demo/worker.ex ==\n"
            "** (CompileError) lib/demo/worker.ex:12: undefined function handle_job/1\n"
            "    (elixir 1.17.2) expanding macro: Kernel.def/2\n"
            "\n"
            'could not compile dependency :demo, "mix compile" failed\n'
            "mix format --check-formatted\n"
            "** (Mix) mix format --check-formatted failed, 1 file is not formatted\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "elixir_mix_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertIn("mix", result["reproduction_command"])

    def test_exunit_failure_classifies_as_elixir_mix_failure(self) -> None:
        log = (
            "Run mix test\n"
            "Compiling 14 files (.ex)\n"
            ".....\n"
            "\n"
            "  1) test totals items sums prices (DemoWeb.CartTest)\n"
            "     test/demo_web/cart_test.exs:8\n"
            "     Assertion with == failed\n"
            "     code:  assert Cart.total(items) == 30\n"
            "     left:  25\n"
            "     right: 30\n"
            "\n"
            "Finished in 0.4 seconds\n"
            "5 tests, 1 failures\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "elixir_mix_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_hex_version_solving_failure_wins_over_python_dependency_resolution(self) -> None:
        log = (
            "Run mix deps.get\n"
            "Resolving Hex dependencies...\n"
            "Because myapp depends on ecto ~> 3.10 and myapp depends on ecto_sql ~> 3.9, "
            "version solving failed.\n"
            "** (Mix) Hex dependency resolution failed\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "elixir_mix_failure")

    def test_python_poetry_conflict_still_classifies_as_python_dependency_resolution(self) -> None:
        log = (
            "Run poetry install --no-root\n"
            "SolverProblemError\n"
            "Because demo-service depends on api-client (^4.0) and worker-plugin depends on "
            "api-client (<4.0), version solving failed.\n"
            "So, because demo-project depends on both demo-service and worker-plugin, "
            "version solving failed.\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "python_dependency_resolution")


class DatabaseMigrationFailureClassification(unittest.TestCase):
    def test_alembic_missing_revision_classifies_as_database_migration_failure(self) -> None:
        log = (
            "Run alembic upgrade head\n"
            "INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.\n"
            "INFO  [alembic.runtime.migration] Will assume transactional DDL.\n"
            "Traceback (most recent call last):\n"
            '  File "/usr/local/bin/alembic", line 8, in <module>\n'
            "    sys.exit(main())\n"
            "alembic.util.exc.CommandError: Can't locate revision identified by 'a1b2c3d4e5f6'\n"
            "Target database is not up to date.\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "database_migration_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_prisma_drift_classifies_as_database_migration_failure(self) -> None:
        log = (
            "Run prisma migrate deploy\n"
            "Prisma schema loaded from prisma/schema.prisma\n"
            "\n"
            "Error: P3009\n"
            "\n"
            "migrate found failed migrations in the target database, new migrations will not "
            "be applied.\n"
            "Drift detected: Your database schema is not in sync with your migration history.\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "database_migration_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)


class KubernetesDeployFailureClassification(unittest.TestCase):
    def test_immutable_field_classifies_as_kubernetes_deploy_failure(self) -> None:
        log = (
            "Run kubectl apply -f deployment.yaml\n"
            'error: unable to recognize "deployment.yaml": no matches for kind '
            '"Deployment" in version "apps/v1beta1"\n'
            'The Deployment "web" is invalid: spec.selector: field is immutable\n'
            "Error from server (Invalid): error when applying patch\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "kubernetes_deploy_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_admission_webhook_denial_classifies_as_kubernetes_deploy_failure(self) -> None:
        log = (
            "Run kustomize build overlays/prod | kubectl apply -f -\n"
            'Error from server (Forbidden): error when creating "STDIN": admission webhook '
            "\"validate.gatekeeper.sh\" denied the request: image tag ':latest' is not allowed\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "kubernetes_deploy_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_plain_connection_refused_stays_network_transient_failure(self) -> None:
        log = (
            "Run kubectl get nodes\n"
            "The connection to the server 10.0.0.1:6443 was refused - did you specify "
            "the right host or port?\n"
            "Connection refused\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "network_transient_failure")


class HelmChartFailureClassification(unittest.TestCase):
    def test_helm_lint_schema_and_kubeversion_classifies_as_helm_chart_failure(self) -> None:
        log = (
            "Run helm lint . -f values.yaml\n"
            "==> Linting .\n"
            "[ERROR] values.yaml: Error: values don't meet the specifications of the schema\n"
            "[ERROR] Chart.yaml: Error: chart requires kubeVersion: >= 1.25.0 which is "
            "incompatible with Kubernetes v1.23.4\n"
            "\n"
            "Error: 1 chart(s) linted, 1 chart(s) failed\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "helm_chart_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)
        self.assertIn("helm", result["reproduction_command"])

    def test_helm_upgrade_template_nil_pointer_classifies_as_helm_chart_failure(self) -> None:
        log = (
            "Run helm upgrade web ./chart -f values-prod.yaml\n"
            "Error: UPGRADE FAILED: template: web/templates/deployment.yaml:14:8: "
            'executing "web/templates/deployment.yaml" at <.Values.image.tag>: '
            "nil pointer evaluating interface {}.Tag\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "helm_chart_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)


class DocsBuildFailureClassification(unittest.TestCase):
    def test_sphinx_warning_as_error_classifies_as_docs_build_failure(self) -> None:
        log = (
            "Run sphinx-build -W -b html docs docs/_build/html\n"
            "checking consistency...\n"
            "docs/guide/advanced.rst: WARNING: document isn't included in any toctree\n"
            "\n"
            "Warning, treated as error:\n"
            "docs/index.rst:12: toctree contains reference to nonexisting document "
            "'guide/missing'\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "docs_build_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_mkdocs_strict_broken_link_classifies_as_docs_build_failure(self) -> None:
        log = (
            "Run mkdocs build --strict\n"
            "WARNING -  Doc file 'guide/configuration.md' contains a relative link "
            "'install.md', but the target 'guide/install.md' is not found among "
            "documentation files.\n"
            "Aborted with 1 warnings in strict mode!\n"
        )
        result = classify_ci_log(log)
        self.assertEqual(result["failure_class"], "docs_build_failure")
        self.assertGreaterEqual(result["confidence"], 0.7)

    def test_docusaurus_broken_link_wins_over_node_dependency_install(self) -> None:
        # The log runs through npm; the Docusaurus signals must still win so the
        # failure is not misread as a Node dependency problem.
        log = (
            "Run npm run build\n"
            "> docs@0.0.0 build\n"
            "> docusaurus build\n"
            "[ERROR] Docusaurus found broken links!\n"
            "- Broken link on source page path = /docs/intro:\n"
            "   -> linking to /docs/getting-started/missing-page\n"
            "Error: Unable to build website for locale en.\n"
        )
        self.assertEqual(classify_ci_log(log)["failure_class"], "docs_build_failure")


class SchemaContractExpansion(unittest.TestCase):
    def test_schema_command_lists_new_failure_classes(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "schema", "ci-result"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        schema = json.loads(proc.stdout)
        enum = schema["properties"]["failure_class"]["enum"]
        self.assertIn("node_test_failure", enum)
        self.assertIn("node_dependency_install", enum)
        self.assertIn("rust_lint", enum)
        self.assertIn("go_lint", enum)
        self.assertIn("typescript_typecheck", enum)
        self.assertIn("release_publish_failure", enum)
        self.assertIn("git_checkout_failure", enum)
        self.assertIn("git_merge_conflict", enum)
        self.assertIn("secrets_or_permissions_failure", enum)
        self.assertIn("artifact_or_cache_failure", enum)
        self.assertIn("pre_commit_hook_failure", enum)
        self.assertIn("docs_build_failure", enum)
        self.assertIn("node_script_missing", enum)
        self.assertNotIn("node_dependency_failure", enum)
        self.assertNotIn("lint_failure", enum)
        self.assertNotIn("typecheck_failure", enum)
        self.assertNotIn("publish_failure", enum)
        self.assertNotIn("checkout_failure", enum)
        self.assertNotIn("permissions_failure", enum)

    def test_every_rule_failure_class_is_declared_in_the_schema_enum(self) -> None:
        # Guard against drift: any class the classifier can emit must be a valid
        # value in the published ci-result schema, or downstream consumers that
        # validate against it will reject a legitimate classification.
        from patchrail.ci.classify import RULES

        proc = subprocess.run(
            [sys.executable, "-m", "patchrail", "schema", "ci-result"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        enum = set(json.loads(proc.stdout)["properties"]["failure_class"]["enum"])
        missing = [rule["failure_class"] for rule in RULES if rule["failure_class"] not in enum]
        self.assertEqual(missing, [], f"rule classes missing from schema enum: {missing}")
        self.assertIn("unknown", enum)


if __name__ == "__main__":
    unittest.main()
