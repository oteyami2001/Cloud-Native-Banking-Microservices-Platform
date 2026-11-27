# Validation scenarios (T01–T30)

Legend — **Offline**: passed locally against moto with no AWS credentials
(`pytest`, 2026-11-26, 170 tests). **CI**: passed in a GitHub Actions run
(record run id). **Live**: verified in the deployed dev environment (record
timestamp + evidence). Nothing is marked Live or CI until it has actually run.

| ID | Scenario | Evidence (test / tool) | Offline | CI | Live |
|---|---|---|---|---|---|
| T01 | Customer registration succeeds | `test_banking_flow::test_customer_registration_succeeds` | ✅ | ✅ 45889062755 | ✅ 2026-11-26 (Cognito user → profile created in UI) |
| T02 | Valid authentication succeeds | `test_authenticated_customer_can_use_api` (claims simulated; Cognito login needs live) | ✅ (simulated) | ✅ 45889062755 | ✅ 2026-11-26 (Cognito hosted UI, code + PKCE) |
| T03 | Invalid/expired JWT rejected | `test_invalid_or_expired_tokens_are_rejected` ×5; `scripts/live_smoke.py` | ✅ | ✅ 45889062755 | ✅ 2026-11-26 (8/8 → 401) |
| T04 | No access to another customer's account | `test_customer_cannot_access_another_customers_account` | ✅ | ✅ 45889062755 | ☐ |
| T05 | Account creation | `test_account_creation_with_documented_opening_balance` | ✅ | ✅ 45889062755 | ✅ 2026-11-26 (checking $4,850 + savings via documented opening journals) |
| T06 | Balance retrieval | `test_balance_retrieval` | ✅ | ✅ 45889062755 | ✅ 2026-11-26 (balances shown from ledger) |
| T07 | Valid internal transfer | `test_valid_internal_transfer_succeeds` | ✅ | ✅ 45889062755 | ✅ 2026-11-26 (TRF-01M8D5AANPKV181M1HFC: checking −$250 / savings +$250; total conserved at $5,350) |
| T08 | Insufficient funds rejected | `test_insufficient_funds_is_rejected_without_posting` | ✅ | ✅ 45889062755 | ✅ 2026-11-27 ($300 from ****APZ4 holding $250 → TRF-01M8DQ6A686Y2CFW4WN8 REJECTED INSUFFICIENT_FUNDS; no entry posted, all balances unchanged, combined $25,350) |
| T09 | Zero/negative/malformed amounts rejected | `test_zero_negative_malformed…` ×9, float parse test | ✅ | ✅ 45889062755 | ☐ |
| T10 | Currency mismatch rejected | `test_unsupported_currency_and_currency_mismatch_are_rejected` | ✅ | ✅ 45889062755 | ☐ |
| T11 | Duplicate transfer posts once | `test_duplicate_request_does_not_post_twice`, concurrent duplicate test | ✅ | ✅ 45889062755 | ✅ 2026-11-27 browser double-click on Confirm: one transfer TRF-01M8DPM6BPZTKVMESMWB, one −$10.00 entry; ****EJKY $4,590, ****HZBQ $6,510 (server-side replay covered by CI) |
| T12 | Concurrent transfers cannot overdraw | `test_concurrent_transfers_cannot_overdraw` (10 threads, moto per-call serialisation) | ✅ | ✅ 45889062755 | ☐ |
| T13 | Self-transfer rejected | `test_self_transfer_is_rejected` | ✅ | ✅ 45889062755 | ☐ |
| T14 | Failed atomic write → no partial posting | `test_failed_atomic_write_produces_no_partial_posting` (injected failing item) | ✅ | ✅ 45889062755 | ☐ |
| T15 | Ledger reconciles | `test_reconciliation_balances_after_activity`, property tests, tampering detection | ✅ | ✅ 45889062755 | ☐ |
| T16 | High-risk transaction held/rejected | `test_high_risk_transfer_is_held_without_posting`, `…rejected` | ✅ | ✅ 45889062755 | ✅ 2026-11-27 (TRF-01M8D6CKRY7D1MSZ22WN $6,000 held PENDING_REVIEW; source balance unchanged at $20,000); reviewer rejection: TRF-01M8DQDNF21D3C5S2QAH $5,500 held (score 60, FR-001/FR-007) → REJECTED, no posting, balances unchanged) |
| T17 | Unauthorized fraud approval rejected | `test_customer_cannot_approve_held_transfer_or_supply_fraud_approval` | ✅ | ✅ 45889062755 | ☐ |
| T18 | Authorized approval revalidated | `test_authorised_approval_is_revalidated_before_posting` + balance/tamper/frozen tests | ✅ | ✅ 45889062755 | ✅ 2026-11-27 (reviewer approved TRF-01M8D6CKRY7D1MSZ22WN → COMPLETED; ****1TXA $20,000→$14,000, ****HZBQ $500→$6,500, combined $25,350 unchanged) |
| T19 | Fraud failure prevents posting | `test_fraud_service_failure_prevents_posting` | ✅ | ✅ 45889062755 | ☐ |
| T20 | Outbox publication failure recoverable | `test_partial_publication_failure_is_reported_and_recoverable` | ✅ | ✅ 45889062755 | ☐ |
| T21 | Duplicate event delivery safe | `test_duplicate_event_delivery_is_handled_safely` | ✅ | ✅ 45889062755 | ☐ |
| T22 | Notification failure → retry/DLQ | `test_notification_failure_enters_retry_flow` (DLQ redrive needs live) | ✅ (partial) | ✅ 45889062755 | ☐ |
| T23 | Audit evidence generated | `test_audit_evidence_is_generated_with_checksum` | ✅ | ✅ 45889062755 | ☐ |
| T24 | Unauthorized IAM operation denied | Static IAM tests (`test_terraform_static.py`); live `AccessDenied` check pending | ◐ static | ☐ | ☐ |
| T25 | Insecure Terraform blocked | Checkov fails `tests/terraform/fixtures/insecure` (21 failed checks, run locally) | ✅ (local tool) | ✅ 45889062736 | ☐ |
| T26 | Unapproved deployment prevented | Workflow structure tests; requires GitHub environment protection rules | ◐ static | ☐ | ☐ |
| T27 | Failed release rolled back | `scripts/deploy_lambda.py` rollback path + `tests/unit/test_deploy_script.py` | ✅ | ✅ | ✅ deploy-services 45904772462: release judged unhealthy → all 10 aliases rolled back automatically (trigger was a false positive, since fixed) |
| T28 | Drift detected | `drift-detection.yml`; needs live state | ☐ | ☐ | ☐ |
| T29 | Restore + reconciliation tested | `runbooks/database-recovery.md`; needs live PITR | ☐ | ☐ | ☐ |
| T30 | Project resources cleaned up | `cleanup.yml` + `scripts/verify_cleanup.sh`; needs live | ☐ | ☐ | ☐ |

**Offline status: 23 verified, 2 partially (static), 1 verified with a local tool, 4 require AWS.**
**GitHub CI (2026-11-26, `main` @ e038c6e):** T01–T23 passed in `ci` run 45889062755; T25 negative test passed in `security-scan` run 45889062736. Live AWS: T01, T02, T03, T05, T06, T07, T08, T11 (UI), T16, T18 and T27 verified (2026-11-26/27); remaining live scenarios pending.
