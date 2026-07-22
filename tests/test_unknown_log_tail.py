"""When PatchRail cannot name the cause, it should still show where it lost the trail.

`unknown` with no runner annotation was the emptiest answer the tool could give: `signals: []`,
"No high-confidence local signal found.", and not one line of the log. apache/kafka run
29805964231 is the case that made it visible -- 1,164 lines in, and the job dies one line above
the boilerplate exit-code annotation on `Could not find the PR that triggered this workflow
request`. Three seconds of human scrolling; PatchRail printed none of it.

The tail is EXTRACTION, never classification: the class stays `unknown`, the confidence stays
0.15, and the heuristic is positional (the last lines that carried output) rather than lexical.
A rule for "Could not find the PR" would fix apache/kafka and no other log in the world.

A sub-threshold verdict is the same dead end wearing a class name -- rails/rails at 0.3 tells the
reader to go read the raw log while showing none of it -- so the same extraction covers it. One
implementation, one cap, one redaction; only the condition that turns it on is wider.

Two properties matter more than the feature itself and are pinned below: a log that DOES
classify must come back untouched, and raw log printed for the first time must not carry a
secret out with it.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from patchrail.cli import _render_markdown, _render_text
from patchrail.ci.classify import classify_ci_log

_ROOT = Path(__file__).resolve().parents[1]
_REALWORLD = Path(__file__).resolve().parent / "data" / "realworld"
_DATA = Path(__file__).resolve().parent / "data"

_SCHEMA = json.loads(
    (_ROOT / "src" / "patchrail" / "schemas" / "ci-result.v1.schema.json").read_text(
        encoding="utf-8"
    )
)

# The line apache/kafka's governance gate actually died on.
KAFKA_CAUSE = "Could not find the PR that triggered this workflow request"

# A log that never saw GitHub Actions: no `<job>\t<step>\t<timestamp>` columns, no `##[error]`
# annotation, no exit-code boilerplate to cut at. The tail has to work off the end of the file
# alone, because plenty of CI (GitLab, Buildkite, Jenkins, a local `2>&1 | tee`) looks like this.
PLAIN_LOG = (_DATA / "plain-gate-no-annotation.log").read_text(encoding="utf-8")

# A fake GitHub token, in the shape `redact_ci_log` recognises, sitting in the very lines the
# tail hands back. A log saved to disk still carries what Actions would have masked on the way
# out; printing it back would break the promise the whole product rests on.
FAKE_TOKEN = "ghp_0123456789abcdefghijklmnopqrstuvwxyz"
LEAKY_LOG = (
    "starting nightly publish\n"
    "resolving release manifest\n"
    "manifest resolved\n"
    f"calling registry with token {FAKE_TOKEN}\n"
    "registry refused the upload for release 4.2.0\n"
)


def _realworld(name: str) -> dict:
    return classify_ci_log((_REALWORLD / name).read_text(encoding="utf-8", errors="replace"))


class UnknownHandsBackTheEndOfTheLog(unittest.TestCase):
    def test_kafka_tail_names_the_line_the_job_died_on(self) -> None:
        """The 1,164-line shrug now carries the line a maintainer would have scrolled to."""
        result = _realworld("kafka-29805964231.log")

        # Extraction, not classification: the verdict is byte-for-byte what it was before.
        self.assertEqual(result["failure_class"], "unknown")
        self.assertEqual(result["confidence"], 0.15)
        self.assertEqual(result["signals"], [])

        tail = result["log_tail"]
        self.assertIn(KAFKA_CAUSE, tail)
        self.assertLessEqual(len(tail), 5)
        jsonschema.validate(result, _SCHEMA)

    def test_kafka_cause_reaches_the_user_in_text_markdown_and_json(self) -> None:
        """A key nobody renders is a key nobody reads. All three formats must show the line."""
        result = _realworld("kafka-29805964231.log")

        text = _render_text(result)
        self.assertIn(KAFKA_CAUSE, text)
        self.assertIn("Log ends with:", text)

        markdown = _render_markdown(result)
        self.assertIn(KAFKA_CAUSE, markdown)
        self.assertIn("## Where the log ends", markdown)
        # It is raw log, and it must never be dressed up as a diagnosis.
        self.assertIn("not** a diagnosis", markdown)

        self.assertIn(KAFKA_CAUSE, json.dumps(result))

    def test_plain_log_without_actions_markup_still_gets_a_tail(self) -> None:
        """Nothing here is GitHub-Actions-shaped, so the tail cannot depend on being so."""
        result = classify_ci_log(PLAIN_LOG)

        self.assertEqual(result["failure_class"], "unknown")
        tail = result["log_tail"]
        self.assertIn("gate refused to promote release 4.2.0", tail)
        self.assertEqual(tail[-1], "gate refused to promote release 4.2.0")
        jsonschema.validate(result, _SCHEMA)

    def test_a_secret_in_the_last_lines_never_reaches_the_output(self) -> None:
        """Raw log goes out for the first time here. It goes out redacted or not at all."""
        result = classify_ci_log(LEAKY_LOG)

        rendered = "\n".join((json.dumps(result), _render_text(result), _render_markdown(result)))
        self.assertNotIn(FAKE_TOKEN, rendered)
        self.assertIn("<github-token>", rendered)
        # Redacting must not cost the user the line itself.
        self.assertIn("registry refused the upload for release 4.2.0", result["log_tail"])


class ALowConfidenceVerdictAlsoShowsTheLog(unittest.TestCase):
    """ "Go read the raw log" is not an answer while we show none of it.

    rails/rails run 29648807728 answers `ruby_bundle_failure` at 0.3 -- carried by three `bundle`
    invocations, none of which failed -- and the report already tells the reader to treat that as
    a hint and go read the log. The tail is the same mechanism as `unknown`'s, turned on by the
    same weakness of evidence.
    """

    # What actually broke: `assets:precompile`, inside a container build. Not the Gemfile the
    # class points at.
    RAILS_CAUSE = "./bin/rails assets:precompile"

    def test_rails_keeps_its_verdict_and_gains_the_end_of_its_log(self) -> None:
        result = _realworld("rails-29648807728.log")

        # Extraction, not classification: the weak verdict is still exactly the weak verdict.
        self.assertEqual(result["failure_class"], "ruby_bundle_failure")
        self.assertEqual(result["confidence"], 0.3)

        tail = result["log_tail"]
        self.assertLessEqual(len(tail), 5)
        self.assertIn(self.RAILS_CAUSE, "\n".join(tail))
        jsonschema.validate(result, _SCHEMA)

    def test_the_framing_does_not_claim_nothing_matched(self) -> None:
        """A rule DID match here, so the `unknown` wording would be a lie."""
        result = _realworld("rails-29648807728.log")

        text = _render_text(result)
        self.assertIn(self.RAILS_CAUSE, text)
        self.assertIn("Could not prove the cause", text)
        self.assertNotIn("Could not name the cause", text)

        markdown = _render_markdown(result)
        self.assertIn(self.RAILS_CAUSE, markdown)
        self.assertIn("## Where the log ends", markdown)
        self.assertIn("not** a diagnosis", markdown)
        self.assertNotIn("No rule matched this log", markdown)

    def test_the_tail_is_redacted_on_this_path_too(self) -> None:
        """One implementation, so one redaction -- pinned on the wider condition as well."""
        log = (
            "run\tbundle\t2026-07-20T09:00:01.0Z bundle install\n"
            "run\tbundle\t2026-07-20T09:00:02.0Z bundle exec rake release\n"
            f"run\tbundle\t2026-07-20T09:00:03.0Z pushing with token {FAKE_TOKEN}\n"
            "run\tbundle\t2026-07-20T09:00:04.0Z bundler could not push release 4.2.0\n"
        )
        result = classify_ci_log(log)

        self.assertLess(float(result["confidence"]), 0.35)
        rendered = "\n".join((json.dumps(result), _render_text(result), _render_markdown(result)))
        self.assertNotIn(FAKE_TOKEN, rendered)
        self.assertIn("<github-token>", rendered)


class AClassifiedLogIsUntouched(unittest.TestCase):
    def test_a_confident_verdict_gains_no_tail_and_no_new_output(self) -> None:
        """spring-boot classifies. Nothing about its answer may change."""
        result = _realworld("springboot-29780604983.log")

        self.assertEqual(result["failure_class"], "java_build_failure")
        self.assertNotIn("log_tail", result)
        for rendered in (_render_text(result), _render_markdown(result)):
            self.assertNotIn("Log ends with:", rendered)
            self.assertNotIn("Where the log ends", rendered)

    def test_a_successful_run_is_told_it_passed_not_shown_a_tail(self) -> None:
        """A green log has no failure to point at; a tail would only muddy that answer."""
        result = classify_ci_log(
            "build\tmvn verify\t2026-07-15T09:00:01.0Z [INFO] Building demo 1.0.0\n"
            "build\tmvn verify\t2026-07-15T09:00:30.0Z [INFO] BUILD SUCCESS\n"
            "build\tmvn verify\t2026-07-15T09:00:31.0Z [INFO] Total time:  29.501 s\n"
        )

        self.assertEqual(result["failure_class"], "unknown")
        self.assertTrue(result["likely_successful_run"])
        self.assertNotIn("log_tail", result)
        self.assertNotIn("Log ends with:", _render_text(result))

    def test_a_runner_annotation_still_wins_over_the_tail(self) -> None:
        """The runner naming the error beats us guessing at where the log stopped."""
        result = classify_ci_log(
            "action\tUNKNOWN STEP\t2026-07-14T00:17:41.7947450Z with:\n"
            'action\tUNKNOWN STEP\t2026-07-14T00:17:41.9474342Z ##[error]"github-token" length '
            "must be less than or equal to 100 characters long\n"
            "action\tUNKNOWN STEP\t2026-07-14T00:17:41.9688844Z Cleaning up orphan processes\n"
        )

        self.assertEqual(result["failure_class"], "unknown")
        self.assertTrue(result["runner_errors"])
        self.assertNotIn("log_tail", result)


if __name__ == "__main__":
    unittest.main()
