# Threat Model

## Assets

- CI logs that may contain secrets.
- Repository names and private paths.
- Maintainer write permissions.
- Release and package publishing credentials.

## Local trust boundary

PatchRail runs locally and classifies logs with local rules. Local CI
classification, pilot-pack generation, and Agent Control Plane queue import do
not need a GitHub token, billing account, external model, webhook, or GitHub App.

The default queue state is human-gated. Imported work items remain pending and
`write_actions_allowed=false`; approval records a local decision but does not
open pull requests, comment on issues, push branches, or contact third-party
repositories.

## Pilot pack trust boundary

`patchrail ci pilot-pack` accepts a local CI log and writes a consent-only
handoff directory. The raw input log is read for local classification and
redaction, but the pack output must contain only:

- `failed-ci.redacted.log`
- `patchrail-report.md`
- `patchrail-result.json`
- `pilot-manifest.json`
- `README.md`

The manifest is the queue import contract. It declares
`schema_version=patchrail.ci_pilot_pack.v1`, records
`source.raw_log_copied=false`, lists the local redacted artifacts, and states
that maintainer review is required before sharing.

`patchrail queue add --from-pilot-pack` accepts either the pack directory or the
manifest path. It validates the manifest schema, rejects manifests where
`source.raw_log_copied` is not `false`, loads the local CI result, stores
relative artifact references, and creates a pending local work item with
`write_actions_allowed=false`.

## Main risks

| Risk | Mitigation |
| --- | --- |
| Secret leakage in shared logs | Run `patchrail redact` before publishing fixtures |
| Accidental raw-log packaging | `patchrail ci pilot-pack` writes `failed-ci.redacted.log` and records `source.raw_log_copied=false` |
| Tampered pilot-pack manifest | `queue add --from-pilot-pack` validates `schema_version` and rejects manifests that copied raw logs |
| Confusing queue approval with write permission | Queue approval remains local; imported items keep `write_actions_allowed=false` |
| Overconfident repair suggestions | Unknown or low-signal failures are triage-only |
| Unapproved repository writes | Local workflows do not open PRs, comment on issues, push branches, or request GitHub write scopes |
| Abuse against third-party repos | No auto-commenting, auto-PR, or auto-claim behavior |

## Redaction scope

PatchRail v0.1 redacts common GitHub-style tokens, generic secret assignments,
bearer tokens, API-key-shaped values, email addresses and home-directory paths.
It is a safety layer, not a guarantee that arbitrary logs are safe to publish.

## Future work

- Expand JSON schemas as queue/control-plane outputs become public.
- Add explicit approval gates for any future write-capable workflow.
- Add stronger fixture-pack integrity checks if pilot packs are exchanged across
  machines instead of reviewed locally.
