# PatchRail CI Report

- Root cause: `python_dependency_resolution`
- Confidence: `0.89`
- Subsystem: Python dependency installation
- Reproduce: `python -m pip install -r requirements.txt`
- Suggested action: Pin or relax the conflicting dependency range, then rerun the same install command and the affected tests.

## Evidence signals

- `Could not find a version that satisfies the requirement`
- `Cannot install .*because these package versions have conflicting dependencies`
- `ResolutionImpossible`

## Safety

PatchRail classified this log locally. It did not create a pull request, post a comment, claim funding, or send data to an external service.
