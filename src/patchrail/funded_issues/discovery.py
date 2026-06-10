from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "patchrail.funded_issues.v1"
CLIENT_PROFILE_SCHEMA_VERSION = "patchrail.funded_issues.client_profile.v1"
VALIDATION_SCHEMA_VERSION = "patchrail.funded_issues.validation.v1"
SHORTLIST_SCHEMA_VERSION = "patchrail.funded_issues.shortlist.v1"
CLIENT_REPORT_SCHEMA_VERSION = "patchrail.funded_issues.client_report.v1"
RECHECK_QUEUE_SCHEMA_VERSION = "patchrail.funded_issues.recheck_queue.v1"
CASH_ACTIONS_SCHEMA_VERSION = "patchrail.funded_issues.cash_actions.v1"
FULFILLMENT_PACKET_SCHEMA_VERSION = "patchrail.funded_issues.fulfillment_packet.v1"
COMPETITION_SIGNAL_SCHEMA_VERSION = "patchrail.funded_issues.competition.v1"
COMPETITION_BATCH_SCHEMA_VERSION = "patchrail.funded_issues.competition_batch.v1"
PAYOUT_EFFORT_SIGNAL_SCHEMA_VERSION = "patchrail.funded_issues.payout_effort.v1"
PAYOUT_EFFORT_BATCH_SCHEMA_VERSION = "patchrail.funded_issues.payout_effort_batch.v1"
STALENESS_SIGNAL_SCHEMA_VERSION = "patchrail.funded_issues.staleness.v1"
STALENESS_BATCH_SCHEMA_VERSION = "patchrail.funded_issues.staleness_batch.v1"
TESTABILITY_SIGNAL_SCHEMA_VERSION = "patchrail.funded_issues.testability.v1"
TESTABILITY_BATCH_SCHEMA_VERSION = "patchrail.funded_issues.testability_batch.v1"
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
    "closed_or_inactive",
    "requires_external_contact",
    "no_contribution_guidelines",
    "spam_attractive",
    "stale_no_maintainer_signal",
}
PRIMARY_SOURCE_REVIEW_FLAGS = {
    "aggregator_only_source",
    "discovery_only_source",
    "primary_source_required",
}

# Competition / noise-trap signal flags. These are intentionally NOT in
# HIGH_RISK_FLAGS: a contested bounty can still be a real, winnable issue, so it
# costs score and confidence (via the generic risk-flag penalty) without forcing
# an automatic no-go. They productize the per-prospect recon the desk does by
# hand (e.g. counting competing PRs and comment volume on a sponsor's bounties).
CONTESTED_BOUNTY_FLAG = "contested_bounty"
CROWDED_NO_ASSIGNMENT_FLAG = "crowded_no_assignment"
COMPETITION_THRESHOLDS = {
    "competing_pr_count_contested": 3,
    "distinct_claimants_contested": 3,
    "comment_count_busy": 15,
}

# Payout-vs-effort signal. The flag is intentionally NOT in HIGH_RISK_FLAGS: a
# low-paying bounty can still be worth doing for portfolio/strategic reasons, so
# it costs score via the generic risk penalty without forcing an automatic
# no-go. Productizes the desk's effort-budget floor (REVENUE_PLAN §16.1: a
# $150/h minimum effective rate before engineering time is committed).
DEFAULT_TARGET_HOURLY_RATE_USD = 150.0
PAYOUT_EFFORT_FLAG = "payout_too_low_for_effort"
PAYOUT_EFFORT_THRESHOLDS = {
    "target_hourly_rate_usd": DEFAULT_TARGET_HOURLY_RATE_USD,
    "low_ratio": 0.5,
    "marginal_ratio": 1.0,
}

# Staleness / liveness signal. Productizes the desk's core "filter stale traps"
# value prop (REVENUE_PLAN §10.2 STALE_NO_MAINTAINER_SIGNAL): derive an
# opportunity_state recommendation from observable issue age plus whether a
# maintainer is still engaging, instead of eyeballing it per prospect. A
# ``stale``/``dormant`` result emits the existing high-risk
# ``stale_no_maintainer_signal`` flag (forces no-go, like a closed/stale state),
# while a merely ``aging`` result emits the softer, non-high-risk
# ``aging_low_activity`` flag (costs score via the generic risk penalty without
# forcing a no-go). Inputs are public age/activity metadata only; this never
# claims, comments, or contacts anyone.
STALE_NO_MAINTAINER_FLAG = "stale_no_maintainer_signal"
AGING_LOW_ACTIVITY_FLAG = "aging_low_activity"
STALENESS_THRESHOLDS = {
    "active_max_days": 30,
    "aging_max_days": 90,
    "stale_max_days": 180,
    "long_unresolved_days": 365,
}

# Testability / reproducibility signal. Productizes the desk's "can you verify
# it?" check (REVENUE_PLAN §9.2 Tests row, §10.2 NO_REPRO_OR_TEST_PATH): a funded
# issue you cannot objectively reproduce or test is hard to close even when the
# bounty is real, because the maintainer cannot tell a correct fix from a
# plausible one. The flag is intentionally NOT in HIGH_RISK_FLAGS: a docs or
# config issue can be legitimately untestable, so a missing test path costs score
# via the generic risk penalty without forcing an automatic no-go. Inputs are
# observable issue-body signals only; this never claims, comments, or contacts
# anyone.
NO_REPRO_OR_TEST_PATH_FLAG = "no_repro_or_test_path"

VALID_OPPORTUNITY_STATES = {"active", "closed", "stale", "unknown"}
VALID_RISK_LEVELS = {"high", "low", "medium"}
VALID_DECISION_GATES = {
    "go_after_recheck",
    "needs_authorization",
    "needs_funding_verification",
    "no_go",
    "watchlist",
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
    opportunity_state: str = "unknown"

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
        return (
            self.risk_level != "high"
            and self.opportunity_state not in {"closed", "stale"}
            and not self.primary_source_required
        )

    @property
    def primary_source_required(self) -> bool:
        return bool(set(self.risk_flags).intersection(PRIMARY_SOURCE_REVIEW_FLAGS))

    @property
    def source_review(self) -> dict[str, Any]:
        return {
            "primary_source_required": self.primary_source_required,
            "risk_flags": sorted(set(self.risk_flags).intersection(PRIMARY_SOURCE_REVIEW_FLAGS)),
            "required_before_shortlist": self.primary_source_required,
            "next_step": (
                "verify funding and current state from a permitted primary public/API source"
                if self.primary_source_required
                else "standard public-state recheck"
            ),
        }

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
            "source_review": self.source_review,
            "opportunity_state": self.opportunity_state,
            "maintainer_permission": self.maintainer_permission,
            "contribution_guidelines_url": self.contribution_guidelines_url,
            "read_only": True,
            "blocked_actions": BLOCKED_ACTIONS,
        }


@dataclass(frozen=True)
class ClientProfile:
    name: str | None = None
    languages: tuple[str, ...] = ()
    min_usd: float | None = None
    allowed_opportunity_states: tuple[str, ...] = ()
    allowed_risk_levels: tuple[str, ...] = ()
    excluded_risk_flags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CLIENT_PROFILE_SCHEMA_VERSION,
            "name": self.name,
            "languages": list(self.languages),
            "min_usd": self.min_usd,
            "allowed_opportunity_states": list(self.allowed_opportunity_states),
            "allowed_risk_levels": list(self.allowed_risk_levels),
            "excluded_risk_flags": list(self.excluded_risk_flags),
            "read_only": True,
        }


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("expected a list")
    return [str(item) for item in value]


def _as_normalized_tuple(value: Any) -> tuple[str, ...]:
    return tuple(sorted({item.strip().lower() for item in _as_string_list(value) if item.strip()}))


def _profile_from_mapping(raw: dict[str, Any]) -> ClientProfile:
    schema_version = raw.get("schema_version")
    if schema_version != CLIENT_PROFILE_SCHEMA_VERSION:
        raise ValueError(f"profile must use schema_version {CLIENT_PROFILE_SCHEMA_VERSION}")
    min_usd = raw.get("min_usd")
    if min_usd is not None:
        min_usd = float(min_usd)
        if min_usd < 0:
            raise ValueError("profile min_usd must be >= 0")
    states = tuple(
        _normalize_opportunity_state_filter(state)
        for state in _as_normalized_tuple(raw.get("allowed_opportunity_states"))
    )
    risk_levels = tuple(
        _normalize_risk_level_filter(risk_level)
        for risk_level in _as_normalized_tuple(raw.get("allowed_risk_levels"))
    )
    return ClientProfile(
        name=str(raw["name"]) if raw.get("name") else None,
        languages=_as_normalized_tuple(raw.get("languages")),
        min_usd=min_usd,
        allowed_opportunity_states=states,
        allowed_risk_levels=risk_levels,
        excluded_risk_flags=_as_normalized_tuple(raw.get("excluded_risk_flags")),
    )


def load_client_profile(source: Path) -> ClientProfile:
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("profile source must contain an object")
    return _profile_from_mapping(payload)


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
        opportunity_state=_normalize_opportunity_state(
            raw.get("opportunity_state") or raw.get("state") or raw.get("status")
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


def validate_funded_issues(issues: list[FundedIssue]) -> dict[str, Any]:
    duplicate_ids = _duplicates(issue.id for issue in issues)
    duplicate_references = _duplicates(issue.reference for issue in issues)
    missing_funding = [
        issue.reference
        for issue in issues
        if issue.funding_amount is None or issue.funding_currency is None
    ]
    missing_guidelines = [
        issue.reference for issue in issues if not issue.contribution_guidelines_url
    ]
    missing_signals = [issue.reference for issue in issues if not issue.contribution_signals]
    high_risk = [issue.reference for issue in issues if issue.risk_level == "high"]
    stale_or_closed = [
        issue.reference for issue in issues if issue.opportunity_state in {"closed", "stale"}
    ]
    warnings = {
        "duplicate_ids": duplicate_ids,
        "duplicate_references": duplicate_references,
        "missing_funding": missing_funding,
        "missing_contribution_guidelines": missing_guidelines,
        "missing_contribution_signals": missing_signals,
        "high_risk": high_risk,
        "stale_or_closed": stale_or_closed,
    }
    warning_count = sum(len(items) for items in warnings.values())
    risk_levels = Counter(issue.risk_level for issue in issues)
    opportunity_states = Counter(issue.opportunity_state for issue in issues)
    return {
        "schema_version": VALIDATION_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "status": "ok" if warning_count == 0 else "needs_review",
        "read_only": True,
        "total_loaded": len(issues),
        "warning_count": warning_count,
        "warnings": warnings,
        "counts": {
            "safe_to_list": sum(1 for issue in issues if issue.safe_to_list),
            "high_risk": risk_levels.get("high", 0),
            "medium_risk": risk_levels.get("medium", 0),
            "low_risk": risk_levels.get("low", 0),
            "active": opportunity_states.get("active", 0),
            "stale": opportunity_states.get("stale", 0),
            "closed": opportunity_states.get("closed", 0),
            "unknown_state": opportunity_states.get("unknown", 0),
        },
        "blocked_actions": BLOCKED_ACTIONS,
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Validation is local and read-only. Warnings require human review before the dataset "
            "is used as paid-opportunity evidence."
        ),
    }


def _duplicates(values: Any) -> list[str]:
    counts = Counter(str(value) for value in values)
    return sorted(value for value, count in counts.items() if count > 1)


def summarize_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = True,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    opportunity_state = _normalize_opportunity_state_filter(opportunity_state)
    risk_level = _normalize_risk_level_filter(risk_level)
    filtered: list[FundedIssue] = []
    for issue in issues:
        if safe_only and not issue.safe_to_list:
            continue
        if not _matches_report_filter(
            issue,
            profile=profile,
            platform=platform,
            language=language,
            min_usd=min_usd,
            opportunity_state=opportunity_state,
            risk_level=risk_level,
        ):
            continue
        filtered.append(issue)
    return {
        "schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "total_loaded": len(issues),
        "total_returned": len(filtered),
        "filters": {
            "profile": profile.to_dict() if profile else None,
            "platform": platform,
            "language": language,
            "min_usd": min_usd,
            "opportunity_state": opportunity_state,
            "risk_level": risk_level,
        },
        "issues": [issue.to_dict() for issue in filtered],
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
    }


def report_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    opportunity_state = _normalize_opportunity_state_filter(opportunity_state)
    risk_level = _normalize_risk_level_filter(risk_level)
    client_fit_gaps = _client_fit_gaps(issues, profile)
    summary = summarize_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    scoped_issues = [
        issue
        for issue in issues
        if _matches_report_filter(
            issue,
            profile=profile,
            platform=platform,
            language=language,
            min_usd=min_usd,
            opportunity_state=opportunity_state,
            risk_level=risk_level,
        )
    ]
    returned_issues = [_issue_from_mapping(issue) for issue in summary["issues"]]
    risk_levels = Counter(issue.risk_level for issue in scoped_issues)
    platforms = Counter(issue.platform for issue in scoped_issues)
    languages = Counter(issue.language or "unknown" for issue in scoped_issues)
    risk_flags = Counter(flag for issue in scoped_issues for flag in issue.risk_flags)
    opportunity_states = Counter(issue.opportunity_state for issue in scoped_issues)
    funding_known = sum(1 for issue in scoped_issues if issue.funding_amount is not None)
    funding_unknown = len(scoped_issues) - funding_known
    scored_rows = [_score_issue(issue) for issue in scoped_issues]
    decision_summary = _decision_summary(scored_rows)
    delivery_budget = _delivery_budget(scored_rows)
    source_quality = _source_quality(scored_rows)
    recheck_plan = _recheck_plan(scored_rows)
    evidence_debt = _evidence_debt(recheck_plan)
    client_fit_summary = _client_fit_summary(issues, profile, client_fit_gaps)
    intake_followup = _intake_followup(
        client_fit_summary=client_fit_summary,
        recheck_plan=recheck_plan,
        delivery_budget=delivery_budget,
        source_quality=source_quality,
        decision_summary=decision_summary,
    )
    cash_path_status = _cash_path_status(intake_followup)
    delivery_pack = _delivery_pack(scored_rows)
    safe_candidates = sorted(
        (issue for issue in returned_issues if issue.safe_to_list),
        key=_candidate_sort_key,
    )
    return {
        "schema_version": "patchrail.funded_issues.report.v1",
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": {
            "profile": profile.to_dict() if profile else None,
            "platform": platform,
            "language": language,
            "min_usd": min_usd,
            "opportunity_state": opportunity_state,
            "risk_level": risk_level,
        },
        "totals": {
            "loaded": len(issues),
            "in_scope": len(scoped_issues),
            "returned": len(returned_issues),
            "safe_to_list": sum(1 for issue in scoped_issues if issue.safe_to_list),
            "high_risk": risk_levels.get("high", 0),
            "funding_known": funding_known,
            "funding_unknown": funding_unknown,
        },
        "breakdown": {
            "risk_levels": dict(sorted(risk_levels.items())),
            "platforms": dict(sorted(platforms.items())),
            "languages": dict(sorted(languages.items())),
            "risk_flags": dict(sorted(risk_flags.items())),
            "opportunity_states": dict(sorted(opportunity_states.items())),
        },
        "no_go_moat": {
            "high_risk_or_excluded": sum(1 for issue in scoped_issues if not issue.safe_to_list),
            "missing_contribution_guidelines": sum(
                1 for issue in scoped_issues if not issue.contribution_guidelines_url
            ),
            "ambiguous_scope": risk_flags.get("ambiguous_scope", 0),
            "spam_attractive": risk_flags.get("spam_attractive", 0),
            "funding_unknown": funding_unknown,
            "stale_or_closed": sum(
                1 for issue in scoped_issues if issue.opportunity_state in {"closed", "stale"}
            ),
        },
        "decision_summary": decision_summary,
        "delivery_budget": delivery_budget,
        "delivery_pack": delivery_pack,
        "source_quality": source_quality,
        "recheck_plan": recheck_plan,
        "evidence_debt": evidence_debt,
        "client_fit_summary": client_fit_summary,
        "client_fit_gaps": client_fit_gaps,
        "intake_followup": intake_followup,
        "cash_path_status": cash_path_status,
        "operator_next_steps": _operator_next_steps(
            cash_path_status=cash_path_status,
            intake_followup=intake_followup,
            recheck_plan=recheck_plan,
            delivery_pack=delivery_pack,
        ),
        "top_safe_candidates": [
            {
                "reference": issue.reference,
                "title": issue.title,
                "platform": issue.platform,
                "funding": issue.funding_display,
                "opportunity_state": issue.opportunity_state,
                "risk_level": issue.risk_level,
                "signals": issue.contribution_signals,
                "url": issue.url,
            }
            for issue in safe_candidates
        ],
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Local read-only report only. PatchRail does not claim rewards, post comments, "
            "open pull requests, contact maintainers, or rank work by money alone."
        ),
    }


