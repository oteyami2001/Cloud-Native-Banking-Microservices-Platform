# ADR-0008: Cognito authentication and layered authorization

* Status: Accepted · Date: 2026-11-26

## Decision
Cognito user pool with a **public** SPA client (no secret) using the
authorization-code flow with PKCE; 15-minute access tokens; refresh-token
rotation via Cognito; optional TOTP MFA (ON in staging/prod references).
Custom scopes `novabank/read|write|admin`; groups `customers`,
`fraud-reviewers`, `auditors`.

The HTTP API JWT authorizer validates signature, expiry, issuer and audience
and enforces route scopes. Services re-check issuer, client id, token use,
expiry, scopes and groups, derive the customer id server-side from
`IDENTITY#<sub>`, and enforce object ownership.

Token handling in the SPA: tokens are kept **in memory** (lost on reload →
silent re-login via the hosted UI session). This avoids persistent storage
exposure to XSS at the cost of extra redirects; a strict CSP reduces XSS risk.
A backend-for-frontend with HttpOnly cookies would be stronger and is noted
as a production improvement.
