import { useEffect, useRef, useState } from "react";
import { ApiError, newIdempotencyKey } from "../lib/api";
import { formatMinor, parseAmountToMinor } from "../lib/money";
import type { Account, Transfer as TransferT } from "../lib/types";
import { useApi } from "../lib/useApi";
import { ErrorNote, StatusPill } from "../components/Layout";

const ACCOUNT_ID = /^ACC-[0-9A-Z]{20}$/;

export function validateTransfer(source: string, destination: string, amount: string): { minor: number } | { error: string } {
  if (!source) return { error: "Choose a source account" };
  if (!ACCOUNT_ID.test(destination)) return { error: "Destination must be a NovaBank account ID (ACC-…)" };
  if (source === destination) return { error: "Source and destination must be different" };
  const minor = parseAmountToMinor(amount);
  if (minor === null) return { error: "Enter a positive amount with at most two decimals" };
  if (minor > 100_000_000) return { error: "Amount exceeds the sandbox maximum" };
  return { minor };
}

export function TransferPage() {
  const api = useApi();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [amount, setAmount] = useState("250.00");
  const [step, setStep] = useState<"form" | "confirm" | "done">("form");
  const [result, setResult] = useState<TransferT | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  // One key per intended transfer: retries of the same submission reuse it.
  const key = useRef(newIdempotencyKey());

  useEffect(() => {
    api.accounts().then((p) => { setAccounts(p.items); setSource(p.items[0]?.account_id ?? ""); }, setError);
  }, [api]);

  const check = validateTransfer(source, destination, amount);

  const submit = async () => {
    if (!("minor" in check)) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.transfer({ source_account_id: source, destination_account_id: destination, amount_minor: check.minor, currency: "USD" }, key.current));
      setStep("done");
    } catch (e) {
      const body = e instanceof ApiError ? (e.body as { transfer?: TransferT } | null) : null;
      if (body?.transfer) {
        setResult(body.transfer);
        setStep("done");
      }
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    key.current = newIdempotencyKey();
    setStep("form");
    setResult(null);
    setError(null);
  };

  return (
    <section className="card narrow">
      <h2>Transfer money</h2>
      {step === "form" && (
        <form onSubmit={(e) => { e.preventDefault(); if ("minor" in check) setStep("confirm"); }}>
          <label>
            From
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {accounts.map((a) => <option key={a.account_id} value={a.account_id}>{a.account_type} {a.masked_number}</option>)}
            </select>
          </label>
          <label>
            To (NovaBank account ID)
            <input value={destination} onChange={(e) => setDestination(e.target.value.trim())} list="own-accounts" placeholder="ACC-…" />
            <datalist id="own-accounts">
              {accounts.filter((a) => a.account_id !== source).map((a) => <option key={a.account_id} value={a.account_id}>{a.account_type} {a.masked_number}</option>)}
            </datalist>
          </label>
          <label>
            Amount (USD)
            <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" aria-describedby="amount-help" />
          </label>
          <p id="amount-help" className="muted small">Amounts are sent as integer cents. Large or unusual transfers may be held for security review.</p>
          {"error" in check && destination && <p className="error" role="alert">{check.error}</p>}
          <button className="btn" type="submit" disabled={!("minor" in check)}>Review transfer</button>
        </form>
      )}
      {step === "confirm" && "minor" in check && (
        <div>
          <p>Send <strong>{formatMinor(check.minor)}</strong> from <span className="mono">{source}</span> to <span className="mono">{destination}</span>?</p>
          <div className="actions">
            <button className="btn" onClick={() => void submit()} disabled={busy}>{busy ? "Submitting…" : "Confirm transfer"}</button>
            <button className="btn ghost" onClick={() => setStep("form")} disabled={busy}>Edit</button>
          </div>
          <ErrorNote error={error} />
          {error ? <p className="muted small">Retrying uses the same idempotency key, so the transfer cannot post twice.</p> : null}
        </div>
      )}
      {step === "done" && result && (
        <div className="result">
          <StatusPill status={result.status} />
          <p>
            {result.status === "COMPLETED" && <>Transfer of {formatMinor(result.amount_minor)} completed.</>}
            {result.status === "PENDING_REVIEW" && <>Your transfer is being reviewed by our security team. No money has moved yet.</>}
            {(result.status === "REJECTED" || result.status === "FAILED") && <>The transfer was not completed{result.reason_code ? ` (${result.reason_code})` : ""}. No money moved.</>}
          </p>
          <p className="mono small">Reference {result.transfer_id}</p>
          <button className="btn ghost" onClick={reset}>New transfer</button>
        </div>
      )}
    </section>
  );
}