def score_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    opportunity_state = _normalize_opportunity_state_filter(opportunity_state)
    risk_level = _normalize_risk_level_filter(risk_level)
    scored = [
        _score_issue(issue)
        for issue in issues
        if _matches_report_filter(
            issue,
            profile=profile,
            platform=platform,
            language=language,
            min_usd=min_usd,
            opportunity_state=opportunity_state,
            risk_level=risk_level,
        )
    ]
    if safe_only:
        scored = [row for row in scored if row["issue"]["safe_to_list"]]
    ratings = Counter(row["rating"] for row in scored)
    return {
        "schema_version": "patchrail.funded_issues.score.v1",
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": {
            "profile": profile.to_dict() if profile else None,
            "platform": platform,
            "language": language,
            "min_usd": min_usd,
            "opportunity_state": opportunity_state,
            "risk_level": risk_level,
        },
        "total_loaded": len(issues),
        "total_scored": len(scored),
        "rating_counts": dict(sorted(ratings.items())),
        "scores": sorted(
            scored,
            key=lambda row: (-int(row["score"]), row["issue"]["reference"]),
        ),
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Local read-only readiness scoring only. Funding is context, not an instruction to "
            "claim rewards, post comments, open pull requests, or contact maintainers."
        ),
    }


def shortlist_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    score_payload = score_funded_issues(
        issues,
        safe_only=False,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    report_payload = report_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    candidate_rows = [
        row
        for row in score_payload["scores"]
        if _is_shortlist_candidate_row(row) and (not safe_only or row["issue"]["safe_to_list"])
    ]
    no_go_rows = [row for row in score_payload["scores"] if row["rating"] == "no_go"]
    decision_summary = _decision_summary(score_payload["scores"])
    delivery_budget = _delivery_budget(score_payload["scores"])
    source_quality = _source_quality(score_payload["scores"])
    recheck_plan = _recheck_plan(score_payload["scores"])
    evidence_debt = _evidence_debt(recheck_plan)
    client_fit_summary = _client_fit_summary(issues, profile, report_payload["client_fit_gaps"])
    intake_followup = _intake_followup(
        client_fit_summary=client_fit_summary,
        recheck_plan=recheck_plan,
        delivery_budget=delivery_budget,
        source_quality=source_quality,
        decision_summary=decision_summary,
    )
    cash_path_status = _cash_path_status(intake_followup)
    delivery_pack = _delivery_pack(score_payload["scores"])
    return {
        "schema_version": SHORTLIST_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "limit": limit,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": score_payload["filters"],
        "summary": {
            "total_loaded": score_payload["total_loaded"],
            "total_scored": score_payload["total_scored"],
            "rating_counts": score_payload["rating_counts"],
            "in_scope": report_payload["totals"]["in_scope"],
            "safe_to_list": report_payload["totals"]["safe_to_list"],
            "high_risk": report_payload["totals"]["high_risk"],
            "opportunity_states": report_payload["breakdown"]["opportunity_states"],
        },
        "shortlist": candidate_rows[:limit],
        "no_go_evidence": no_go_rows,
        "no_go_moat": report_payload["no_go_moat"],
        "decision_summary": {
            **decision_summary,
            "candidate_rows": len(candidate_rows),
            "no_go_rows": len(no_go_rows),
        },
        "delivery_budget": delivery_budget,
        "delivery_pack": delivery_pack,
        "source_quality": source_quality,
        "recheck_plan": recheck_plan,
        "evidence_debt": evidence_debt,
        "client_fit_summary": client_fit_summary,
        "client_fit_gaps": report_payload["client_fit_gaps"],
        "intake_followup": intake_followup,
        "cash_path_status": cash_path_status,
        "operator_next_steps": _operator_next_steps(
            cash_path_status=cash_path_status,
            intake_followup=intake_followup,
            recheck_plan=recheck_plan,
            delivery_pack=delivery_pack,
        ),
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Decision support only. PatchRail does not claim rewards, post comments, open pull "
            "requests, contact maintainers, or guarantee merge or payout outcomes."
        ),
    }


CLIENT_REPORT_DISCLAIMER = (
    "This report is read-only opportunity intelligence. It does not guarantee bounty "
    "availability, merge acceptance, payout, or maintainer response. No claims, comments, "
    "outreach, or PR submissions were made by PatchRail unless explicitly authorized in writing."
)


def _client_report_maintainer_activity(issue: dict[str, Any]) -> str:
    state = issue.get("opportunity_state")
    if state == "active":
        return "active opportunity state; recent maintainer signal observed"
    if state == "stale":
        return "stale; no recent maintainer signal"
    if state == "closed":
        return "closed or inactive"
    return "maintainer activity unconfirmed"


def _client_report_scope(issue: dict[str, Any], reason_codes: list[str]) -> str:
    if "SCOPE_TOO_BROAD" in reason_codes:
        return "broad — scope not yet bounded"
    if issue.get("contribution_signals"):
        return "narrow — contribution signals documented"
    return "unconfirmed — no contribution signals recorded"


def _client_report_effort(reason_codes: list[str]) -> str | None:
    if "PAYOUT_TOO_LOW_FOR_EFFORT" in reason_codes:
        return "payout may be low relative to estimated effort"
    return None


def _client_report_recommendation_row(row: dict[str, Any]) -> dict[str, Any]:
    issue = row["issue"]
    reason_codes = list(row["reason_codes"])
    effort = _client_report_effort(reason_codes)
    recommendation: dict[str, Any] = {
        "reference": issue["reference"],
        "title": issue["title"],
        "url": issue["url"],
        "platform": issue["platform"],
        "language": issue.get("language"),
        "payout": issue["funding"]["display"],
        "state": issue["opportunity_state"],
        "maintainer_activity": _client_report_maintainer_activity(issue),
        "scope": _client_report_scope(issue, reason_codes),
        "risk": issue["risk_level"],
        "effort": effort,
        "recommended_next_step": row["recommended_next_step"],
        "confidence": row["confidence"],
        "decision": "Go" if row["decision_gate"] == "go_after_recheck" else "Watchlist",
    }
    return recommendation


def _client_report_watchlist_row(row: dict[str, Any]) -> dict[str, Any]:
    issue = row["issue"]
    reason_codes = list(row["reason_codes"])
    blocker = reason_codes[0] if reason_codes else "review pending"
    return {
        "reference": issue["reference"],
        "title": issue["title"],
        "url": issue["url"],
        "payout": issue["funding"]["display"],
        "blocker": blocker,
        "trigger_to_promote": row["recommended_next_step"],
    }


def _client_report_no_go_row(row: dict[str, Any]) -> dict[str, Any]:
    issue = row["issue"]
    reason_codes = list(row["reason_codes"])
    return {
        "reference": issue["reference"],
        "title": issue["title"],
        "url": issue["url"],
        "payout": issue["funding"]["display"],
        "reason_code": reason_codes[0] if reason_codes else "NO_MAJOR_REVIEW_GAPS",
        "reason_codes": reason_codes,
        "evidence": row["recommended_next_step"],
    }


def _client_report_executive_summary(
    *,
    reviewed: int,
    go_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    no_go_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    go_count = len(go_rows)
    watchlist_count = len(watchlist_rows)
    no_go_count = len(no_go_rows)
    actionable_pct = round(100 * go_count / reviewed, 1) if reviewed else 0.0
    top_recommendation = None
    if go_rows:
        top = go_rows[0]["issue"]
        top_recommendation = f"{top['reference']} ({top['funding']['display']}, Go)"
    no_go_reason_counts = Counter(
        row["reason_code"] for row in (_client_report_no_go_row(r) for r in no_go_rows)
    )
    dominant_no_go_reason = None
    if no_go_reason_counts:
        code, count = no_go_reason_counts.most_common(1)[0]
        dominant_no_go_reason = {
            "reason_code": code,
            "count": count,
            "of_total": no_go_count,
        }
    return {
        "reviewed": reviewed,
        "go": go_count,
        "watchlist": watchlist_count,
        "no_go": no_go_count,
        "actionable_percent": actionable_pct,
        "top_recommendation": top_recommendation,
        "dominant_no_go_reason": dominant_no_go_reason,
    }


def _client_report_patterns(
    *,
    go_rows: list[dict[str, Any]],
    no_go_rows: list[dict[str, Any]],
    no_go_moat: dict[str, Any],
) -> dict[str, Any]:
    no_go_reason_counts = Counter(code for row in no_go_rows for code in row["reason_codes"])
    go_platform_counts = Counter(row["issue"]["platform"] for row in go_rows)
    go_language_counts = Counter((row["issue"].get("language") or "unknown") for row in go_rows)
    no_go_platform_counts = Counter(row["issue"]["platform"] for row in no_go_rows)
    return {
        "no_go_reason_code_counts": dict(no_go_reason_counts.most_common()),
        "go_platform_counts": dict(sorted(go_platform_counts.items())),
        "go_language_counts": dict(sorted(go_language_counts.items())),
        "no_go_platform_counts": dict(sorted(no_go_platform_counts.items())),
        "moat_highlights": {
            "high_risk_or_excluded": no_go_moat["high_risk_or_excluded"],
            "funding_unknown": no_go_moat["funding_unknown"],
            "ambiguous_scope": no_go_moat["ambiguous_scope"],
            "stale_or_closed": no_go_moat["stale_or_closed"],
        },
    }


def _client_report_operating_procedure(
    *,
    go_rows: list[dict[str, Any]],
    watchlist_rows: list[dict[str, Any]],
    no_go_rows: list[dict[str, Any]],
) -> list[str]:
    steps: list[str] = []
    if go_rows:
        top = go_rows[0]["issue"]
        steps.append(
            f"Start review with {top['reference']} (highest-confidence Go pick); "
            "reproduce locally before any client-side engagement decision."
        )
        for row in go_rows[1:]:
            issue = row["issue"]
            steps.append(
                f"Prepare a local feasibility note for {issue['reference']} and "
                "re-check assignment/competition before any engagement decision."
            )
    else:
        steps.append(
            "No Go candidates in this batch; expand permitted read-only sources before "
            "ranking again."
        )
    if watchlist_rows:
        steps.append(
            "Do not invest in Watchlist items until each promotion trigger fires; "
            "re-check public state on the listed cadence."
        )
    if no_go_rows:
        steps.append(
            f"Skip the entire No-go list ({len(no_go_rows)} rows); keep it as exclusion "
            "evidence rather than spending engineering time."
        )
    steps.append(
        "Do not claim, comment, open pull requests, or contact maintainers without explicit "
        "written client authorization and confirmation that project rules allow it."
    )
    return steps


def _normalize_report_date(report_date: str) -> str:
    """Validate an injected report date and return its canonical string form.

    Accepts an ISO calendar date (``YYYY-MM-DD``) or an ISO datetime; rejects
    anything else so a client-facing deliverable can never ship a garbage date.
    """
    stripped = report_date.strip()
    try:
        return date.fromisoformat(stripped).isoformat()
    except ValueError:
        pass
    try:
        datetime.fromisoformat(stripped)
    except ValueError:
        raise ValueError(
            f"report_date must be a valid ISO date (YYYY-MM-DD), got {report_date!r}"
        ) from None
    return stripped


def client_report_funded_issues(
    issues: list[FundedIssue],
    *,
    client_name: str,
    report_date: str,
    prepared_by: str = "PatchRail Opportunity Desk",
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    if not client_name or not client_name.strip():
        raise ValueError("client_name must be a non-empty string")
    if not report_date or not report_date.strip():
        raise ValueError("report_date must be a non-empty ISO date string")
    normalized_date = _normalize_report_date(report_date)
    shortlist_payload = shortlist_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
        limit=limit,
    )
    go_rows = [
        row for row in shortlist_payload["shortlist"] if row["decision_gate"] == "go_after_recheck"
    ]
    watchlist_rows = [
        row for row in shortlist_payload["shortlist"] if row["decision_gate"] == "watchlist"
    ]
    no_go_rows = shortlist_payload["no_go_evidence"]
    no_go_moat = shortlist_payload["no_go_moat"]
    reviewed = shortlist_payload["summary"]["total_scored"]
    return {
        "schema_version": CLIENT_REPORT_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "client_name": client_name.strip(),
        "prepared_by": prepared_by,
        "date": normalized_date,
        "scope": f"{reviewed} public funded open-source issues reviewed",
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": shortlist_payload["filters"],
        "executive_summary": _client_report_executive_summary(
            reviewed=reviewed,
            go_rows=go_rows,
            watchlist_rows=watchlist_rows,
            no_go_rows=no_go_rows,
        ),
        "top_recommendations": [_client_report_recommendation_row(row) for row in go_rows],
        "watchlist": [_client_report_watchlist_row(row) for row in watchlist_rows],
        "no_go_list": [_client_report_no_go_row(row) for row in no_go_rows],
        "no_go_moat_evidence": {
            "raw_results_reviewed": shortlist_payload["summary"]["total_loaded"],
            "in_scope_reviewed": reviewed,
            "high_risk_or_excluded": no_go_moat["high_risk_or_excluded"],
            "missing_contribution_guidelines": no_go_moat["missing_contribution_guidelines"],
            "ambiguous_scope": no_go_moat["ambiguous_scope"],
            "spam_attractive": no_go_moat["spam_attractive"],
            "funding_unknown": no_go_moat["funding_unknown"],
            "stale_or_closed": no_go_moat["stale_or_closed"],
            "final_go_candidates": len(go_rows),
        },
        "patterns_observed": _client_report_patterns(
            go_rows=go_rows,
            no_go_rows=no_go_rows,
            no_go_moat=no_go_moat,
        ),
        "recommended_operating_procedure": _client_report_operating_procedure(
            go_rows=go_rows,
            watchlist_rows=watchlist_rows,
            no_go_rows=no_go_rows,
        ),
        "disclaimer": CLIENT_REPORT_DISCLAIMER,
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Client-facing read-only opportunity intelligence. PatchRail does not claim rewards, "
            "post comments, open pull requests, contact maintainers, or guarantee merge or payout "
            "outcomes."
        ),
    }


def recheck_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    score_payload = score_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    scored_rows = score_payload["scores"]
    recheck_plan = _recheck_plan(scored_rows)
    queue_rows = [
        _recheck_queue_row(row)
        for row in scored_rows
        if _recheck_action_for_gate(str(row["decision_gate"])) != "archive_as_no_go_evidence"
    ]
    queue_rows.sort(
        key=lambda row: (
            _recheck_priority_rank(row["priority"]),
            row["platform"],
            row["reference"],
        )
    )
    queue_rows_before_limit = len(queue_rows)
    if max_rows is not None:
        queue_rows = queue_rows[:max_rows]
    focus_batch = _recheck_focus_batch(queue_rows)
    return {
        "schema_version": RECHECK_QUEUE_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": score_payload["filters"],
        "queue_limit": max_rows,
        "total_loaded": score_payload["total_loaded"],
        "total_scored": score_payload["total_scored"],
        "queue_rows_before_limit": queue_rows_before_limit,
        "queue_rows": len(queue_rows),
        "no_go_archive_rows": recheck_plan["no_go_rows"],
        "priority_counts": recheck_plan["priority_counts"],
        "action_counts": recheck_plan["action_counts"],
        "focus_batch": focus_batch,
        "items": queue_rows,
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Recheck queue is local read-only tracker work. It schedules evidence review only; "
            "it does not claim rewards, post comments, contact maintainers, open pull requests, "
            "or guarantee merge or payout outcomes."
        ),
    }


def cash_actions_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
    max_actions: int | None = None,
) -> dict[str, Any]:
    if max_actions is not None and max_actions < 1:
        raise ValueError("max_actions must be at least 1")
    report_payload = report_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    actions = _cash_action_rows(report_payload)
    actions_before_limit = len(actions)
    if max_actions is not None:
        actions = actions[:max_actions]
    return {
        "schema_version": CASH_ACTIONS_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": report_payload["filters"],
        "cash_path_status": report_payload["cash_path_status"],
        "intake_followup": report_payload["intake_followup"],
        "delivery_pack": report_payload["delivery_pack"],
        "source_quality": report_payload["source_quality"],
        "operator_next_steps": report_payload["operator_next_steps"],
        "action_limit": max_actions,
        "actions_before_limit": actions_before_limit,
        "action_rows": len(actions),
        "items": actions,
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Cash actions are internal structured handoff only, not external prose. They do "
            "not create a payment route, claim rewards, post comments, contact maintainers, "
            "open pull requests, or guarantee merge or payout outcomes."
        ),
    }


