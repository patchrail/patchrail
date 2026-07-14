# jq cookbook for the JSON classifier output

`patchrail ci classify --format json` (and `ci explain --format json`) emit a
stable, documented schema: `schema_version: "patchrail.ci_result.v1"`. This
page is a set of copy-pasteable [jq](https://jqlang.github.io/jq/) recipes
for wiring that output into scripts and CI plumbing.

Every recipe below was run against the fixtures bundled in
`examples/ci-triage/`.

## Stable schema fields

`schema_version` is the field to check before parsing anything else — it
only changes on a breaking format change. As of this page it is
`patchrail.ci_result.v1`. The other fields used in these recipes
(`failure_class`, `confidence`, `reproduction_command`, `redaction.redactions`)
are part of that same versioned schema.

## Extract just the failure class

```bash
patchrail ci classify --log build.log | jq -r .failure_class
```

```
python_dependency_resolution
```

## Gate a script on confidence

Use `jq -e` so the exit code reflects the check — non-zero (and no stdout)
when the condition is false, which is exactly what a CI gate wants:

```bash
patchrail ci classify --log build.log | jq -e '.confidence >= 0.7'
```

```bash
if patchrail ci classify --log build.log | jq -e '.confidence >= 0.7' > /dev/null; then
  echo "confident classification"
fi
```

## Get the reproduction command

```bash
patchrail ci classify --log build.log | jq -r .reproduction_command
```

```
python -m pip install -r requirements.txt
```

## Batch-triage a directory of logs into a TSV

```bash
for f in examples/ci-triage/*.log; do
  patchrail ci classify --log "$f" --format json \
    | jq -r --arg name "$(basename "$f")" '[$name, .failure_class, .confidence] | @tsv'
done
```

```
browser-playwright-navigation-timeout.log	browser_test_failure	0.89
browser-playwright-webserver-timeout.log	browser_test_failure	0.71
cypress-browser-launch.log	browser_test_failure	0.89
db-migration-alembic-revision.log	database_migration_failure	0.89
db-migration-prisma-drift.log	database_migration_failure	0.89
...
```

Pipe that into a file to build a spreadsheet-friendly triage report:
`... > triage-report.tsv`.

## Count redaction hits when running with `--redact`

```bash
patchrail ci classify --log build.log --redact --format json | jq '.redaction.redactions'
```

For a log with no known-pattern secrets, this is an empty object — that
means nothing in `docs/redaction.md`'s pattern list matched, not that the
log is free of anything worth a human review:

```json
{}
```

For a log containing, say, a GitHub token and an email address:

```json
{
  "email": 1,
  "github_token": 1
}
```

See `docs/redaction.md` for the full list of redaction categories.

## Check coverage against the supported classes

`patchrail ci classes --format json` is a different payload with its own
version, `patchrail.ci_classes.v2` — it is the inventory of what the classifier
can diagnose, not the result of classifying anything. Fetch it with
`patchrail schema ci-classes`.

`unknown` is deliberately **not** in `classes`/`count`. It is what `ci explain`
returns when no rule matches, so counting it would put an entry in your
denominator that no log can ever be classified as. It is still reported, under
`fallback`:

```bash
patchrail ci classes --format json | jq '{count, classes: (.classes | length), fallback: .fallback.failure_class}'
```

```json
{
  "count": 40,
  "classes": 40,
  "fallback": "unknown"
}
```

Which classes did a directory of logs actually exercise?

```bash
supported=$(patchrail ci classes --format json | jq -r '.classes[].failure_class' | sort)
seen=$(for log in ci-logs/*.log; do
  patchrail ci explain --log "$log" --format json | jq -r 'select(.failure_class != "unknown") | .failure_class'
done | sort -u)
comm -23 <(echo "$supported") <(echo "$seen")   # supported classes with no log in the corpus
```

Filtering `unknown` out of `seen` is what keeps the two sides comparable: a log
that matched no rule is a gap in the corpus, not a class.

## Related

- [Quickstart](quickstart.md) for install and first-run commands.
- [Redaction reference](redaction.md) for what `.redaction.redactions` counts mean.
