import { useCallback, useEffect, useState } from "react";
import { formatMinor } from "../lib/money";
import type { FraudAlert } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote, StatusPill } from "../components/Layout";

export function FraudReview() {
  const api = useApi();
  const [alerts, setAlerts] = useState<FraudAlert[] | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => api.fraudAlerts().then((p) => setAlerts(p.items), setError), [api]);
  useEffect(() => { void load(); }, [load]);

  const act = async (alert: FraudAlert, action: "approve" | "reject") => {
    setError(null);
    try {
      const t = action === "approve" ? await api.approve(alert.transfer_id, "Reviewed in sandbox") : await api.reject(alert.transfer_id, "Rejected in sandbox");
      setMessage(`${alert.transfer_id}: ${t.status}`);
    } catch (e) {
      setError(e);
    }
    await load();
  };

  return (
    <section>
      <h2>Fraud review queue</h2>
      <p className="muted">Approval re-checks request integrity, decision validity, account status and funds before posting. You cannot review your own transfers.</p>
      <ErrorNote error={error} />
      {message && <p className="ok">{message}</p>}
      {alerts === null ? <p>Loading…</p> : alerts.length === 0 ? <p className="muted">No open alerts.</p> : (
        <table className="ledger">
          <thead><tr><th>Transfer</th><th className="num">Amount</th><th>Score</th><th>Rules</th><th>Policy</th><th>Decision</th><th /></tr></thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.decision_id}>
                <td className="mono">{a.transfer_id}</td>
                <td className="num">{formatMinor(a.amount_minor)}</td>
                <td><span className={`score ${a.risk_score >= 90 ? "high" : "mid"}`}>{a.risk_score}</span></td>
                <td>{a.triggered_rules.join(", ")}</td>
                <td>{a.policy_version}</td>
                <td><StatusPill status={a.decision} /></td>
                <td className="actions">
                  {a.decision === "PENDING_REVIEW" && (
                    <>
                      <button className="btn small" onClick={() => void act(a, "approve")}>Approve</button>
                      <button className="btn ghost small" onClick={() => void act(a, "reject")}>Reject</button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
