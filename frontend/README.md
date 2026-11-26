# NovaBank Digital — frontend

React 18 + TypeScript + Vite. Navy/teal banking UI; every screen is labelled synthetic.

```bash
npm ci
npm run dev        # http://localhost:5173 — talks to scripts/local_api.py (offline personas)
npm test           # vitest (money parsing, PKCE, API client, transfer validation, routing guard)
npm run build
```

Modes (`.env.example`): `VITE_AUTH_MODE=local` uses simulated personas against the
offline API; `cognito` uses the Cognito hosted UI with authorization code + PKCE.
Access tokens are kept in memory only (ADR-0008); a reload requires signing in again.

Note: `package-lock.json` was generated with npm 11 because npm 10.9 hits an
arborist bug resolving vitest 5's optional peers; `npm ci` with npm 10 works on
the committed lockfile.
