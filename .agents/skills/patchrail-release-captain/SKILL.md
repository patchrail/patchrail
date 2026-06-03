---
name: patchrail-release-captain
description: Use when preparing a PatchRail release, changelog update, package build, release evidence page, or release notes draft.
---

# PatchRail Release Captain

Prepare release evidence. Do not publish packages, create tags, or announce
releases unless the maintainer explicitly asks for that external action.

## Workflow

1. Read `docs/release-process.md`.
2. Check `pyproject.toml`, `CHANGELOG.md`, README quickstart, docs links, and
   release evidence pages for drift.
3. Build sdist and wheel.
4. Run package checks and a clean wheel smoke install.
5. Update release evidence with exact command results.
6. Leave any remaining publish steps as explicit maintainer gates.

## Required Checks

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run --extra dev ruff format --check .
uv run --extra dev python -m build
uv run --extra dev twine check dist/*
```

## Safety

- Do not publish to PyPI without an explicit maintainer release request.
- Do not create or push release tags unless requested.
- Do not invent download, adoption, or CI metrics.
- Keep release notes focused on verified behavior.
