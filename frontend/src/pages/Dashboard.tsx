import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../lib/api";
import { formatMinor, parseAmountToMinor } from "../lib/money";
import type { Account, Balance } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote } from "../components/Layout";

interface Row {
  account: Account;
  balance: Balance | null;
}

export function Dashboard() {
  const api = useApi();
  const [rows, setRows] = useState<Row[] | null>(null);
  const [needsProfile, setNeedsProfile] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [name, setName] = useState("");
  const [opening, setOpening] = useState("4850.00");
  const [type, setType] = useState<"CHECKING" | "SAVINGS">("CHECKING");

  const load = useCallback(async () => {
    setError(null);
    try {
      await api.me();
      const page = await api.accounts();
      const balances = await Promise.all(page.items.map((a) => api.balance(a.account_id).catch(() => null)));
      setRows(page.items.map((account, i) => ({ account, balance: balances[i] ?? null })));
      setNeedsProfile(false);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setNeedsProfile(true);
      else setError(e);
    }
  }, [api]);

  useEffect(() => {
    void load();
  }, [load]);

  if (needsProfile) {
    return (
      <section className="card narrow">
        <h2>Create your synthetic profile</h2>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            try {
              await api.register(name);
              await load();
            } catch (err) {
              setError(err);
            }
          }}
        >
          <label>
            Display name
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required placeholder="e.g. Alice Synthetic" />
          </label>
          <button className="btn" type="submit">Create profile</button>
        </form>
        <ErrorNote error={error} />
      </section>
    );
  }

  const total = rows?.reduce((sum, r) => sum + (r.balance?.available_balance_minor ?? 0), 0) ?? 0;
  return (
    <section>
      <div className="section-head">
        <h2>Your accounts</h2>
        <div className="total">Combined balance <strong>{formatMinor(total)}</strong></div>
      </div>
      <ErrorNote error={error} />
      {rows === null ? (
        <p>Loading…</p>
      ) : rows.length === 0 ? (
        <p className="muted">No accounts yet. Open one below.</p>
      ) : (
        <div className="account-grid">
          {rows.map(({ account, balance }) => (
            <Link key={account.account_id} to={`/accounts/${account.account_id}`} className="account-card">
              <span className="acct-type">{account.account_type === "CHECKING" ? "Checking" : "Savings"}</span>
              <span className="acct-number">{account.masked_number}</span>
              <span className="acct-balance">{balance ? formatMinor(balance.available_balance_minor) : "—"}</span>
              <span className="synthetic-tag">synthetic · {account.status}</span>
            </Link>
          ))}
        </div>
      )}
      <form
        className="card inline-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const minor = opening ? parseAmountToMinor(opening) : undefined;
          if (opening && minor === null) {
            setError(new Error("Opening deposit must be a positive amount with up to 2 decimals"));
            return;
          }
          try {
            await api.openAccount(type, minor ?? undefined);
            await load();
          } catch (err) {
            setError(err);
          }
        }}
      >
        <h3>Open an account</h3>
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value as "CHECKING" | "SAVINGS")}>
            <option value="CHECKING">Checking</option>
            <option value="SAVINGS">Savings</option>
          </select>
        </label>
        <label>
          Synthetic opening deposit (USD, optional, max 25,000)
          <input value={opening} onChange={(e) => setOpening(e.target.value)} inputMode="decimal" />
        </label>
        <button className="btn" type="submit">Open account</button>
        <p className="muted small">Opening deposits are posted as balanced journals (Dr GL-1000 / Cr your account).</p>
      </form>
    </section>
  );
}