def fulfillment_packet_funded_issues(
    issues: list[FundedIssue],
    *,
    safe_only: bool = False,
    profile: ClientProfile | None = None,
    platform: str | None = None,
    language: str | None = None,
    min_usd: float | None = None,
    opportunity_state: str | None = None,
    risk_level: str | None = None,
    max_items: int | None = None,
) -> dict[str, Any]:
    if max_items is not None and max_items < 1:
        raise ValueError("max_items must be at least 1")
    report_payload = report_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    recheck_payload = recheck_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    cash_payload = cash_actions_funded_issues(
        issues,
        safe_only=safe_only,
        profile=profile,
        platform=platform,
        language=language,
        min_usd=min_usd,
        opportunity_state=opportunity_state,
        risk_level=risk_level,
    )
    items = _fulfillment_items(
        report_payload=report_payload,
        recheck_payload=recheck_payload,
        cash_payload=cash_payload,
    )
    qa_gates = _fulfillment_qa_gates(report_payload)
    items_before_limit = len(items)
    if max_items is not None:
        items = items[:max_items]
    return {
        "schema_version": FULFILLMENT_PACKET_SCHEMA_VERSION,
        "source_schema_version": SCHEMA_VERSION,
        "read_only": True,
        "safe_only": safe_only,
        "blocked_actions": BLOCKED_ACTIONS,
        "filters": report_payload["filters"],
        "packet_limit": max_items,
        "items_before_limit": items_before_limit,
        "item_rows": len(items),
        "status": _fulfillment_status(report_payload),
        "suggested_package": report_payload["delivery_budget"]["suggested_package"],
        "cash_path_status": report_payload["cash_path_status"],
        "operator_next_steps": report_payload["operator_next_steps"],
        "totals": {
            "loaded": report_payload["totals"]["loaded"],
            "in_scope": report_payload["totals"]["in_scope"],
            "candidate_references": len(
                report_payload["delivery_pack"]["handoff"]["candidate_references"]
            ),
            "verification_references": len(
                report_payload["delivery_pack"]["handoff"]["verification_references"]
            ),
            "no_go_references": len(report_payload["delivery_pack"]["handoff"]["no_go_references"]),
            "active_rechecks": report_payload["recheck_plan"]["recheck_rows"],
            "source_count": len(report_payload["source_quality"]["sources"]),
        },
        "qa_gates": qa_gates,
        "delivery_readiness": _fulfillment_delivery_readiness(
            qa_gates=qa_gates,
            items=items,
            report_payload=report_payload,
        ),
        "operations_digest": _fulfillment_operations_digest(
            qa_gates=qa_gates,
            items=items,
            report_payload=report_payload,
        ),
        "evidence_manifest": _fulfillment_evidence_manifest(
            report_payload=report_payload,
            recheck_payload=recheck_payload,
            cash_payload=cash_payload,
        ),
        "report_assembly_plan": _fulfillment_report_assembly_plan(
            qa_gates=qa_gates,
            report_payload=report_payload,
        ),
        "handoff": {
            "candidate_references": report_payload["delivery_pack"]["handoff"][
                "candidate_references"
            ],
            "verification_references": report_payload["delivery_pack"]["handoff"][
                "verification_references"
            ],
            "no_go_references": report_payload["delivery_pack"]["handoff"]["no_go_references"],
            "sections": [
                "client_fit_summary",
                "source_quality",
                "delivery_pack",
                "recheck_queue",
                "cash_actions",
                "evidence_manifest",
                "report_assembly_plan",
            ],
            "external_body_allowed": False,
            "payment_route_allowed_now": False,
            "requires_written_acceptance_before_payment_route": True,
        },
        "items": items,
        "requirements": {
            "network_required": False,
            "github_write_permission_required": False,
            "external_model_required": False,
            "billing_required": False,
        },
        "boundary": (
            "Fulfillment packet is internal delivery operations data for read-only decision "
            "support. It is not customer-facing prose, does not create a payment route, "
            "does not claim rewards, post comments, contact maintainers, open pull requests, "
            "or guarantee merge or payout outcomes."
        ),
    }


def _fulfillment_evidence_manifest(
    *,
    report_payload: dict[str, Any],
    recheck_payload: dict[str, Any],
    cash_payload: dict[str, Any],
) -> dict[str, Any]:
    source_quality = report_payload["source_quality"]
    handoff = report_payload["delivery_pack"]["handoff"]
    recheck_plan = report_payload["recheck_plan"]
    intake_followup = report_payload["intake_followup"]
    cash_actions = cash_payload["items"]
    required_intake_fields = [
        field["field"]
        for field in intake_followup["requested_fields"]
        if field["required_before_paid_delivery"]
    ]
    copy_brief_actions = [
        str(row["action"]) for row in cash_actions if row.get("copy_brief_facts") is not None
    ]
    artifacts = [
        _evidence_manifest_artifact(
            artifact="source_batch",
            status="ready" if source_quality["sources"] else "blocked",
            source_fields=["source_quality.sources", "filters"],
            references=sorted(source_quality["sources"].keys()),
            required_before_delivery=True,
            next_safe_local_action="add permitted public/API source rows",
        ),
        _evidence_manifest_artifact(
            artifact="scored_candidate_set",
            status="ready" if handoff["candidate_references"] else "blocked",
            source_fields=["delivery_pack.handoff.candidate_references", "scores"],
            references=handoff["candidate_references"],
            required_before_delivery=True,
            next_safe_local_action="expand permitted sources or run scoring before shortlist assembly",
        ),
        _evidence_manifest_artifact(
            artifact="public_state_recheck_queue",
            status="blocked" if recheck_plan["recheck_rows"] else "ready",
            source_fields=["recheck_plan.next_rows"],
            references=[row["reference"] for row in recheck_plan["next_rows"]],
            required_before_delivery=True,
            next_safe_local_action="complete read-only public-state rechecks for active candidates",
        ),
        _evidence_manifest_artifact(
            artifact="no_go_archive",
            status="ready",
            source_fields=["delivery_pack.handoff.no_go_references", "no_go_moat"],
            references=handoff["no_go_references"],
            required_before_delivery=False,
            next_safe_local_action="preserve no-go rows as exclusion evidence",
        ),
        _evidence_manifest_artifact(
            artifact="buyer_intake_record",
            status="blocked" if required_intake_fields else "ready",
            source_fields=["intake_followup.requested_fields"],
            references=required_intake_fields,
            required_before_delivery=True,
            next_safe_local_action="collect missing buyer-fit fields through a facts-only copy brief",
        ),
        _evidence_manifest_artifact(
            artifact="copy_brief_facts",
            status="ready" if copy_brief_actions else "not_needed",
            source_fields=["cash_actions.items.copy_brief_facts"],
            references=copy_brief_actions,
            required_before_delivery=False,
            next_safe_local_action="hand facts-only payload to OpenClaw/Opus only after a real reply branch exists",
        ),
        _evidence_manifest_artifact(
            artifact="payment_acceptance_record",
            status="blocked",
            source_fields=["cash_path_status"],
            references=[],
            required_before_delivery=True,
            next_safe_local_action="wait for written buyer acceptance before creating any payment route",
        ),
    ]
    required_artifacts = [
        artifact for artifact in artifacts if artifact["required_before_delivery"]
    ]
    blocked_artifacts = [
        artifact["artifact"] for artifact in required_artifacts if artifact["status"] != "ready"
    ]
    return {
        "schema_version": "patchrail.funded_issues.evidence_manifest.v1",
        "status": "ready_for_paid_delivery" if not blocked_artifacts else "blocked_internal",
        "artifact_count": len(artifacts),
        "required_artifact_count": len(required_artifacts),
        "ready_required_artifact_count": len(required_artifacts) - len(blocked_artifacts),
        "blocked_artifacts": blocked_artifacts,
        "artifacts": artifacts,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
        "boundary": (
            "Evidence manifest is internal readiness data. It does not write customer prose, "
            "create payment routes, claim rewards, contact maintainers, post comments, open "
            "pull requests, or guarantee merge/payout outcomes."
        ),
    }


def _evidence_manifest_artifact(
    *,
    artifact: str,
    status: str,
    source_fields: list[str],
    references: list[str],
    required_before_delivery: bool,
    next_safe_local_action: str,
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "status": status,
        "source_fields": source_fields,
        "references": sorted(set(references)),
        "required_before_delivery": required_before_delivery,
        "next_safe_local_action": next_safe_local_action,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
    }


