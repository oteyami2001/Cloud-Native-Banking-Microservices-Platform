## Summary

<!-- What changed and why. -->

## Phase / scope

- [ ] Phase:
- [ ] No AWS resources are created or changed by merging this PR (Terraform runs only through approved workflows)

## Financial integrity checklist

- [ ] Money remains integer minor units (no floats)
- [ ] Only the ledger service writes balances
- [ ] Postings remain atomic and idempotent
- [ ] New events are versioned and documented in `contracts/events/`

## Security checklist

- [ ] Object-level authorization on any new endpoint
- [ ] No secrets, tokens or real customer data in code, logs or fixtures
- [ ] Third-party Actions pinned to commit SHAs
- [ ] Security findings fixed or documented as an exception in `policies/exceptions/`

## Validation

| Check | Result |
|---|---|
| `make test` | |
| `make tf-test` | |
| Scenarios affected (T01–T30) | |
