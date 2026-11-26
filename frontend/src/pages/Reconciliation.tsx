import { useEffect, useState } from "react";
import { formatMinor } from "../lib/money";
import type { ReconciliationReport } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote, StatusPill } from "../components/Layout";

export function Reconciliation() {
  const api = useApi();
  const [reports, setReports] = useState<ReconciliationReport[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api.reconciliation().then((r) => setReports(r.items), setError); }, [api]);
  return (
    <section>
      <h2>Ledger reconciliation</h2>
      <p className="muted">Each run verifies balances against entries, balanced journals, the accounting equation and transfer/journal consistency. Reports are stored as SHA-256-indexed evidence.</p>
      <ErrorNote error={error} />
      {reports === null ? <p>Loading…</p> : reports.length === 0 ? <p className="muted">No reports yet (runs hourly, or run scripts/reconcile_ledger.py).</p> : (
        <table className="ledger">
          <thead><tr><th>Generated</th><th>Status</th><th className="num">Accounts</th><th className="num">Journals</th><th className="num">Assets</th><th className="num">Liabilities</th><th>Evidence SHA-256</th></tr></thead>
          <tbody>
            {reports.map((r) => (
              <tr key={r.run_id}>
                <td>{new Date(r.generated_at).toLocaleString()}</td>
                <td><StatusPill status={r.status} /></td>
                <td className="num">{r.accounts_checked}</td>
                <td className="num">{r.journals_checked}</td>
                <td className="num">{formatMinor(r.total_assets_minor)}</td>
                <td className="num">{formatMinor(r.total_liabilities_minor)}</td>
                <td className="mono small">{r.sha256.slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