def _fulfillment_report_assembly_plan(
    *,
    qa_gates: list[dict[str, Any]],
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    gate_map = {str(gate["gate"]): gate for gate in qa_gates}
    handoff = report_payload["delivery_pack"]["handoff"]
    decision_summary = report_payload["decision_summary"]
    source_quality = report_payload["source_quality"]
    no_go_moat = report_payload["no_go_moat"]
    sections = [
        _report_assembly_section(
            section="executive_summary",
            source_fields=["decision_summary", "source_quality.summary", "cash_path_status"],
            references=[],
            blocked_by=[],
            next_safe_local_action="summarize batch decision, blocker count, and cash-path status",
        ),
        _report_assembly_section(
            section="top_recommendations",
            source_fields=[
                "delivery_pack.handoff.candidate_references",
                "recheck_plan.next_rows",
            ],
            references=handoff["candidate_references"] + handoff["verification_references"],
            blocked_by=_blocked_report_section_gates(
                gate_map,
                ["public_state_recheck_complete", "buyer_intake_fields_complete"],
            ),
            next_safe_local_action="complete public-state rechecks before turning candidates into recommendations",
        ),
        _report_assembly_section(
            section="watchlist",
            source_fields=["recheck_plan.next_rows", "source_quality.sources"],
            references=handoff["verification_references"],
            blocked_by=_blocked_report_section_gates(gate_map, ["public_state_recheck_complete"]),
            next_safe_local_action="keep verification rows as watchlist until funding and state are current",
        ),
        _report_assembly_section(
            section="no_go_list",
            source_fields=["delivery_pack.handoff.no_go_references", "no_go_moat"],
            references=handoff["no_go_references"],
            blocked_by=[],
            next_safe_local_action="preserve no-go rows as exclusion evidence",
        ),
        _report_assembly_section(
            section="patterns_observed",
            source_fields=["source_quality.summary", "breakdown.risk_flags", "no_go_moat"],
            references=[],
            blocked_by=[],
            next_safe_local_action="summarize source quality and recurring no-go patterns internally",
        ),
        _report_assembly_section(
            section="recommended_operating_procedure",
            source_fields=["operator_next_steps", "operations_digest"],
            references=[],
            blocked_by=_blocked_report_section_gates(
                gate_map,
                ["buyer_intake_fields_complete", "payment_route_written_acceptance"],
            ),
            next_safe_local_action="keep the procedure internal until buyer scope and payment route preconditions are met",
        ),
        _report_assembly_section(
            section="disclaimer",
            source_fields=["boundary", "blocked_actions", "requirements"],
            references=[],
            blocked_by=[],
            next_safe_local_action="keep read-only/no-guarantee boundaries visible in every delivered report",
        ),
    ]
    blocked_sections = [section for section in sections if section["blocked_by"]]
    customer_delivery_ready = not blocked_sections and bool(
        gate_map.get("payment_route_written_acceptance", {}).get("passed")
    )
    return {
        "schema_version": "patchrail.funded_issues.report_assembly_plan.v1",
        "status": (
            "ready_for_customer_delivery"
            if customer_delivery_ready
            else "blocked_before_customer_delivery"
        ),
        "internal_assembly_ready": bool(
            decision_summary["total_rows"] and source_quality["summary"]["source_count"]
        ),
        "customer_delivery_ready": customer_delivery_ready,
        "section_count": len(sections),
        "ready_sections": [section["section"] for section in sections if not section["blocked_by"]],
        "blocked_sections": [section["section"] for section in blocked_sections],
        "source_quality_status": source_quality["summary"]["status"],
        "candidate_references": list(handoff["candidate_references"]),
        "verification_references": list(handoff["verification_references"]),
        "no_go_references": list(handoff["no_go_references"]),
        "no_go_signal_count": int(no_go_moat["high_risk_or_excluded"]),
        "sections": sections,
        "payment_route_allowed_now": False,
        "external_body_allowed": False,
        "customer_facing_prose_allowed": False,
        "requires_written_acceptance_before_delivery": True,
        "boundary": (
            "Report assembly plan is internal structure only. It may organize evidence for "
            "OpenClaw/Opus or a paid delivery workflow, but it does not write customer prose, "
            "create payment routes, claim rewards, contact maintainers, post comments, open "
            "pull requests, or guarantee merge/payout outcomes."
        ),
    }


def _blocked_report_section_gates(
    gate_map: dict[str, dict[str, Any]],
    gate_names: list[str],
) -> list[str]:
    return [
        gate_name for gate_name in gate_names if not bool(gate_map.get(gate_name, {}).get("passed"))
    ]


def _report_assembly_section(
    *,
    section: str,
    source_fields: list[str],
    references: list[str],
    blocked_by: list[str],
    next_safe_local_action: str,
) -> dict[str, Any]:
    return {
        "section": section,
        "status": "blocked_before_customer_delivery" if blocked_by else "ready_for_internal_draft",
        "source_fields": source_fields,
        "references": sorted(set(references)),
        "blocked_by": blocked_by,
        "next_safe_local_action": next_safe_local_action,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
    }


def _cash_action_rows(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cash_path_status = report_payload["cash_path_status"]
    intake_followup = report_payload["intake_followup"]
    recheck_plan = report_payload["recheck_plan"]
    delivery_pack = report_payload["delivery_pack"]
    source_quality = report_payload["source_quality"]

    if cash_path_status["next_revenue_action"] == "collect_buyer_intake":
        rows.append(
            _cash_action_row(
                action="collect_buyer_intake",
                priority="high",
                reason="Required buyer-fit fields are missing before paid delivery.",
                requested_fields=[
                    field["field"]
                    for field in intake_followup["requested_fields"]
                    if field["required_before_paid_delivery"]
                ],
                evidence_references=delivery_pack["handoff"]["candidate_references"],
                suggested_package=intake_followup["suggested_package"],
                copy_brief_allowed=True,
            )
        )

    if recheck_plan["recheck_rows"]:
        rows.append(
            _cash_action_row(
                action="run_read_only_recheck",
                priority="high"
                if cash_path_status["next_revenue_action"] == "run_read_only_recheck"
                else "medium",
                reason="Candidate or watchlist rows need current public-state evidence.",
                requested_fields=[
                    field["field"]
                    for field in intake_followup["requested_fields"]
                    if field["field"] == "public_state_recheck_window"
                ],
                evidence_references=[row["reference"] for row in recheck_plan["next_rows"]],
                suggested_package=intake_followup["suggested_package"],
                copy_brief_allowed=False,
            )
        )

    if cash_path_status["next_revenue_action"] == "confirm_paid_scope":
        rows.append(
            _cash_action_row(
                action="confirm_paid_scope",
                priority="high",
                reason="Rows are buyer-ready after local checks; confirm package and written scope.",
                requested_fields=[],
                evidence_references=delivery_pack["handoff"]["candidate_references"],
                suggested_package=intake_followup["suggested_package"],
                copy_brief_allowed=True,
            )
        )

    if cash_path_status["next_revenue_action"] == "expand_permitted_sources":
        rows.append(
            _cash_action_row(
                action="expand_permitted_sources",
                priority="medium",
                reason="Current filters produced no buyer-ready candidates.",
                requested_fields=[
                    field["field"]
                    for field in intake_followup["requested_fields"]
                    if field["field"] in {"permitted_sources", "source_expansion_preferences"}
                ],
                evidence_references=[],
                suggested_package=intake_followup["suggested_package"],
                copy_brief_allowed=False,
                source_names=sorted(source_quality["sources"].keys()),
            )
        )

    if not rows:
        rows.append(
            _cash_action_row(
                action="expand_permitted_sources",
                priority="medium",
                reason="No internal cash action matched this batch; expand permitted sources.",
                requested_fields=[],
                evidence_references=[],
                suggested_package=intake_followup["suggested_package"],
                copy_brief_allowed=False,
                source_names=sorted(source_quality["sources"].keys()),
            )
        )

    return sorted(rows, key=lambda row: (_recheck_priority_rank(row["priority"]), row["action"]))


def _cash_action_row(
    *,
    action: str,
    priority: str,
    reason: str,
    requested_fields: list[str],
    evidence_references: list[str],
    suggested_package: str,
    copy_brief_allowed: bool,
    source_names: list[str] | None = None,
) -> dict[str, Any]:
    copy_brief_facts = _copy_brief_facts_for_action(
        action=action,
        reason=reason,
        requested_fields=requested_fields,
        evidence_references=evidence_references,
        suggested_package=suggested_package,
        copy_brief_allowed=copy_brief_allowed,
        source_names=source_names or [],
    )
    return {
        "action": action,
        "priority": priority,
        "reason": reason,
        "requested_fields": requested_fields,
        "evidence_references": evidence_references,
        "source_names": source_names or [],
        "suggested_package": suggested_package,
        "copy_brief_allowed": copy_brief_allowed,
        "copy_brief_facts": copy_brief_facts,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
        "requires_written_acceptance_before_payment_route": True,
        "blocked_actions": BLOCKED_ACTIONS,
        "boundary": (
            "Internal facts-only handoff. Do not write external prose here, create a payment "
            "route, claim rewards, post comments, contact maintainers, open pull requests, "
            "or imply merge/payout certainty."
        ),
    }


def _copy_brief_facts_for_action(
    *,
    action: str,
    reason: str,
    requested_fields: list[str],
    evidence_references: list[str],
    suggested_package: str,
    copy_brief_allowed: bool,
    source_names: list[str],
) -> dict[str, Any] | None:
    if not copy_brief_allowed:
        return None
    key_facts = [
        f"internal_action={action}",
        f"suggested_package={suggested_package}",
        f"reason={reason}",
        "payment_route_allowed_now=false",
        "requires_written_acceptance_before_payment_route=true",
    ]
    if requested_fields:
        key_facts.append(f"requested_fields={','.join(requested_fields)}")
    if evidence_references:
        key_facts.append(f"evidence_references={','.join(evidence_references)}")
    if source_names:
        key_facts.append(f"source_names={','.join(source_names)}")
    return {
        "schema_version": "patchrail.funded_issues.copy_brief_facts.v1",
        "type": "reply",
        "lead": "buyer_or_active_thread",
        "goal": action,
        "key_facts": key_facts,
        "tone": "concise, async-only, commercial, brand-safe",
        "constraints": [
            "facts-only packet for OpenClaw/Opus",
            "do not include a customer-facing body in this payload",
            "no calls, demos, calendar links, claims, comments, pull requests, maintainer outreach",
            "no merge, payout, legal, financial, availability, or maintainer-response guarantees",
            "do not create or offer a payment route before written buyer acceptance",
        ],
        "urgency": "normal",
        "thread_ref": "fill_from_live_reply_or_pipeline_record",
        "forbidden_fields": ["body", "draft", "email_body"],
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
    }


def _fulfillment_status(report_payload: dict[str, Any]) -> str:
    status = str(report_payload["intake_followup"]["status"])
    return {
        "needs_buyer_intake": "needs_buyer_intake",
        "ready_after_read_only_recheck": "needs_read_only_recheck",
        "ready_for_scope_confirmation": "ready_for_scope_confirmation",
        "needs_source_expansion": "needs_source_expansion",
    }[status]


def _fulfillment_qa_gates(report_payload: dict[str, Any]) -> list[dict[str, Any]]:
    intake_followup = report_payload["intake_followup"]
    recheck_plan = report_payload["recheck_plan"]
    source_quality = report_payload["source_quality"]
    delivery_pack = report_payload["delivery_pack"]
    return [
        _fulfillment_qa_gate(
            gate="buyer_intake_fields_complete",
            passed=intake_followup["required_before_paid_delivery"] == 0,
            reason=("Required buyer-fit fields must be present before paid delivery can start."),
            evidence=[
                field["field"]
                for field in intake_followup["requested_fields"]
                if field["required_before_paid_delivery"]
            ],
        ),
        _fulfillment_qa_gate(
            gate="public_state_recheck_complete",
            passed=recheck_plan["recheck_rows"] == 0,
            reason="Candidate rows need current public-state evidence before delivery use.",
            evidence=[row["reference"] for row in recheck_plan["next_rows"]],
        ),
        _fulfillment_qa_gate(
            gate="source_quality_recorded",
            passed=bool(source_quality["sources"]),
            reason="The packet needs at least one permitted local source row.",
            evidence=sorted(source_quality["sources"].keys()),
        ),
        _fulfillment_qa_gate(
            gate="no_go_evidence_preserved",
            passed=True,
            reason="No-go rows stay in the packet as exclusion evidence, not work targets.",
            evidence=delivery_pack["handoff"]["no_go_references"],
        ),
        _fulfillment_qa_gate(
            gate="payment_route_written_acceptance",
            passed=False,
            reason="Payment routes require written buyer acceptance or a buyer-requested route.",
            evidence=[],
        ),
        _fulfillment_qa_gate(
            gate="third_party_write_boundary",
            passed=True,
            reason=("Fulfillment is local read-only work and does not authorize external writes."),
            evidence=BLOCKED_ACTIONS,
        ),
    ]


def _fulfillment_qa_gate(
    *,
    gate: str,
    passed: bool,
    reason: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "gate": gate,
        "passed": passed,
        "reason": reason,
        "evidence": evidence,
    }


def _fulfillment_delivery_readiness(
    *,
    qa_gates: list[dict[str, Any]],
    items: list[dict[str, Any]],
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    blocking_gates = [gate["gate"] for gate in qa_gates if not gate["passed"]]
    blocking_items = [item for item in items if item["blocks_paid_delivery"]]
    ready_for_paid_delivery = not blocking_gates and not blocking_items
    return {
        "ready_for_paid_delivery": ready_for_paid_delivery,
        "status": "ready_for_paid_delivery" if ready_for_paid_delivery else "blocked_internal",
        "passed_gates": [gate["gate"] for gate in qa_gates if gate["passed"]],
        "blocking_gates": blocking_gates,
        "blocking_item_actions": sorted({str(item["action"]) for item in blocking_items}),
        "blocking_reference_scope": sorted(
            {reference for item in blocking_items for reference in item["reference_scope"]}
        ),
        "next_internal_action": report_payload["cash_path_status"]["next_revenue_action"],
        "payment_route_allowed_now": False,
        "external_body_allowed": False,
        "boundary": (
            "Delivery readiness is internal operations status only. It does not authorize "
            "customer-facing prose, payment routes, claims, comments, maintainer contact, "
            "pull requests, or merge/payout guarantees."
        ),
    }


def _fulfillment_operations_digest(
    *,
    qa_gates: list[dict[str, Any]],
    items: list[dict[str, Any]],
    report_payload: dict[str, Any],
) -> dict[str, Any]:
    blocking_gates = [
        _operations_digest_step(
            source="qa_gate",
            action=str(gate["gate"]),
            owner=_fulfillment_owner(str(gate["gate"])),
            priority="high",
            evidence=list(gate["evidence"]),
            reason=str(gate["reason"]),
            blocks_paid_delivery=True,
        )
        for gate in qa_gates
        if not gate["passed"]
    ]
    blocking_items = [
        _operations_digest_step(
            source=str(item["stage"]),
            action=str(item["action"]),
            owner=_fulfillment_owner(str(item["action"])),
            priority=str(item["priority"]),
            evidence=list(item["reference_scope"]) or list(item["evidence_required"]),
            reason=str(item["reason"]),
            blocks_paid_delivery=True,
        )
        for item in items
        if item["blocks_paid_delivery"]
    ]
    critical_path = blocking_gates + blocking_items
    safe_local_actions = [
        step
        for step in critical_path
        if step["owner"] == "patchrail_operator"
        and step["action"] != "payment_route_written_acceptance"
    ]
    stage_counts = Counter(str(item["stage"]) for item in items)
    blocking_stage_counts = Counter(
        str(item["stage"]) for item in items if item["blocks_paid_delivery"]
    )
    passed_gates = sum(1 for gate in qa_gates if gate["passed"])
    gate_pass_rate = round(passed_gates / len(qa_gates), 2) if qa_gates else 1.0
    return {
        "schema_version": "patchrail.funded_issues.operations_digest.v1",
        "status": "ready_for_paid_delivery" if not critical_path else "blocked_internal",
        "next_blocker": critical_path[0] if critical_path else None,
        "next_safe_local_action": safe_local_actions[0] if safe_local_actions else None,
        "blocking_count": len(critical_path),
        "gate_pass_rate": gate_pass_rate,
        "stage_counts": dict(sorted(stage_counts.items())),
        "blocking_stage_counts": dict(sorted(blocking_stage_counts.items())),
        "non_blocking_actions": sorted(
            {str(item["action"]) for item in items if not item["blocks_paid_delivery"]}
        ),
        "critical_path": critical_path,
        "cash_path_status": report_payload["cash_path_status"]["status"],
        "payment_route_allowed_now": False,
        "external_body_allowed": False,
        "boundary": (
            "Operations digest is internal read-only delivery triage. It may guide local "
            "tracker work or facts-only copy-briefs, but it does not write customer prose, "
            "create payment routes, claim rewards, contact maintainers, post comments, "
            "open pull requests, or guarantee merge/payout outcomes."
        ),
    }


def _operations_digest_step(
    *,
    source: str,
    action: str,
    owner: str,
    priority: str,
    evidence: list[str],
    reason: str,
    blocks_paid_delivery: bool,
) -> dict[str, Any]:
    return {
        "source": source,
        "action": action,
        "owner": owner,
        "priority": priority,
        "evidence": evidence,
        "reason": reason,
        "blocks_paid_delivery": blocks_paid_delivery,
    }


def _fulfillment_owner(action: str) -> str:
    if action in {
        "public_state_recheck_complete",
        "source_quality_recorded",
        "no_go_evidence_preserved",
        "run_read_only_recheck",
        "recheck_public_issue_state",
        "preserve_no_go_evidence",
        "expand_permitted_sources",
    }:
        return "patchrail_operator"
    if action in {
        "buyer_intake_fields_complete",
        "collect_buyer_intake",
        "confirm_paid_scope",
        "payment_route_written_acceptance",
    }:
        return "buyer_or_written_acceptance"
    return "policy_boundary"


def _fulfillment_items(
    *,
    report_payload: dict[str, Any],
    recheck_payload: dict[str, Any],
    cash_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in cash_payload["items"]:
        items.append(
            _fulfillment_item(
                stage="cash_path",
                priority=row["priority"],
                action=row["action"],
                reference_scope=row["evidence_references"] or row["source_names"],
                evidence_required=row["requested_fields"],
                reason=row["reason"],
                blocks_paid_delivery=row["action"]
                in {"collect_buyer_intake", "confirm_paid_scope"},
            )
        )
    for row in recheck_payload["items"]:
        items.append(
            _fulfillment_item(
                stage="public_state_recheck",
                priority=row["priority"],
                action=row["action"],
                reference_scope=[row["reference"]],
                evidence_required=row["evidence_checklist"],
                reason=row["reason"],
                blocks_paid_delivery=True,
            )
        )
    if not report_payload["source_quality"]["sources"]:
        items.append(
            _fulfillment_item(
                stage="source_expansion",
                priority="high",
                action="expand_permitted_sources",
                reference_scope=[],
                evidence_required=["permitted public/API source name", "source URL"],
                reason="No permitted source rows matched this packet.",
                blocks_paid_delivery=True,
            )
        )
    return sorted(
        items,
        key=lambda item: (
            _recheck_priority_rank(str(item["priority"])),
            str(item["stage"]),
            str(item["action"]),
        ),
    )


def _fulfillment_item(
    *,
    stage: str,
    priority: str,
    action: str,
    reference_scope: list[str],
    evidence_required: list[str],
    reason: str,
    blocks_paid_delivery: bool,
) -> dict[str, Any]:
    return {
        "stage": stage,
        "priority": priority,
        "action": action,
        "reference_scope": reference_scope,
        "evidence_required": evidence_required,
        "reason": reason,
        "blocks_paid_delivery": blocks_paid_delivery,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
        "github_write_permission_required": False,
        "network_required": False,
        "blocked_actions": BLOCKED_ACTIONS,
        "boundary": (
            "Internal read-only fulfillment item. Do not write customer prose here, create "
            "a payment route, claim rewards, post comments, contact maintainers, open pull "
            "requests, or imply merge/payout certainty."
        ),
    }


def _recheck_queue_row(row: dict[str, Any]) -> dict[str, Any]:
    issue = row["issue"]
    decision_gate = str(row["decision_gate"])
    action = _recheck_action_for_gate(decision_gate)
    return {
        "reference": issue["reference"],
        "title": issue["title"],
        "url": issue["url"],
        "platform": issue["platform"],
        "funding": issue["funding"]["display"],
        "opportunity_state": issue["opportunity_state"],
        "risk_level": issue["risk_level"],
        "score": row["score"],
        "confidence": row["confidence"],
        "decision_gate": decision_gate,
        "priority": _recheck_priority_for_gate(decision_gate),
        "action": action,
        "reason": _recheck_reason_for_gate(decision_gate),
        "evidence_checklist": _recheck_evidence_checklist(action),
        "recommended_next_step": row["recommended_next_step"],
        "blocked_actions": BLOCKED_ACTIONS,
    }


def _recheck_focus_batch(queue_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not queue_rows:
        return {
            "status": "clear",
            "primary_action": "none",
            "priority": "none",
            "item_count": 0,
            "references": [],
            "platform_counts": {},
            "evidence_checklist": [],
            "boundary": (
                "No active recheck batch exists. Do not invent outreach, claims, comments, "
                "pull requests, payment routes, or payout/merge guarantees."
            ),
        }

    first = queue_rows[0]
    primary_action = str(first["action"])
    priority = str(first["priority"])
    focused_rows = [
        row for row in queue_rows if row["action"] == primary_action and row["priority"] == priority
    ]
    platform_counts = Counter(str(row["platform"]) for row in focused_rows)
    return {
        "status": "active_recheck_batch",
        "primary_action": primary_action,
        "priority": priority,
        "item_count": len(focused_rows),
        "references": [str(row["reference"]) for row in focused_rows],
        "platform_counts": dict(sorted(platform_counts.items())),
        "evidence_checklist": list(first["evidence_checklist"]),
        "boundary": (
            "Focus batch is the next local read-only tracker maintenance slice. It schedules "
            "evidence checks only and does not authorize external prose, payment routes, claims, "
            "comments, maintainer contact, pull requests, or payout/merge guarantees."
        ),
    }


def _recheck_evidence_checklist(action: str) -> list[str]:
    checklists = {
        "recheck_public_issue_state": [
            "confirm issue is still open from permitted public/API source",
            "confirm no assignee or active competing pull request",
            "confirm funding is still visible before paid shortlist use",
        ],
        "recheck_scope_and_noise": [
            "confirm scope is still narrow enough for paid review",
            "confirm recent maintainer signal or clear acceptance criteria",
            "confirm row is not only useful as no-go evidence",
        ],
        "verify_funding_visibility": [
            "confirm visible amount and currency from permitted public/API source",
            "record funding source URL or park as funding unclear",
            "do not rank by amount until funding is verified",
        ],
        "confirm_client_authorization": [
            "keep row parked unless buyer authorizes bounded review",
            "do not contact maintainers or touch third-party repositories",
            "record authorization boundary before any deeper analysis",
        ],
    }
    return checklists.get(
        action,
        ["review public evidence locally and preserve read-only boundaries"],
    )


def _decision_summary(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    gate_counts = Counter(str(row["decision_gate"]) for row in scored_rows)
    gate_counts = Counter({gate: gate_counts.get(gate, 0) for gate in sorted(VALID_DECISION_GATES)})
    candidate_rows = sum(1 for row in scored_rows if _is_shortlist_candidate_row(row))
    no_go_rows = sum(1 for row in scored_rows if row["rating"] == "no_go")
    return {
        "total_rows": len(scored_rows),
        "candidate_rows": candidate_rows,
        "no_go_rows": no_go_rows,
        "gate_counts": dict(gate_counts),
        "verification_needed": gate_counts["needs_funding_verification"],
        "authorization_needed": gate_counts["needs_authorization"],
        "recommended_batch_action": _recommended_batch_action(
            candidate_rows=candidate_rows,
            no_go_rows=no_go_rows,
            verification_needed=gate_counts["needs_funding_verification"],
            authorization_needed=gate_counts["needs_authorization"],
        ),
        "safety_boundary": (
            "Use for local decision support only; re-check public state before any engagement "
            "decision and do not claim, comment, pull-request, or contact maintainers automatically."
        ),
    }


def _recommended_batch_action(
    *,
    candidate_rows: int,
    no_go_rows: int,
    verification_needed: int,
    authorization_needed: int,
) -> str:
    if candidate_rows:
        return (
            "Review go-after-recheck and watchlist candidates locally; keep no-go rows as "
            "exclusion evidence and verify public state before any engagement decision."
        )
    if verification_needed:
        return (
            "Verify funding and current issue state from permitted public/API sources before "
            "ranking this batch."
        )
    if authorization_needed:
        return (
            "Keep authorization-gated rows parked unless the client separately requests a "
            "bounded review."
        )
    if no_go_rows:
        return "Do not spend engineering time on this batch; use no-go rows as evidence."
    return "No in-scope rows; expand permitted read-only sources before ranking."


def _delivery_budget(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    minutes_by_gate = {
        "go_after_recheck": 10,
        "watchlist": 10,
        "needs_funding_verification": 4,
        "needs_authorization": 3,
        "no_go": 3,
    }
    package = _suggested_package_for_rows(len(scored_rows))
    max_paid_hours = {
        "none": 0,
        "mini_diagnostic": 3,
        "validation_sprint": 5,
        "opportunity_shortlist": 10,
        "custom_batch": None,
    }[package]
    estimated_minutes = sum(
        minutes_by_gate.get(str(row["decision_gate"]), 3) for row in scored_rows
    )
    estimated_hours = round(estimated_minutes / 60, 2)
    l2_rows = sum(1 for row in scored_rows if _is_shortlist_candidate_row(row))
    l1_rows = len(scored_rows) - l2_rows
    return {
        "suggested_package": package,
        "estimated_review_minutes": estimated_minutes,
        "estimated_review_hours": estimated_hours,
        "max_paid_hours": max_paid_hours,
        "within_margin_budget": (
            True if max_paid_hours is None else estimated_hours <= max_paid_hours
        ),
        "analysis_rows": {
            "l1_state_and_noise_review": l1_rows,
            "l2_scope_and_readiness_review": l2_rows,
            "l3_deep_dive_deferred": 0,
        },
        "boundary": (
            "Budget is for local read-only triage. Do not clone repos, run deep repro, "
            "contact maintainers, claim rewards, or open pull requests before paid scope."
        ),
    }


def _delivery_pack(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_rows = [row for row in scored_rows if _is_shortlist_candidate_row(row)]
    verification_rows = [
        row
        for row in scored_rows
        if row["decision_gate"] in {"needs_funding_verification", "needs_authorization"}
    ]
    no_go_rows = [row for row in scored_rows if row["decision_gate"] == "no_go"]
    phases = [
        _delivery_phase(
            phase="l1_state_and_noise_review",
            rows=verification_rows + no_go_rows,
            objective="Confirm current public state, funding visibility, and exclusion evidence.",
            exit_criteria="Every row is parked for missing evidence or excluded as no-go evidence.",
        ),
        _delivery_phase(
            phase="l2_shortlist_readiness_review",
            rows=candidate_rows,
            objective="Re-check active candidate rows before using paid shortlist time.",
            exit_criteria="Candidate rows have current public state, scope, and contribution rules checked.",
        ),
        _delivery_phase(
            phase="l3_deep_dive_deferred",
            rows=[],
            objective="Defer reproduction and implementation research until paid scope is explicit.",
            exit_criteria="No deep-dive work starts from this read-only tracker artifact.",
        ),
    ]
    return {
        "suggested_package": _suggested_package_for_rows(len(scored_rows)),
        "phase_counts": {phase["phase"]: phase["row_count"] for phase in phases},
        "phases": phases,
        "handoff": {
            "candidate_references": _delivery_references(candidate_rows),
            "verification_references": _delivery_references(verification_rows),
            "no_go_references": _delivery_references(no_go_rows),
        },
        "boundary": (
            "Delivery pack is a local read-only work plan for paid decision support. It does "
            "not authorize claiming, commenting, contacting maintainers, opening pull requests, "
            "or guaranteeing merge or payout outcomes."
        ),
    }


def _delivery_phase(
    *,
    phase: str,
    rows: list[dict[str, Any]],
    objective: str,
    exit_criteria: str,
) -> dict[str, Any]:
    return {
        "phase": phase,
        "row_count": len(rows),
        "references": _delivery_references(rows),
        "objective": objective,
        "exit_criteria": exit_criteria,
    }


def _delivery_references(rows: list[dict[str, Any]]) -> list[str]:
    return sorted(str(row["issue"]["reference"]) for row in rows)


def _source_quality(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in scored_rows:
        source = str(row["issue"]["platform"])
        grouped.setdefault(source, []).append(row)

    sources: dict[str, dict[str, Any]] = {}
    for source, rows in sorted(grouped.items()):
        total_rows = len(rows)
        candidate_rows = sum(1 for row in rows if _is_shortlist_candidate_row(row))
        no_go_rows = sum(1 for row in rows if row["rating"] == "no_go")
        safe_to_list = sum(1 for row in rows if row["issue"]["safe_to_list"])
        funding_verification_needed = sum(
            1 for row in rows if row["decision_gate"] == "needs_funding_verification"
        )
        authorization_needed = sum(
            1 for row in rows if row["decision_gate"] == "needs_authorization"
        )
        scores = [int(row["score"]) for row in rows]
        usable_signal_ratio = round(candidate_rows / total_rows, 2) if total_rows else 0
        sources[source] = {
            "total_rows": total_rows,
            "candidate_rows": candidate_rows,
            "no_go_rows": no_go_rows,
            "safe_to_list": safe_to_list,
            "funding_verification_needed": funding_verification_needed,
            "authorization_needed": authorization_needed,
            "average_score": round(sum(scores) / total_rows, 2) if total_rows else 0,
            "usable_signal_ratio": usable_signal_ratio,
            "recommended_use": _recommended_source_use(
                candidate_rows=candidate_rows,
                no_go_rows=no_go_rows,
                funding_verification_needed=funding_verification_needed,
                authorization_needed=authorization_needed,
            ),
        }
    return {
        "summary": _source_quality_rollup(sources),
        "sources": sources,
        "boundary": (
            "Source quality is read-only benchmarking for Opportunity Desk triage. It is not "
            "permission to scrape aggressively, claim rewards, contact maintainers, comment, "
            "or open pull requests."
        ),
    }


def _is_shortlist_candidate_row(row: dict[str, Any]) -> bool:
    return row["decision_gate"] in {"go_after_recheck", "watchlist"}


def _source_quality_rollup(sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_count = len(sources)
    total_rows = sum(int(source["total_rows"]) for source in sources.values())
    candidate_rows = sum(int(source["candidate_rows"]) for source in sources.values())
    no_go_rows = sum(int(source["no_go_rows"]) for source in sources.values())
    funding_verification_needed = sum(
        int(source["funding_verification_needed"]) for source in sources.values()
    )
    authorization_needed = sum(int(source["authorization_needed"]) for source in sources.values())
    candidate_source_count = sum(1 for source in sources.values() if source["candidate_rows"])
    no_go_only_source_count = sum(
        1 for source in sources.values() if source["no_go_rows"] and not source["candidate_rows"]
    )
    status = _source_quality_status(
        source_count=source_count,
        candidate_source_count=candidate_source_count,
        funding_verification_needed=funding_verification_needed,
        authorization_needed=authorization_needed,
        no_go_only_source_count=no_go_only_source_count,
    )
    return {
        "source_count": source_count,
        "total_rows": total_rows,
        "candidate_rows": candidate_rows,
        "no_go_rows": no_go_rows,
        "candidate_source_count": candidate_source_count,
        "no_go_only_source_count": no_go_only_source_count,
        "funding_verification_needed": funding_verification_needed,
        "authorization_needed": authorization_needed,
        "status": status,
        "next_tracker_action": _source_quality_next_tracker_action(status),
        "boundary": (
            "Source summary is local tracker evidence only. It does not authorize scraping, "
            "claims, comments, maintainer contact, pull requests, or payout/merge guarantees."
        ),
    }


def _source_quality_status(
    *,
    source_count: int,
    candidate_source_count: int,
    funding_verification_needed: int,
    authorization_needed: int,
    no_go_only_source_count: int,
) -> str:
    if source_count == 0:
        return "no_sources"
    if candidate_source_count:
        return "candidate_sources_available"
    if funding_verification_needed:
        return "needs_funding_verification"
    if authorization_needed:
        return "needs_authorization"
    if no_go_only_source_count:
        return "no_go_only_sources"
    return "collect_more_rows"


def _source_quality_next_tracker_action(status: str) -> str:
    return {
        "no_sources": "Expand permitted public/API sources before ranking this batch.",
        "candidate_sources_available": (
            "Run read-only public-state recheck on candidate sources before paid shortlist use."
        ),
        "needs_funding_verification": (
            "Verify visible funding and current state from permitted public/API sources."
        ),
        "needs_authorization": "Keep authorization-gated source rows parked until buyer scope exists.",
        "no_go_only_sources": (
            "Use these sources as no-go moat evidence and expand coverage before pitching."
        ),
        "collect_more_rows": "Collect more permitted source rows before ranking this batch.",
    }[status]


def _recheck_plan(scored_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for row in scored_rows:
        issue = row["issue"]
        decision_gate = str(row["decision_gate"])
        action = _recheck_action_for_gate(decision_gate)
        priority = _recheck_priority_for_gate(decision_gate)
        rows.append(
            {
                "reference": issue["reference"],
                "platform": issue["platform"],
                "decision_gate": decision_gate,
                "priority": priority,
                "action": action,
                "reason": _recheck_reason_for_gate(decision_gate),
            }
        )

    active_rechecks = [row for row in rows if row["action"] != "archive_as_no_go_evidence"]
    priority_counts = Counter(row["priority"] for row in active_rechecks)
    action_counts = Counter(row["action"] for row in rows)
    return {
        "total_rows": len(rows),
        "recheck_rows": len(active_rechecks),
        "no_go_rows": action_counts.get("archive_as_no_go_evidence", 0),
        "priority_counts": dict(sorted(priority_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "next_rows": sorted(
            active_rechecks,
            key=lambda row: (
                _recheck_priority_rank(row["priority"]),
                row["platform"],
                row["reference"],
            ),
        ),
        "boundary": (
            "Recheck plan is local read-only tracker triage. It schedules evidence review only; "
            "it does not claim, comment, contact maintainers, open pull requests, or guarantee payout."
        ),
    }


def _evidence_debt(recheck_plan: dict[str, Any]) -> dict[str, Any]:
    active_rows = list(recheck_plan["next_rows"])
    action_counts = Counter(str(row["action"]) for row in active_rows)
    platform_counts = Counter(str(row["platform"]) for row in active_rows)
    priority_counts = Counter(str(row["priority"]) for row in active_rows)
    highest_priority = active_rows[0]["priority"] if active_rows else "none"
    next_action = active_rows[0]["action"] if active_rows else "ready_for_delivery_readiness_review"
    return {
        "status": "active_evidence_debt" if active_rows else "clear",
        "blocking_rows": len(active_rows),
        "archive_only_rows": int(recheck_plan["no_go_rows"]),
        "highest_priority": highest_priority,
        "next_action": next_action,
        "action_counts": dict(sorted(action_counts.items())),
        "platform_counts": dict(sorted(platform_counts.items())),
        "priority_counts": dict(sorted(priority_counts.items())),
        "references": [str(row["reference"]) for row in active_rows],
        "payment_route_allowed_now": False,
        "external_body_allowed": False,
        "boundary": (
            "Evidence debt is internal read-only delivery readiness data. It schedules public/API "
            "evidence review only and does not authorize claims, comments, maintainer contact, "
            "pull requests, external prose, payment routes, or payout/merge guarantees."
        ),
    }


def _recheck_action_for_gate(decision_gate: str) -> str:
    return {
        "go_after_recheck": "recheck_public_issue_state",
        "watchlist": "recheck_scope_and_noise",
        "needs_funding_verification": "verify_funding_visibility",
        "needs_authorization": "confirm_client_authorization",
        "no_go": "archive_as_no_go_evidence",
    }.get(decision_gate, "recheck_public_issue_state")


def _recheck_priority_for_gate(decision_gate: str) -> str:
    return {
        "go_after_recheck": "high",
        "needs_funding_verification": "high",
        "watchlist": "medium",
        "needs_authorization": "medium",
        "no_go": "none",
    }.get(decision_gate, "medium")


def _recheck_reason_for_gate(decision_gate: str) -> str:
    return {
        "go_after_recheck": "Candidate rows need current public state recheck before shortlist use.",
        "watchlist": "Watchlist rows need scope/noise recheck before paid review time.",
        "needs_funding_verification": (
            "Funding or current state is unclear and must be verified from permitted sources."
        ),
        "needs_authorization": "Row should stay parked until client authorization is explicit.",
        "no_go": "Keep as exclusion evidence; do not spend delivery time.",
    }.get(decision_gate, "Review public state before ranking this row.")


def _recheck_priority_rank(priority: str) -> int:
    return {"high": 0, "medium": 1, "low": 2, "none": 3}.get(priority, 2)


def _client_fit_gaps(
    issues: list[FundedIssue],
    profile: ClientProfile | None,
) -> list[dict[str, Any]]:
    if profile is None:
        return []

    rows: list[dict[str, Any]] = []
    for issue in issues:
        gaps = _client_fit_gap_codes(issue, profile)
        if not gaps:
            continue
        rows.append(
            {
                "reference": issue.reference,
                "title": issue.title,
                "url": issue.url,
                "platform": issue.platform,
                "gap_codes": gaps,
                "gap_summary": _client_fit_gap_summary(gaps),
            }
        )
    return rows


def _client_fit_summary(
    issues: list[FundedIssue],
    profile: ClientProfile | None,
    client_fit_gaps: list[dict[str, Any]],
) -> dict[str, Any]:
    total_rows = len(issues)
    excluded_rows = len(client_fit_gaps) if profile else 0
    matching_rows = max(0, total_rows - excluded_rows)
    gap_counts = Counter(gap_code for row in client_fit_gaps for gap_code in row["gap_codes"])
    return {
        "profile_name": profile.name if profile and profile.name else None,
        "status": _client_fit_status(profile, total_rows, matching_rows, excluded_rows),
        "total_rows": total_rows,
        "matching_rows": matching_rows,
        "excluded_rows": excluded_rows,
        "gap_counts": dict(sorted(gap_counts.items())),
        "recommended_action": _client_fit_recommended_action(
            profile=profile,
            total_rows=total_rows,
            matching_rows=matching_rows,
            excluded_rows=excluded_rows,
        ),
        "boundary": (
            "Client fit is local buyer-fit evidence only. It does not authorize claiming "
            "rewards, contacting maintainers, posting comments, or opening pull requests."
        ),
    }


def _client_fit_status(
    profile: ClientProfile | None,
    total_rows: int,
    matching_rows: int,
    excluded_rows: int,
) -> str:
    if profile is None:
        return "no_profile"
    if total_rows == 0:
        return "no_rows"
    if matching_rows == 0:
        return "no_matching_rows"
    if excluded_rows:
        return "partial_match"
    return "all_rows_match"


def _client_fit_recommended_action(
    *,
    profile: ClientProfile | None,
    total_rows: int,
    matching_rows: int,
    excluded_rows: int,
) -> str:
    if profile is None:
        return "Attach a read-only client profile before buyer-specific shortlist delivery."
    if total_rows == 0:
        return "Expand permitted read-only sources before buyer-fit ranking."
    if matching_rows == 0:
        return (
            "Do not pitch this batch as buyer-ready; expand sources or adjust the client profile."
        )
    if excluded_rows:
        return "Use matching rows for shortlist review and keep excluded rows as fit-gap evidence."
    return "Use this batch for buyer-specific shortlist review after public-state recheck."


def _intake_followup(
    *,
    client_fit_summary: dict[str, Any],
    recheck_plan: dict[str, Any],
    delivery_budget: dict[str, Any],
    source_quality: dict[str, Any],
    decision_summary: dict[str, Any],
) -> dict[str, Any]:
    requested_fields: list[dict[str, Any]] = []
    if client_fit_summary["status"] == "no_profile":
        requested_fields.extend(
            [
                _intake_field(
                    "preferred_languages",
                    "Needed to filter funded issues to stacks the buyer can actually work.",
                    True,
                ),
                _intake_field(
                    "minimum_payout_usd",
                    "Needed to keep low-value rows out of a paid shortlist.",
                    True,
                ),
                _intake_field(
                    "allowed_risk_levels",
                    "Needed to avoid proposing high-risk rows as buyer-ready.",
                    True,
                ),
            ]
        )
    elif client_fit_summary["status"] in {"no_matching_rows", "partial_match"}:
        requested_fields.append(
            _intake_field(
                "profile_gap_confirmation",
                "Needed to decide whether to expand sources or adjust buyer-fit filters.",
                True,
            )
        )

    if recheck_plan["recheck_rows"]:
        requested_fields.append(
            _intake_field(
                "public_state_recheck_window",
                "Needed because active candidates require read-only public-state recheck before delivery.",
                False,
            )
        )

    if not source_quality["sources"]:
        requested_fields.append(
            _intake_field(
                "permitted_sources",
                "Needed because no source rows matched the current filters.",
                True,
            )
        )
    elif decision_summary["candidate_rows"] == 0 and decision_summary["no_go_rows"] > 0:
        requested_fields.append(
            _intake_field(
                "source_expansion_preferences",
                "Needed because the current batch is useful as no-go evidence but has no candidates.",
                False,
            )
        )

    required_count = sum(1 for field in requested_fields if field["required_before_paid_delivery"])
    if required_count:
        status = "needs_buyer_intake"
    elif recheck_plan["recheck_rows"]:
        status = "ready_after_read_only_recheck"
    elif decision_summary["candidate_rows"]:
        status = "ready_for_scope_confirmation"
    else:
        status = "needs_source_expansion"

    return {
        "status": status,
        "suggested_package": delivery_budget["suggested_package"],
        "required_before_paid_delivery": required_count,
        "requested_fields": requested_fields,
        "next_internal_action": _intake_next_internal_action(status),
        "boundary": (
            "Intake follow-up is structured internal handoff data. It is not customer-facing "
            "email copy and does not authorize claims, comments, pull requests, maintainer "
            "outreach, payout guarantees, or payment routes without written buyer acceptance."
        ),
    }


def _intake_field(
    field: str,
    reason: str,
    required_before_paid_delivery: bool,
) -> dict[str, Any]:
    return {
        "field": field,
        "reason": reason,
        "required_before_paid_delivery": required_before_paid_delivery,
    }


def _intake_next_internal_action(status: str) -> str:
    return {
        "needs_buyer_intake": (
            "Use these fields as facts in a PatchRail copy-brief after buyer interest; do not write "
            "external prose here."
        ),
        "ready_after_read_only_recheck": (
            "Run read-only public-state recheck before turning candidates into a paid report."
        ),
        "ready_for_scope_confirmation": (
            "Confirm paid scope and package; create payment route only after written buyer acceptance."
        ),
        "needs_source_expansion": (
            "Expand permitted read-only sources before pitching this batch as buyer-ready."
        ),
    }[status]


def _cash_path_status(intake_followup: dict[str, Any]) -> dict[str, Any]:
    status = str(intake_followup["status"])
    next_actions = {
        "needs_buyer_intake": "collect_buyer_intake",
        "ready_after_read_only_recheck": "run_read_only_recheck",
        "ready_for_scope_confirmation": "confirm_paid_scope",
        "needs_source_expansion": "expand_permitted_sources",
    }
    return {
        "status": status,
        "next_revenue_action": next_actions[status],
        "copy_brief_facts_available": status
        in {"needs_buyer_intake", "ready_for_scope_confirmation"},
        "payment_route_allowed_now": False,
        "requires_written_acceptance_before_payment_route": True,
        "buyer_ready": status == "ready_for_scope_confirmation",
        "boundary": (
            "Cash-path status is internal structured handoff only. It is not external prose, "
            "does not create a payment route, and does not authorize claims, comments, pull "
            "requests, maintainer outreach, or payout/merge guarantees."
        ),
    }


def _operator_next_steps(
    *,
    cash_path_status: dict[str, Any],
    intake_followup: dict[str, Any],
    recheck_plan: dict[str, Any],
    delivery_pack: dict[str, Any],
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    primary_action = str(cash_path_status["next_revenue_action"])
    required_fields = [
        field["field"]
        for field in intake_followup["requested_fields"]
        if field["required_before_paid_delivery"]
    ]
    optional_recheck_fields = [
        field["field"]
        for field in intake_followup["requested_fields"]
        if field["field"] == "public_state_recheck_window"
    ]
    candidate_refs = delivery_pack["handoff"]["candidate_references"]
    no_go_refs = delivery_pack["handoff"]["no_go_references"]
    recheck_refs = [row["reference"] for row in recheck_plan["next_rows"]]

    if primary_action == "collect_buyer_intake":
        steps.append(
            _operator_next_step(
                action="collect_buyer_intake",
                priority="high",
                source="cash_path",
                reason="Buyer-fit fields are missing before the batch can become paid delivery.",
                reference_scope=candidate_refs,
                evidence_required=required_fields,
                blocks_paid_delivery=True,
                copy_brief_allowed=True,
            )
        )
    elif primary_action == "confirm_paid_scope":
        steps.append(
            _operator_next_step(
                action="confirm_paid_scope",
                priority="high",
                source="cash_path",
                reason="Rows are ready for paid scope confirmation after read-only checks.",
                reference_scope=candidate_refs,
                evidence_required=[],
                blocks_paid_delivery=True,
                copy_brief_allowed=True,
            )
        )
    elif primary_action == "expand_permitted_sources":
        steps.append(
            _operator_next_step(
                action="expand_permitted_sources",
                priority="high",
                source="source_quality",
                reason="Current permitted rows are not enough for buyer-ready delivery.",
                reference_scope=[],
                evidence_required=["permitted public/API source name", "source URL"],
                blocks_paid_delivery=True,
                copy_brief_allowed=False,
            )
        )

    if recheck_plan["recheck_rows"]:
        steps.append(
            _operator_next_step(
                action="run_read_only_recheck",
                priority="high" if primary_action == "run_read_only_recheck" else "medium",
                source="recheck_plan",
                reason="Active candidate rows need current public-state evidence before delivery.",
                reference_scope=recheck_refs,
                evidence_required=optional_recheck_fields
                or ["public issue state", "funding visibility", "staleness/noise check"],
                blocks_paid_delivery=True,
                copy_brief_allowed=False,
            )
        )

    if no_go_refs:
        steps.append(
            _operator_next_step(
                action="preserve_no_go_evidence",
                priority="low",
                source="delivery_pack",
                reason="No-go rows strengthen the decision-support moat and should stay in the packet.",
                reference_scope=no_go_refs,
                evidence_required=["exclusion reason", "public source reference"],
                blocks_paid_delivery=False,
                copy_brief_allowed=False,
            )
        )

    if not steps:
        steps.append(
            _operator_next_step(
                action="expand_permitted_sources",
                priority="medium",
                source="source_quality",
                reason="No operator step matched this batch; collect more permitted read-only rows.",
                reference_scope=[],
                evidence_required=["permitted public/API source name", "source URL"],
                blocks_paid_delivery=True,
                copy_brief_allowed=False,
            )
        )

    steps.sort(key=lambda step: (_recheck_priority_rank(step["priority"]), step["action"]))
    return {
        "schema_version": "patchrail.funded_issues.operator_next_steps.v1",
        "status": cash_path_status["status"],
        "primary_action": primary_action,
        "copy_brief_facts_available": cash_path_status["copy_brief_facts_available"],
        "payment_route_allowed_now": False,
        "external_body_allowed": False,
        "steps": steps,
        "boundary": (
            "Operator next steps are internal structured handoff only. This handoff does "
            "not write external prose, create payment routes, claim rewards, post comments, "
            "contact maintainers, open pull requests, or imply merge/payout certainty."
        ),
    }


def _operator_next_step(
    *,
    action: str,
    priority: str,
    source: str,
    reason: str,
    reference_scope: list[str],
    evidence_required: list[str],
    blocks_paid_delivery: bool,
    copy_brief_allowed: bool,
) -> dict[str, Any]:
    return {
        "priority": priority,
        "action": action,
        "source": source,
        "reason": reason,
        "reference_scope": reference_scope,
        "evidence_required": evidence_required,
        "blocks_paid_delivery": blocks_paid_delivery,
        "copy_brief_allowed": copy_brief_allowed,
        "external_body_allowed": False,
        "payment_route_allowed_now": False,
        "blocked_actions": BLOCKED_ACTIONS,
    }


def _client_fit_gap_codes(issue: FundedIssue, profile: ClientProfile) -> list[str]:
    gaps: list[str] = []
    if profile.languages and (issue.language or "").lower() not in profile.languages:
        gaps.append("LANGUAGE_MISMATCH")
    if profile.min_usd is not None:
        if issue.funding_amount is None:
            gaps.append("FUNDING_UNKNOWN")
        elif issue.funding_currency != "USD":
            gaps.append("FUNDING_CURRENCY_NOT_USD")
        elif issue.funding_amount < profile.min_usd:
            gaps.append("FUNDING_BELOW_MIN_USD")
    if (
        profile.allowed_opportunity_states
        and issue.opportunity_state not in profile.allowed_opportunity_states
    ):
        gaps.append("OPPORTUNITY_STATE_NOT_ALLOWED")
    if profile.allowed_risk_levels and issue.risk_level not in profile.allowed_risk_levels:
        gaps.append("RISK_LEVEL_NOT_ALLOWED")
    if profile.excluded_risk_flags:
        excluded_flags = sorted(set(issue.risk_flags).intersection(profile.excluded_risk_flags))
        gaps.extend(f"EXCLUDED_RISK_FLAG:{flag}" for flag in excluded_flags)
    return gaps


def _client_fit_gap_summary(gaps: list[str]) -> str:
    if not gaps:
        return "Matches the local client profile."
    labels = {
        "LANGUAGE_MISMATCH": "language outside the profile",
        "FUNDING_UNKNOWN": "funding is unknown",
        "FUNDING_CURRENCY_NOT_USD": "funding is not in USD",
        "FUNDING_BELOW_MIN_USD": "funding below profile minimum",
        "OPPORTUNITY_STATE_NOT_ALLOWED": "opportunity state outside the profile",
        "RISK_LEVEL_NOT_ALLOWED": "risk level outside the profile",
    }
    rendered = [
        labels.get(gap, f"excluded risk flag {gap.split(':', 1)[1]}")
        if gap.startswith("EXCLUDED_RISK_FLAG:")
        else labels.get(gap, gap.lower())
        for gap in gaps
    ]
    return "; ".join(rendered)


def _recommended_source_use(
    *,
    candidate_rows: int,
    no_go_rows: int,
    funding_verification_needed: int,
    authorization_needed: int,
) -> str:
    if candidate_rows:
        return "Prioritize for L2 review after public-state recheck."
    if funding_verification_needed:
        return "Use only after funding and current-state verification."
    if authorization_needed:
        return "Park until a client separately authorizes bounded review."
    if no_go_rows:
        return "Use as no-go moat evidence before expanding this source."
    return "Collect more rows before ranking this source."


def _suggested_package_for_rows(row_count: int) -> str:
    if row_count == 0:
        return "none"
    if row_count <= 5:
        return "mini_diagnostic"
    if row_count <= 20:
        return "validation_sprint"
    if row_count <= 50:
        return "opportunity_shortlist"
    return "custom_batch"


def _score_issue(issue: FundedIssue) -> dict[str, Any]:
    score = 35
    components: dict[str, int] = {
        "base": 35,
        "funding_visible": 0,
        "guidelines_visible": 0,
        "contribution_signals": 0,
        "risk_penalty": 0,
        "safe_boundary_bonus": 0,
    }
    reason_codes: list[str] = []

    if issue.funding_amount is not None and issue.funding_currency:
        components["funding_visible"] = 15
    else:
        reason_codes.append("FUNDING_STATE_UNCLEAR")

    if issue.contribution_guidelines_url:
        components["guidelines_visible"] = 15
    else:
        reason_codes.append("NO_CONTRIBUTION_GUIDELINES")

    components["contribution_signals"] = min(len(issue.contribution_signals), 3) * 8
    if not issue.contribution_signals:
        reason_codes.append("NO_REPRO_OR_CONTRIBUTION_SIGNAL")

    if issue.risk_flags:
        risk_penalty = 15 * len(issue.risk_flags)
        if issue.risk_level == "high":
            risk_penalty += 20
        components["risk_penalty"] = -risk_penalty
        reason_codes.extend(_risk_reason_code(flag) for flag in issue.risk_flags)
    else:
        components["safe_boundary_bonus"] = 10

    if issue.opportunity_state == "closed":
        components["risk_penalty"] -= 35
        reason_codes.append("CLOSED_OR_INACTIVE")
    elif issue.opportunity_state == "stale":
        components["risk_penalty"] -= 30
        reason_codes.append("STALE_NO_MAINTAINER_SIGNAL")
    elif issue.opportunity_state == "unknown":
        reason_codes.append("OPPORTUNITY_STATE_UNCLEAR")

    score += sum(value for key, value in components.items() if key != "base")
    score = max(0, min(100, score))
    if issue.risk_level == "high" or issue.opportunity_state in {"closed", "stale"}:
        rating = "no_go"
    elif score >= 80:
        rating = "go_candidate"
    elif score >= 55:
        rating = "watchlist"
    else:
        rating = "no_go"

    return {
        "issue": issue.to_dict(),
        "score": score,
        "confidence": _confidence_for_issue(issue),
        "rating": rating,
        "decision_gate": _decision_gate_for_score(issue, rating, reason_codes),
        "reason_codes": sorted(set(reason_codes)) or ["NO_MAJOR_REVIEW_GAPS"],
        "components": components,
        "recommended_next_step": _recommended_next_step_for_score(issue, rating, reason_codes),
    }


def _confidence_for_issue(issue: FundedIssue) -> float:
    confidence = 0.5
    if issue.funding_amount is not None and issue.funding_currency:
        confidence += 0.15
    if issue.contribution_guidelines_url:
        confidence += 0.15
    confidence += min(len(issue.contribution_signals), 3) * 0.05

    if issue.opportunity_state == "active":
        confidence += 0.05
    elif issue.opportunity_state == "unknown":
        confidence -= 0.15
    elif issue.opportunity_state in {"closed", "stale"}:
        confidence -= 0.2

    confidence -= min(len(issue.risk_flags), 4) * 0.05
    if issue.risk_level == "high":
        confidence -= 0.1
    return round(max(0.05, min(0.99, confidence)), 2)


def _decision_gate_for_score(
    issue: FundedIssue,
    rating: str,
    reason_codes: list[str],
) -> str:
    reason_code_set = set(reason_codes)
    if issue.opportunity_state in {"closed", "stale"}:
        return "no_go"
    if "NEEDS_AUTHORIZATION" in reason_code_set:
        return "needs_authorization"
    if (
        "FUNDING_STATE_UNCLEAR" in reason_code_set
        or "PRIMARY_SOURCE_REQUIRED" in reason_code_set
        or "DISCOVERY_ONLY_SOURCE" in reason_code_set
        or issue.opportunity_state == "unknown"
    ):
        return "needs_funding_verification"
    if issue.risk_level == "high":
        return "no_go"
    if rating == "go_candidate":
        return "go_after_recheck"
    if rating == "watchlist":
        return "watchlist"
    return "no_go"


def _recommended_next_step_for_score(
    issue: FundedIssue,
    rating: str,
    reason_codes: list[str],
) -> str:
    reason_code_set = set(reason_codes)
    if issue.opportunity_state in {"closed", "stale"}:
        return "Do not engage unless public project evidence shows the opportunity is live again."
    if issue.risk_level == "high":
        return "Keep as no-go evidence unless the client separately authorizes a bounded review."
    if "PRIMARY_SOURCE_REQUIRED" in reason_code_set or "DISCOVERY_ONLY_SOURCE" in reason_code_set:
        return (
            "Verify funding and current issue state from a permitted primary public/API source "
            "before shortlist ranking."
        )
    if "FUNDING_STATE_UNCLEAR" in reason_code_set or issue.opportunity_state == "unknown":
        return "Verify funding and current issue state from permitted public/API sources before ranking."
    if "NO_CONTRIBUTION_GUIDELINES" in reason_code_set:
        return "Treat as watchlist until contribution rules and maintainer expectations are clear."
    if rating == "go_candidate":
        return "Reproduce locally and re-check assignment, active PRs, and funding before any engagement decision."
    if rating == "watchlist":
        return "Keep in the watchlist and wait for clearer public maintainer or testability signal."
    return "Do not spend engineering time on this opportunity in the current batch."


def _risk_reason_code(flag: str) -> str:
    return {
        "ambiguous_scope": "SCOPE_TOO_BROAD",
        "bounty_farming_language": "BOUNTY_FARMING_RISK",
        "requires_external_contact": "NEEDS_AUTHORIZATION",
        "no_contribution_guidelines": "NO_CONTRIBUTION_GUIDELINES",
        "aggregator_only_source": "PRIMARY_SOURCE_REQUIRED",
        "discovery_only_source": "DISCOVERY_ONLY_SOURCE",
        "primary_source_required": "PRIMARY_SOURCE_REQUIRED",
        "spam_attractive": "SPAM_ATTRACTIVE",
        "stale_no_maintainer_signal": "STALE_NO_MAINTAINER_SIGNAL",
        "closed_or_inactive": "CLOSED_OR_INACTIVE",
        "contested_bounty": "CONTESTED_HIGH_COMPETITION",
        "crowded_no_assignment": "CROWDED_NO_CLEAR_OWNER",
        "payout_too_low_for_effort": "PAYOUT_TOO_LOW_FOR_EFFORT",
        "aging_low_activity": "AGING_LOW_ACTIVITY",
        "no_repro_or_test_path": "NO_REPRO_OR_TEST_PATH",
    }.get(flag, f"RISK_{flag.upper()}")


def _normalize_opportunity_state(value: Any) -> str:
    if value is None:
        return "unknown"
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"active", "open", "opened", "live", "available"}:
        return "active"
    if normalized in {"closed", "completed", "done", "paid", "resolved", "cancelled"}:
        return "closed"
    if normalized in {"stale", "inactive", "abandoned", "expired"}:
        return "stale"
    return normalized if normalized in VALID_OPPORTUNITY_STATES else "unknown"


def _normalize_opportunity_state_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _normalize_opportunity_state(value)
    if normalized not in VALID_OPPORTUNITY_STATES:
        raise ValueError(f"invalid opportunity_state: {value}")
    return normalized


def _normalize_risk_level_filter(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in VALID_RISK_LEVELS:
        raise ValueError(f"invalid risk_level: {value}")
    return normalized


def _matches_report_filter(
    issue: FundedIssue,
    *,
    profile: ClientProfile | None,
    platform: str | None,
    language: str | None,
    min_usd: float | None,
    opportunity_state: str | None,
    risk_level: str | None,
) -> bool:
    if profile:
        if profile.languages and (issue.language or "").lower() not in profile.languages:
            return False
        effective_min_usd = profile.min_usd
        if effective_min_usd is not None:
            if issue.funding_currency != "USD" or issue.funding_amount is None:
                return False
            if issue.funding_amount < effective_min_usd:
                return False
        if (
            profile.allowed_opportunity_states
            and issue.opportunity_state not in profile.allowed_opportunity_states
        ):
            return False
        if profile.allowed_risk_levels and issue.risk_level not in profile.allowed_risk_levels:
            return False
        if profile.excluded_risk_flags and set(issue.risk_flags).intersection(
            profile.excluded_risk_flags
        ):
            return False
    if platform and issue.platform.lower() != platform.lower():
        return False
    if language and (issue.language or "").lower() != language.lower():
        return False
    if min_usd is not None:
        if issue.funding_currency != "USD" or issue.funding_amount is None:
            return False
        if issue.funding_amount < min_usd:
            return False
    if opportunity_state and issue.opportunity_state != opportunity_state:
        return False
    if risk_level and issue.risk_level != risk_level:
        return False
    return True


def _candidate_sort_key(issue: FundedIssue) -> tuple[int, int, float, str]:
    has_guidelines = 1 if issue.contribution_guidelines_url else 0
    signal_count = len(issue.contribution_signals)
    funding_amount = issue.funding_amount if issue.funding_currency == "USD" else 0.0
    return (-has_guidelines, -signal_count, -funding_amount, issue.reference)


def _coerce_count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def _coerce_optional_count(value: Any, name: str) -> int | None:
    if value is None:
        return None
    return _coerce_count(value, name)


def _coerce_optional_bool(value: Any, name: str) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"{name} must be a boolean or null")


def _coerce_amount(
    value: Any,
    name: str,
    *,
    allow_none: bool = True,
    allow_zero: bool = True,
) -> float | None:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{name} is required")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'>= 0' if allow_zero else '> 0'}")
    return value


def assess_bounty_competition(
    *,
    competing_pr_count: int = 0,
    distinct_claimants: int = 0,
    comment_count: int = 0,
    assigned: bool = False,
) -> dict[str, Any]:
    """Derive a read-only competition / noise-trap signal for a funded issue.

    Productizes the per-prospect recon the desk does by hand: many solvers racing
    the same bounty, or high comment volume with no clear owner, is a noise trap
    where engineering effort is often wasted even when the issue itself is real.
    Inputs are public metadata counts only; this never claims, comments, or
    contacts anyone. Returns risk flags that an operator can merge into a
    FundedIssue's ``risk_flags`` (they apply the normal risk penalty and emit the
    curated ``CONTESTED_HIGH_COMPETITION`` / ``CROWDED_NO_CLEAR_OWNER`` codes).
    """
    competing_pr_count = _coerce_count(competing_pr_count, "competing_pr_count")
    distinct_claimants = _coerce_count(distinct_claimants, "distinct_claimants")
    comment_count = _coerce_count(comment_count, "comment_count")
    if not isinstance(assigned, bool):
        raise ValueError("assigned must be a boolean")

    contested = (
        competing_pr_count >= COMPETITION_THRESHOLDS["competing_pr_count_contested"]
        or distinct_claimants >= COMPETITION_THRESHOLDS["distinct_claimants_contested"]
    )
    crowded_no_owner = not assigned and (
        comment_count >= COMPETITION_THRESHOLDS["comment_count_busy"]
        or distinct_claimants >= COMPETITION_THRESHOLDS["distinct_claimants_contested"]
    )

    flags: list[str] = []
    if contested:
        flags.append(CONTESTED_BOUNTY_FLAG)
    if crowded_no_owner:
        flags.append(CROWDED_NO_ASSIGNMENT_FLAG)

    if contested and crowded_no_owner:
        level = "high"
    elif flags:
        level = "elevated"
    else:
        level = "low"

    reason_codes = sorted({_risk_reason_code(flag) for flag in flags}) or [
        "NO_COMPETITION_PRESSURE"
    ]

    if level == "high":
        next_step = (
            "Treat as a noise trap: multiple solvers are racing this bounty with no clear "
            "owner. Keep as no-go/watchlist evidence unless the client specifically wants it "
            "and assignment is clarified from a permitted public source."
        )
    elif level == "elevated":
        next_step = (
            "Verify assignment and active PR count from permitted public sources before "
            "ranking; effort may be wasted if another solver is already ahead."
        )
    else:
        next_step = "No significant competition pressure from the provided public metadata."

    return {
        "schema_version": COMPETITION_SIGNAL_SCHEMA_VERSION,
        "read_only": True,
        "level": level,
        "risk_flags": flags,
        "reason_codes": reason_codes,
        "observed": {
            "competing_pr_count": competing_pr_count,
            "distinct_claimants": distinct_claimants,
            "comment_count": comment_count,
            "assigned": assigned,
        },
        "thresholds": dict(COMPETITION_THRESHOLDS),
        "recommended_next_step": next_step,
    }


_COMPETITION_LEVEL_ORDER = {"high": 0, "elevated": 1, "low": 2}


def _competition_sort_key(result: dict[str, Any]) -> tuple[int, int, str]:
    observed = result["observed"]
    pressure = (
        observed["competing_pr_count"] + observed["distinct_claimants"] + observed["comment_count"]
    )
    return (
        _COMPETITION_LEVEL_ORDER.get(result["level"], 3),
        -pressure,
        result["reference"],
    )


def assess_competition_batch(observations: Any) -> dict[str, Any]:
    """Assess read-only competition / noise-trap pressure across a batch of bounties.

    Productizes the per-prospect recon the desk does by hand into a single pass:
    given public metadata counts for several funded issues, surface which ones are
    contested or crowded noise traps so an operator can drop them before spending
    engineering time. ``observations`` is a list of dicts, each with an optional
    ``reference`` (or ``id``/``url``) label plus the public counts consumed by
    :func:`assess_bounty_competition` (``competing_pr_count``, ``distinct_claimants``,
    ``comment_count``, ``assigned``). Results are sorted highest-pressure first.
    This never claims, comments on, or contacts anyone.
    """
    if not isinstance(observations, list):
        raise ValueError("competition observations must be a list")

    results: list[dict[str, Any]] = []
    level_counts = {"high": 0, "elevated": 0, "low": 0}
    contested = 0
    crowded = 0

    for index, raw in enumerate(observations):
        if not isinstance(raw, dict):
            raise ValueError(f"competition observation #{index} must be an object")
        reference = raw.get("reference") or raw.get("id") or raw.get("url")
        if reference is not None and not isinstance(reference, str):
            raise ValueError(f"competition observation #{index} reference must be a string")
        signal = assess_bounty_competition(
            competing_pr_count=raw.get("competing_pr_count", 0),
            distinct_claimants=raw.get("distinct_claimants", 0),
            comment_count=raw.get("comment_count", 0),
            assigned=raw.get("assigned", False),
        )
        level_counts[signal["level"]] += 1
        if CONTESTED_BOUNTY_FLAG in signal["risk_flags"]:
            contested += 1
        if CROWDED_NO_ASSIGNMENT_FLAG in signal["risk_flags"]:
            crowded += 1
        results.append(
            {
                "reference": reference or f"observation-{index + 1}",
                "level": signal["level"],
                "risk_flags": signal["risk_flags"],
                "reason_codes": signal["reason_codes"],
                "observed": signal["observed"],
                "recommended_next_step": signal["recommended_next_step"],
            }
        )

    results.sort(key=_competition_sort_key)
    noise_traps = level_counts["high"] + level_counts["elevated"]

    return {
        "schema_version": COMPETITION_BATCH_SCHEMA_VERSION,
        "read_only": True,
        "reviewed": len(results),
        "summary": {
            "reviewed": len(results),
            "noise_traps": noise_traps,
            "high": level_counts["high"],
            "elevated": level_counts["elevated"],
            "low": level_counts["low"],
            "contested_bounty": contested,
            "crowded_no_assignment": crowded,
        },
        "thresholds": dict(COMPETITION_THRESHOLDS),
        "results": results,
        "blocked_actions": list(BLOCKED_ACTIONS),
    }


def assess_payout_effort(
    *,
    funding_amount: float | None = None,
    funding_currency: str = "USD",
    estimated_effort_hours: float | None = None,
    target_hourly_rate_usd: float = DEFAULT_TARGET_HOURLY_RATE_USD,
) -> dict[str, Any]:
    """Derive a read-only payout-vs-effort signal for a funded issue.

    Productizes the desk's effort-budget check (REVENUE_PLAN §16.1): a bounty
    whose payout implies an effective hourly rate well below the target floor is
    rarely worth engineering time even when the issue itself is real. Inputs are
    public funding metadata plus the operator's own private effort estimate; this
    never claims, comments, or contacts anyone. A ``low`` result emits the curated
    ``PAYOUT_TOO_LOW_FOR_EFFORT`` code and a ``payout_too_low_for_effort`` flag an
    operator can merge into a FundedIssue's ``risk_flags`` (it costs score via the
    normal risk penalty without forcing an automatic no-go).
    """
    funding_amount = _coerce_amount(funding_amount, "funding_amount", allow_zero=True)
    estimated_effort_hours = _coerce_amount(
        estimated_effort_hours, "estimated_effort_hours", allow_zero=False
    )
    target_hourly_rate_usd = _coerce_amount(
        target_hourly_rate_usd,
        "target_hourly_rate_usd",
        allow_none=False,
        allow_zero=False,
    )
    currency = (funding_currency or "USD").strip().upper() or "USD"

    effective_hourly_rate: float | None = None
    payout_effort_ratio: float | None = None
    flags: list[str] = []

    if funding_amount is None or estimated_effort_hours is None:
        level = "unknown"
        reason_codes = ["FUNDING_STATE_UNCLEAR"]
        next_step = (
            "Provide both the public funding amount and an effort estimate before ranking; "
            "payout-vs-effort cannot be assessed from the provided metadata."
        )
    elif currency != "USD":
        level = "unverified_currency"
        reason_codes = ["PAYOUT_CURRENCY_UNVERIFIED"]
        next_step = (
            f"Funding is in {currency}; convert to USD from a permitted public rate before "
            "comparing against the effort-budget floor."
        )
    else:
        effective_hourly_rate = round(funding_amount / estimated_effort_hours, 2)
        payout_effort_ratio = round(effective_hourly_rate / target_hourly_rate_usd, 4)
        if payout_effort_ratio >= PAYOUT_EFFORT_THRESHOLDS["marginal_ratio"]:
            level = "strong"
            reason_codes = ["PAYOUT_PROPORTIONATE_TO_EFFORT"]
            next_step = (
                "Payout is proportionate to the estimated effort against the target rate; safe "
                "to rank on the usual liveness/scope/maintainer signals."
            )
        elif payout_effort_ratio >= PAYOUT_EFFORT_THRESHOLDS["low_ratio"]:
            level = "marginal"
            reason_codes = ["PAYOUT_NEAR_EFFORT_FLOOR"]
            next_step = (
                "Payout is near the effort-budget floor; only pursue if the effort estimate is "
                "conservative or the issue carries strategic/portfolio value."
            )
        else:
            level = "low"
            flags.append(PAYOUT_EFFORT_FLAG)
            reason_codes = [_risk_reason_code(PAYOUT_EFFORT_FLAG)]
            next_step = (
                "Effective hourly rate is well below the target floor; keep as no-go/watchlist "
                "evidence unless the effort estimate is revised down from real scope review."
            )

    return {
        "schema_version": PAYOUT_EFFORT_SIGNAL_SCHEMA_VERSION,
        "read_only": True,
        "level": level,
        "risk_flags": flags,
        "reason_codes": reason_codes,
        "observed": {
            "funding_amount": funding_amount,
            "funding_currency": currency,
            "estimated_effort_hours": estimated_effort_hours,
            "effective_hourly_rate": effective_hourly_rate,
            "payout_effort_ratio": payout_effort_ratio,
        },
        "thresholds": {
            "target_hourly_rate_usd": target_hourly_rate_usd,
            "low_ratio": PAYOUT_EFFORT_THRESHOLDS["low_ratio"],
            "marginal_ratio": PAYOUT_EFFORT_THRESHOLDS["marginal_ratio"],
        },
        "recommended_next_step": next_step,
    }


_PAYOUT_EFFORT_LEVEL_ORDER = {
    "low": 0,
    "marginal": 1,
    "unverified_currency": 2,
    "unknown": 3,
    "strong": 4,
}


def _payout_effort_sort_key(result: dict[str, Any]) -> tuple[int, float, str]:
    ratio = result["observed"]["payout_effort_ratio"]
    ratio_key = ratio if ratio is not None else float("inf")
    return (
        _PAYOUT_EFFORT_LEVEL_ORDER.get(result["level"], 5),
        ratio_key,
        result["reference"],
    )


def assess_payout_effort_batch(observations: Any) -> dict[str, Any]:
    """Assess read-only payout-vs-effort across a batch of bounties.

    Productizes the desk's effort-budget triage into a single pass: given public
    funding metadata plus an effort estimate for several funded issues, surface
    which ones pay too little for the work so an operator can drop them before
    spending engineering time. ``observations`` is a list of dicts, each with an
    optional ``reference`` (or ``id``/``url``) label plus the values consumed by
    :func:`assess_payout_effort` (``funding_amount``, ``funding_currency``,
    ``estimated_effort_hours``, optional ``target_hourly_rate_usd``). Results are
    sorted worst-payout first. This never claims, comments on, or contacts anyone.
    """
    if not isinstance(observations, list):
        raise ValueError("payout-effort observations must be a list")

    results: list[dict[str, Any]] = []
    level_counts = {
        "low": 0,
        "marginal": 0,
        "strong": 0,
        "unknown": 0,
        "unverified_currency": 0,
    }

    for index, raw in enumerate(observations):
        if not isinstance(raw, dict):
            raise ValueError(f"payout-effort observation #{index} must be an object")
        reference = raw.get("reference") or raw.get("id") or raw.get("url")
        if reference is not None and not isinstance(reference, str):
            raise ValueError(f"payout-effort observation #{index} reference must be a string")
        signal = assess_payout_effort(
            funding_amount=raw.get("funding_amount"),
            funding_currency=raw.get("funding_currency", "USD"),
            estimated_effort_hours=raw.get("estimated_effort_hours"),
            target_hourly_rate_usd=raw.get(
                "target_hourly_rate_usd", DEFAULT_TARGET_HOURLY_RATE_USD
            ),
        )
        level_counts[signal["level"]] += 1
        results.append(
            {
                "reference": reference or f"observation-{index + 1}",
                "level": signal["level"],
                "risk_flags": signal["risk_flags"],
                "reason_codes": signal["reason_codes"],
                "observed": signal["observed"],
                "recommended_next_step": signal["recommended_next_step"],
            }
        )

    results.sort(key=_payout_effort_sort_key)

    return {
        "schema_version": PAYOUT_EFFORT_BATCH_SCHEMA_VERSION,
        "read_only": True,
        "reviewed": len(results),
        "summary": {
            "reviewed": len(results),
            "underpaid": level_counts["low"],
            "low": level_counts["low"],
            "marginal": level_counts["marginal"],
            "strong": level_counts["strong"],
            "unknown": level_counts["unknown"],
            "unverified_currency": level_counts["unverified_currency"],
        },
        "thresholds": dict(PAYOUT_EFFORT_THRESHOLDS),
        "results": results,
        "blocked_actions": list(BLOCKED_ACTIONS),
    }


_STALENESS_NEXT_STEP = {
    "active": (
        "Recent public activity; safe to rank on the usual scope/competition/payout signals."
    ),
    "aging": (
        "Activity is slowing; confirm a maintainer is still engaged from a permitted public "
        "source before committing engineering time."
    ),
    "stale": (
        "No recent maintainer signal; treat as stale/no-go evidence unless public project state "
        "shows the opportunity is live again."
    ),
    "dormant": (
        "Long-dormant with no maintainer signal; keep as no-go evidence — a classic "
        "stale-bounty trap where effort is wasted even if the issue itself is real."
    ),
    "unknown": (
        "Verify the last public activity date from a permitted source before ranking; staleness "
        "cannot be assessed from the provided metadata."
    ),
}


def assess_issue_staleness(
    *,
    days_since_last_activity: int | None = None,
    days_since_created: int | None = None,
    maintainer_recently_active: bool | None = None,
) -> dict[str, Any]:
    """Derive a read-only staleness / liveness signal for a funded issue.

    Productizes the desk's core value prop ("filter stale traps"): instead of
    eyeballing per prospect whether a bounty is alive, derive an
    ``opportunity_state`` recommendation from observable issue age plus whether a
    maintainer is still engaging. Inputs are public age/activity metadata only;
    this never claims, comments, or contacts anyone.

    ``days_since_last_activity`` drives the base level (active/aging/stale/
    dormant). ``maintainer_recently_active`` adjusts severity by one notch: an
    engaged maintainer softens a stale/dormant issue (it is old but not dead),
    while an explicitly absent maintainer hardens an active/aging issue (recent
    solver churn with no maintainer is the classic noise trap). The returned
    ``risk_flags`` can be merged into a FundedIssue's ``risk_flags``: a
    ``stale``/``dormant`` result emits the high-risk ``stale_no_maintainer_signal``
    flag (forces no-go), while ``aging`` emits the softer ``aging_low_activity``
    flag (costs score via the normal risk penalty without forcing a no-go).
    """
    days_since_last_activity = _coerce_optional_count(
        days_since_last_activity, "days_since_last_activity"
    )
    days_since_created = _coerce_optional_count(days_since_created, "days_since_created")
    maintainer_recently_active = _coerce_optional_bool(
        maintainer_recently_active, "maintainer_recently_active"
    )

    long_unresolved = (
        days_since_created is not None
        and days_since_created >= STALENESS_THRESHOLDS["long_unresolved_days"]
    )

    if days_since_last_activity is None:
        level = "unknown"
    elif days_since_last_activity <= STALENESS_THRESHOLDS["active_max_days"]:
        level = "active"
    elif days_since_last_activity <= STALENESS_THRESHOLDS["aging_max_days"]:
        level = "aging"
    elif days_since_last_activity <= STALENESS_THRESHOLDS["stale_max_days"]:
        level = "stale"
    else:
        level = "dormant"

    if level != "unknown" and maintainer_recently_active is True:
        level = {"dormant": "stale", "stale": "aging", "aging": "active"}.get(level, level)
    elif level != "unknown" and maintainer_recently_active is False:
        level = {"active": "aging", "aging": "stale"}.get(level, level)

    if level in {"stale", "dormant"}:
        flags = [STALE_NO_MAINTAINER_FLAG]
        recommended_state = "stale"
    elif level == "aging":
        flags = [AGING_LOW_ACTIVITY_FLAG]
        recommended_state = "active"
    elif level == "active":
        flags = []
        recommended_state = "active"
    else:
        flags = []
        recommended_state = "unknown"

    if flags:
        reason_codes = sorted({_risk_reason_code(flag) for flag in flags})
    elif level == "active":
        reason_codes = ["RECENT_PUBLIC_ACTIVITY"]
    else:
        reason_codes = ["STALENESS_UNVERIFIED"]

    return {
        "schema_version": STALENESS_SIGNAL_SCHEMA_VERSION,
        "read_only": True,
        "level": level,
        "recommended_opportunity_state": recommended_state,
        "risk_flags": flags,
        "reason_codes": reason_codes,
        "observed": {
            "days_since_last_activity": days_since_last_activity,
            "days_since_created": days_since_created,
            "maintainer_recently_active": maintainer_recently_active,
            "long_unresolved": long_unresolved,
        },
        "thresholds": dict(STALENESS_THRESHOLDS),
        "recommended_next_step": _STALENESS_NEXT_STEP[level],
    }


_STALENESS_LEVEL_ORDER = {"dormant": 0, "stale": 1, "aging": 2, "unknown": 3, "active": 4}


def _staleness_sort_key(result: dict[str, Any]) -> tuple[int, int, str]:
    days = result["observed"]["days_since_last_activity"]
    days_key = -days if days is not None else 0
    return (
        _STALENESS_LEVEL_ORDER.get(result["level"], 5),
        days_key,
        result["reference"],
    )


def assess_staleness_batch(observations: Any) -> dict[str, Any]:
    """Assess read-only staleness across a batch of funded issues.

    Productizes the desk's stale-trap triage into a single pass: given public
    age/activity metadata for several bounties, surface which ones are stale or
    long-dormant so an operator can drop them before spending engineering time.
    ``observations`` is a list of dicts, each with an optional ``reference``
    (or ``id``/``url``) label plus the values consumed by
    :func:`assess_issue_staleness` (``days_since_last_activity``,
    ``days_since_created``, optional ``maintainer_recently_active``). Results are
    sorted most-stale first. This never claims, comments on, or contacts anyone.
    """
    if not isinstance(observations, list):
        raise ValueError("staleness observations must be a list")

    results: list[dict[str, Any]] = []
    level_counts = {"active": 0, "aging": 0, "stale": 0, "dormant": 0, "unknown": 0}

    for index, raw in enumerate(observations):
        if not isinstance(raw, dict):
            raise ValueError(f"staleness observation #{index} must be an object")
        reference = raw.get("reference") or raw.get("id") or raw.get("url")
        if reference is not None and not isinstance(reference, str):
            raise ValueError(f"staleness observation #{index} reference must be a string")
        signal = assess_issue_staleness(
            days_since_last_activity=raw.get("days_since_last_activity"),
            days_since_created=raw.get("days_since_created"),
            maintainer_recently_active=raw.get("maintainer_recently_active"),
        )
        level_counts[signal["level"]] += 1
        results.append(
            {
                "reference": reference or f"observation-{index + 1}",
                "level": signal["level"],
                "recommended_opportunity_state": signal["recommended_opportunity_state"],
                "risk_flags": signal["risk_flags"],
                "reason_codes": signal["reason_codes"],
                "observed": signal["observed"],
                "recommended_next_step": signal["recommended_next_step"],
            }
        )

    results.sort(key=_staleness_sort_key)

    return {
        "schema_version": STALENESS_BATCH_SCHEMA_VERSION,
        "read_only": True,
        "reviewed": len(results),
        "summary": {
            "reviewed": len(results),
            "stale_or_dormant": level_counts["stale"] + level_counts["dormant"],
            "active": level_counts["active"],
            "aging": level_counts["aging"],
            "stale": level_counts["stale"],
            "dormant": level_counts["dormant"],
            "unknown": level_counts["unknown"],
        },
        "thresholds": dict(STALENESS_THRESHOLDS),
        "results": results,
        "blocked_actions": list(BLOCKED_ACTIONS),
    }


_TESTABILITY_NEXT_STEP = {
    "verifiable": (
        "An objective verification path exists (failing test or reproduction plus diagnostics); "
        "safe to rank on the usual liveness/scope/maintainer signals."
    ),
    "partially_verifiable": (
        "Some reproduction signal exists but no clear pass/fail check; estimate the cost of "
        "writing a failing test before committing engineering time."
    ),
    "unverifiable": (
        "No reproduction steps, failing test, logs, or expected-vs-actual behaviour; keep as "
        "no-go/watchlist evidence unless the issue body is updated with a way to verify a fix."
    ),
    "unknown": (
        "Read the public issue body for reproduction steps, a failing test, logs, or "
        "expected-vs-actual behaviour before ranking; testability cannot be assessed from the "
        "provided metadata."
    ),
}


def assess_issue_testability(
    *,
    has_failing_test: bool | None = None,
    has_reproduction_steps: bool | None = None,
    has_stack_trace_or_logs: bool | None = None,
    has_expected_vs_actual: bool | None = None,
) -> dict[str, Any]:
    """Derive a read-only testability / reproducibility signal for a funded issue.

    Productizes the desk's "can you verify it?" check (REVENUE_PLAN §9.2 Tests row,
    §10.2 ``NO_REPRO_OR_TEST_PATH``): a funded issue with no way to objectively
    reproduce or test the fix is hard to close even when the bounty is real,
    because the maintainer cannot distinguish a correct patch from a plausible one.
    Inputs are observable issue-body signals only; this never claims, comments, or
    contacts anyone.

    A failing test gives an objective pass/fail check on its own; reproduction
    steps combined with diagnostics (a stack trace/logs or an expected-vs-actual
    statement) also establish a verification path. Any single weaker signal yields
    ``partially_verifiable``. When every known signal is absent the result is
    ``unverifiable`` and emits the soft ``no_repro_or_test_path`` flag an operator
    can merge into a FundedIssue's ``risk_flags`` (it costs score via the normal
    risk penalty without forcing an automatic no-go, since docs/config issues can
    be legitimately untestable). When no signal is observed the result is
    ``unknown`` and is not penalized.
    """
    has_failing_test = _coerce_optional_bool(has_failing_test, "has_failing_test")
    has_reproduction_steps = _coerce_optional_bool(has_reproduction_steps, "has_reproduction_steps")
    has_stack_trace_or_logs = _coerce_optional_bool(
        has_stack_trace_or_logs, "has_stack_trace_or_logs"
    )
    has_expected_vs_actual = _coerce_optional_bool(has_expected_vs_actual, "has_expected_vs_actual")

    signals = (
        has_failing_test,
        has_reproduction_steps,
        has_stack_trace_or_logs,
        has_expected_vs_actual,
    )
    known = [value for value in signals if value is not None]
    present_signal_count = sum(1 for value in known if value)

    if not known:
        level = "unknown"
    else:
        objective_check = bool(has_failing_test)
        repro = bool(has_reproduction_steps)
        diagnostics = bool(has_stack_trace_or_logs) or bool(has_expected_vs_actual)
        if objective_check or (repro and diagnostics):
            level = "verifiable"
        elif repro or diagnostics:
            level = "partially_verifiable"
        else:
            level = "unverifiable"

    if level == "unverifiable":
        flags = [NO_REPRO_OR_TEST_PATH_FLAG]
        reason_codes = [_risk_reason_code(NO_REPRO_OR_TEST_PATH_FLAG)]
    elif level == "verifiable":
        flags = []
        reason_codes = ["VERIFIABLE_TEST_PATH"]
    elif level == "partially_verifiable":
        flags = []
        reason_codes = ["PARTIAL_TEST_PATH"]
    else:
        flags = []
        reason_codes = ["TESTABILITY_UNVERIFIED"]

    return {
        "schema_version": TESTABILITY_SIGNAL_SCHEMA_VERSION,
        "read_only": True,
        "level": level,
        "risk_flags": flags,
        "reason_codes": reason_codes,
        "observed": {
            "has_failing_test": has_failing_test,
            "has_reproduction_steps": has_reproduction_steps,
            "has_stack_trace_or_logs": has_stack_trace_or_logs,
            "has_expected_vs_actual": has_expected_vs_actual,
            "known_signal_count": len(known),
            "present_signal_count": present_signal_count,
        },
        "recommended_next_step": _TESTABILITY_NEXT_STEP[level],
    }


_TESTABILITY_LEVEL_ORDER = {
    "unverifiable": 0,
    "partially_verifiable": 1,
    "unknown": 2,
    "verifiable": 3,
}


def _testability_sort_key(result: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _TESTABILITY_LEVEL_ORDER.get(result["level"], 4),
        result["observed"]["present_signal_count"],
        result["reference"],
    )


def assess_testability_batch(observations: Any) -> dict[str, Any]:
    """Assess read-only testability across a batch of funded issues.

    Productizes the desk's verifiability triage into a single pass: given the
    observable reproduction/test signals for several bounties, surface which ones
    cannot be objectively verified so an operator can drop them before spending
    engineering time. ``observations`` is a list of dicts, each with an optional
    ``reference`` (or ``id``/``url``) label plus the booleans consumed by
    :func:`assess_issue_testability` (``has_failing_test``,
    ``has_reproduction_steps``, ``has_stack_trace_or_logs``,
    ``has_expected_vs_actual``). Results are sorted least-verifiable first. This
    never claims, comments on, or contacts anyone.
    """
    if not isinstance(observations, list):
        raise ValueError("testability observations must be a list")

    results: list[dict[str, Any]] = []
    level_counts = {
        "verifiable": 0,
        "partially_verifiable": 0,
        "unverifiable": 0,
        "unknown": 0,
    }

    for index, raw in enumerate(observations):
        if not isinstance(raw, dict):
            raise ValueError(f"testability observation #{index} must be an object")
        reference = raw.get("reference") or raw.get("id") or raw.get("url")
        if reference is not None and not isinstance(reference, str):
            raise ValueError(f"testability observation #{index} reference must be a string")
        signal = assess_issue_testability(
            has_failing_test=raw.get("has_failing_test"),
            has_reproduction_steps=raw.get("has_reproduction_steps"),
            has_stack_trace_or_logs=raw.get("has_stack_trace_or_logs"),
            has_expected_vs_actual=raw.get("has_expected_vs_actual"),
        )
        level_counts[signal["level"]] += 1
        results.append(
            {
                "reference": reference or f"observation-{index + 1}",
                "level": signal["level"],
                "risk_flags": signal["risk_flags"],
                "reason_codes": signal["reason_codes"],
                "observed": signal["observed"],
                "recommended_next_step": signal["recommended_next_step"],
            }
        )

    results.sort(key=_testability_sort_key)

    return {
        "schema_version": TESTABILITY_BATCH_SCHEMA_VERSION,
        "read_only": True,
        "reviewed": len(results),
        "summary": {
            "reviewed": len(results),
            "unverifiable": level_counts["unverifiable"],
            "partially_verifiable": level_counts["partially_verifiable"],
            "verifiable": level_counts["verifiable"],
            "unknown": level_counts["unknown"],
        },
        "results": results,
        "blocked_actions": list(BLOCKED_ACTIONS),
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
