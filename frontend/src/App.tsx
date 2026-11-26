import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { useAuth } from "./lib/auth";
import { AccountDetails } from "./pages/AccountDetails";
import { Callback } from "./pages/Callback";
import { Dashboard } from "./pages/Dashboard";
import { FraudReview } from "./pages/FraudReview";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Notifications } from "./pages/Notifications";
import { Reconciliation } from "./pages/Reconciliation";
import { TransferPage } from "./pages/Transfer";

/** UI-level guard only; the API enforces authorization on every request. */
function Protected({ group, children }: { group?: string | string[]; children: ReactNode }) {
  const { session } = useAuth();
  if (!session) return <Navigate to="/login" replace />;
  const groups = group === undefined ? [] : Array.isArray(group) ? group : [group];
  if (groups.length && !groups.some((g) => session.groups.includes(g))) {
    return <p className="error" role="alert">Your role does not have access to this page.</p>;
  }
  return <>{children}</>;
}

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/login" element={<Login />} />
        <Route path="/callback" element={<Callback />} />
        <Route path="/dashboard" element={<Protected group="customers"><Dashboard /></Protected>} />
        <Route path="/accounts/:id" element={<Protected group="customers"><AccountDetails /></Protected>} />
        <Route path="/transfer" element={<Protected group="customers"><TransferPage /></Protected>} />
        <Route path="/notifications" element={<Protected group="customers"><Notifications /></Protected>} />
        <Route path="/admin/fraud" element={<Protected group="fraud-reviewers"><FraudReview /></Protected>} />
        <Route path="/admin/reconciliation" element={<Protected group={["auditors", "fraud-reviewers"]}><Reconciliation /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
