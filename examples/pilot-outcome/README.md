# Consent-Only Pilot Outcome Example

This example shows how to summarize a read-only PatchRail maintainer pilot
without publishing raw logs, private repository names, personal data, secrets,
or unapproved adopter claims.

The repository name, log path, and outcome below are synthetic. Do not count this example as adoption evidence.

## Pilot Boundary

- Maintainer permission: confirmed for the real pilot before any public mention.
- Public listing permission: not granted until the maintainer explicitly says so.
- Raw CI log: kept outside the report and never copied into the pilot pack.
- Shared artifacts: redacted log excerpt, `patchrail-report.md`,
  `patchrail-result.json`, and `pilot-manifest.json`.
- Write actions: not allowed.
- External models: not used.
- GitHub permissions: read-only or none.

## Local Commands

```bash
patchrail doctor --format markdown
patchrail ci pilot-pack --log failed-ci.log --out-dir patchrail-pilot-pack
patchrail ci pilot-summary --pack patchrail-pilot-pack --ci-provider "GitHub Actions" --toolchain Python > pilot-summary.md
patchrail queue --db patchrail-pilot.sqlite init
patchrail queue --db patchrail-pilot.sqlite add --from-pilot-pack patchrail-pilot-pack
patchrail queue --db patchrail-pilot.sqlite audit --format jsonl
```

## Safe Outcome Summary

```markdown
Pilot type: CI triage
Repository mention: not approved for public listing
PatchRail version: 0.1.0
CI provider: GitHub Actions
Toolchain: Python
Raw log copied: no
Write actions allowed: no

Result:
PatchRail classified the failure as `python_dependency_resolution` and pointed
to the dependency resolver error in the redacted log. The suggested maintainer
action was useful because it narrowed review to dependency constraints rather
than test code.

Follow-up:
The maintainer may submit a synthetic fixture that preserves the resolver error
without exposing repository names, user paths, tokens, or emails.
```

## Public Issue Snippet

Use this shape in an adopter or pilot report issue only after checking the
redacted artifacts manually:

```markdown
## Consent

- [x] I maintain this repository or have permission to run PatchRail on it.
- [x] I am not sharing raw secrets, private logs, personal data, or private paths.
- [ ] PatchRail may list the repository in `ADOPTERS.md` if this report is accepted.

Repository approved for public mention: no

## PatchRail version

0.1.0

## Workflow used

CI triage with `patchrail ci pilot-pack` and local queue import.

## Result

PatchRail identified a dependency-resolution failure and produced a useful
maintainer action from redacted evidence.

## Safe evidence

Only redacted report excerpts and the pilot manifest are safe to share. The raw log remains private and was not copied into the pilot pack.
```

`patchrail ci pilot-summary` defaults to keeping the repository unlisted. Pass
`--repository-mention-approved yes` only after the maintainer explicitly
approves public listing.

## Do Not Include

- raw CI logs;
- private repository names unless public mention is explicitly approved;
- usernames, emails, customer names, or local home paths;
- tokens, API keys, bearer headers, or `.env` content;
- screenshots containing secrets;
- claims that PatchRail fixed code, opened a pull request, or contacted a
  maintainer during a read-only pilot.
