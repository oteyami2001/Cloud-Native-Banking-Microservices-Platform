# Banking business model and accounting

## Scenario
NovaBank Digital (fictional) is modernising a monolith into cloud-native
services. Customers register, open checking and savings accounts, view
balances and history, and move money between NovaBank accounts. Risky
transfers are held for review by fraud analysts; auditors review
reconciliation evidence. **Everything is synthetic** and labelled as such in
the API (`"synthetic": true`) and UI.

## Accounting model (double entry)
From the bank's perspective:

| Account | Class | Normal side | Increases with |
|---|---|---|---|
| Customer deposit (checking/savings) `ACC-…` | Liability (the bank owes the customer) | Credit | Credit |
| `GL-1000` Synthetic Funding | Asset (stands in for cash/settlement) | Debit | Debit |

Every journal satisfies **Σ debits = Σ credits**, so the accounting equation
**Assets = Liabilities (+ Equity = 0)** always holds.

| Event | Journal |
|---|---|
| Synthetic opening deposit of $4,850 | Dr GL-1000 485000 / Cr ACC-checking 485000 |
| Transfer $250 checking → savings | Dr ACC-checking 25000 / Cr ACC-savings 25000 |
| Transfer to another customer | Dr ACC-sender / Cr ACC-recipient |
| Authorised reversal | Dr ACC-recipient / Cr ACC-sender (new journal `REV-…`) |

Customer statements show the customer's view: a **debit to a deposit account
reduces** the customer's balance ("money out"), a credit increases it. Each
entry records `side`, `direction`, `amount_minor` and `signed_amount_minor`.
The customer-facing entries are not a complete general ledger on their own;
`GL-1000` and the journal headers complete it.

**Initial balances** originate only from documented opening-balance journals
(sandbox feature flag, capped at $25,000 per account), never untracked writes.

## Financial invariants (tested)
1. Internal transfers conserve the combined balance.
2. Every journal balances; entries match journal lines.
3. No negative balance (customer or GL).
4. Duplicate requests never create duplicate postings.
5. Failed transactions change nothing.
6. Concurrent transactions cannot overspend.
7. Reconciliation detects any mismatch between balances and entries.

## Money representation
Integer minor units everywhere (`25000` = $250.00). JSON floats are rejected at
parse time; `Decimal` values read from DynamoDB must be integral. Maximum
single transfer $1,000,000.00; maximum balance $10,000,000,000.00.

## Out of scope
Interest, fees, overdrafts, card payments, ACH/wire, FX, statements,
regulatory reporting, KYC. No real identity data is collected.
