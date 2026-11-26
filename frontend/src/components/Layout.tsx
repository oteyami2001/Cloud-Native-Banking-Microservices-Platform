import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";

export function SandboxBanner() {
  return (
    <div className="sandbox-banner" role="note">
      Demonstration sandbox — all accounts, balances and transactions are synthetic. No real money moves.
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const isReviewer = session?.groups.includes("fraud-reviewers");
  const isAuditor = session?.groups.includes("auditors") || isReviewer;
  const isCustomer = session?.groups.includes("customers");
  return (
    <>
      <SandboxBanner />
      <header className="topbar">
        <NavLink to="/" className="brand" aria-label="NovaBank Digital home">
          <span className="brand-mark">N</span> NovaBank <span className="brand-sub">Digital</span>
        </NavLink>
        {session && (
          <nav aria-label="Main">
            {isCustomer && <NavLink to="/dashboard">Accounts</NavLink>}
            {isCustomer && <NavLink to="/transfer">Transfer</NavLink>}
            {isCustomer && <NavLink to="/notifications">Notifications</NavLink>}
            {isReviewer && <NavLink to="/admin/fraud">Fraud review</NavLink>}
            {isAuditor && <NavLink to="/admin/reconciliation">Reconciliation</NavLink>}
          </nav>
        )}
        <div className="session">
          {session ? (
            <>
              <span className="who">{session.name}</span>
              <button className="btn ghost" onClick={() => { logout(); navigate("/"); }}>Sign out</button>
            </>
          ) : (
            <NavLink className="btn" to="/login">Sign in</NavLink>
          )}
        </div>
      </header>
      <main className="container">{children}</main>
      <footer className="footer">NovaBank Digital is a fictional portfolio project. Not a bank. Not FDIC insured. No real data.</footer>
    </>
  );
}

export function ErrorNote({ error }: { error: unknown }) {
  if (!error) return null;
  const message = error instanceof Error ? error.message : String(error);
  const code = (error as { code?: string }).code;
  return <p className="error" role="alert">{code ? <strong>{code}: </strong> : null}{message}</p>;
}

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill pill-${status.toLowerCase()}`}>{status.replace(/_/g, " ")}</span>;
}
