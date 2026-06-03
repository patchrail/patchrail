from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from patchrail.funded_issues.discovery import FundedIssue, funded_issues_payload


SUPPORTED_PROVIDERS = ("algora", "github", "openpledge", "polar")

_AMBIGUOUS_SCOPE_TERMS = (
    "architecture",
    "broad",
    "entire",
    "rewrite",
    "unclear",
)
_SPAM_ATTRACTIVE_LABELS = ("bounty", "reward", "paid")
_CONTRIBUTION_SIGNAL_LABELS = (
    "ci",
    "bug",
    "good first issue",
    "good-first-issue",
    "help wanted",
    "tests",
)


def import_provider_export(provider: str, source: Path) -> dict[str, Any]:
    provider = provider.lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = _extract_records(payload)
    issues = [
        _issue_from_provider_record(provider, record, index) for index, record in enumerate(records)
    ]
    return funded_issues_payload(
        issues,
        import_source={
            "provider": provider,
            "path": str(source),
            "records_loaded": len(records),
            "local_file_only": True,
        },
    )


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("issues", "items", "bounties", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                records = value
                break
        else:
            records = [payload]
    else:
        raise ValueError("provider export must be a JSON object or array")
    if not all(isinstance(record, dict) for record in records):
        raise ValueError("provider export records must be objects")
    return records


def _issue_from_provider_record(provider: str, raw: dict[str, Any], index: int) -> FundedIssue:
    repository = _repository(raw)
    issue_number = _issue_number(raw)
    title = _first_string(raw, "title", "name", "summary") or "Untitled funded issue"
    url = _first_string(raw, "url", "html_url", "issue_url", "github_url") or repository
    amount, currency = _funding(raw)
    labels = _labels(raw)
    contribution_guidelines_url = _first_string(
        raw,
        "contribution_guidelines_url",
        "contributing_url",
        "guidelines_url",
    )
    contribution_signals = _contribution_signals(raw, labels, contribution_guidelines_url)
    risk_flags = _risk_flags(raw, title, labels, amount, contribution_guidelines_url)
    identifier = _first_string(raw, "id", "node_id", "slug") or _stable_id(
        provider, repository, issue_number, title, index
    )
    language = _first_string(raw, "language", "primary_language", "repo_language")
    return FundedIssue(
        id=str(identifier),
        platform=provider,
        repository=repository,
        issue_number=issue_number,
        title=title,
        url=url,
        funding_amount=amount,
        funding_currency=currency,
        language=language,
        labels=labels,
        contribution_signals=contribution_signals,
        risk_flags=risk_flags,
        maintainer_permission=str(raw.get("maintainer_permission") or "public_issue_only"),
        contribution_guidelines_url=contribution_guidelines_url,
    )


def _repository(raw: dict[str, Any]) -> str:
    direct = _first_string(raw, "repository", "repo", "repo_full_name", "full_name")
    if direct:
        return direct
    nested = raw.get("repository")
    if isinstance(nested, dict):
        nested_name = _first_string(nested, "full_name", "name")
        owner = nested.get("owner")
        if nested_name and "/" in nested_name:
            return nested_name
        if isinstance(owner, dict):
            owner_name = _first_string(owner, "login", "name")
        else:
            owner_name = str(owner) if owner else None
        if owner_name and nested_name:
            return f"{owner_name}/{nested_name}"
    owner = _first_string(raw, "owner", "org", "organization")
    repo_name = _first_string(raw, "repo_name", "project", "name")
    if owner and repo_name:
        return f"{owner}/{repo_name}"
    url = _first_string(raw, "url", "html_url", "issue_url", "github_url") or ""
    match = re.search(r"github\.com/([^/\s]+/[^/\s#]+)", url)
    if match:
        return match.group(1).removesuffix(".git")
    return "unknown/unknown"


def _issue_number(raw: dict[str, Any]) -> int | None:
    for key in ("issue_number", "number", "github_issue_number", "issue"):
        value = raw.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    url = _first_string(raw, "url", "html_url", "issue_url", "github_url") or ""
    match = re.search(r"/issues/(\d+)", url)
    return int(match.group(1)) if match else None


def _funding(raw: dict[str, Any]) -> tuple[float | None, str | None]:
    funding = raw.get("funding")
    if isinstance(funding, dict):
        amount = _numeric(funding.get("amount") or funding.get("value") or funding.get("usd"))
        currency = _first_string(funding, "currency", "currency_code")
        return amount, currency.upper() if currency else None

    bounty = raw.get("bounty")
    if isinstance(bounty, dict):
        amount = _numeric(bounty.get("amount") or bounty.get("value") or bounty.get("usd"))
        currency = _first_string(bounty, "currency", "currency_code")
        return amount, currency.upper() if currency else None

    for key in ("amount_usd", "reward_usd", "bounty_usd", "funding_usd"):
        amount = _numeric(raw.get(key))
        if amount is not None:
            return amount, "USD"

    amount = _numeric(raw.get("amount") or raw.get("reward") or raw.get("bounty_amount"))
    currency = _first_string(raw, "currency", "currency_code")
    return amount, currency.upper() if currency else None


def _labels(raw: dict[str, Any]) -> list[str]:
    labels = raw.get("labels")
    if not isinstance(labels, list):
        return []
    values = []
    for label in labels:
        if isinstance(label, dict):
            value = _first_string(label, "name", "label")
        else:
            value = str(label)
        if value:
            values.append(value)
    return values


def _contribution_signals(
    raw: dict[str, Any], labels: list[str], contribution_guidelines_url: str | None
) -> list[str]:
    signals = _string_list(raw.get("contribution_signals"))
    normalized_labels = {label.lower() for label in labels}
    for label in normalized_labels:
        if label in _CONTRIBUTION_SIGNAL_LABELS:
            signals.append(f"label:{label}")
    body = _first_string(raw, "body", "description") or ""
    if "reproduction" in body.lower() or "steps to reproduce" in body.lower():
        signals.append("reproduction included")
    if contribution_guidelines_url:
        signals.append("contribution guidelines linked")
    return sorted(set(signals))


def _risk_flags(
    raw: dict[str, Any],
    title: str,
    labels: list[str],
    amount: float | None,
    contribution_guidelines_url: str | None,
) -> list[str]:
    flags = _string_list(raw.get("risk_flags"))
    title_lower = title.lower()
    label_lowers = {label.lower() for label in labels}
    if any(term in title_lower for term in _AMBIGUOUS_SCOPE_TERMS):
        flags.append("ambiguous_scope")
    if any(label in label_lowers for label in _SPAM_ATTRACTIVE_LABELS):
        flags.append("spam_attractive")
    if amount is not None and amount >= 1000 and not contribution_guidelines_url:
        flags.append("spam_attractive")
    if not contribution_guidelines_url:
        flags.append("no_contribution_guidelines")
    return sorted(set(flags))


def _first_string(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _stable_id(
    provider: str, repository: str, issue_number: int | None, title: str, index: int
) -> str:
    digest = hashlib.sha256(f"{repository}:{issue_number}:{title}:{index}".encode()).hexdigest()[
        :12
    ]
    return f"{provider}-{digest}"
