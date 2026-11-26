import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { formatMinor } from "../lib/money";
import type { Account, Balance, Entry } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote } from "../components/Layout";

export function AccountDetails() {
  const { id = "" } = useParams();
  const api = useApi();
  const [account, setAccount] = useState<Account | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    Promise.all([api.account(id), api.balance(id), api.transactions(id)])
      .then(([a, b, page]) => {
        setAccount(a);
        setBalance(b);
        setEntries(page.items);
        setCursor(page.next_cursor);
      })
      .catch(setError);
  }, [api, id]);

  if (error) return <ErrorNote error={error} />;
  if (!account || !balance) return <p>Loading…</p>;
  return (
    <section>
      <Link to="/dashboard">← Accounts</Link>
      <div className="section-head">
        <h2>{account.account_type === "CHECKING" ? "Checking" : "Savings"} {account.masked_number}</h2>
        <div className="total">Available <strong>{formatMinor(balance.available_balance_minor)}</strong></div>
      </div>
      <table className="ledger">
        <caption>Transaction history (synthetic, newest first)</caption>
        <thead>
          <tr><th>Posted</th><th>Description</th><th>Reference</th><th className="num">Amount</th></tr>
        </thead>
        <tbody>
          {entries.map((e) => (
            <tr key={e.entry_id}>
              <td>{new Date(e.posted_at).toLocaleString()}</td>
              <td>{e.description}</td>
              <td className="mono">{e.transfer_id ?? e.journal_type}</td>
              <td className={`num ${e.direction === "CREDIT" ? "credit" : "debit"}`}>
                {e.direction === "CREDIT" ? "+" : "−"}{formatMinor(e.amount_minor)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {cursor && (
        <button
          className="btn ghost"
          onClick={() => api.transactions(id, cursor).then((p) => { setEntries((prev) => [...prev, ...p.items]); setCursor(p.next_cursor); }, setError)}
        >
          Load more
        </button>
      )}
    </section>
  );
}
