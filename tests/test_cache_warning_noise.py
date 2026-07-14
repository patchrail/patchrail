"""A cache that declined to save, and an action the runner merely booted, are not failures.

Grounded in a real failed run of pandas-dev/pandas (`Doc Build and Upload`, run 29342614636),
where the doc build died on a Sphinx crash and PatchRail reported
`artifact_or_cache_failure` at 0.89 confidence instead.

Three signals carried that verdict, and not one of them witnessed a failure:

  * `Download action repository 'actions/upload-artifact@...'` -- the runner resolving the
    actions it is about to use, printed by every run that mentions the action, green ones
    included.
  * `##[warning]Failed to save: Unable to reserve cache with key ...` -- on the WARNING
    channel, twice.
  * `... another job may be creating this cache.` -- the runner explaining that this is two
    matrix jobs racing for one cache key, i.e. the most ordinary event in a big CI matrix.

`actions/cache` settles it in its own source: `saveImpl` wraps the save in
`try { ... } catch { logWarning(...) }`, so a save error is reported through `core.warning`
and never `core.setFailed`. A cache that failed to save CANNOT be why a job failed.

The real error sat 2000 lines below the first warning (`##[error]Process completed with exit
code 2`), outvoted by post-failure cleanup noise.
"""

from __future__ import annotations

import unittest

from patchrail.ci.classify import classify_ci_log

# The pandas run, in the shape `gh run view --log-failed` serves it: the runner boots and
# echoes the actions it will use, Sphinx crashes, the job dies, and the cache steps run in
# `Post job cleanup` and warn that they could not reserve their key.
PANDAS_DOC_BUILD = """\
Download action repository 'actions/upload-artifact@bbbca2ddaa5d8feaa63e36b76fdaad77386f024f' (SHA:bbbca2ddaa5d8feaa63e36b76fdaad77386f024f)
Run micromamba-shell -n test -- python -m sphinx -b html doc/source doc/build/html
Exception occurred:
  File "/opt/conda/envs/test/lib/python3.12/site-packages/sphinx/registry.py", line 442, in load_extension
    raise ExtensionError(msg, err) from err
sphinx.errors.ExtensionError: Could not import extension numpydoc
To report this error to the developers, please open an issue at <https://github.com/sphinx-doc/sphinx/issues/>. Thanks!
##[error]Process completed with exit code 2.
Post job cleanup.
##[warning]Failed to save: Unable to reserve cache with key micromamba-environment--linux-64-test-args-8b1a9cc-root-dcc80ee
##[warning]Failed to save: Unable to reserve cache with key micromamba-downloads--linux-64, another job may be creating this cache.
"""


class ACacheThatDeclinedToSaveIsNotWhyTheJobFailed(unittest.TestCase):
    def test_the_pandas_doc_build_is_not_an_artifact_or_cache_failure(self) -> None:
        result = classify_ci_log(PANDAS_DOC_BUILD)

        self.assertNotEqual(result["failure_class"], "artifact_or_cache_failure")

    def test_unknown_is_the_answer_rather_than_a_confident_wrong_one(self) -> None:
        # `unknown` at 0.15 says the true thing. 0.89 on a cache that was working sends a
        # maintainer to debug the one component the log proves is fine.
        result = classify_ci_log(PANDAS_DOC_BUILD)

        self.assertEqual(result["failure_class"], "unknown")

    def test_a_cache_warning_cannot_explain_a_step_that_exited_non_zero(self) -> None:
        # The runner annotated an error, so some step exited non-zero -- and `actions/cache`
        # reports save failures through `core.warning`, so it was not this one.
        log = (
            "Run actions/cache@v4\n"
            "##[error]Process completed with exit code 1.\n"
            "##[warning]Failed to save: Unable to reserve cache with key node-modules-abc123, "
            "another job may be creating this cache.\n"
        )

        result = classify_ci_log(log)

        self.assertNotEqual(result["failure_class"], "artifact_or_cache_failure")


