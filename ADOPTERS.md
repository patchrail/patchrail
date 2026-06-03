# PatchRail Adopters

PatchRail lists external adopters only with explicit maintainer permission.
Please do not add private repositories, customer names, or unapproved pilot
details.

## Current Status

PatchRail is collecting first read-only maintainer pilots. There are no public external adopters listed yet.

Use [examples/pilot-outcome](examples/pilot-outcome/README.md) as the safe
shape for a pilot summary before requesting a public adopter listing.

## How To Be Listed

Open an adopter report issue when you have run PatchRail on a repository you
maintain or are authorized to test:

- repository or organization name approved for public mention;
- PatchRail version or commit used;
- workflow used, such as CI triage, queue demo, or funded issue read-only scan;
- safe outcome summary without raw logs, secrets, or private paths;
- whether you permit PatchRail to list the repo here.

Accepted entries should stay factual and short:

```markdown
- `owner/repo` - Used PatchRail CI triage on GitHub Actions logs; fixture PR pending.
```

## Privacy Boundary

Do not submit raw CI logs, private repository names, usernames, email addresses,
tokens, local home paths, customer names, or screenshots containing secrets.
Use `patchrail redact` and review the output manually before sharing anything.
