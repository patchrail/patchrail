# PatchRail Consent-Only Pilot Summary

## Consent

- Maintainer permission: required before running or publishing pilot results.
- Repository approved for public mention: `true`
- Repository: `patchrail/patchrail`
- Raw CI log copied into pack: `false`
- Maintainer review required before sharing: `true`

## Pilot Context

- CI provider: `GitHub Actions fixture`
- Toolchain: `Python`
- Classification correct: `yes`
- Suggested maintainer action useful: `yes`

## Result

- Root cause: `python_dependency_resolution`
- Confidence: `0.95`
- Subsystem: `Python dependency installation`
- Suggested action: Pin or relax the conflicting dependency range, then rerun the same install command and the affected tests.

## Safety

PatchRail ran locally. It did not copy the raw log, call external models, open a pull request, post a comment, contact a maintainer, claim funding, or request repository write access.

Before publishing this summary, review the redacted log and report manually.
