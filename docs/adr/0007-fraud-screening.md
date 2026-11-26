# ADR-0007: Deterministic, versioned fraud screening; fail closed

* Status: Accepted · Date: 2026-11-26

## Decision
A rules engine (`policies/fraud-rules.yaml`) scores amount, velocity, new
recipient, account age and operator flags. Decisions (score, rules, policy
version, timestamp, correlation id, request fingerprint) are stored by the
fraud service; the transfer stores only references. Thresholds: ≥40 hold for
review, ≥90 reject. Policy content is pinned by checksum per version in tests.

* Screening errors → transfer `FAILED`, nothing posted (fail closed).
* `PENDING_REVIEW` posts nothing. Approval requires `novabank/admin` +
  `fraud-reviewers`, forbids self-review, and revalidates request integrity,
  decision validity/expiry, account status/ownership and balance at posting.
* Customer-supplied fraud fields are rejected by strict validation.
* No paid AI service in v1. Rules are illustrative, not a validated model.
