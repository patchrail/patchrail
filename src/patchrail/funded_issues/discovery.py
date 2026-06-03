from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "patchrail.funded_issues.v1"
BLOCKED_ACTIONS = [
    "automatic_claims",
    "automatic_pull_requests",
    "automatic_issue_comments",
    "mass_outreach",
    "ranking_by_money_only",
]

HIGH_RISK_FLAGS = {
    "ambiguous_scope",
    "bounty_farming_language",
    "requires_external_contact",
    "no_contribution_guidelines",
    "spam_attractive",
}


@dataclass(frozen=True)
class FundedIssue:
    id: str
    platform: str
    repository: str
    issue_number: int | None
    title: str
    url: str
    funding_amount: float | None = None
    funding_currency: str | None = None
    language: str | None = None
    labels: list[str] = field(default_factory=list)
    contribution_signals: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    maintainer_permission: str = "public_issue_only"
    contribution_guidelines_url: str | None = None

    @property
    def reference(self) -> str:
        if self.issue_number is None:
            return self.repository
        return f"{self.repository}#{self.issue_number}"

    @property
    def funding_display(self) -> str:
        if self.funding_amount is None or self.funding_currency is None:
            return "unknown"
        amount = (
            int(self.funding_amount) if self.funding_amount.is_integer() else self.funding_amount
        )
        return f"{amount} {self.funding_currency}"

    @property
    def risk_level(self) -> str:
        if any(flag in HIGH_RISK_FLAGS for flag in self.risk_flags):
            return "high"
        if not self.contribution_guidelines_url:
            return "medium"
        return "low"

    @property
    def safe_to_list(self) -> bool:
        return self.risk_level != "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "repository": self.repository,
            "issue_number": self.issue_number,
            "reference": self.reference,
            "title": self.title,
            "url": self.url,
            "funding": {
                "amount": self.funding_amount,
                "currency": self.funding_currency,
                "display": self.funding_display,
            },
            "language": self.language,
            "labels": self.labels,
            "contribution_signals": self.contribution_signals,
            "risk_flags": self.risk_flags,
            "risk_level": self.risk_level,
            "safe_to_list": self.safe_to_list,
            "maintainer_permission": self.maintainer_permission,
            "contribution_guidelines_url": self.contribution_guidelines_url,
            "read_only": True,
            "blocked_actions": BLOCKED_ACTIONS,
        }


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [str(item) for item in value]


def _issue_from_mapping(raw: dict[str, Any]) -> FundedIssue:
    funding = raw.get("funding") or {}
    if not isinstance(funding, dict):
        raise ValueError("funding must be an object")
    amount = funding.get("amount")
    if amount is not None:
        amount = float(amount)
    issue_number = raw.get("issue_number")
    if issue_number is not None:
        issue_number = int(issue_number)
    return FundedIssue(
        id=str(raw["id"]),
        platform=str(raw["platform"]),
        repository=str(raw["repository"]),
        issue_number=issue_number,
        title=str(raw["title"]),
        url=str(raw["url"]),
        funding_amount=amount,
        funding_currency=str(funding["currency"]) if funding.get("currency") else None,
        language=str(raw["language"]) if raw.get("language") else None,
        labels=_as_string_list(raw.get("labels")),
        contribution_signals=_as_string_list(raw.get("contribution_signals")),
        risk_flags=_as_string_list(raw.get("risk_flags")),
        maintainer_permission=str(raw.get("maintainer_permission") or "public_issue_only"),
        contribution_guidelines_url=(
            str(raw["contribution_guidelines_url"])
            if raw.get("contribution_guidelines_url")
            else None
        ),
    )


def load_funded_issues(source: Path) -> list[FundedIssue]:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"source must use schema_version {SCHEMA_VERSION}")
    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        raise ValueError("source must contain an issues list")
    issues = []
    for raw_issue in raw_issues:
        if not isinstance(raw_issue, dict):
            raise ValueError("each issue must be an object")
        issues.append(_issue_from_mapping(raw_issue))
    return issues


def funded_issues_payload(
    issues: list[FundedIssue],
    *,
    import_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "blocked_actions": BLOCKED_ACTIONS,
        "issues": [issue.to_dict() for issue in issues],
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
    }
    if import_source:
        payload["import_source"] = import_source
    return payload


def summarize_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = True,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
) -> dict[str, Any]:
    filtered: list[FundedIssue] = []
    for issue in issues:
        if safe_only and not issue.safe_to_list:
            continue
        if platform and issue.platform.lower() != platform.lower():
            continue
        if language and (issue.language or "").lower() != language.lower():
            continue
        if min_usd is not None:
            if issue.funding_currency != "USD" or issue.funding_amount is None:
                continue
            if issue.funding_amount < min_usd:
                continue
        filtered.append(issue)
    return {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "total_loaded": len(issues),
        "total_returned": len(filtered),
        "issues": [issue.to_dict() for issue in filtered],
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
    }


def explain_issue(issues: list[FundedIssue], reference: str) -> dict[str, Any]:
    for issue in issues:
        if reference in {issue.id, issue.reference, issue.url}:
            return {
                "schema_version": SCHEMA_VERSION,
                "read_only": True,
                "issue": issue.to_dict(),
                "ethics": {
                    "allowed": [
                        "read public funding metadata",
                        "review contribution guidelines",
                        "prepare a local maintainer-readiness note",
                    ],
                    "blocked": BLOCKED_ACTIONS,
                },
                "recommendation": _recommendation_for(issue),
            }
    raise KeyError(reference)


def _recommendation_for(issue: FundedIssue) -> str:
    if issue.risk_level == "high":
        return (
            "Do not pursue automatically. Keep this as read-only metadata unless a maintainer "
            "explicitly invites help and the scope is clarified."
        )
    if issue.risk_level == "medium":
        return (
            "Review contribution guidelines before any work. Treat funding as context, not as the "
            "primary ranking signal."
        )
    return (
        "Safe to keep in a local funded-maintenance shortlist. Any contribution still requires "
        "normal maintainer review and project rules."
    )
