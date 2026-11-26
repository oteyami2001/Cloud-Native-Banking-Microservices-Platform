"""Deterministic, explainable fraud rules engine (no paid AI services)."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

SUPPORTED_CONDITIONS = {
    "amount_minor_gte",
    "velocity_1h_gte",
    "new_recipient",
    "source_account_age_hours_lt",
    "unusual_activity",
}


@dataclass(frozen=True)
class ScreeningContext:
    amount_minor: int
    velocity_1h: int
    new_recipient: bool
    source_account_age_hours: float
    unusual_activity: bool


@dataclass(frozen=True)
class Assessment:
    risk_score: int
    decision: str
    triggered_rules: list[str]
    policy_version: str


def _matches(condition: str, expected: Any, ctx: ScreeningContext) -> bool:
    if condition == "amount_minor_gte":
        return ctx.amount_minor >= expected
    if condition == "velocity_1h_gte":
        return ctx.velocity_1h >= expected
    if condition == "new_recipient":
        return ctx.new_recipient is expected
    if condition == "source_account_age_hours_lt":
        return ctx.source_account_age_hours < expected
    if condition == "unusual_activity":
        return ctx.unusual_activity is expected
    raise ValueError(f"Unsupported fraud rule condition: {condition}")  # validated at load


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(policy.get("policy_version"), str):
        raise ValueError("policy_version is required")
    th = policy.get("thresholds", {})
    if not 0 < th.get("pending_review_score", 0) < th.get("reject_score", 0):
        raise ValueError("thresholds must satisfy 0 < pending_review_score < reject_score")
    ids = set()
    for rule in policy.get("rules", []):
        if rule["id"] in ids:
            raise ValueError(f"Duplicate rule id {rule['id']}")
        ids.add(rule["id"])
        if not isinstance(rule.get("score"), int) or rule["score"] <= 0:
            raise ValueError(f"Rule {rule['id']} needs a positive integer score")
        unknown = set(rule.get("when", {})) - SUPPORTED_CONDITIONS
        if unknown or not rule.get("when"):
            raise ValueError(f"Rule {rule['id']} has invalid conditions: {sorted(unknown)}")
    return policy


@cache
def load_policy() -> dict[str, Any]:
    explicit = os.environ.get("FRAUD_RULES_PATH")
    packaged = Path(__file__).with_name("fraud-rules.json")
    if explicit:
        path = Path(explicit)
    elif packaged.exists():
        path = packaged
    else:
        path = Path(__file__).resolve().parents[2] / "policies" / "fraud-rules.yaml"
    if path.suffix in {".yaml", ".yml"}:
        import yaml  # dev-only dependency; Lambda artifacts ship JSON

        return validate_policy(yaml.safe_load(path.read_text()))
    return validate_policy(json.loads(path.read_text()))


def policy_checksum(policy: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()


def assess(ctx: ScreeningContext, policy: dict[str, Any] | None = None) -> Assessment:
    policy = policy or load_policy()
    score = 0
    triggered: list[str] = []
    for rule in policy["rules"]:
        if all(_matches(cond, expected, ctx) for cond, expected in rule["when"].items()):
            score += rule["score"]
            triggered.append(rule["id"])
    score = min(score, 100)
    th = policy["thresholds"]
    if score >= th["reject_score"]:
        decision = "REJECTED"
    elif score >= th["pending_review_score"]:
        decision = "PENDING_REVIEW"
    else:
        decision = "APPROVED"
    return Assessment(score, decision, triggered, policy["policy_version"])
