# Funded Issues Ethics

Funded issue discovery is experimental and intentionally read-only. Funding can
be a useful sustainability signal for open source maintenance when handled
carefully, but it must never become bounty farming.

## Policy

Any future funded issue feature must be read-only by default.

PatchRail must not:

- claim rewards automatically;
- rank work only by funding amount;
- mass-comment on third-party issues;
- submit automatic pull requests to repositories without maintainer permission;
- bypass platform limits or project contribution rules;
- encourage low-quality contributions for payout capture.

## Intended Use

The intended future use is contribution readiness, not bounty farming:

- identify funded maintenance areas;
- explain project contribution rules;
- warn when an issue is likely to attract spam;
- help maintainers understand where work is funded;
- help contributors decide whether they can contribute meaningfully.

## Default Boundary

The safe default is local output only:

```bash
patchrail funded-issues list \
  --source examples/funded-issues-readonly/issues.json \
  --format json

patchrail funded-issues explain example/project#42 \
  --source examples/funded-issues-readonly/issues.json \
  --format markdown
```

No comment, pull request, claim or contact action happens from these commands.
The default list view filters out high-risk records. `--include-risky` only
changes local output visibility; it still does not permit write actions.

Provider exports can be normalized from local files:

```bash
patchrail funded-issues import \
  --provider github \
  --source examples/funded-issues-readonly/provider-github-export.json \
  --format json \
  --out .patchrail-funded-issues.json
```

Supported provider export labels are `algora`, `github`, `openpledge`, and
`polar`. This is an offline import path: PatchRail reads a JSON file already on
disk and converts it into `patchrail.funded_issues.v1`. It does not fetch
provider APIs, scrape websites, require credentials, or request GitHub write
permission.

## Local Source Contract

The public implementation reads local JSON files only. It does not fetch
platform APIs, scrape websites, call models, require billing, or ask for GitHub
write permissions.

Each record is evaluated for:

- contribution-readiness signals;
- contribution guideline availability;
- anti-abuse risk flags;
- maintainer permission posture;
- funding metadata as context, not as the ranking objective.

High-risk examples include ambiguous scope, spam-attractive funding, missing
contribution guidelines, and language that frames the work as payout capture.