class TheBoundaryOfTheFix(unittest.TestCase):
    """Where the runner never reported an error, a warning is still the only lead we have.

    `test_artifact_warning_alone_still_classifies_as_artifact` in test_ci_classify_expansion
    pins the same decision from the other side; this states plainly that the fix left it
    alone. One lead beats none -- there is simply no failure to explain in such a log.
    """

    def test_a_warning_in_a_log_with_no_runner_error_still_stands(self) -> None:
        log = (
            "Run actions/upload-artifact@v4\n"
            "No files were found with the provided path: dist/*.whl."
            " No artifacts will be uploaded.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")

    def test_a_success_announced_through_the_error_channel_does_not_arm_the_fix(self) -> None:
        # #329's lesson, held: `##[error]✅ ...` is not proof that a step exited non-zero, so
        # it must not be what tips a warning-only verdict into `unknown`.
        log = (
            "Run actions/upload-artifact@v4\n"
            "##[error]✅ Autofix task started.\n"
            "No files were found with the provided path: dist/*.whl."
            " No artifacts will be uploaded.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")


class AGenuineArtifactOrCacheFailureStillFires(unittest.TestCase):
    """The guards. Every terminal signal the class owns must survive the fix."""

    def test_a_5xx_from_the_cache_service_is_still_a_failure(self) -> None:
        # The toolkit's own severity split: warning for most failures, ERROR for 5xx.
        log = (
            "Run actions/upload-artifact@v4\n"
            "Beginning upload of artifact content to blob storage\n"
            "Cache service responded with 500\n"
            "##[error]An error occurred while trying to determine the artifact upload location.\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")

    def test_a_failed_create_artifact_is_still_a_failure(self) -> None:
        log = (
            "Run actions/upload-artifact@v4\n"
            "##[error]Failed to CreateArtifact: Received non-retryable error\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")

    def test_a_duplicate_artifact_name_is_still_a_failure(self) -> None:
        log = (
            "Run actions/upload-artifact@v4\n"
            "##[error]Failed to CreateArtifact: an artifact with this name already exists "
            "on the workflow run\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")

    def test_a_cache_warning_riding_alongside_a_real_cache_error_still_fires(self) -> None:
        # The noun keeps earning its keep as corroboration: a terminal signal is present, so
        # the rule fires and the benign warning rides along instead of suppressing it.
        log = (
            "Run actions/cache@v4\n"
            "##[warning]Failed to save: Unable to reserve cache with key node-modules-abc123\n"
            "##[error]Cache service responded with 503\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "artifact_or_cache_failure")


class ACondaBillOfMaterialsIsNotAnEvent(unittest.TestCase):
    """pandas installs its whole dev toolchain to build docs. Installed is not run.

    The same doc-build log names `mypy` six times without ever running it -- once as the
    `environment.yml` spec, then through the solver's transaction table, `Linking`, the
    package tables and `conda list`. pip's half of this was already handled (`Collecting`,
    `Downloading`); conda's was not, so a Sphinx crash came out `python_type_check` at 0.53.
    """

    CONDA_ENV_SETUP = """\
Run mamba-org/setup-micromamba@v2
  environment-file: environment.yml
    - mypy=1.17.1
Transaction

  Installing:
   + mypy                                         1.17.1  py311h49ec1c0_1       conda-forge
   + sphinx                                        8.1.3  pyhd8ed1ab_0          conda-forge

  Linking mypy-1.17.1-py311h49ec1c0_1
Run python -m sphinx -b html doc/source doc/build/html
sphinx.errors.ExtensionError: Could not import extension numpydoc
##[error]Process completed with exit code 2.
"""

    def test_a_tool_the_job_only_installed_does_not_carry_the_verdict(self) -> None:
        result = classify_ci_log(self.CONDA_ENV_SETUP)

        self.assertNotEqual(result["failure_class"], "python_type_check")

    def test_a_mypy_that_actually_ran_and_failed_is_still_a_type_check_failure(self) -> None:
        # The guard. Installed-only is silent; INVOKED and failing still classifies.
        log = (
            "Run mypy pandas/\n"
            "pandas/core/frame.py:42: error: Incompatible return value type "
            '(got "int", expected "str")  [return-value]\n'
            "Found 1 error in 1 file (checked 120 source files)\n"
        )

        result = classify_ci_log(log)

        self.assertEqual(result["failure_class"], "python_type_check")


if __name__ == "__main__":
    unittest.main()
