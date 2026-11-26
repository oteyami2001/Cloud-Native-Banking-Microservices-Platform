import { Link } from "react-router-dom";

export function Landing() {
  return (
    <section className="hero">
      <div>
        <h1>Banking, rebuilt for the cloud.</h1>
        <p className="lead">
          NovaBank Digital demonstrates secure, event-driven banking on AWS: atomic double-entry
          ledger postings, duplicate-proof transfers, explainable fraud screening and verifiable audit evidence.
        </p>
        <div className="actions">
          <Link className="btn" to="/login">Open the sandbox</Link>
          <a className="btn ghost" href="https://github.com/oteyami2001/Cloud-Native-Banking-Microservices-Platform" rel="noreferrer">View the architecture</a>
        </div>
      </div>
      <ul className="feature-grid">
        <li><strong>Atomic transfers</strong><span>One DynamoDB transaction moves money, writes both ledger entries and the outbox event — or nothing.</span></li>
        <li><strong>Idempotent by design</strong><span>Retries never post twice, even across timeouts.</span></li>
        <li><strong>Fraud screening</strong><span>Versioned, explainable rules; risky transfers wait for an independent reviewer.</span></li>
        <li><strong>Reconciliation</strong><span>Balances, journals and the accounting equation are checked continuously.</span></li>
      </ul>
    </section>
  );
}
