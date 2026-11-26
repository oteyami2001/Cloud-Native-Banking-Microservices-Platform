from __future__ import annotations

import copy

import pytest
from hypothesis import given
from hypothesis import strategies as st

from services.fraud.rules import ScreeningContext, assess, load_policy, policy_checksum, validate_policy

#: Any change to policies/fraud-rules.yaml must bump policy_version and add
#: its checksum here, so a rule can never change silently under an old version.
PINNED = {"2026.11.1": "a642f5a389b6482687875abfa9f69116080f039f4133ca0cdb53efa24dba158b"}


def ctx(**kw):
    base = {"amount_minor": 25_000, "velocity_1h": 0, "new_recipient": False, "source_account_age_hours": 1000.0, "unusual_activity": False}
    return ScreeningContext(**{**base, **kw})


def test_policy_version_is_pinned():
    policy = load_policy()
    assert policy["policy_version"] in PINNED
    expected = PINNED[policy["policy_version"]]
    if expected is not None:
        assert policy_checksum(policy) == expected


@pytest.mark.parametrize(
    "context,decision,rules",
    [
        (ctx(), "APPROVED", []),
        (ctx(amount_minor=500_000), "PENDING_REVIEW", ["FR-001"]),
        (ctx(amount_minor=900_000), "PENDING_REVIEW", ["FR-001", "FR-002"]),
        (ctx(amount_minor=900_000, source_account_age_hours=2), "REJECTED", ["FR-001", "FR-002", "FR-007"]),
        (ctx(velocity_1h=10), "PENDING_REVIEW", ["FR-003", "FR-004"]),
        (ctx(new_recipient=True, amount_minor=150_000), "APPROVED", ["FR-005", "FR-006"]),
        (
            ctx(new_recipient=True, amount_minor=600_000, source_account_age_hours=2),
            "PENDING_REVIEW",
            ["FR-001", "FR-005", "FR-006", "FR-007"],
        ),
        (ctx(unusual_activity=True, velocity_1h=5), "PENDING_REVIEW", ["FR-003", "FR-008"]),
    ],
)
def test_rule_outcomes_are_deterministic_and_explainable(context, decision, rules):
    result = assess(context)
    assert result.decision == decision and result.triggered_rules == rules
    assert result.policy_version == load_policy()["policy_version"]


@given(st.integers(1, 100_000_000), st.integers(0, 50), st.booleans(), st.floats(0, 10_000), st.booleans())
def test_score_is_bounded_and_monotonic_in_amount(amount, velocity, new_recipient, age, unusual):
    base = ScreeningContext(amount, velocity, new_recipient, age, unusual)
    bigger = ScreeningContext(amount * 2, velocity, new_recipient, age, unusual)
    a, b = assess(base), assess(bigger)
    assert 0 <= a.risk_score <= 100
    assert b.risk_score >= a.risk_score


def test_invalid_policies_are_refused():
    good = load_policy()
    bad_threshold = copy.deepcopy(good)
    bad_threshold["thresholds"]["reject_score"] = 10
    dup = copy.deepcopy(good)
    dup["rules"].append(dict(good["rules"][0]))
    unknown = copy.deepcopy(good)
    unknown["rules"][0]["when"] = {"customer_says_ok": True}
    for policy in (bad_threshold, dup, unknown, {"thresholds": {}}):
        with pytest.raises(ValueError):
            validate_policy(policy)
