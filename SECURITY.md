# Security Policy

## Supported versions

PatchRail is pre-1.0. Security fixes are released on the latest minor version.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting when available. If that is not
available, contact PatchRail through the repository's listed security contact.

Do not paste secrets, private CI logs, access tokens, customer data, or private
repository names into public issues.

## Log safety

CI logs can contain tokens, internal paths, hostnames, package registry URLs, and
deployment metadata. PatchRail v0.1 processes logs locally and does not send them
to a remote service by default.

Before sharing a log fixture publicly:

1. Remove tokens and credentials.
2. Replace private user, org, repo, and host names.
3. Normalize local file paths.
4. Keep only the smallest excerpt needed to classify the failure.

## Pilot pack boundary

`patchrail ci pilot-pack` is designed for consent-only maintainer pilots. It
creates a local handoff directory with a redacted log, Markdown report,
structured CI result, manifest, and README. It must not be treated as proof that
the original raw log is safe to publish.

Security properties:

- The pack manifest uses `schema_version=patchrail.ci_pilot_pack.v1`.
- The generated manifest records `source.raw_log_copied=false`.
- The output directory contains `failed-ci.redacted.log`, not the raw input log.
- Maintainer review is still required before sharing any artifact publicly.
- The pack does not grant GitHub permissions, call external models, contact
  third-party repositories, open pull requests, comment on issues, or require
  billing.

`patchrail queue add --from-pilot-pack` imports only local pilot-pack artifacts
into the Agent Control Plane. The importer validates the manifest schema,
rejects packs that claim a raw log was copied, stores local artifact references,
and creates a pending work item with `write_actions_allowed=false`.
