import { useNavigate, useSearchParams } from "react-router-dom";
import { PERSONAS, useAuth } from "../lib/auth";
import { config } from "../lib/config";

export function Login() {
  const { loginLocal, loginCognito } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const expired = params.get("expired") === "1" ? <p className="error" role="alert">Your session has expired. Please sign in again.</p> : null;
  if (config.authMode === "cognito") {
    return (
      <section className="card narrow">
        <h2>Sign in</h2>
        {expired}
        <p>You will be redirected to the NovaBank sign-in page (Amazon Cognito, authorization code + PKCE). MFA may be required.</p>
        <button className="btn" onClick={() => void loginCognito()}>Continue to secure sign-in</button>
      </section>
    );
  }
  return (
    <section className="card narrow">
      <h2>Choose a sandbox persona</h2>
      {expired}
      <p className="muted">Offline mode: authentication is simulated by the local API. In AWS this page redirects to Cognito.</p>
      <ul className="persona-list">
        {PERSONAS.map((p) => (
          <li key={p.id}>
            <button
              className="persona"
              onClick={() => {
                loginLocal(p);
                navigate(p.groups.includes("customers") ? "/dashboard" : p.groups.includes("fraud-reviewers") ? "/admin/fraud" : "/admin/reconciliation");
              }}
            >
              <strong>{p.name}</strong>
              <span>{p.description}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
