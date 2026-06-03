# Funded Issues Read-Only Demo

This fixture shows the future funded issue scout boundary:

```bash
patchrail funded-issues list --source examples/funded-issues-readonly/issues.json
patchrail funded-issues explain example/project#42 --source examples/funded-issues-readonly/issues.json
```

The command reads local JSON only. It does not claim rewards, post comments,
open pull requests, contact maintainers, or rank work by funding alone.

Provider exports can be normalized locally before listing:

```bash
patchrail funded-issues import \
  --provider github \
  --source examples/funded-issues-readonly/provider-github-export.json \
  --out .patchrail-funded-issues.json

patchrail funded-issues list --source .patchrail-funded-issues.json
```

The import command does not fetch APIs or scrape websites. It only transforms a
local JSON export into PatchRail's read-only funded issue schema.
