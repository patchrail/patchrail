# Consent-Only Pilot Request Package

This package helps maintainers test PatchRail without giving repository write
access or sharing private logs. Use it only when a maintainer opts in, asks for
instructions, or opens an adopter report. It is not an outreach automation
template.

PatchRail should count a pilot as public evidence only after the maintainer has
reviewed the result and explicitly approved what may be listed.

## Maintainer Consent Checklist

Before a pilot can be cited publicly, confirm:

- the maintainer owns the repository or is authorized to test it;
- the repository name is approved for public mention, or it stays private;
- raw logs, secrets, private paths, personal data, and customer names are not
  included;
- PatchRail ran locally or in a maintainer-controlled workflow;
- no pull request, issue comment, funded-issue claim, or other write action was
  created by PatchRail;
- no external model or billing service was required for the pilot;
- the maintainer reviewed whether the classification and suggested action were
  useful.

If any item is missing, keep the result as private feedback and do not add it to
`ADOPTERS.md`.

## Copyable Maintainer Instructions

Use this when a maintainer wants to run a first read-only trial:

````markdown
Run a local PatchRail pilot on one failed CI log:

1. Install PatchRail:

   ```bash
   pipx install patchrail
   ```

2. Check the safety posture:

   ```bash
   patchrail doctor --format markdown
   ```

3. Generate a redacted local pilot pack:

   ```bash
   patchrail ci pilot-pack --log failed-ci.log --out-dir patchrail-pilot-pack
   ```

4. Review `patchrail-pilot-pack/failed-ci.redacted.log` manually. Do not share
   it if it still contains secrets, private paths, personal data, customer
   names, or private repository identifiers.

5. Create a safe outcome summary:

   ```bash
   patchrail ci pilot-summary \
     --pack patchrail-pilot-pack \
     --ci-provider "GitHub Actions" \
     --toolchain Python \
     --classification-correct yes \
     --maintainer-action-useful yes
   ```

6. If you approve public repository listing, add:

   ```bash
   --repository owner/repo --repository-mention-approved yes
   ```

   Otherwise omit the repository or use `--repository-mention-approved no`.
````

The command sequence does not grant repository write permission, open pull
requests, comment on issues, call external models, claim funded issues, or copy
the raw log into the pilot pack.

## Evidence Intake

Accepted public evidence should include only:

- PatchRail version or commit SHA;
- CI provider and toolchain;
- whether the classification was correct;
- whether the suggested maintainer action was useful;
- safe redacted report excerpt, if the maintainer reviewed it;
- `pilot-manifest.json` metadata showing `raw_log_copied=false`;
- explicit repository mention approval when an adopter listing is requested.

Do not include:

- raw logs;
- secrets, tokens, emails, private paths, or screenshots with credentials;
- private repository names without approval;
- claims that PatchRail fixed code, opened a pull request, commented on an
  issue, contacted a maintainer, or used a model when it did not.

## Public Listing Rule

`ADOPTERS.md` is permission-only. A pilot may be listed when all of these are
true:

1. the maintainer submitted an adopter report or equivalent public permission;
2. the repository or organization is approved for public mention;
3. the evidence is redacted and reviewable;
4. PatchRail's role is described as read-only CI triage, queue demo, GitHub
   Action artifact, or another accurate local-first workflow.

If the maintainer does not approve a public repository mention, record only an
anonymous aggregate metric with `patchrail ci pilot-metrics`.

## Aggregate Metrics

Use reviewed JSON summaries to update metrics without exposing private names:

```bash
patchrail ci pilot-metrics pilot-summary-*.json --format markdown
```

The aggregate may count reviewed summaries and approved public repository
mentions. It must not turn unapproved private pilots into adopter listings.

## Related Files

- [Maintainer pilot guide](pilot-guide.md)
- [Adopters](../ADOPTERS.md)
- [Metrics](metrics.md)
- [Adopter report issue template](../.github/ISSUE_TEMPLATE/adopter_report.md)
- [Consent-only pilot outcome example](../examples/pilot-outcome/README.md)
