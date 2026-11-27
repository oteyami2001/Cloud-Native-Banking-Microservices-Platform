# Reliability and disaster recovery

## Failure handling
| Failure | Mechanism | Tested |
|---|---|---|
| Lambda execution failure | Bounded retries (streams 5, SQS 5), DLQs, alarms | offline (T22) |
| Duplicate transfer request | Durable idempotency | offline (T11) |
| Concurrent balance updates | Conditional atomic writes + conflict retry | offline (T12) |
| Insufficient balance | Rejected, no partial posting | offline (T08, T14) |
| Fraud service unavailable | Fail closed (`FAILED`) | offline (T19) |
| Notification failure | SQS retry → DLQ, redrive | offline (T22) |
| Duplicate event delivery | Idempotent consumers | offline (T21) |
| Event publication failure | Partial batch failure + outbox reconciliation | offline (T20) |
| Ambiguous ledger outcome | `APPROVED_FOR_POSTING` + idempotent resume | offline |
| Failed deployment | Alias rollback (automatic in pipeline) | pending live (T27) |
| Data loss / corruption | PITR restore + reconciliation | pending live (T29) |
| Unauthorized infra change | Daily drift detection | pending live (T28) |
| Ledger inconsistency | Hourly reconciliation + alarm | offline (T15) |

## Targets (proposed; database restore measured 2026-11-27)
| Metric | Target | Measurement method |
|---|---|---|
| API read latency | p95 ≤ 500 ms at demo load | CloudWatch `Latency` p95, bounded load test |
| Approved transfer latency | p95 ≤ 2 s | client-side timing in integration tests |
| Duplicate postings | 0 in tested retry scenarios | tests + reconciliation |
| RTO (database) | ≤ 60 min | timed restore drill per runbook. **Measured: table restore 2 min 20 s and 4 min 9 s** (two drills, ledger + transfers, synthetic data). This covers restore + read-only validation only; switching services to the restored data was not exercised |
| RPO (database) | ≤ 5 min | PITR timestamp vs. last committed journal. **Measured: restored to the exact requested second** (05:10:00Z): the transfer posted at 05:11:10Z was absent, everything earlier present |

Single region only. Multi-region DR is not implemented and not claimed;
active-active financial writes are explicitly out of scope because they
would break single-writer balance guarantees.
